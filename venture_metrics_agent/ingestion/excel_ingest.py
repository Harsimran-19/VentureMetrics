"""Ingest raw Excel rows and unique URLs into SQLite."""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

import pandas as pd

from venture_metrics_agent.ingestion.excel_profiler import (
    CATEGORY_HINTS,
    NOTES_HINTS,
    REGION_HINTS,
    TITLE_HINTS,
    find_excel_files,
)
from venture_metrics_agent.ingestion.source_registry import (
    canonicalize_url,
    classify_source,
    init_db,
    source_domain,
)
from venture_metrics_agent.ingestion.url_extractor import extract_urls_from_row


def ingest_excel_folder(folder_path: str | Path, db_path: str | Path, rebuild: bool = False) -> dict[str, int]:
    if rebuild:
        Path(db_path).unlink(missing_ok=True)

    conn = init_db(db_path)
    stats = {
        "files_processed": 0,
        "sheets_processed": 0,
        "rows_processed": 0,
        "urls_detected": 0,
        "sources_created": 0,
        "duplicate_urls": 0,
    }

    for file_path in find_excel_files(folder_path):
        excel_file = pd.ExcelFile(file_path)
        file_id = _insert_excel_file(conn, file_path, len(excel_file.sheet_names))
        stats["files_processed"] += 1

        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=object)
            df = df.where(pd.notna(df), None)
            columns = [str(column) for column in df.columns]
            sheet_urls = 0

            sheet_id = _insert_excel_sheet(conn, file_id, sheet_name, len(df), columns, 0)
            stats["sheets_processed"] += 1

            detected_columns = {
                "title": _first_matching_column(columns, TITLE_HINTS),
                "category": _first_matching_column(columns, CATEGORY_HINTS),
                "region": _first_matching_column(columns, REGION_HINTS),
                "notes": _first_matching_column(columns, NOTES_HINTS),
            }

            for row_index, row in df.iterrows():
                row_number = int(row_index) + 2
                row_dict = {
                    str(column): _json_safe(value)
                    for column, value in row.to_dict().items()
                }
                urls = extract_urls_from_row(row_dict)
                sheet_urls += len(urls)
                stats["urls_detected"] += len(urls)
                stats["rows_processed"] += 1

                detected_title = _value_for(row_dict, detected_columns["title"])
                detected_category = _value_for(row_dict, detected_columns["category"])
                detected_region = _value_for(row_dict, detected_columns["region"])
                detected_notes = _value_for(row_dict, detected_columns["notes"])

                _insert_raw_row(
                    conn,
                    file_id=file_id,
                    sheet_id=sheet_id,
                    row_number=row_number,
                    row_dict=row_dict,
                    detected_title=detected_title,
                    detected_category=detected_category,
                    detected_region=detected_region,
                    detected_notes=detected_notes,
                    urls=urls,
                )

                for url in urls:
                    created = _upsert_source(
                        conn,
                        url=url,
                        title_from_excel=detected_title,
                        file_name=file_path.name,
                        sheet_name=sheet_name,
                        row_number=row_number,
                    )
                    if created:
                        stats["sources_created"] += 1
                    else:
                        stats["duplicate_urls"] += 1

            _update_sheet_url_count(conn, sheet_id, sheet_urls)

    conn.commit()
    conn.close()
    return stats


def source_registry_summary(db_path: str | Path) -> dict[str, Any]:
    conn = init_db(db_path)
    conn.row_factory = sqlite_row_factory

    total = conn.execute("SELECT COUNT(*) AS count FROM sources").fetchone()["count"]
    by_status = conn.execute(
        "SELECT status, COUNT(*) AS count FROM sources GROUP BY status ORDER BY count DESC"
    ).fetchall()
    by_source_type = conn.execute(
        "SELECT source_type, COUNT(*) AS count FROM sources GROUP BY source_type ORDER BY count DESC"
    ).fetchall()
    by_reliability = conn.execute(
        "SELECT reliability_label, COUNT(*) AS count FROM sources GROUP BY reliability_label ORDER BY count DESC"
    ).fetchall()
    conn.close()

    return {
        "total": total,
        "by_status": {row["status"]: row["count"] for row in by_status},
        "by_source_type": {row["source_type"]: row["count"] for row in by_source_type},
        "by_reliability": {row["reliability_label"]: row["count"] for row in by_reliability},
    }


