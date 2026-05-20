"""Chunk fetched documents while preserving source traceability."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venture_metrics_agent.ingestion.excel_ingest import sqlite_row_factory
from venture_metrics_agent.ingestion.source_registry import init_db


@dataclass(frozen=True)
class ChunkOptions:
    target_chars: int = 3600
    overlap_chars: int = 500
    min_chars: int = 250


def build_chunks(db_path: str | Path, *, rebuild: bool = False, options: ChunkOptions | None = None) -> dict[str, int]:
    """Create document chunks and a SQLite FTS index."""
    options = options or ChunkOptions()
    conn = init_db(db_path)
    conn.row_factory = sqlite_row_factory

    if rebuild:
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text,
                title,
                source_domain,
                source_type
            )
            """
        )
        conn.execute("DELETE FROM chunks")

    documents = conn.execute(
        """
        SELECT
            d.id AS document_id,
            d.source_id,
            d.title,
            d.text,
            d.local_path,
            d.metadata_json,
            s.canonical_url,
            s.source_domain,
            s.source_type,
            s.reliability_label,
            s.original_file_name,
            s.original_sheet_name,
            s.original_row_number
        FROM documents d
        JOIN sources s ON s.id = d.source_id
        ORDER BY d.id
        """
    ).fetchall()

    stats = {"documents_seen": len(documents), "documents_indexed": 0, "chunks_created": 0, "chunks_skipped": 0}

    for document in documents:
        existing = conn.execute("SELECT COUNT(*) AS count FROM chunks WHERE document_id = ?", (document["document_id"],)).fetchone()
        if existing["count"] and not rebuild:
            stats["chunks_skipped"] += int(existing["count"])
            continue

        document_chunks = chunk_text(document["text"], options=options)
        if not document_chunks:
            continue

        for chunk_index, text in enumerate(document_chunks):
            metadata = {
                "source_id": document["source_id"],
                "url": document["canonical_url"],
                "source_domain": document["source_domain"],
                "source_type": document["source_type"],
                "reliability_label": document["reliability_label"],
                "title": document["title"],
                "file_name": document["original_file_name"],
                "sheet_name": document["original_sheet_name"],
                "row_number": document["original_row_number"],
                "chunk_index": chunk_index,
                "local_path": document["local_path"],
            }
            cursor = conn.execute(
                """
                INSERT INTO chunks (
                    document_id,
                    source_id,
                    chunk_index,
                    text,
                    char_count,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document["document_id"],
                    document["source_id"],
                    chunk_index,
                    text,
                    len(text),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            conn.execute(
                """
                INSERT INTO chunks_fts(rowid, text, title, source_domain, source_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    text,
                    document["title"] or "",
                    document["source_domain"] or "",
                    document["source_type"] or "",
                ),
            )
            stats["chunks_created"] += 1

        stats["documents_indexed"] += 1

    conn.commit()
    conn.close()
    return stats


def chunk_text(text: str, *, options: ChunkOptions | None = None) -> list[str]:
    options = options or ChunkOptions()
    clean_text = _clean_text(text)
    if len(clean_text) < options.min_chars:
        return []
    if len(clean_text) <= options.target_chars:
        return [clean_text]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", clean_text) if paragraph.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if current and current_len + paragraph_len + 2 > options.target_chars:
            chunks.append("\n\n".join(current).strip())
            overlap = _tail_overlap(chunks[-1], options.overlap_chars)
            current = [overlap, paragraph] if overlap else [paragraph]
            current_len = sum(len(item) for item in current) + (2 * max(len(current) - 1, 0))
        else:
            current.append(paragraph)
            current_len += paragraph_len + 2

    if current:
        chunks.append("\n\n".join(current).strip())

    return [chunk for chunk in chunks if len(chunk) >= options.min_chars]


def _clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tail_overlap(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return ""
    tail = text[-overlap_chars:]
    boundary = max(tail.find("\n\n"), tail.find(". "), tail.find("。"))
    if boundary > 0:
        tail = tail[boundary:].strip()
    return tail.strip()
