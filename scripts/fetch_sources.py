#!/usr/bin/env python3
"""Fetch pending source URLs into local markdown documents using Tavily Extract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH, DEFAULT_DOCUMENTS_DIR
from venture_metrics_agent.ingestion.fetcher import FetchOptions, fetch_pending_sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument(
        "--documents-dir",
        default=str(DEFAULT_DOCUMENTS_DIR),
        help="Directory where extracted markdown documents are written.",
    )
    parser.add_argument("--limit", type=int, default=25, help="Maximum number of sources to fetch.")
    parser.add_argument("--batch-size", type=int, default=5, help="URLs per Tavily Extract request.")
    parser.add_argument("--retry-failed", action="store_true", help="Retry sources currently marked failed.")
    parser.add_argument(
        "--extract-depth",
        choices=["basic", "advanced"],
        default="advanced",
        help="Tavily extraction depth. Advanced is the default for fuller document extraction.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "text"],
        default="markdown",
        help="Tavily output format.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Tavily extraction timeout per request.")
    parser.add_argument("--min-chars", type=int, default=200, help="Minimum extracted characters to keep.")
    args = parser.parse_args()

    stats = fetch_pending_sources(
        args.db,
        args.documents_dir,
        options=FetchOptions(
            limit=args.limit,
            batch_size=args.batch_size,
            retry_failed=args.retry_failed,
            extract_depth=args.extract_depth,
            output_format=args.format,
            timeout=args.timeout,
            min_chars=args.min_chars,
        ),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
