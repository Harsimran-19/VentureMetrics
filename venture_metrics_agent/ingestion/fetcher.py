"""Fetch source documents using Tavily Extract as the primary extractor."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from venture_metrics_agent.ingestion.excel_ingest import export_source_registry, sqlite_row_factory
from venture_metrics_agent.ingestion.source_registry import init_db


TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"


@dataclass(frozen=True)
class FetchOptions:
    limit: int = 25
    batch_size: int = 5
    retry_failed: bool = False
    extract_depth: str = "advanced"
    output_format: str = "markdown"
    timeout: float = 30.0
    min_chars: int = 200


def fetch_pending_sources(
    db_path: str | Path,
    documents_dir: str | Path,
    *,
    api_key: str | None = None,
    options: FetchOptions | None = None,
) -> dict[str, Any]:
    options = options or FetchOptions()
    key = api_key or os.environ.get("TAVILY_API_KEY") or _read_env_value("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is missing. Add it to .env or export it in the shell.")

    documents_path = Path(documents_dir)
    documents_path.mkdir(parents=True, exist_ok=True)

    conn = init_db(db_path)
    conn.row_factory = sqlite_row_factory
    sources = _load_sources(conn, options)

    stats: dict[str, Any] = {
        "requested": len(sources),
        "fetched": 0,
        "failed": 0,
        "skipped": 0,
        "documents_dir": str(documents_path),
        "errors": [],
    }

    for batch in _chunks(sources, options.batch_size):
        response = _tavily_extract(
            [source["canonical_url"] for source in batch],
            api_key=key,
            extract_depth=options.extract_depth,
            output_format=options.output_format,
            timeout=options.timeout,
        )
        results_by_url = {
            _normalize_result_url(result.get("url", "")): result
            for result in response.get("results", [])
        }

        for source in batch:
            result = results_by_url.get(_normalize_result_url(source["canonical_url"]))
            if not result:
                reason = _failed_reason(source["canonical_url"], response)
                _mark_source(conn, source["id"], "failed", error_message=reason)
                stats["failed"] += 1
                stats["errors"].append({"source_id": source["id"], "url": source["canonical_url"], "error": reason})
                continue

            raw_content = str(result.get("raw_content") or "").strip()
            if len(raw_content) < options.min_chars:
                reason = f"Extracted content too short: {len(raw_content)} chars"
                _mark_source(conn, source["id"], "skipped", error_message=reason)
                stats["skipped"] += 1
                stats["errors"].append({"source_id": source["id"], "url": source["canonical_url"], "error": reason})
                continue

            fetched_at = datetime.now(timezone.utc).isoformat()
            title = _extract_title(raw_content) or source.get("title_from_excel") or source.get("source_domain")
            content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
            local_path = _write_document(
                documents_path,
                source=source,
                title=title,
                content=raw_content,
                fetched_at=fetched_at,
                metadata={
                    "tavily_request_id": response.get("request_id"),
                    "tavily_response_time": response.get("response_time"),
                    "tavily_usage": response.get("usage"),
                    "favicon": result.get("favicon"),
                    "images": result.get("images", []),
                },
            )
            _insert_document(
                conn,
                source_id=source["id"],
                title=title,
                text=raw_content,
                fetched_at=fetched_at,
                local_path=str(local_path),
                metadata={
                    "url": source["canonical_url"],
                    "source_domain": source.get("source_domain"),
                    "source_type": source.get("source_type"),
                    "reliability_label": source.get("reliability_label"),
                    "tavily_request_id": response.get("request_id"),
                    "tavily_response_time": response.get("response_time"),
                    "tavily_usage": response.get("usage"),
                },
            )
            _mark_source(
                conn,
                source["id"],
                "fetched",
                title_from_page=title,
                fetched_at=fetched_at,
                content_hash=content_hash,
                error_message=None,
            )
            stats["fetched"] += 1

        conn.commit()

    export_source_registry(db_path, Path(db_path).with_name("source_registry.csv"))
    conn.close()
    return stats


def _load_sources(conn: sqlite3.Connection, options: FetchOptions) -> list[dict[str, Any]]:
    statuses = ("pending", "failed") if options.retry_failed else ("pending",)
    placeholders = ", ".join("?" for _ in statuses)
    return conn.execute(
        f"""
        SELECT
            id,
            url,
            canonical_url,
            source_domain,
            title_from_excel,
            title_from_page,
            source_type,
            reliability_label,
            status
        FROM sources
        WHERE status IN ({placeholders})
        ORDER BY id
        LIMIT ?
        """,
        (*statuses, options.limit),
    ).fetchall()


def _tavily_extract(
    urls: list[str],
    *,
    api_key: str,
    extract_depth: str,
    output_format: str,
    timeout: float,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "urls": urls,
            "extract_depth": extract_depth,
            "format": output_format,
            "include_images": False,
            "include_favicon": True,
            "include_usage": True,
            "timeout": min(max(timeout, 1.0), 60.0),
        }
    ).encode("utf-8")
    request = Request(
        TAVILY_EXTRACT_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout + 10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily Extract HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Tavily Extract connection failed: {exc.reason}") from exc


def _failed_reason(url: str, response: dict[str, Any]) -> str:
    normalized = _normalize_result_url(url)
    for failed in response.get("failed_results", []):
        failed_url = _normalize_result_url(str(failed.get("url") or ""))
        if failed_url == normalized:
            return str(failed.get("error") or failed.get("message") or "Tavily extraction failed")
    return "No Tavily extraction result returned"


def _write_document(
    documents_dir: Path,
    *,
    source: dict[str, Any],
    title: str | None,
    content: str,
    fetched_at: str,
    metadata: dict[str, Any],
) -> Path:
    file_path = documents_dir / f"source_{int(source['id']):06d}.md"
    frontmatter = {
        "source_id": source["id"],
        "url": source["canonical_url"],
        "source_domain": source.get("source_domain"),
        "source_type": source.get("source_type"),
        "reliability_label": source.get("reliability_label"),
        "title": title,
        "fetched_at": fetched_at,
        "extraction_method": "tavily_extract",
        **metadata,
    }
    text = [
        "---",
        json.dumps(frontmatter, ensure_ascii=False, indent=2),
        "---",
        "",
        f"# {title or source.get('source_domain') or 'Untitled Source'}",
        "",
        content,
        "",
    ]
    file_path.write_text("\n".join(text), encoding="utf-8")
    return file_path


def _insert_document(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    title: str | None,
    text: str,
    fetched_at: str,
    local_path: str,
    metadata: dict[str, Any],
) -> None:
    conn.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))
    conn.execute(
        """
        INSERT INTO documents (
            source_id,
            title,
            text,
            language,
            published_date,
            fetched_at,
            extraction_method,
            local_path,
            metadata_json
        )
        VALUES (?, ?, ?, NULL, NULL, ?, 'tavily_extract', ?, ?)
        """,
        (source_id, title, text, fetched_at, local_path, json.dumps(metadata, ensure_ascii=False)),
    )


def _mark_source(
    conn: sqlite3.Connection,
    source_id: int,
    status: str,
    *,
    title_from_page: str | None = None,
    fetched_at: str | None = None,
    content_hash: str | None = None,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE sources
        SET
            status = ?,
            title_from_page = COALESCE(?, title_from_page),
            fetched_at = COALESCE(?, fetched_at),
            content_hash = COALESCE(?, content_hash),
            error_message = ?
        WHERE id = ?
        """,
        (status, title_from_page, fetched_at, content_hash, error_message, source_id),
    )


def _extract_title(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = re.sub(r"^#+\s*", "", stripped).strip()
            if title:
                return title[:300]
    for line in content.splitlines():
        stripped = line.strip()
        if len(stripped) >= 8:
            return stripped[:300]
    return None


def _read_env_value(key: str, env_path: str | Path = ".env") -> str | None:
    path = Path(env_path)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _normalize_result_url(url: str) -> str:
    return url.strip().rstrip("/")
