from venture_metrics_agent.ingestion.source_registry import (
    canonicalize_url,
    classify_source,
    source_domain,
)


def test_canonicalize_url_removes_fragment_and_trailing_slash() -> None:
    assert canonicalize_url("https://Example.com/path/#section") == "https://example.com/path"


def test_source_domain_removes_www() -> None:
    assert source_domain("https://www.hkstp.org/") == "hkstp.org"


def test_classify_government_source() -> None:
    assert classify_source("https://www.gov.hk/en/theme/") == ("government", "very_high")


def test_classify_university_source() -> None:
    assert classify_source("https://www.hku.hk/research") == ("university", "high")

