"""URL extraction helpers for unknown Excel sheet formats."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from urllib.parse import urlparse, urlunparse


URL_RE = re.compile(
    r"""(?ix)
    \b(
        https?://[^\s<>"'）),，。；;]+
        |
        www\.[^\s<>"'）),，。；;]+
    )
    """
)

TRAILING_PUNCTUATION = ".,;:!?)）]】}\"'"


def normalize_url(url: str) -> str:
    """Normalize obvious URL variants without changing meaning."""
    cleaned = url.strip().strip(TRAILING_PUNCTUATION)
    if cleaned.startswith("www."):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned

    netloc = parsed.netloc.lower()
    scheme = parsed.scheme.lower()
    path = parsed.path or ""
    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path)
    return urlunparse(normalized)


def extract_urls_from_text(value: object) -> list[str]:
    """Extract URLs from any cell-like value."""
    if value is None:
        return []

    text = str(value)
    urls: list[str] = []
    seen: set[str] = set()

    for match in URL_RE.findall(text):
        url = normalize_url(match)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)

    return urls


def extract_urls_from_row(row: Mapping[str, object] | Iterable[object]) -> list[str]:
    """Extract unique URLs from a row while preserving first-seen order."""
    values = row.values() if isinstance(row, Mapping) else row
    urls: list[str] = []
    seen: set[str] = set()

    for value in values:
        for url in extract_urls_from_text(value):
            if url not in seen:
                urls.append(url)
                seen.add(url)

    return urls

