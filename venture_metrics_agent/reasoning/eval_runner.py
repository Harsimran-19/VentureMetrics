"""Evaluation harness for comparing the legacy agent and reasoning controller."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from venture_metrics_agent.llm.provider import LLMConfig, LLMProvider
from venture_metrics_agent.retrieval.agent import QueryOptions, answer_question
from venture_metrics_agent.retrieval.web_search import WebResult
from venture_metrics_agent.reasoning.controller import ReasoningOptions, answer_question_reasoning
from venture_metrics_agent.reasoning.tools import ReasoningToolbox, WebSearchObservation


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_intent: str | None = None
    expected_source_mode: str | None = None
    expect_web_used: bool | None = None
    min_citations: int | None = None
    max_citations: int | None = None
    must_have_decision: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class EvalOptions:
    top_k: int = 8
    use_web_fallback: bool = True
    simulate_web: bool = True
    include_legacy: bool = True


DEFAULT_EVAL_CASES = [
    EvalCase(
        id="casual_hi",
        question="hi",
        expected_intent="casual_chat",
        expected_source_mode="no_tools",
        expect_web_used=False,
        max_citations=0,
        notes="A greeting must not retrieve or search.",
    ),
    EvalCase(
        id="system_help",
        question="What can you do?",
        expected_intent="system_help",
        expected_source_mode="no_tools",
        expect_web_used=False,
        max_citations=0,
        notes="Capability questions should not touch evidence tools.",
    ),
    EvalCase(
        id="internal_hk_support",
        question="Which sources are related to Hong Kong entrepreneurship support?",
        expected_intent="internal_research",
        expected_source_mode="internal_only",
        expect_web_used=False,
        min_citations=1,
        notes="Should be answerable from indexed university/source evidence.",
    ),
    EvalCase(
        id="current_hk_grants",
        question="What are the latest Hong Kong startup grants?",
        expected_intent="current_research",
        expect_web_used=True,
        min_citations=1,
        must_have_decision="use_web_search",
        notes="Current/latest questions should allow controlled web use.",
    ),
    EvalCase(
        id="vague",
        question="research this",
        expected_intent="clarification_needed",
        expected_source_mode="insufficient",
        expect_web_used=False,
        max_citations=0,
        notes="Vague research requests should ask for clarification.",
    ),
]


class SimulatedWebToolbox(ReasoningToolbox):
    def __init__(self, db_path: str | Path) -> None:
        super().__init__(db_path)
        self.web_queries: list[str] = []

    def web_search(self, query: str, *, max_results: int = 4) -> WebSearchObservation:
        self.web_queries.append(query)
        return WebSearchObservation(
            results=[
                WebResult(
                    title="Simulated official Hong Kong startup grant source",
                    url="https://www.gov.hk/en/theme/business/startup-grants",
                    content=(
                        "A simulated official public source describes current Hong Kong startup grants, "
                        "funding programmes, application support, eligibility, and public-sector startup resources."
                    ),
                    score=0.99,
                )
            ][:max_results]
        )


def run_eval_suite(
    db_path: str | Path,
    *,
    cases: list[EvalCase] | None = None,
    options: EvalOptions | None = None,
) -> dict[str, Any]:
    cases = cases or DEFAULT_EVAL_CASES
    options = options or EvalOptions()
    llm = LLMProvider(LLMConfig(api_key=None))

    with tempfile.TemporaryDirectory(prefix="venture_metrics_eval_") as tmpdir:
        working_db = Path(tmpdir) / "eval.db"
        shutil.copy2(db_path, working_db)

        results = []
        for case in cases:
            toolbox = SimulatedWebToolbox(working_db) if options.simulate_web else None
            reasoning = answer_question_reasoning(
                working_db,
                case.question,
                options=ReasoningOptions(
                    top_k=options.top_k,
                    use_web_fallback=options.use_web_fallback,
                    remember_web_results=False,
                ),
                llm=llm,
                toolbox=toolbox,
            )
            legacy = None
            if options.include_legacy:
                legacy = answer_question(
                    working_db,
                    case.question,
                    options=QueryOptions(top_k=options.top_k, use_web_fallback=False),
                    llm=llm,
                )
            results.append(_score_case(case, reasoning, legacy))

    passed = sum(1 for result in results if result["passed"])
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": passed / len(results) if results else 0.0,
            "reasoning_web_used_count": sum(1 for result in results if result["reasoning"]["used_web_fallback"]),
            "reasoning_no_tool_count": sum(1 for result in results if result["reasoning"]["source_mode"] == "no_tools"),
        },
        "results": results,
    }


def _score_case(case: EvalCase, reasoning: dict[str, Any], legacy: dict[str, Any] | None) -> dict[str, Any]:
    checks = []
    route = reasoning.get("route") or {}
    trace = reasoning.get("reasoning_trace") or []
    decisions = [step.get("decision") for step in trace if isinstance(step, dict)]
    citations = reasoning.get("citations") or []

    if case.expected_intent is not None:
        checks.append(_check("intent", route.get("intent") == case.expected_intent, route.get("intent"), case.expected_intent))
    if case.expected_source_mode is not None:
        checks.append(
            _check("source_mode", reasoning.get("source_mode") == case.expected_source_mode, reasoning.get("source_mode"), case.expected_source_mode)
        )
    if case.expect_web_used is not None:
        checks.append(
            _check("web_used", bool(reasoning.get("used_web_fallback")) is case.expect_web_used, reasoning.get("used_web_fallback"), case.expect_web_used)
        )
    if case.min_citations is not None:
        checks.append(_check("min_citations", len(citations) >= case.min_citations, len(citations), case.min_citations))
    if case.max_citations is not None:
        checks.append(_check("max_citations", len(citations) <= case.max_citations, len(citations), case.max_citations))
    if case.must_have_decision is not None:
        checks.append(_check("decision", case.must_have_decision in decisions, decisions, case.must_have_decision))

    return {
        "id": case.id,
        "question": case.question,
        "notes": case.notes,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "reasoning": _summary(reasoning),
        "legacy": _summary(legacy) if legacy else None,
    }


def _check(name: str, passed: bool, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "actual": actual, "expected": expected}


def _summary(response: dict[str, Any] | None) -> dict[str, Any]:
    if response is None:
        return {}
    trace = response.get("reasoning_trace") or []
    return {
        "confidence": response.get("confidence"),
        "source_mode": response.get("source_mode"),
        "used_web_fallback": bool(response.get("used_web_fallback")),
        "citation_count": len(response.get("citations") or []),
        "rejected_count": len(response.get("rejected_evidence") or []),
        "intent": (response.get("route") or {}).get("intent"),
        "decisions": [step.get("decision") for step in trace if isinstance(step, dict)],
    }


def eval_cases_from_json(path: str | Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalCase(**item) for item in raw]
