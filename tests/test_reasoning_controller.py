from __future__ import annotations

from pathlib import Path

from venture_metrics_agent.retrieval.evidence_scorer import EvidenceAssessment
from venture_metrics_agent.retrieval.retriever import RetrievalResult
from venture_metrics_agent.retrieval.web_search import WebResult
from venture_metrics_agent.reasoning import ReasoningOptions, answer_question_reasoning
from venture_metrics_agent.reasoning.tools import InternalSearchObservation, WebSearchObservation


class FakeLLM:
    is_configured = False


class FakeToolbox:
    def __init__(self, observation: InternalSearchObservation) -> None:
        self.observation = observation
        self.internal_calls = 0
        self.web_calls = 0

    def internal_search(self, question: str, *, top_k: int = 8) -> InternalSearchObservation:
        self.internal_calls += 1
        return self.observation

    def web_search(self, query: str, *, max_results: int = 4) -> WebSearchObservation:
        self.web_calls += 1
        return WebSearchObservation(
            results=[
                WebResult(
                    title="Official grant page",
                    url="https://example.gov/grants",
                    content="Official grant evidence for startups.",
                    score=0.9,
                )
            ]
        )


class SequenceToolbox(FakeToolbox):
    def __init__(self, observations: list[InternalSearchObservation]) -> None:
        super().__init__(observations[-1])
        self.observations = observations
        self.queries: list[str] = []

    def internal_search(self, question: str, *, top_k: int = 8) -> InternalSearchObservation:
        self.internal_calls += 1
        self.queries.append(question)
        index = min(self.internal_calls - 1, len(self.observations) - 1)
        return self.observations[index]


