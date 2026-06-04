"""Internal evidence retrieval over local SQLite chunks."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venture_metrics_agent.ingestion.excel_ingest import sqlite_row_factory
from venture_metrics_agent.ingestion.source_registry import init_db


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: int
    document_id: int
    source_id: int
    chunk_index: int
    text: str
    score: float
    title: str | None
    url: str | None
    source_domain: str | None
    source_type: str | None
    reliability_label: str | None
    file_name: str | None
    sheet_name: str | None
    row_number: int | None

    def citation(self) -> dict[str, Any]:
        return {
            "title": self.title or self.source_domain or f"Source {self.source_id}",
            "url": self.url,
            "source_type": self.source_type,
            "reliability": self.reliability_label,
        }


def retrieve_internal_evidence(db_path: str | Path, question: str, *, top_k: int = 8) -> list[RetrievalResult]:
    conn = init_db(db_path)
    conn.row_factory = sqlite_row_factory
    try:
        rows = _fts_search(conn, question, top_k=top_k)
        if len(rows) < max(3, top_k // 2):
            rows = _merge_rows(rows, _fallback_like_search(conn, question, top_k=top_k))
        return [_row_to_result(row) for row in rows[:top_k]]
    finally:
        conn.close()


def _fts_search(conn: sqlite3.Connection, question: str, *, top_k: int) -> list[dict[str, Any]]:
    query = _to_fts_query(question)
    if not query:
        return []
    try:
        return conn.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                c.source_id,
                c.chunk_index,
                c.text,
                bm25(chunks_fts) * -1 AS score,
                d.title,
                s.canonical_url AS url,
                s.source_domain,
                s.source_type,
                s.reliability_label,
                s.original_file_name AS file_name,
                s.original_sheet_name AS sheet_name,
                s.original_row_number AS row_number
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            JOIN sources s ON s.id = c.source_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts)
            LIMIT ?
            """,
            (query, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _fallback_like_search(conn: sqlite3.Connection, question: str, *, top_k: int) -> list[dict[str, Any]]:
    terms = _important_terms(question)
    if not terms:
        return []

    rows = conn.execute(
        """
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.source_id,
            c.chunk_index,
            c.text,
            d.title,
            s.canonical_url AS url,
            s.source_domain,
            s.source_type,
            s.reliability_label,
            s.original_file_name AS file_name,
            s.original_sheet_name AS sheet_name,
            s.original_row_number AS row_number
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN sources s ON s.id = c.source_id
        ORDER BY c.id
        """
    ).fetchall()

    scored_rows: list[dict[str, Any]] = []
    lowered_terms = [term.lower() for term in terms]
    for row in rows:
        haystack = f"{row['title'] or ''} {row['text']}".lower()
        score = sum(haystack.count(term) for term in lowered_terms)
        if score:
            row = dict(row)
            row["score"] = float(score)
            scored_rows.append(row)

    scored_rows.sort(key=lambda row: row["score"], reverse=True)
    return scored_rows[:top_k]


def _merge_rows(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {row["chunk_id"] for row in primary}
    merged = list(primary)
    for row in secondary:
        if row["chunk_id"] not in seen:
            merged.append(row)
            seen.add(row["chunk_id"])
    return merged


def _row_to_result(row: dict[str, Any]) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=int(row["chunk_id"]),
        document_id=int(row["document_id"]),
        source_id=int(row["source_id"]),
        chunk_index=int(row["chunk_index"]),
        text=row["text"],
        score=float(row.get("score") or 0.0),
        title=row.get("title"),
        url=row.get("url"),
        source_domain=row.get("source_domain"),
        source_type=row.get("source_type"),
        reliability_label=row.get("reliability_label"),
        file_name=row.get("file_name"),
        sheet_name=row.get("sheet_name"),
        row_number=row.get("row_number"),
    )


def _to_fts_query(question: str) -> str:
    terms = _important_terms(question)
    # Prefix matching helps with simple inflections while staying valid FTS syntax.
    return " OR ".join(f'"{term}"*' for term in terms[:10])


def _important_terms(question: str) -> list[str]:
    raw_terms = re.findall(r"[\w\u4e00-\u9fff]{2,}", question.lower())
    stopwords = {
        "what",
        "which",
        "where",
        "when",
        "search",
        "web",
        "too",
        "answer",
        "about",
        "sources",
        "source",
        "evidence",
        "mention",
        "mentions",
        "appear",
        "appears",
        "most",
        "relevant",
        "indexed",
        "related",
        "have",
        "does",
        "with",
        "from",
        "the",
        "and",
        "for",
        "are",
        "我们",
        "哪些",
        "什么",
        "有关",
    }
    terms: list[str] = []
    for term in raw_terms:
        term = _normalize_term(term)
        if term in stopwords:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def _normalize_term(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith("s") and len(term) > 4:
        return term[:-1]
    return term


def results_to_context(results: list[RetrievalResult], *, max_chars: int = 12000, start_index: int = 1) -> str:
    blocks: list[str] = []
    remaining = max_chars
    for index, result in enumerate(results, start=start_index):
        text = clean_display_text(result.text)
        if len(text) > 1600:
            text = text[:1600].rsplit(" ", 1)[0].strip() + "..."
        block = (
            f"[{index}] {result.title or result.source_domain or 'Untitled'}\n"
            f"URL: {result.url}\n"
            f"Type: {result.source_type}; Reliability: {result.reliability_label}\n"
            f"Evidence: {text}"
        )
        if len(block) > remaining:
            break
        blocks.append(block)
        remaining -= len(block)
    return "\n\n".join(blocks)


def unique_citations(results: list[RetrievalResult], *, limit: int = 6) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        key = result.url or str(result.source_id)
        if key in seen:
            continue
        citations.append(result.citation())
        seen.add(key)
        if len(citations) >= limit:
            break
    return citations


def clean_display_text(text: str) -> str:
    """Make extracted markdown readable for prompts and UI snippets."""
    cleaned = text or ""
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", cleaned)
    cleaned = re.sub(r"\[[^\]]*\]\(\s*[^)]*\.(?:jpg|jpeg|png|gif|webp)[^)]*\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[\]\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\(javascript:[^)]+\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"[*_`#>|]+", " ", cleaned)
    cleaned = re.sub(r"Copyright\s+[^.。！？]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:Prev|Next)\)?\s*\d*\)?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
