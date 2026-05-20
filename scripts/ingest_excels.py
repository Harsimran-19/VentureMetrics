#!/usr/bin/env python3
"""Ingest Excel rows and build the initial source registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH, DEFAULT_EXCEL_FOLDER
from venture_metrics_agent.ingestion.excel_ingest import (
    export_source_registry,
    ingest_excel_folder,
    source_registry_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "folder",
        nargs="?",
        default=str(DEFAULT_EXCEL_FOLDER),
        help="Folder containing Excel files.",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database path.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate the SQLite database before ingestion.",
    )
    parser.add_argument(
        "--export",
        default="venture_metrics_agent/data/processed/source_registry.csv",
        help="CSV or JSON path for exporting the source registry.",
    )
    args = parser.parse_args()

    stats = ingest_excel_folder(args.folder, args.db, rebuild=args.rebuild)
    summary = source_registry_summary(args.db)
    export_path = export_source_registry(args.db, args.export)

    print(
        json.dumps(
            {"ingestion": stats, "source_registry": summary, "export_path": str(export_path)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
