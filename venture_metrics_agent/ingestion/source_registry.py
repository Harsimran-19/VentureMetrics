"""Source registry classification and database helpers."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from venture_metrics_agent.observability.telemetry import create_observability_tables


GOV_HINTS = ("gov", "政府", "policy", "grant")
UNIVERSITY_HINTS = (
    "edu",
    "hku",
    "cuhk",
    "cityu",
    "polyu",
    "ust",
    "hkust",
    "university",
    "college",
    "大学",
)
SCIENCE_PARK_HINTS = ("hkstp", "cyberport", "sciencepark", "science-park", "科技园")
INVESTOR_HINTS = ("vc", "venture", "capital", "invest", "portfolio", "fund")
MEDIA_HINTS = (
    "news",
    "media",
    "reuters",
    "bloomberg",
    "scmp",
    "forbes",
    "techcrunch",
)
DATABASE_HINTS = ("database", "crunchbase", "pitchbook", "cbinsights")
REPORT_HINTS = ("report", "whitepaper", "pdf", "报告", "白皮书")


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()

    path = re.sub(r"/+$", "", parsed.path or "")
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        fragment="",
    )
    return urlunparse(normalized)


def source_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def classify_source(url: str, title: str | None = None) -> tuple[str, str]:
    domain = source_domain(url)
    haystack = f"{domain} {url} {title or ''}".lower()

    if any(hint in haystack for hint in GOV_HINTS):
        return "government", "very_high"
    if any(hint in haystack for hint in UNIVERSITY_HINTS):
        return "university", "high"
    if any(hint in haystack for hint in SCIENCE_PARK_HINTS):
        return "science_park", "high"
    if any(hint in haystack for hint in INVESTOR_HINTS):
        return "investor", "medium_high"
    if any(hint in haystack for hint in DATABASE_HINTS):
        return "database", "medium"
    if any(hint in haystack for hint in REPORT_HINTS):
        return "report", "medium"
    if any(hint in haystack for hint in MEDIA_HINTS):
        return "media", "medium"
    return "unknown", "low"


def init_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    _create_tables(conn)
    create_observability_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS excel_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sheet_count INTEGER NOT NULL,
            profile_json TEXT
        );

        CREATE TABLE IF NOT EXISTS excel_sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            sheet_name TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            columns_json TEXT NOT NULL,
            detected_url_count INTEGER NOT NULL,
            FOREIGN KEY(file_id) REFERENCES excel_files(id)
        );

        CREATE TABLE IF NOT EXISTS raw_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            sheet_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            original_row_json TEXT NOT NULL,
            detected_title TEXT,
            detected_category TEXT,
            detected_region TEXT,
            detected_notes TEXT,
            detected_urls_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(file_id) REFERENCES excel_files(id),
            FOREIGN KEY(sheet_id) REFERENCES excel_sheets(id)
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            canonical_url TEXT NOT NULL UNIQUE,
            source_domain TEXT,
            title_from_excel TEXT,
            title_from_page TEXT,
            source_type TEXT NOT NULL,
            reliability_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            original_file_name TEXT,
            original_sheet_name TEXT,
            original_row_number INTEGER,
            fetched_at TEXT,
            content_hash TEXT,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            title TEXT,
            text TEXT NOT NULL,
            language TEXT,
            published_date TEXT,
            fetched_at TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            local_path TEXT,
            metadata_json TEXT,
            FOREIGN KEY(source_id) REFERENCES sources(id)
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            source_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            metadata_json TEXT,
            embedding_id TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id),
            FOREIGN KEY(source_id) REFERENCES sources(id),
            UNIQUE(document_id, chunk_index)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            title,
            source_domain,
            source_type
        );

        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            confidence TEXT NOT NULL,
            source_mode TEXT NOT NULL,
            used_web_fallback INTEGER NOT NULL DEFAULT 0,
            citations_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
