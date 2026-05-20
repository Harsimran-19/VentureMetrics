from venture_metrics_agent.ingestion.url_extractor import (
    extract_urls_from_row,
    extract_urls_from_text,
    normalize_url,
)


def test_extracts_http_and_www_urls() -> None:
    text = "See https://Example.com/path?a=1 and www.hkstp.org/test."

    assert extract_urls_from_text(text) == [
        "https://example.com/path?a=1",
        "https://www.hkstp.org/test",
    ]


def test_extracts_unique_urls_from_row() -> None:
    row = {
        "title": "Policy",
        "link": "https://www.gov.hk/en/",
        "notes": "Duplicate https://www.gov.hk/en/",
    }

    assert extract_urls_from_row(row) == ["https://www.gov.hk/en/"]


def test_normalize_url_removes_trailing_punctuation() -> None:
    assert normalize_url("https://example.com/report).") == "https://example.com/report"

