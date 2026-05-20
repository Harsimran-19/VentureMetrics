"""Local prototype configuration."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEL_FOLDER = PROJECT_ROOT / "document_sources"
DEFAULT_DATA_DIR = PROJECT_ROOT / "venture_metrics_agent" / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "processed" / "venture_metrics.db"
DEFAULT_DOCUMENTS_DIR = DEFAULT_DATA_DIR / "documents"
