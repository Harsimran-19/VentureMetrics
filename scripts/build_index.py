#!/usr/bin/env python3
"""Build the local chunk and retrieval index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.retrieval.chunker import ChunkOptions, build_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--rebuild", action="store_true", help="Delete existing chunks before rebuilding.")
    parser.add_argument("--target-chars", type=int, default=3600, help="Target chunk size in characters.")
    parser.add_argument("--overlap-chars", type=int, default=500, help="Chunk overlap in characters.")
    parser.add_argument("--min-chars", type=int, default=250, help="Minimum chunk size to index.")
    args = parser.parse_args()

    stats = build_chunks(
        args.db,
        rebuild=args.rebuild,
        options=ChunkOptions(
            target_chars=args.target_chars,
            overlap_chars=args.overlap_chars,
            min_chars=args.min_chars,
        ),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
