"""Runnable architecture adapters for comparison mode."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from venture_metrics_agent.architectures.base import (
    ArchitectureMetadata,
    ArchitectureOptions,
    ArchitectureResult,
    normalize_response,
    timed_response,
)
from venture_metrics_agent.architectures.helpers import (
    confidence_from_evidence,
    direct_route_response,
    maybe_remember_web,
    merge_internal_results,
    missing_dimensions,
    query_variants,
    route_payload,
    should_use_web_for_coverage,
    source_mode,
    synthesize_extractive,
)
from venture_metrics_agent.llm.provider import LLMProvider
from venture_metrics_agent.retrieval.agent import QueryOptions, answer_question
from venture_metrics_agent.retrieval.evidence_scorer import assess_evidence
from venture_metrics_agent.retrieval.retriever import retrieve_internal_evidence
from venture_metrics_agent.reasoning import ReasoningOptions, answer_question_reasoning
from venture_metrics_agent.reasoning.tools import ReasoningToolbox
from venture_metrics_agent.reasoning.verifier import verify_evidence


class LinearRAGAdapter:
    metadata = ArchitectureMetadata(
        id="linear_rag",
        label="Linear RAG Baseline",
        family="RAG",
        status="implemented_baseline",
        description="Original retrieve-score-answer pipeline with optional web fallback.",
        strengths=["Simple", "Fast", "Good baseline for internal source questions"],
        limitations=["No planning", "Weak coverage checks", "Can sound like a search-results formatter"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        response = answer_question(
            db_path,
            question,
            options=QueryOptions(top_k=options.top_k, use_web_fallback=options.use_web_fallback),
            llm=llm,
            chat_history=chat_history,
            telemetry_session_id=telemetry_session_id,
        )
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))


class DeterministicControllerAdapter:
    metadata = ArchitectureMetadata(
        id="deterministic_controller",
        label="Current Deterministic Controller",
        family="RLM-inspired workflow",
        status="implemented_current",
        description="Current route-plan-act-observe-verify controller. Python chooses tools deterministically.",
        strengths=["Handles casual chat", "Structured trace", "Rejects weak chunks"],
        limitations=["Not true ReAct", "Not full RLM", "Web fallback is still too conservative"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        response = answer_question_reasoning(
            db_path,
            question,
            options=ReasoningOptions(
                top_k=options.top_k,
                use_web_fallback=options.use_web_fallback,
                max_web_results=options.max_web_results,
                max_internal_iterations=min(options.max_iterations, 3),
                remember_web_results=options.remember_web_results,
            ),
            llm=llm,
            chat_history=chat_history,
            telemetry_session_id=telemetry_session_id,
        )
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))


class CoverageRAGAdapter:
    metadata = ArchitectureMetadata(
        id="coverage_rag",
        label="Corrective Coverage RAG",
        family="CRAG-inspired",
        status="experimental",
        description="Retrieves internal evidence, verifies answer coverage, and escalates to web when dimensions are missing.",
        strengths=["Directly targets partial-answer failures", "Better for current/comparison questions"],
        limitations=["Coverage rules are deterministic", "Web path still depends on search adapter quality"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        direct = direct_route_response(
            question,
            llm=llm,
            chat_history=chat_history,
            use_web_fallback=options.use_web_fallback,
        )
        if direct:
            return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(direct), tool_calls=0)

        toolbox = ReasoningToolbox(db_path)
        trace: list[dict[str, Any]] = []
        route = route_payload(question, use_web_fallback=options.use_web_fallback)
        trace.append({"phase": "route", "decision": route["intent"], "observation": route})
        trace.append({"phase": "plan", "decision": "coverage_rag", "reason": "Retrieve internally, then check answer coverage."})

        internal = toolbox.internal_search(question, top_k=options.top_k)
        verified = verify_evidence(question, internal.results, internal.assessment)
        trace.append(
            {
                "phase": "act",
                "decision": "internal_search",
                "tool": "internal_search",
                "observation": internal.summary(),
            }
        )
        trace.append({"phase": "verify", "decision": "coverage_check", "observation": verified.summary()})

        web_results = []
        should_web, missing = should_use_web_for_coverage(
            question,
            internal.assessment,
            verified,
            web_allowed=options.use_web_fallback,
        )
        if should_web:
            web = toolbox.web_search(question, max_results=options.max_web_results)
            web_results = web.results
            trace.append(
                {
                    "phase": "act",
                    "decision": "web_search_for_missing_coverage",
                    "tool": "web_search",
                    "observation": web.summary(),
                }
            )
            maybe_remember_web(db_path, question, web_results, enabled=options.remember_web_results, trace=trace)
        else:
            trace.append({"phase": "act", "decision": "skip_web_search", "tool": "web_search", "observation": {"missing": missing}})

        confidence = confidence_from_evidence(internal.assessment, verified, web_results)
        gaps = [*verified.missing_information]
        if missing:
            gaps.append("Missing or weak answer coverage: " + ", ".join(missing))
        response = synthesize_extractive(
            question,
            verified.accepted_internal,
            web_results,
            confidence=confidence,
            source_mode=source_mode(verified.accepted_internal, web_results),
            gaps=gaps,
            trace=trace,
        )
        if should_web:
            response["used_web_fallback"] = True
        response["route"] = route
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))


class PlanExecuteAdapter:
    metadata = ArchitectureMetadata(
        id="plan_execute",
        label="Plan-and-Execute Research",
        family="agent workflow",
        status="experimental",
        description="Decomposes the question into search variants, runs focused internal searches, then validates merged coverage.",
        strengths=["Better for comparisons and multi-part questions", "Traceable sub-searches"],
        limitations=["Planner is deterministic in this prototype", "Can spend more retrieval calls"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        direct = direct_route_response(
            question,
            llm=llm,
            chat_history=chat_history,
            use_web_fallback=options.use_web_fallback,
        )
        if direct:
            return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(direct), tool_calls=0)

        toolbox = ReasoningToolbox(db_path)
        trace: list[dict[str, Any]] = []
        route = route_payload(question, use_web_fallback=options.use_web_fallback)
        queries = query_variants(question, max_queries=options.max_iterations)
        trace.append({"phase": "route", "decision": route["intent"], "observation": route})
        trace.append({"phase": "plan", "decision": "decompose_query", "observation": {"queries": queries}})

        observations = []
        for query in queries:
            observation = toolbox.internal_search(query, top_k=max(3, options.top_k // 2))
            observations.append(observation)
            trace.append(
                {
                    "phase": "act",
                    "decision": "execute_subquery",
                    "tool": "internal_search",
                    "observation": {"query": query, **observation.summary()},
                }
            )

        merged = merge_internal_results([observation.results for observation in observations], limit=options.top_k)
        assessment = assess_evidence(question, merged)
        verified = verify_evidence(question, merged, assessment)
        missing = missing_dimensions(question, verified.accepted_internal)
        trace.append({"phase": "verify", "decision": "merged_coverage_check", "observation": {**verified.summary(), "missing": missing}})

        web_results = []
        used_web = False
        if options.use_web_fallback and (verified.needs_more_evidence or missing):
            used_web = True
            web = toolbox.web_search(question, max_results=options.max_web_results)
            web_results = web.results
            trace.append({"phase": "act", "decision": "web_search_after_plan", "tool": "web_search", "observation": web.summary()})
            maybe_remember_web(db_path, question, web_results, enabled=options.remember_web_results, trace=trace)

        confidence = confidence_from_evidence(assessment, verified, web_results)
        gaps = [*verified.missing_information]
        if missing:
            gaps.append("Plan execution did not cover: " + ", ".join(missing))
        response = synthesize_extractive(
            question,
            verified.accepted_internal,
            web_results,
            confidence=confidence,
            source_mode=source_mode(verified.accepted_internal, web_results),
            gaps=gaps,
            trace=trace,
        )
        if used_web:
            response["used_web_fallback"] = True
        response["route"] = route
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))


class ReActLoopAdapter:
    metadata = ArchitectureMetadata(
        id="react_loop",
        label="ReAct-Style Tool Loop",
        family="ReAct-inspired",
        status="experimental",
        description="A bounded Thought/Action/Observation-style loop using internal search and web search tools.",
        strengths=["Good meeting comparison for tool-loop behavior", "Useful for follow-up research turns"],
        limitations=["Prototype is deterministic, not a true LLM-driven ReAct loop"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        direct = direct_route_response(
            question,
            llm=llm,
            chat_history=chat_history,
            use_web_fallback=options.use_web_fallback,
        )
        if direct:
            return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(direct), tool_calls=0)

        toolbox = ReasoningToolbox(db_path)
        route = route_payload(question, use_web_fallback=options.use_web_fallback)
        trace: list[dict[str, Any]] = [
            {"phase": "route", "decision": route["intent"], "observation": route},
            {"phase": "thought", "decision": "need_observation", "reason": "Start with internal evidence before answering."}
        ]
        internal = toolbox.internal_search(question, top_k=options.top_k)
        verified = verify_evidence(question, internal.results, internal.assessment)
        trace.append({"phase": "action", "decision": "search_internal", "tool": "internal_search", "observation": internal.summary()})
        trace.append({"phase": "observation", "decision": "assess_internal", "observation": verified.summary()})

        web_results = []
        should_web, missing = should_use_web_for_coverage(
            question,
            internal.assessment,
            verified,
            web_allowed=options.use_web_fallback,
        )
        if should_web:
            trace.append(
                {
                    "phase": "thought",
                    "decision": "need_external_observation",
                    "reason": "Internal evidence is incomplete or the question needs freshness.",
                    "observation": {"missing": missing},
                }
            )
            web = toolbox.web_search(question, max_results=options.max_web_results)
            web_results = web.results
            trace.append({"phase": "action", "decision": "search_web", "tool": "web_search", "observation": web.summary()})
            maybe_remember_web(db_path, question, web_results, enabled=options.remember_web_results, trace=trace)
        trace.append({"phase": "thought", "decision": "finalize", "reason": "Stop after bounded tool observations and synthesize."})

        confidence = confidence_from_evidence(internal.assessment, verified, web_results)
        response = synthesize_extractive(
            question,
            verified.accepted_internal,
            web_results,
            confidence=confidence,
            source_mode=source_mode(verified.accepted_internal, web_results),
            gaps=[*verified.missing_information, *(["Missing coverage: " + ", ".join(missing)] if missing else [])],
            trace=trace,
        )
        if should_web:
            response["used_web_fallback"] = True
        response["route"] = route
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))


class CAGPackAdapter:
    metadata = ArchitectureMetadata(
        id="cag_pack",
        label="CAG Source Pack",
        family="CAG-inspired",
        status="experimental",
        description="Uses a larger curated evidence pack in one context-style answer path instead of iterative web/tool loops.",
        strengths=["Simple comparison for long-context/source-pack behavior", "No web dependency"],
        limitations=["Not true KV-cache CAG", "Still uses retrieval to build the prototype source pack"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        direct = direct_route_response(
            question,
            llm=llm,
            chat_history=chat_history,
            use_web_fallback=options.use_web_fallback,
        )
        if direct:
            return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(direct), tool_calls=0)

        results = retrieve_internal_evidence(db_path, question, top_k=max(options.top_k, 12))
        assessment = assess_evidence(question, results)
        verified = verify_evidence(question, results, assessment)
        route = route_payload(question, use_web_fallback=options.use_web_fallback)
        trace = [
            {
                "phase": "route",
                "decision": route["intent"],
                "observation": route,
            },
            {
                "phase": "act",
                "decision": "load_cag_source_pack",
                "tool": "internal_search",
                "observation": {"candidate_count": len(results), "accepted_count": len(verified.accepted_internal)},
            }
        ]
        response = synthesize_extractive(
            question,
            verified.accepted_internal[: options.top_k],
            [],
            confidence=verified.confidence,
            source_mode=source_mode(verified.accepted_internal, []),
            gaps=verified.missing_information,
            trace=trace,
        )
        response["route"] = route
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))


class RLMExperimentAdapter:
    metadata = ArchitectureMetadata(
        id="rlm_experiment",
        label="RLM-Inspired Worker Experiment",
        family="RLM-inspired",
        status="research_experiment",
        description="Simulates recursive workers by running focused read-only searches and aggregating their findings.",
        strengths=["Useful bridge toward a true Recursive Language Model harness", "Makes worker findings inspectable"],
        limitations=["Not full RLM: no persistent REPL and no model-written code execution"],
    )

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        started = time.perf_counter()
        direct = direct_route_response(
            question,
            llm=llm,
            chat_history=chat_history,
            use_web_fallback=options.use_web_fallback,
        )
        if direct:
            return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(direct), tool_calls=0)

        toolbox = ReasoningToolbox(db_path)
        workers = query_variants(question, max_queries=options.max_iterations)
        route = route_payload(question, use_web_fallback=options.use_web_fallback)
        trace: list[dict[str, Any]] = [
            {"phase": "route", "decision": route["intent"], "observation": route},
            {"phase": "root", "decision": "spawn_read_only_workers", "observation": {"workers": workers}},
        ]
        worker_results = []
        for index, worker_query in enumerate(workers, start=1):
            observation = toolbox.internal_search(worker_query, top_k=max(2, options.top_k // 3))
            worker_results.append(observation.results)
            trace.append(
                {
                    "phase": "worker",
                    "decision": "inspect_slice",
                    "tool": "internal_search",
                    "observation": {"worker": index, "query": worker_query, **observation.summary()},
                }
            )
        merged = merge_internal_results(worker_results, limit=options.top_k)
        assessment = assess_evidence(question, merged)
        verified = verify_evidence(question, merged, assessment)
        missing = missing_dimensions(question, verified.accepted_internal)
        trace.append({"phase": "root", "decision": "aggregate_worker_findings", "observation": {**verified.summary(), "missing": missing}})

        web_results = []
        used_web = False
        if options.use_web_fallback and (verified.needs_more_evidence or missing):
            used_web = True
            web = toolbox.web_search(question, max_results=options.max_web_results)
            web_results = web.results
            trace.append({"phase": "root", "decision": "external_worker_search", "tool": "web_search", "observation": web.summary()})
            maybe_remember_web(db_path, question, web_results, enabled=options.remember_web_results, trace=trace)

        response = synthesize_extractive(
            question,
            verified.accepted_internal,
            web_results,
            confidence=confidence_from_evidence(assessment, verified, web_results),
            source_mode=source_mode(verified.accepted_internal, web_results),
            gaps=[*verified.missing_information, *(["Worker coverage missing: " + ", ".join(missing)] if missing else [])],
            trace=trace,
        )
        if used_web:
            response["used_web_fallback"] = True
        response["route"] = route
        return timed_response(self.metadata.id, self.metadata.label, started, normalize_response(response))
