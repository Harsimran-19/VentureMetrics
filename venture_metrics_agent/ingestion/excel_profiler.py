"""Profile arbitrary Excel workbooks before ingestion."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from venture_metrics_agent.ingestion.url_extractor import extract_urls_from_row


EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}

TITLE_HINTS = {
    "title",
    "name",
    "article",
    "report",
    "topic",
    "标题",
    "名称",
    "项目",
    "文件",
}
CATEGORY_HINTS = {
    "category",
    "type",
    "sector",
    "分类",
    "类型",
}
REGION_HINTS = {
    "region",
    "city",
    "country",
    "area",
    "location",
    "地区",
    "城市",
    "国家",
    "区域",
    "地点",
}
NOTES_HINTS = {
    "note",
    "notes",
    "summary",
    "description",
    "remark",
    "备注",
    "简介",
    "描述",
    "摘要",
}


def find_excel_files(folder_path: str | Path) -> list[Path]:
    folder = Path(folder_path)
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.lower() in EXCEL_SUFFIXES
        and not path.name.startswith("~$")
    )


def profile_folder(folder_path: str | Path) -> dict[str, Any]:
    folder = Path(folder_path)
    files = find_excel_files(folder)
    file_profiles = [profile_workbook(path) for path in files]

    all_urls = [
        url
        for file_profile in file_profiles
        for sheet in file_profile["sheets"]
        for url in sheet["urls"]
    ]
    url_counts = Counter(all_urls)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "folder_path": str(folder),
        "totals": {
            "files": len(file_profiles),
            "sheets": sum(len(file_profile["sheets"]) for file_profile in file_profiles),
            "rows": sum(
                sheet["row_count"]
                for file_profile in file_profiles
                for sheet in file_profile["sheets"]
            ),
            "urls": len(all_urls),
            "unique_urls": len(url_counts),
            "duplicate_urls": sum(count - 1 for count in url_counts.values() if count > 1),
        },
        "files": file_profiles,
    }


def profile_workbook(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    excel_file = pd.ExcelFile(path)
    sheets = [profile_sheet(path, sheet_name) for sheet_name in excel_file.sheet_names]

    return {
        "file_name": path.name,
        "file_path": str(path),
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def profile_sheet(file_path: str | Path, sheet_name: str) -> dict[str, Any]:
    df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=object)
    df = df.where(pd.notna(df), None)
    columns = [str(column) for column in df.columns]

    row_urls: list[list[str]] = []
    column_url_counts: Counter[str] = Counter()
    all_urls: list[str] = []

    for _, row in df.iterrows():
        row_dict = {str(column): _json_safe(value) for column, value in row.to_dict().items()}
        urls = extract_urls_from_row(row_dict)
        row_urls.append(urls)
        all_urls.extend(urls)

        for column, value in row_dict.items():
            if extract_urls_from_row([value]):
                column_url_counts[column] += len(extract_urls_from_row([value]))

    duplicate_url_count = sum(count - 1 for count in Counter(all_urls).values() if count > 1)

    return {
        "sheet_name": sheet_name,
        "column_names": columns,
        "row_count": int(len(df)),
        "detected_url_columns": [
            {"column_name": column, "url_count": count}
            for column, count in column_url_counts.most_common()
        ],
        "url_count": len(all_urls),
        "unique_url_count": len(set(all_urls)),
        "duplicate_url_count": duplicate_url_count,
        "likely_title_columns": _detect_columns(columns, TITLE_HINTS),
        "likely_category_columns": _detect_columns(columns, CATEGORY_HINTS),
        "likely_region_columns": _detect_columns(columns, REGION_HINTS),
        "likely_notes_columns": _detect_columns(columns, NOTES_HINTS),
        "empty_column_ratio": _empty_column_ratio(df),
        "sample_rows": _sample_rows(df),
        "urls": all_urls,
    }


def write_profile_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compact_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": report["generated_at"],
        "folder_path": report["folder_path"],
        "totals": report["totals"],
        "files": [
            {
                "file_name": file_profile["file_name"],
                "sheet_count": file_profile["sheet_count"],
                "sheets": [
                    {
                        "sheet_name": sheet["sheet_name"],
                        "row_count": sheet["row_count"],
                        "column_count": len(sheet["column_names"]),
                        "url_count": sheet["url_count"],
                        "unique_url_count": sheet["unique_url_count"],
                        "duplicate_url_count": sheet["duplicate_url_count"],
                        "detected_url_columns": sheet["detected_url_columns"],
                        "likely_title_columns": sheet["likely_title_columns"],
                        "likely_category_columns": sheet["likely_category_columns"],
                        "likely_region_columns": sheet["likely_region_columns"],
                    }
                    for sheet in file_profile["sheets"]
                ],
            }
            for file_profile in report["files"]
        ],
    }


def _detect_columns(columns: list[str], hints: set[str]) -> list[str]:
    detected: list[str] = []
    for column in columns:
        normalized = column.strip().lower()
        if any(hint in normalized for hint in hints):
            detected.append(column)
    return detected


def _empty_column_ratio(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {str(column): 1.0 for column in df.columns}

    ratios: dict[str, float] = {}
    for column in df.columns:
        empty_count = 0
        for value in df[column].tolist():
            if value is None or str(value).strip() == "":
                empty_count += 1
        ratios[str(column)] = round(empty_count / len(df), 4)
    return ratios


def _sample_rows(df: pd.DataFrame, limit: int = 3) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        samples.append({str(column): _json_safe(value) for column, value in row.to_dict().items()})
    return samples


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

