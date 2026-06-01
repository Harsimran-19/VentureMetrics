"""SQLite-backed telemetry for agent runs, traces, retrieval, and evals."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venture_metrics_agent.observability.langfuse_sink import export_agent_response_to_langfuse


@dataclass(frozen=True)
class TelemetryRecord:
    session_id: int
    run_id: int
    question_message_id: int
    answer_message_id: int


@dataclass(frozen=True)
class EvalTelemetryRecord:
    eval_run_id: int
    eval_result_count: int


def init_observability_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_observability_tables(conn)
    return conn


def create_observability_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            confidence TEXT NOT NULL,
            source_mode TEXT NOT NULL,
            used_web_fallback INTEGER NOT NULL DEFAULT 0,
            citations_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT NOT NULL UNIQUE,
            title TEXT,
            user_label TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_message_id INTEGER,
            answer_message_id INTEGER,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            confidence TEXT NOT NULL,
            source_mode TEXT NOT NULL,
            used_web_fallback INTEGER NOT NULL DEFAULT 0,
            model_name TEXT,
            provider_name TEXT,
            error_message TEXT,
            route_json TEXT NOT NULL DEFAULT '{}',
            trace_json TEXT NOT NULL DEFAULT '[]',
            gaps_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(id),
            FOREIGN KEY(question_message_id) REFERENCES chat_messages(id),
            FOREIGN KEY(answer_message_id) REFERENCES chat_messages(id)
        );

        CREATE TABLE IF NOT EXISTS agent_run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            phase TEXT,
            decision TEXT,
            reason TEXT,
            tool TEXT,
            observation_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES agent_runs(id)
        );

        CREATE TABLE IF NOT EXISTS retrieval_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            query TEXT NOT NULL,
            top_k INTEGER,
            result_count INTEGER NOT NULL,
            assessment_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES agent_runs(id)
        );

        CREATE TABLE IF NOT EXISTS retrieval_event_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            source_id INTEGER,
            chunk_id INTEGER,
            title TEXT,
            url TEXT,
            source_type TEXT,
            reliability TEXT,
            score REAL,
            snippet TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(event_id) REFERENCES retrieval_events(id)
        );

        CREATE TABLE IF NOT EXISTS answer_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            citation_index INTEGER NOT NULL,
            title TEXT,
            url TEXT,
            source_type TEXT,
            reliability TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(run_id) REFERENCES agent_runs(id)
        );

        CREATE TABLE IF NOT EXISTS user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            rating INTEGER,
            label TEXT,
            comment TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES agent_runs(id)
        );

        CREATE TABLE IF NOT EXISTS eval_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            question TEXT NOT NULL,
            expected_behavior TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS eval_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eval_run_id INTEGER NOT NULL,
            eval_case_id INTEGER,
            agent_run_id INTEGER,
            score REAL,
            passed INTEGER,
            label TEXT,
            reason TEXT,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(eval_run_id) REFERENCES eval_runs(id),
            FOREIGN KEY(eval_case_id) REFERENCES eval_cases(id),
            FOREIGN KEY(agent_run_id) REFERENCES agent_runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run_id ON agent_run_steps(run_id);
        CREATE INDEX IF NOT EXISTS idx_retrieval_events_run_id ON retrieval_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_retrieval_event_results_event_id ON retrieval_event_results(event_id);
        CREATE INDEX IF NOT EXISTS idx_answer_citations_run_id ON answer_citations(run_id);
        CREATE INDEX IF NOT EXISTS idx_eval_results_eval_run_id ON eval_results(eval_run_id);
        """
    )
    conn.commit()


