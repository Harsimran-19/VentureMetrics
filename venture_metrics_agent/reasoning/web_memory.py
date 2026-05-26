"""Persist controlled web-search evidence for future reuse."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from venture_metrics_agent.app.config import DEFAULT_DOCUMENTS_DIR
from venture_metrics_agent.ingestion.source_registry import (
    canonicalize_url,
    classify_source,
    init_db,
    source_domain,
)
from venture_metrics_agent.retrieval.chunker import ChunkOptions, build_chunks
from venture_metrics_agent.retrieval.web_search import WebResult


@dataclass(frozen=True)
class WebMemoryOptions:
    documents_dir: str | Path = DEFAULT_DOCUMENTS_DIR
    min_content_chars: int = 80
    index_min_chars: int = 80


def remember_web_results(
    db_path: str | Path,
    *,
    question: str,
    results: list[WebResult],
    options: WebMemoryOptions | None = None,
) -> dict[str, Any]:
    options = options or WebMemoryOptions()
    documents_dir = Path(options.documents_dir)
    documents_dir.mkdir(parents=True, exist_ok=True)

    conn = init_db(db_path)
    stats: dict[str, Any] = {
        "seen": len(results),
        "sources_created": 0,
        "sources_existing": 0,
        "documents_created": 0,
        "documents_skipped": 0,
        "chunks_created": 0,
        "skipped_urls": [],
    }

    try:
        for result in results:
            content = result.content.strip()
            if len(content) < options.min_content_chars:
                stats["documents_skipped"] += 1
                stats["skipped_urls"].append({"url": result.url, "reason": "web result content too short"})
                continue

            source_id, created = _upsert_web_source(conn, result)
            if created:
                stats["sources_created"] += 1
            else:
                stats["sources_existing"] += 1

            existing_document = conn.execute(
                "SELECT id FROM documents WHERE source_id = ? LIMIT 1",
                (source_id,),
            ).fetchone()
            if existing_document:
                stats["documents_skipped"] += 1
                continue

            fetched_at = datetime.now(timezone.utc).isoformat()
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            local_path = _write_web_document(
                documents_dir,
                source_id=source_id,
                result=result,
                question=question,
                fetched_at=fetched_at,
            )
            _insert_web_document(
                conn,
                source_id=source_id,
                result=result,
                question=question,
                fetched_at=fetched_at,
                local_path=str(local_path),
            )
            conn.execute(
                """
                UPDATE sources
                SET
                    status = 'fetched',
                    title_from_page = COALESCE(title_from_page, ?),
                    fetched_at = COALESCE(fetched_at, ?),
                    content_hash = COALESCE(content_hash, ?),
                    error_message = NULL
                WHERE id = ?
                """,
                (result.title, fetched_at, content_hash, source_id),
            )
            stats["documents_created"] += 1

        conn.commit()
    finally:
        conn.close()

    if stats["documents_created"]:
        chunk_stats = build_chunks(
            db_path,
            rebuild=False,
            options=ChunkOptions(min_chars=options.index_min_chars),
        )
        stats["chunks_created"] = chunk_stats["chunks_created"]

    return stats


def _upsert_web_source(conn, result: WebResult) -> tuple[int, bool]:
    canonical_url = canonicalize_url(result.url)
    detected_type, reliability = classify_source(canonical_url, result.title)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO sources (
            url,
            canonical_url,
            source_domain,
            title_from_excel,
            title_from_page,
            source_type,
            reliability_label,
            status,
            original_file_name,
            original_sheet_name,
            original_row_number
        )
        VALUES (?, ?, ?, NULL, ?, ?, ?, 'pending', '__web_fallback__', 'web_search', NULL)
        """,
        (
            result.url,
            canonical_url,
            source_domain(canonical_url),
            result.title,
            detected_type,
            reliability,
        ),
    )
    created = cursor.rowcount > 0
    row = conn.execute("SELECT id FROM sources WHERE canonical_url = ?", (canonical_url,)).fetchone()
    return int(row[0]), created


def _insert_web_document(
    conn,
    *,
    source_id: int,
    result: WebResult,
    question: str,
    fetched_at: str,
    local_path: str,
) -> None:
    metadata = {
        "url": result.url,
        "web_search_score": result.score,
        "origin": "web_fallback",
        "question": question,
    }
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
        VALUES (?, ?, ?, NULL, NULL, ?, 'web_search_result', ?, ?)
        """,
        (source_id, result.title, result.content, fetched_at, local_path, json.dumps(metadata, ensure_ascii=False)),
    )


def _write_web_document(
    documents_dir: Path,
    *,
    source_id: int,
    result: WebResult,
    question: str,
    fetched_at: str,
) -> Path:
    path = documents_dir / f"source_{source_id:06d}.web.md"
    frontmatter = {
        "source_id": source_id,
        "url": result.url,
        "title": result.title,
        "fetched_at": fetched_at,
        "extraction_method": "web_search_result",
        "origin": "web_fallback",
        "question": question,
        "web_search_score": result.score,
    }
    text = [
        "---",
        json.dumps(frontmatter, ensure_ascii=False, indent=2),
        "---",
        "",
        f"# {result.title or result.url}",
        "",
        result.content,
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    return path