def test_reasoning_greeting_uses_no_tools(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    response = answer_question_reasoning(db_path, "hi", llm=FakeLLM())

    assert response["source_mode"] == "no_tools"
    assert response["used_web_fallback"] is False
    assert response["retrieved_evidence"] == []
    assert response["web_evidence"] == []
    assert "Ask me a Venture Metrics research question" not in response["answer"]
    assert [step["tool"] for step in response["reasoning_trace"]] == [None]


def test_reasoning_social_question_uses_no_tools(tmp_path: Path) -> None:
    response = answer_question_reasoning(tmp_path / "test.db", "how are you?", llm=FakeLLM())

    assert response["source_mode"] == "no_tools"
    assert response["used_web_fallback"] is False
    assert response["citations"] == []
    assert response["retrieved_evidence"] == []
    assert "Ask me a Venture Metrics research question" not in response["answer"]


def test_reasoning_skips_web_when_internal_evidence_is_sufficient(tmp_path: Path) -> None:
    toolbox = FakeToolbox(_internal_observation(confidence="High", sufficient=True))

    response = answer_question_reasoning(
        tmp_path / "test.db",
        "Which sources mention startup funding or grants?",
        options=ReasoningOptions(use_web_fallback=True, max_internal_iterations=1, remember_web_results=False),
        llm=FakeLLM(),
        toolbox=toolbox,
    )

    assert toolbox.internal_calls == 1
    assert toolbox.web_calls == 0
    assert response["source_mode"] == "internal_only"
    assert response["used_web_fallback"] is False
    assert any(step["decision"] == "skip_web_search" for step in response["reasoning_trace"])


def test_reasoning_uses_web_when_internal_evidence_is_weak(tmp_path: Path) -> None:
    toolbox = FakeToolbox(_internal_observation(confidence="Low", sufficient=False))

    response = answer_question_reasoning(
        tmp_path / "test.db",
        "Which sources mention startup funding or grants?",
        options=ReasoningOptions(use_web_fallback=True, max_internal_iterations=1, remember_web_results=False),
        llm=FakeLLM(),
        toolbox=toolbox,
    )

    assert toolbox.internal_calls == 1
    assert toolbox.web_calls == 1
    assert response["source_mode"] == "internal_plus_web"
    assert response["used_web_fallback"] is True
    assert any(step["decision"] == "use_web_search" for step in response["reasoning_trace"])


def test_reasoning_uses_web_when_legacy_score_is_high_but_evidence_is_irrelevant(tmp_path: Path) -> None:
    toolbox = FakeToolbox(
        _internal_observation(
            confidence="High",
            sufficient=True,
            text="This page is about unrelated university laboratory facilities and staff directories.",
            title="Unrelated University Page",
            url="https://example.edu/labs",
        )
    )

    response = answer_question_reasoning(
        tmp_path / "test.db",
        "Which sources mention startup funding or grants?",
        options=ReasoningOptions(use_web_fallback=True, max_internal_iterations=1, remember_web_results=False),
        llm=FakeLLM(),
        toolbox=toolbox,
    )

    assert toolbox.internal_calls == 1
    assert toolbox.web_calls == 1
    assert response["source_mode"] == "web_only"
    assert response["rejected_evidence"][0]["reason"] == "The source text does not cover the main terms in the question."
    assert any(step["decision"] == "verify_internal_relevance" for step in response["reasoning_trace"])


def test_reasoning_returns_insufficient_when_irrelevant_internal_evidence_and_web_disabled(tmp_path: Path) -> None:
    toolbox = FakeToolbox(
        _internal_observation(
            confidence="High",
            sufficient=True,
            text="This page is about unrelated university laboratory facilities and staff directories.",
            title="Unrelated University Page",
            url="https://example.edu/labs",
        )
    )

    response = answer_question_reasoning(
        tmp_path / "test.db",
        "Which sources mention startup funding or grants?",
        options=ReasoningOptions(use_web_fallback=False, max_internal_iterations=1, remember_web_results=False),
        llm=FakeLLM(),
        toolbox=toolbox,
    )

    assert toolbox.web_calls == 0
    assert response["confidence"] == "Insufficient evidence"
    assert response["source_mode"] == "insufficient"
    assert response["retrieved_evidence"] == []
    assert response["rejected_evidence"]


def test_reasoning_refines_internal_query_before_answering(tmp_path: Path) -> None:
    toolbox = SequenceToolbox(
        [
            _internal_observation(
                confidence="High",
                sufficient=True,
                text="This page is about unrelated university laboratory facilities and staff directories.",
                title="Unrelated University Page",
                url="https://example.edu/labs",
            ),
            _internal_observation(
                confidence="High",
                sufficient=True,
                text="The source describes startup funding support and grant programmes in Hong Kong.",
                title="Startup Funding Source",
                url="https://example.edu/startup-funding",
                chunk_id=2,
                source_id=2,
            ),
        ]
    )

    response = answer_question_reasoning(
        tmp_path / "test.db",
        "Which sources mention startup funding or grants?",
        options=ReasoningOptions(use_web_fallback=False, max_internal_iterations=2, remember_web_results=False),
        llm=FakeLLM(),
        toolbox=toolbox,
    )

    assert toolbox.internal_calls == 2
    assert toolbox.queries[0] == "Which sources mention startup funding or grants?"
    assert toolbox.queries[1] != toolbox.queries[0]
    assert response["source_mode"] == "internal_only"
    assert response["retrieved_evidence"]
    assert any(step["decision"] == "refine_internal_query" for step in response["reasoning_trace"])


def _internal_observation(
    *,
    confidence: str,
    sufficient: bool,
    text: str = "The source describes startup funding support and grant programmes in Hong Kong.",
    title: str = "Startup Funding Source",
    url: str = "https://example.edu/startup-funding",
    chunk_id: int = 1,
    source_id: int = 1,
) -> InternalSearchObservation:
    return InternalSearchObservation(
        results=[
            RetrievalResult(
                chunk_id=chunk_id,
                document_id=1,
                source_id=source_id,
                chunk_index=0,
                text=text,
                score=1.0,
                title=title,
                url=url,
                source_domain="example.edu",
                source_type="university",
                reliability_label="high",
                file_name="sample.xlsx",
                sheet_name="Sheet1",
                row_number=2,
            )
        ],
        assessment=EvidenceAssessment(
            is_sufficient=sufficient,
            confidence=confidence,
            reason="Test assessment.",
            needs_web_fallback=not sufficient,
            missing_information=[] if sufficient else ["Internal evidence is weak."],
        ),
    )
