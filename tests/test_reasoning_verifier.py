from venture_metrics_agent.retrieval.evidence_scorer import EvidenceAssessment
from venture_metrics_agent.retrieval.retriever import RetrievalResult
from venture_metrics_agent.reasoning.verifier import verify_evidence


def test_verifier_accepts_hong_kong_university_domain_for_hong_kong_question() -> None:
    result = RetrievalResult(
        chunk_id=1,
        document_id=1,
        source_id=1,
        chunk_index=0,
        text="The entrepreneurship centre offers startup support, competitions, mentorship, and funding.",
        score=1.0,
        title="Entrepreneurship Centre",
        url="https://www.eduhk.hk/example",
        source_domain="eduhk.hk",
        source_type="university",
        reliability_label="high",
        file_name="sample.xlsx",
        sheet_name="Sheet1",
        row_number=2,
    )

    verified = verify_evidence(
        "Which sources are related to Hong Kong entrepreneurship support?",
        [result],
        EvidenceAssessment(
            is_sufficient=True,
            confidence="High",
            reason="Test assessment.",
            needs_web_fallback=False,
            missing_information=[],
        ),
    )

    assert verified.answerable is True
    assert verified.accepted_internal == [result]
    assert verified.rejected_internal == []