def record_agent_response(
    db_path: str | Path,
    question: str,
    response: dict[str, Any],
    *,
    agent_name: str,
    session_external_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TelemetryRecord:
    conn = init_observability_db(db_path)
    try:
        record = _record_agent_response(
            conn,
            question,
            response,
            agent_name=agent_name,
            session_external_id=session_external_id,
            metadata=metadata or {},
        )
        conn.commit()
    finally:
        conn.close()
    export_agent_response_to_langfuse(
        question,
        response,
        agent_name=agent_name,
        session_external_id=session_external_id,
        local_run_id=record.run_id,
        metadata=metadata or {},
    )
    return record


def record_eval_report(
    db_path: str | Path,
    report: dict[str, Any],
    *,
    name: str,
    agent_name: str,
    config: dict[str, Any] | None = None,
) -> EvalTelemetryRecord:
    conn = init_observability_db(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO eval_runs (name, agent_name, status, config_json, completed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (name, agent_name, "completed", _json(config or {})),
        )
        eval_run_id = int(cursor.lastrowid)
        count = 0
        for result in _as_list(report.get("results")):
            if not isinstance(result, dict):
                continue
            eval_case_id = _insert_eval_case(conn, result)
            metrics = {
                "checks": _as_list(result.get("checks")),
                "reasoning": result.get("reasoning") or {},
                "legacy": result.get("legacy") or {},
            }
            conn.execute(
                """
                INSERT INTO eval_results (
                    eval_run_id,
                    eval_case_id,
                    score,
                    passed,
                    label,
                    reason,
                    metrics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_run_id,
                    eval_case_id,
                    1.0 if result.get("passed") else 0.0,
                    1 if result.get("passed") else 0,
                    str(result.get("id") or "eval_case"),
                    _eval_reason(result),
                    _json(metrics),
                ),
            )
            count += 1
        conn.commit()
        return EvalTelemetryRecord(eval_run_id=eval_run_id, eval_result_count=count)
    finally:
        conn.close()


def _record_agent_response(
    conn: sqlite3.Connection,
    question: str,
    response: dict[str, Any],
    *,
    agent_name: str,
    session_external_id: str | None,
    metadata: dict[str, Any],
) -> TelemetryRecord:
    answer = str(response.get("answer") or "")
    confidence = str(response.get("confidence") or "Insufficient evidence")
    source_mode = str(response.get("source_mode") or "insufficient")
    used_web_fallback = 1 if response.get("used_web_fallback") else 0
    citations = _as_list(response.get("citations"))
    gaps = _as_list(response.get("gaps"))
    trace = _as_list(response.get("reasoning_trace"))

    conn.execute(
        """
        INSERT INTO query_logs (
            question,
            answer,
            confidence,
            source_mode,
            used_web_fallback,
            citations_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (question, answer, confidence, source_mode, used_web_fallback, _json(citations)),
    )

    session_id = _ensure_session(conn, session_external_id=session_external_id, question=question, metadata=metadata)
    question_message_id = _insert_message(conn, session_id, "user", question, {"agent_name": agent_name})
    answer_message_id = _insert_message(
        conn,
        session_id,
        "assistant",
        answer,
        {
            "agent_name": agent_name,
            "confidence": confidence,
            "source_mode": source_mode,
        },
    )

    cursor = conn.execute(
        """
        INSERT INTO agent_runs (
            session_id,
            question_message_id,
            answer_message_id,
            agent_name,
            status,
            question,
            answer,
            confidence,
            source_mode,
            used_web_fallback,
            model_name,
            provider_name,
            error_message,
            route_json,
            trace_json,
            gaps_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            question_message_id,
            answer_message_id,
            agent_name,
            "completed",
            question,
            answer,
            confidence,
            source_mode,
            used_web_fallback,
            _nullable_str(metadata.get("model_name")),
            _nullable_str(metadata.get("provider_name")),
            _nullable_str(metadata.get("error_message")),
            _json(response.get("route") or {}),
            _json(trace),
            _json(gaps),
            _json(metadata),
        ),
    )
    run_id = int(cursor.lastrowid)

    _insert_steps(conn, run_id, trace)
    _insert_retrieval_event(
        conn,
        run_id,
        event_type="internal",
        query=question,
        results=_as_list(response.get("retrieved_evidence")),
        assessment={"rejected_evidence": _as_list(response.get("rejected_evidence"))},
    )
    _insert_retrieval_event(
        conn,
        run_id,
        event_type="web",
        query=question,
        results=_as_list(response.get("web_evidence")),
        assessment={"used_web_fallback": bool(response.get("used_web_fallback"))},
    )
    _insert_citations(conn, run_id, citations)

    return TelemetryRecord(
        session_id=session_id,
        run_id=run_id,
        question_message_id=question_message_id,
        answer_message_id=answer_message_id,
    )


def _ensure_session(
    conn: sqlite3.Connection,
    *,
    session_external_id: str | None,
    question: str,
    metadata: dict[str, Any],
) -> int:
    external_id = session_external_id or f"local-{uuid.uuid4().hex}"
    title = _session_title(question)
    conn.execute(
        """
        INSERT INTO chat_sessions (external_id, title, metadata_json)
        VALUES (?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            updated_at = CURRENT_TIMESTAMP
        """,
        (external_id, title, _json(metadata.get("session_metadata") or {})),
    )
    row = conn.execute("SELECT id FROM chat_sessions WHERE external_id = ?", (external_id,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to create or load telemetry session.")
    return int(row[0])


def _insert_message(
    conn: sqlite3.Connection,
    session_id: int,
    role: str,
    content: str,
    metadata: dict[str, Any],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO chat_messages (session_id, role, content, metadata_json)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, role, content, _json(metadata)),
    )
    return int(cursor.lastrowid)


def _insert_steps(conn: sqlite3.Connection, run_id: int, trace: list[Any]) -> None:
    for index, step in enumerate(trace, start=1):
        if not isinstance(step, dict):
            continue
        conn.execute(
            """
            INSERT INTO agent_run_steps (
                run_id,
                step_index,
                phase,
                decision,
                reason,
                tool,
                observation_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                _nullable_str(step.get("phase")),
                _nullable_str(step.get("decision")),
                _nullable_str(step.get("reason")),
                _nullable_str(step.get("tool")),
                _json(step.get("observation") or {}),
            ),
        )


def _insert_retrieval_event(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    event_type: str,
    query: str,
    results: list[Any],
    assessment: dict[str, Any],
) -> None:
    if not results and event_type == "internal":
        assessment = {**assessment, "result_count": 0}
    elif not results and event_type == "web":
        assessment = {**assessment, "result_count": 0}

    cursor = conn.execute(
        """
        INSERT INTO retrieval_events (
            run_id,
            event_type,
            query,
            top_k,
            result_count,
            assessment_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, event_type, query, len(results) or None, len(results), _json(assessment)),
    )
    event_id = int(cursor.lastrowid)

    for rank, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        conn.execute(
            """
            INSERT INTO retrieval_event_results (
                event_id,
                rank,
                source_id,
                chunk_id,
                title,
                url,
                source_type,
                reliability,
                score,
                snippet,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                rank,
                _nullable_int(result.get("source_id")),
                _nullable_int(result.get("chunk_id")),
                _nullable_str(result.get("title")),
                _nullable_str(result.get("url")),
                _nullable_str(result.get("source_type")),
                _nullable_str(result.get("reliability")),
                _nullable_float(result.get("score")),
                _nullable_str(result.get("snippet")),
                _json(_metadata_without_known_result_fields(result)),
            ),
        )


def _insert_citations(conn: sqlite3.Connection, run_id: int, citations: list[Any]) -> None:
    for index, citation in enumerate(citations, start=1):
        if not isinstance(citation, dict):
            continue
        conn.execute(
            """
            INSERT INTO answer_citations (
                run_id,
                citation_index,
                title,
                url,
                source_type,
                reliability,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                _nullable_str(citation.get("title")),
                _nullable_str(citation.get("url")),
                _nullable_str(citation.get("source_type")),
                _nullable_str(citation.get("reliability")),
                _json(_metadata_without_known_result_fields(citation)),
            ),
        )


def _metadata_without_known_result_fields(payload: dict[str, Any]) -> dict[str, Any]:
    known = {
        "source_id",
        "chunk_id",
        "title",
        "url",
        "source_type",
        "reliability",
        "score",
        "snippet",
    }
    return {key: value for key, value in payload.items() if key not in known}


def _insert_eval_case(conn: sqlite3.Connection, result: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eval_cases (name, question, expected_behavior, tags_json, metadata_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(result.get("id") or "eval_case"),
            str(result.get("question") or ""),
            _nullable_str(result.get("notes")),
            _json([]),
            _json({"checks": _as_list(result.get("checks"))}),
        ),
    )
    return int(cursor.lastrowid)


def _eval_reason(result: dict[str, Any]) -> str:
    failed_checks = [
        check
        for check in _as_list(result.get("checks"))
        if isinstance(check, dict) and not check.get("passed")
    ]
    if not failed_checks:
        return "All deterministic checks passed."
    names = ", ".join(str(check.get("name")) for check in failed_checks)
    return f"Failed checks: {names}"


def _session_title(question: str) -> str:
    normalized = " ".join(question.split())
    if len(normalized) <= 80:
        return normalized
    return normalized[:77].rstrip() + "..."


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _nullable_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _nullable_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
