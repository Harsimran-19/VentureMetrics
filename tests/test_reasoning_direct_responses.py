from pathlib import Path

from venture_metrics_agent.ingestion.source_registry import init_db
from venture_metrics_agent.reasoning.controller import answer_question_reasoning
from venture_metrics_agent.llm.provider import LLMConfig, LLMProvider


def _unconfigured_llm() -> LLMProvider:
    return LLMProvider(LLMConfig(api_key=None))


def _empty_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "agent.db"
    conn = init_db(db_path)
    conn.close()
    return db_path


def test_nice_to_meet_you_returns_plain_chat_without_tools(tmp_path: Path) -> None:
    response = answer_question_reasoning(_empty_db(tmp_path), "nice to meet you?", llm=_unconfigured_llm())

    assert response["source_mode"] == "no_tools"
    assert response["used_web_fallback"] is False
    assert response["citations"] == []
    assert "Nice to meet you" in response["answer"]


def test_how_are_you_fallback_is_not_robotic(tmp_path: Path) -> None:
    response = answer_question_reasoning(_empty_db(tmp_path), "how are you?", llm=_unconfigured_llm())

    assert response["source_mode"] == "no_tools"
    assert "running normally" not in response["answer"].lower()
    assert "doing well" in response["answer"].lower()


def test_vague_research_prompt_asks_clarifying_question_without_tools(tmp_path: Path) -> None:
    response = answer_question_reasoning(_empty_db(tmp_path), "find funding", llm=_unconfigured_llm())

    assert response["source_mode"] == "no_tools"
    assert response["used_web_fallback"] is False
    assert response["citations"] == []
    assert "funding" in response["answer"].lower()
    assert "?" in response["answer"]


def test_identity_uses_venture_metrics_without_institutional_label(tmp_path: Path) -> None:
    response = answer_question_reasoning(_empty_db(tmp_path), "who are you?", llm=_unconfigured_llm())

    assert response["source_mode"] == "no_tools"
    assert "Venture Metrics" in response["answer"]
    assert "HKU" not in response["answer"]
    assert "TEA" not in response["answer"]
