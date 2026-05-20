#!/usr/bin/env python3
"""Profile Excel files and write a JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.ingestion.excel_profiler import (
    compact_summary,
    profile_folder,
    write_profile_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "folder",
        nargs="?",
        default="document_sources",
        help="Folder containing Excel files. Defaults to document_sources.",
    )
    parser.add_argument(
        "--output",
        default="venture_metrics_agent/data/processed/excel_profile_report.json",
        help="Path for the full JSON profiling report.",
    )
    parser.add_argument(
        "--summary-output",
        default="venture_metrics_agent/data/processed/excel_profile_summary.json",
        help="Path for a compact JSON summary.",
    )
    args = parser.parse_args()

    report = profile_folder(args.folder)
    report_path = write_profile_report(report, args.output)
    summary = compact_summary(report)
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    totals = report["totals"]
    print(f"Wrote full report: {report_path}")
    print(f"Wrote compact summary: {summary_path}")
    print(
        "Profiled "
        f"{totals['files']} files, {totals['sheets']} sheets, {totals['rows']} rows, "
        f"{totals['urls']} URLs ({totals['unique_urls']} unique, {totals['duplicate_urls']} duplicates)."
    )


if __name__ == "__main__":
    main()