def export_source_registry(db_path: str | Path, output_path: str | Path) -> Path:
    conn = init_db(db_path)
    conn.row_factory = sqlite_row_factory
    rows = conn.execute(
        """
        SELECT
            id,
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
            original_row_number,
            fetched_at,
            content_hash,
            error_message
        FROM sources
        ORDER BY id
        """
    ).fetchall()
    conn.close()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    fieldnames = list(rows[0].keys()) if rows else [
        "id",
        "url",
        "canonical_url",
        "source_domain",
        "title_from_excel",
        "title_from_page",
        "source_type",
        "reliability_label",
        "status",
        "original_file_name",
        "original_sheet_name",
        "original_row_number",
        "fetched_at",
        "content_hash",
        "error_message",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return path


def sqlite_row_factory(cursor, row) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _insert_excel_file(conn, file_path: Path, sheet_count: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO excel_files (file_name, file_path, sheet_count)
        VALUES (?, ?, ?)
        """,
        (file_path.name, str(file_path), sheet_count),
    )
    return int(cursor.lastrowid)


def _insert_excel_sheet(conn, file_id: int, sheet_name: str, row_count: int, columns: list[str], url_count: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO excel_sheets (file_id, sheet_name, row_count, columns_json, detected_url_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, sheet_name, row_count, json.dumps(columns, ensure_ascii=False), url_count),
    )
    return int(cursor.lastrowid)


def _update_sheet_url_count(conn, sheet_id: int, url_count: int) -> None:
    conn.execute(
        "UPDATE excel_sheets SET detected_url_count = ? WHERE id = ?",
        (url_count, sheet_id),
    )


def _insert_raw_row(
    conn,
    *,
    file_id: int,
    sheet_id: int,
    row_number: int,
    row_dict: dict[str, Any],
    detected_title: str | None,
    detected_category: str | None,
    detected_region: str | None,
    detected_notes: str | None,
    urls: list[str],
) -> None:
    conn.execute(
        """
        INSERT INTO raw_rows (
            file_id,
            sheet_id,
            row_number,
            original_row_json,
            detected_title,
            detected_category,
            detected_region,
            detected_notes,
            detected_urls_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            sheet_id,
            row_number,
            json.dumps(row_dict, ensure_ascii=False),
            detected_title,
            detected_category,
            detected_region,
            detected_notes,
            json.dumps(urls, ensure_ascii=False),
        ),
    )


def _upsert_source(
    conn,
    *,
    url: str,
    title_from_excel: str | None,
    file_name: str,
    sheet_name: str,
    row_number: int,
) -> bool:
    canonical_url = canonicalize_url(url)
    source_type, reliability_label = classify_source(canonical_url, title_from_excel)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO sources (
            url,
            canonical_url,
            source_domain,
            title_from_excel,
            source_type,
            reliability_label,
            status,
            original_file_name,
            original_sheet_name,
            original_row_number
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            url,
            canonical_url,
            source_domain(canonical_url),
            title_from_excel,
            source_type,
            reliability_label,
            file_name,
            sheet_name,
            row_number,
        ),
    )
    return cursor.rowcount > 0


def _first_matching_column(columns: list[str], hints: set[str]) -> str | None:
    for column in columns:
        normalized = column.strip().lower()
        if any(hint in normalized for hint in hints):
            return column
    return None


def _value_for(row_dict: dict[str, Any], column: str | None) -> str | None:
    if not column:
        return None
    value = row_dict.get(column)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
