from __future__ import annotations

import json
import sqlite3
import sys
from types import SimpleNamespace
from pathlib import Path

from venture_metrics_agent.observability import (
    LangfuseConfig,
    langfuse_status,
    load_langfuse_config,
    record_agent_response,
    record_eval_report,
)
from venture_metrics_agent.observability.langfuse_sink import (
    _langfuse_session_id,
    export_agent_response_to_langfuse,
)


def test_record_agent_response_persists_run_trace_evidence_and_citations(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    response = {
        "answer": "Supported answer.",
        "confidence": "Medium",
        "source_mode": "internal_only",
        "used_web_fallback": False,
        "citations": [
            {
                "title": "Grant page",
                "url": "https://example.edu/grants",
                "source_type": "university",
                "reliability": "high",
            }
        ],
        "gaps": ["One data gap."],
        "retrieved_evidence": [
            {
                "chunk_id": 10,
                "source_id": 7,
                "title": "Grant page",
                "url": "https://example.edu/grants",
                "source_type": "university",
                "reliability": "high",
                "score": 4.2,
                "snippet": "Startup grant evidence.",
            }
        ],
        "web_evidence": [],
        "route": {"intent": "internal_research"},
        "reasoning_trace": [
            {
                "phase": "route",
                "decision": "internal_research",
                "reason": "Question needs local evidence.",
                "tool": None,
                "observation": {"intent": "internal_research"},
            }
        ],
    }

    record = record_agent_response(
        db_path,
        "Which sources mention grants?",
        response,
        agent_name="reasoning_agent",
        session_external_id="test-session",
    )

    conn = sqlite3.connect(db_path)
    try:
        assert _count(conn, "query_logs") == 1
        assert _count(conn, "chat_sessions") == 1
        assert _count(conn, "chat_messages") == 2
        assert _count(conn, "agent_runs") == 1
        assert _count(conn, "agent_run_steps") == 1
        assert _count(conn, "retrieval_events") == 2
        assert _count(conn, "retrieval_event_results") == 1
        assert _count(conn, "answer_citations") == 1

        row = conn.execute(
            "SELECT agent_name, confidence, source_mode, route_json, gaps_json FROM agent_runs WHERE id = ?",
            (record.run_id,),
        ).fetchone()
        assert row[0] == "reasoning_agent"
        assert row[1] == "Medium"
        assert row[2] == "internal_only"
        assert json.loads(row[3]) == {"intent": "internal_research"}
        assert json.loads(row[4]) == ["One data gap."]
    finally:
        conn.close()


def test_record_eval_report_persists_eval_run_cases_and_results(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    report = {
        "summary": {"total": 2, "passed": 1, "failed": 1},
        "results": [
            {
                "id": "casual_hi",
                "question": "hi",
                "notes": "Greeting should not use tools.",
                "passed": True,
                "checks": [{"name": "source_mode", "passed": True}],
                "reasoning": {"source_mode": "no_tools"},
                "legacy": None,
            },
            {
                "id": "current_grants",
                "question": "What are the latest grants?",
                "notes": "Current questions should use web.",
                "passed": False,
                "checks": [{"name": "web_used", "passed": False}],
                "reasoning": {"source_mode": "internal_only"},
                "legacy": None,
            },
        ],
    }

    record = record_eval_report(
        db_path,
        report,
        name="reasoning_eval",
        agent_name="reasoning_agent",
        config={"simulate_web": True},
    )

    conn = sqlite3.connect(db_path)
    try:
        assert record.eval_result_count == 2
        assert _count(conn, "eval_runs") == 1
        assert _count(conn, "eval_cases") == 2
        assert _count(conn, "eval_results") == 2
        row = conn.execute(
            "SELECT passed, label, reason FROM eval_results WHERE label = ?",
            ("current_grants",),
        ).fetchone()
        assert row == (0, "current_grants", "Failed checks: web_used")
    finally:
        conn.close()


def test_load_langfuse_config_reads_optional_env_file(tmp_path: Path, monkeypatch) -> None:
    for key in (
        "LANGFUSE_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_ENVIRONMENT",
        "LANGFUSE_RELEASE",
        "LANGFUSE_SAMPLE_RATE",
    ):
        monkeypatch.delenv(key, raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LANGFUSE_ENABLED=true",
                "LANGFUSE_PUBLIC_KEY=pk-test",
                "LANGFUSE_SECRET_KEY=sk-test",
                "LANGFUSE_BASE_URL=https://langfuse.example.com",
                "LANGFUSE_ENVIRONMENT=test",
                "LANGFUSE_RELEASE=unit",
                "LANGFUSE_SAMPLE_RATE=0.5",
            ]
        ),
        encoding="utf-8",
    )

    config = load_langfuse_config(env_path)
    assert config.is_configured is True
    assert config.base_url == "https://langfuse.example.com"
    assert config.environment == "test"
    assert config.release == "unit"
    assert config.sample_rate == 0.5

    status = langfuse_status(config)
    assert status["enabled"] is True
    assert status["configured"] is True


def test_langfuse_export_propagates_session_id(monkeypatch) -> None:
    fake_module = SimpleNamespace(propagated=[])

    class FakePropagation:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            fake_module.propagated.append(self.kwargs)

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeObservation:
        def __init__(self, client, kwargs):
            self.client = client
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def update(self, **kwargs):
            self.client.observation_updates.append(kwargs)

        def start_as_current_observation(self, **kwargs):
            self.client.child_observations.append(kwargs)
            return FakeObservation(self.client, kwargs)

    class FakeLangfuse:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.root_observations = []
            self.child_observations = []
            self.observation_updates = []
            self.trace_updates = []
            self.flushed = False
            self.__class__.instances.append(self)

        def start_as_current_observation(self, **kwargs):
            self.root_observations.append(kwargs)
            return FakeObservation(self, kwargs)

        def update_current_trace(self, **kwargs):
            self.trace_updates.append(kwargs)

        def flush(self):
            self.flushed = True

    fake_module.Langfuse = FakeLangfuse
    fake_module.propagate_attributes = lambda **kwargs: FakePropagation(**kwargs)
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    export_agent_response_to_langfuse(
        "Which sources mention grants?",
        {
            "answer": "Supported answer.",
            "confidence": "Medium",
            "source_mode": "internal_only",
            "reasoning_trace": [{"phase": "route", "decision": "internal_research"}],
            "retrieved_evidence": [{"title": "Grant page", "url": "https://example.edu/grants"}],
            "citations": [{"title": "Grant page", "url": "https://example.edu/grants"}],
        },
        agent_name="reasoning_agent",
        session_external_id="test-session",
        local_run_id=123,
        config=LangfuseConfig(enabled=True, public_key="pk-test", secret_key="sk-test"),
    )

    client = FakeLangfuse.instances[0]
    assert fake_module.propagated == [{"session_id": "test-session"}]
    assert client.trace_updates[0]["session_id"] == "test-session"
    assert client.root_observations[0]["metadata"]["session_external_id"] == "test-session"
    assert client.child_observations[0]["as_type"] == "span"
    assert client.flushed is True


def test_langfuse_session_id_is_ascii_and_bounded() -> None:
    session_id = _langfuse_session_id(" session-你好-" + ("x" * 220))

    assert session_id is not None
    assert len(session_id) == 200
    assert all(32 <= ord(character) <= 126 for character in session_id)
    assert session_id.startswith("session----")


def _count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])
