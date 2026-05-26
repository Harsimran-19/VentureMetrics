from pathlib import Path

from venture_metrics_agent.ingestion.source_registry import init_db
from venture_metrics_agent.retrieval.web_search import WebResult
from venture_metrics_agent.reasoning.web_memory import WebMemoryOptions, remember_web_results


def test_remember_web_results_creates_source_document_and_chunk(tmp_path: Path) -> None:
    db_path = tmp_path / "web_memory.db"
    docs_dir = tmp_path / "documents"
    content = (
        "The official programme page describes startup funding, grant support, "
        "incubation resources, mentorship, and application requirements for founders in Hong Kong. "
        "It is useful evidence for a Venture Metrics answer about funding programmes."
    )

    stats = remember_web_results(
        db_path,
        question="Find startup funding programmes in Hong Kong.",
        results=[
            WebResult(
                title="Official Startup Funding Programme",
                url="https://example.gov.hk/startup-funding",
                content=content,
                score=0.92,
            )
        ],
        options=WebMemoryOptions(documents_dir=docs_dir, min_content_chars=40, index_min_chars=40),
    )

    assert stats["sources_created"] == 1
    assert stats["documents_created"] == 1
    assert stats["chunks_created"] == 1

    conn = init_db(db_path)
    try:
        source = conn.execute("SELECT status, original_file_name FROM sources").fetchone()
        document = conn.execute("SELECT extraction_method, text FROM documents").fetchone()
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()

    assert source == ("fetched", "__web_fallback__")
    assert document[0] == "web_search_result"
    assert "startup funding" in document[1]
    assert chunk_count == 1
    assert list(docs_dir.glob("source_*.web.md"))
