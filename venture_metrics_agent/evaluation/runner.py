"""Architecture evaluation mode for Venture Metrics."""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from venture_metrics_agent.architectures import ArchitectureOptions, list_architectures, run_architectures
from venture_metrics_agent.evaluation.rag_dimensions import aggregate_rag_score, evaluate_rag_dimensions, rag_passed
from venture_metrics_agent.evaluation.retrieval_metrics import score_retrieval
from venture_metrics_agent.llm.provider import LLMConfig, LLMProvider


APP_PURPOSE = (
    "Venture Metrics is a cited research assistant for Excel-derived startup, university, "
    "commercialization, policy, funding, incubator, and ecosystem sources. It should search "
    "internal evidence first, use web fallback when coverage is weak/current/external, cite sources, "
    "mark confidence, and state gaps instead of hallucinating."
)


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    category: str
    expected_intent: str | None = None
    expect_web: bool | None = None
    expected_source_mode: str | None = None
    min_citations: int = 0
    required_terms: list[str] = field(default_factory=list)
    relevant_source_ids: list[int] = field(default_factory=list)
    relevant_chunk_ids: list[int] = field(default_factory=list)
    reference_answer: str | None = None
    required_claims: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    unanswerable: bool = False
    severity: str = "medium"
    tags: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class EvalOptions:
    top_k: int = 8
    use_web_fallback: bool = True
    max_web_results: int = 4
    architectures: list[str] = field(default_factory=lambda: ["deterministic_controller", "coverage_rag", "plan_execute"])
    output_dir: str | Path | None = None
    no_llm: bool = True
    rag_threshold: float = 0.65


DEFAULT_CASES = [
    EvalCase(
        id="casual_hi",
        question="hi",
        category="casual",
        expected_intent="casual_chat",
        expect_web=False,
        notes="Normal chat should not become a source-search task.",
    ),
    EvalCase(
        id="casual_social",
        question="how are you?",
        category="casual",
        expected_intent="casual_chat",
        expect_web=False,
        notes="Social chat should stay conversational and source-free.",
    ),
    EvalCase(
        id="system_capability",
        question="What can you do for Venture Metrics?",
        category="capability",
        expected_intent="system_help",
        expect_web=False,
        notes="Capability questions should explain the app, not retrieve sources.",
    ),
    EvalCase(
        id="vague_research",
        question="research this",
        category="clarification",
        expected_intent="clarification_needed",
        expect_web=False,
        notes="Underspecified requests should ask for narrowing details.",
    ),
    EvalCase(
        id="internal_hk_support",
        question="Which sources are related to Hong Kong entrepreneurship support?",
        category="internal_answerable",
        expected_intent="internal_research",
        min_citations=1,
        required_terms=["Hong Kong"],
    ),
    EvalCase(
        id="official_hk_startup_support",
        question="Where can a founder get official startup support in Hong Kong, including government programmes, science parks, and incubators?",
        category="official_sources",
        min_citations=1,
        required_terms=["Hong Kong"],
    ),
    EvalCase(
        id="hk_university_spinouts",
        question="Which Hong Kong universities provide spinout, technology transfer, or incubator support for founders?",
        category="university_commercialization",
        min_citations=1,
        required_terms=["Hong Kong", "university"],
    ),
    EvalCase(
        id="patent_ip_support",
        question="What patent, intellectual property, or commercialization support is available in Hong Kong for startups or university-linked founders?",
        category="commercialization",
        min_citations=1,
        required_terms=["patent", "Hong Kong"],
    ),
    EvalCase(
        id="gba_ecosystem_connectors",
        question="Which associations, alliances, or ecosystem organisations could help a startup build connections across Hong Kong and Shenzhen?",
        category="ecosystem",
        min_citations=1,
        required_terms=["Hong Kong", "Shenzhen"],
    ),
    EvalCase(
        id="startup_hiring_channels",
        question="Which hiring platforms, labour portals, or talent programmes look most relevant for startup recruitment in Hong Kong, the UK, and Canada?",
        category="talent",
        min_citations=1,
        required_terms=["Hong Kong"],
    ),
    EvalCase(
        id="source_library_overview",
        question="What topics are covered in the current Venture Metrics source library?",
        category="source_audit",
        min_citations=1,
        required_terms=["source"],
    ),
    EvalCase(
        id="official_sources_audit",
        question="Which sources appear to be official government, university, science park, or incubator sources?",
        category="source_audit",
        min_citations=1,
        required_terms=["government", "university"],
    ),
    EvalCase(
        id="funding_mentions",
        question="Which sources mention startup funding, grants, funds, or competition-based programmes?",
        category="funding",
        min_citations=1,
        required_terms=["funding"],
    ),
    EvalCase(
        id="latest_hk_grants",
        question="What are the latest Hong Kong startup grants?",
        category="current_web_needed",
        expected_intent="current_research",
        expect_web=True,
        min_citations=1,
        required_terms=["Hong Kong", "grant"],
    ),
    EvalCase(
        id="shenzhen_policy_support",
        question="What do the Shenzhen policy sources say about startup subsidies, talent support, and commercialising research?",
        category="shenzhen_policy",
        min_citations=1,
        required_terms=["Shenzhen"],
    ),
    EvalCase(
        id="hk_shenzhen_compare",
        question="Compare the startup support options mentioned for Hong Kong and Shenzhen, including policy, funding, and ecosystem support.",
        category="comparison",
        min_citations=1,
        required_terms=["Hong Kong", "Shenzhen"],
        notes="Known failure class: partial internal evidence should not block further research.",
    ),
    EvalCase(
        id="mainland_benchmark",
        question="Which mainland university incubators or science parks look most relevant as benchmarks for commercialization and startup support?",
        category="weak_internal_or_web",
        min_citations=1,
        required_terms=["university", "incubator"],
    ),
    EvalCase(
        id="internal_only_request",
        question="What answer can you give from internal Venture Metrics sources only about Hong Kong entrepreneurship support?",
        category="internal_only",
        expected_intent="internal_research",
        expect_web=False,
        min_citations=1,
        required_terms=["Hong Kong"],
    ),
    EvalCase(
        id="outside_corpus_global_latest",
        question="What are the latest startup visa changes in France?",
        category="external_current",
        expected_intent="current_research",
        expect_web=True,
        min_citations=1,
        required_terms=["France"],
    ),
    EvalCase(
        id="data_gaps",
        question="What data gaps exist in the current sample files for comparing Hong Kong and Shenzhen startup support?",
        category="gap_analysis",
        min_citations=1,
        required_terms=["Hong Kong", "Shenzhen"],
    ),
]


def run_architecture_eval(
    db_path: str | Path,
    *,
    cases: list[EvalCase] | None = None,
    options: EvalOptions | None = None,
) -> dict[str, Any]:
    cases = cases or DEFAULT_CASES
    options = options or EvalOptions()
    llm = LLMProvider(LLMConfig(api_key=None)) if options.no_llm else None
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="venture_metrics_arch_eval_") as tmpdir:
        working_db = Path(tmpdir) / "eval.db"
        shutil.copy2(db_path, working_db)

        rows: list[dict[str, Any]] = []
        for case in cases:
            architecture_outputs = run_architectures(
                options.architectures,
                working_db,
                case.question,
                options=ArchitectureOptions(
                    top_k=options.top_k,
                    use_web_fallback=options.use_web_fallback,
                    max_web_results=options.max_web_results,
                    remember_web_results=False,
                ),
                llm=llm,
            )
            for output in architecture_outputs:
                rows.append(_score(case, output, options=options))

    summary = _summary(rows, started)
    report = {
        "purpose": APP_PURPOSE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "options": {
            "top_k": options.top_k,
            "use_web_fallback": options.use_web_fallback,
            "max_web_results": options.max_web_results,
            "architectures": options.architectures,
            "no_llm": options.no_llm,
            "rag_threshold": options.rag_threshold,
        },
        "summary": summary,
        "architectures": list_architectures(),
        "cases": [case.__dict__ for case in cases],
        "results": rows,
    }
    if options.output_dir:
        _write_report(report, Path(options.output_dir))
    return report


def eval_cases_from_json(path: str | Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalCase(**item) for item in raw]


def _score(case: EvalCase, output: dict[str, Any], *, options: EvalOptions) -> dict[str, Any]:
    answer = str(output.get("answer") or "")
    citations = output.get("citations") or []
    route = output.get("route") or {}
    checks = []
    if case.expected_intent is not None:
        checks.append(_check("intent", route.get("intent") == case.expected_intent, route.get("intent"), case.expected_intent))
    if case.expect_web is not None:
        checks.append(_check("web_used", bool(output.get("used_web_fallback")) is case.expect_web, output.get("used_web_fallback"), case.expect_web))
    if case.expected_source_mode is not None:
        checks.append(
            _check("source_mode", output.get("source_mode") == case.expected_source_mode, output.get("source_mode"), case.expected_source_mode)
        )
    if case.min_citations:
        checks.append(_check("min_citations", len(citations) >= case.min_citations, len(citations), case.min_citations))
    for term in case.required_terms:
        checks.append(_check(f"answer_contains:{term}", term.lower() in answer.lower(), _short(answer), term))

    smoke_score = sum(1 for check in checks if check["passed"]) / len(checks) if checks else 1.0
    retrieval = score_retrieval(
        output.get("retrieved_evidence") or [],
        relevant_source_ids=case.relevant_source_ids,
        relevant_chunk_ids=case.relevant_chunk_ids,
        k=options.top_k,
    )
    rag_scores = evaluate_rag_dimensions(case, output)
    rag_score = aggregate_rag_score(rag_scores)
    retrieval_score = _retrieval_score(retrieval)
    final_score = _final_score(smoke_score, retrieval_score, rag_score, has_retrieval_ground_truth=bool(retrieval["has_ground_truth"]))
    smoke_passed = all(check["passed"] for check in checks)
    rag_quality_passed = rag_passed(rag_scores, threshold=options.rag_threshold)
    retrieval_passed = _retrieval_passed(retrieval)
    passed = smoke_passed and rag_quality_passed and retrieval_passed
    return {
        "case_id": case.id,
        "category": case.category,
        "question": case.question,
        "architecture": output.get("architecture"),
        "architecture_label": output.get("architecture_label"),
        "passed": passed,
        "smoke_passed": smoke_passed,
        "rag_quality_passed": rag_quality_passed,
        "retrieval_passed": retrieval_passed,
        "heuristic_score": round(smoke_score, 3),
        "overall_score": round(final_score, 3),
        "retrieval_score": retrieval_score,
        "rag_score": rag_score,
        "checks": checks,
        "retrieval_metrics": retrieval,
        "rag_scores": rag_scores,
        "confidence": output.get("confidence"),
        "source_mode": output.get("source_mode"),
        "used_web_fallback": bool(output.get("used_web_fallback")),
        "citation_count": len(citations),
        "latency_ms": (output.get("architecture_metrics") or {}).get("latency_ms"),
        "tool_calls": (output.get("architecture_metrics") or {}).get("tool_calls"),
        "answer_preview": _short(answer, limit=360),
        "answer": answer,
        "citations": citations,
        "retrieved_evidence": output.get("retrieved_evidence") or [],
        "web_evidence": output.get("web_evidence") or [],
        "gaps": output.get("gaps") or [],
        "failure_reasons": _failure_reasons(checks, retrieval, rag_scores),
        "needs_human_review": _needs_human_review(passed, retrieval, rag_score, output),
    }


def _summary(rows: list[dict[str, Any]], started: float) -> dict[str, Any]:
    by_architecture: dict[str, dict[str, Any]] = {}
    by_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        arch = str(row["architecture"])
        bucket = by_architecture.setdefault(
            arch,
            {
                "total": 0,
                "passed": 0,
                "score_sum": 0.0,
                "web_used": 0,
                "avg_latency_ms": 0.0,
                "latency_sum": 0,
            },
        )
        bucket["total"] += 1
        bucket["passed"] += 1 if row["passed"] else 0
        bucket["score_sum"] += float(row["overall_score"])
        bucket["web_used"] += 1 if row["used_web_fallback"] else 0
        bucket["latency_sum"] += int(row["latency_ms"] or 0)

        category = str(row["category"])
        category_bucket = by_category.setdefault(category, {"total": 0, "passed": 0, "score_sum": 0.0})
        category_bucket["total"] += 1
        category_bucket["passed"] += 1 if row["passed"] else 0
        category_bucket["score_sum"] += float(row["overall_score"])

    for bucket in by_architecture.values():
        total = bucket["total"] or 1
        bucket["pass_rate"] = round(bucket["passed"] / total, 3)
        bucket["avg_score"] = round(bucket["score_sum"] / total, 3)
        bucket["avg_latency_ms"] = round(bucket["latency_sum"] / total, 1)
        del bucket["score_sum"]
        del bucket["latency_sum"]
    for bucket in by_category.values():
        total = bucket["total"] or 1
        bucket["pass_rate"] = round(bucket["passed"] / total, 3)
        bucket["avg_score"] = round(bucket["score_sum"] / total, 3)
        del bucket["score_sum"]

    return {
        "total_rows": len(rows),
        "architecture_count": len(by_architecture),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "by_architecture": by_architecture,
        "by_category": by_category,
    }


def _retrieval_score(metrics: dict[str, Any]) -> float | None:
    if not metrics.get("has_ground_truth"):
        return None
    precision = float(metrics.get("precision_at_k") or 0.0)
    recall = float(metrics.get("recall_at_k") or 0.0)
    mrr = float(metrics.get("mrr_at_k") or 0.0)
    return round((0.35 * precision) + (0.45 * recall) + (0.20 * mrr), 4)


def _retrieval_passed(metrics: dict[str, Any]) -> bool:
    if not metrics.get("has_ground_truth"):
        return True
    return float(metrics.get("recall_at_k") or 0.0) > 0.0


def _final_score(
    smoke_score: float,
    retrieval_score: float | None,
    rag_score: float,
    *,
    has_retrieval_ground_truth: bool,
) -> float:
    if has_retrieval_ground_truth and retrieval_score is not None:
        return (0.15 * smoke_score) + (0.25 * retrieval_score) + (0.60 * rag_score)
    return (0.25 * smoke_score) + (0.75 * rag_score)


def _failure_reasons(
    checks: list[dict[str, Any]],
    retrieval_metrics: dict[str, Any],
    rag_scores: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    for check in checks:
        if not check.get("passed"):
            reasons.append(f"Smoke check failed: {check.get('name')}")
    if retrieval_metrics.get("has_ground_truth") and not _retrieval_passed(retrieval_metrics):
        reasons.append("Retrieval missed all labeled relevant chunks/sources.")
    for name, score in rag_scores.items():
        if not score.get("passed"):
            reasons.append(f"RAG dimension failed: {name} - {score.get('critique')}")
    return reasons


def _needs_human_review(
    passed: bool,
    retrieval_metrics: dict[str, Any],
    rag_score: float,
    output: dict[str, Any],
) -> bool:
    if not passed or rag_score < 0.75:
        return True
    if not retrieval_metrics.get("has_ground_truth"):
        return True
    if output.get("confidence") in {"Low", "Insufficient evidence"}:
        return True
    return False


def _write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_csv(report["results"], output_dir / "architecture_scorecard.csv")
    _write_retrieval_csv(report["results"], output_dir / "retrieval_metrics.csv")
    _write_rag_scores_csv(report["results"], output_dir / "rag_judge_scores.csv")
    _write_human_review_csv(report["results"], output_dir / "human_review_queue.csv")
    _write_human_labeling_sheet(report["results"], output_dir / "human_labeling_sheet.csv")
    failures = [_with_empty_human_review(row) for row in report["results"] if not row["passed"]]
    (output_dir / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.md").write_text(_markdown_summary(report), encoding="utf-8")


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "case_id",
        "category",
        "architecture",
        "passed",
        "overall_score",
        "heuristic_score",
        "rag_score",
        "retrieval_score",
        "smoke_passed",
        "rag_quality_passed",
        "retrieval_passed",
        "confidence",
        "source_mode",
        "used_web_fallback",
        "citation_count",
        "latency_ms",
        "tool_calls",
        "needs_human_review",
        "answer_preview",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _write_retrieval_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "case_id",
        "category",
        "architecture",
        "has_ground_truth",
        "precision_at_k",
        "recall_at_k",
        "map_at_k",
        "mrr_at_k",
        "relevant_found",
        "relevant_total",
        "retrieved_count",
        "k",
        "matched_source_ids",
        "matched_chunk_ids",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            metrics = row.get("retrieval_metrics") or {}
            writer.writerow(
                {
                    "case_id": row.get("case_id"),
                    "category": row.get("category"),
                    "architecture": row.get("architecture"),
                    **{field: metrics.get(field) for field in fields[3:]},
                }
            )


def _write_rag_scores_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = ["case_id", "category", "architecture", "dimension", "score", "passed", "label", "critique"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for dimension, score in (row.get("rag_scores") or {}).items():
                writer.writerow(
                    {
                        "case_id": row.get("case_id"),
                        "category": row.get("category"),
                        "architecture": row.get("architecture"),
                        "dimension": dimension,
                        "score": score.get("score"),
                        "passed": score.get("passed"),
                        "label": score.get("label"),
                        "critique": score.get("critique"),
                    }
                )


def _write_human_review_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "case_id",
        "category",
        "architecture",
        "overall_score",
        "rag_score",
        "retrieval_score",
        "confidence",
        "source_mode",
        "failure_reasons",
        "question",
        "answer_preview",
        "human_decision__good_bad_unclear",
        "answer_quality__good_partial_bad",
        "retrieval_quality__good_partial_bad",
        "should_have_used_web__yes_no",
        "should_refuse__yes_no",
        "source_ids_to_add",
        "chunk_ids_to_add",
        "required_claims_to_add",
        "forbidden_claims_to_add",
        "human_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if not row.get("needs_human_review"):
                continue
            writer.writerow(
                {
                    "case_id": row.get("case_id"),
                    "category": row.get("category"),
                    "architecture": row.get("architecture"),
                    "overall_score": row.get("overall_score"),
                    "rag_score": row.get("rag_score"),
                    "retrieval_score": row.get("retrieval_score"),
                    "confidence": row.get("confidence"),
                    "source_mode": row.get("source_mode"),
                    "failure_reasons": "; ".join(row.get("failure_reasons") or []),
                    "question": row.get("question"),
                    "answer_preview": row.get("answer_preview"),
                    "human_decision__good_bad_unclear": "",
                    "answer_quality__good_partial_bad": "",
                    "retrieval_quality__good_partial_bad": "",
                    "should_have_used_web__yes_no": "",
                    "should_refuse__yes_no": "",
                    "source_ids_to_add": "",
                    "chunk_ids_to_add": "",
                    "required_claims_to_add": "",
                    "forbidden_claims_to_add": "",
                    "human_notes": "",
                }
            )


def _write_human_labeling_sheet(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "case_id",
        "category",
        "architecture",
        "question",
        "answer_preview",
        "current_failure_reasons",
        "human_decision__good_bad_unclear",
        "answer_quality__good_partial_bad",
        "retrieval_quality__good_partial_bad",
        "should_have_used_web__yes_no",
        "should_refuse__yes_no",
        "source_ids_to_add",
        "chunk_ids_to_add",
        "required_claims_to_add",
        "forbidden_claims_to_add",
        "human_notes",
    ]
    review_rows = [row for row in rows if row.get("needs_human_review")]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in review_rows:
            writer.writerow(
                {
                    "case_id": row.get("case_id"),
                    "category": row.get("category"),
                    "architecture": row.get("architecture"),
                    "question": row.get("question"),
                    "answer_preview": row.get("answer_preview"),
                    "current_failure_reasons": "; ".join(row.get("failure_reasons") or []),
                    "human_decision__good_bad_unclear": "",
                    "answer_quality__good_partial_bad": "",
                    "retrieval_quality__good_partial_bad": "",
                    "should_have_used_web__yes_no": "",
                    "should_refuse__yes_no": "",
                    "source_ids_to_add": "",
                    "chunk_ids_to_add": "",
                    "required_claims_to_add": "",
                    "forbidden_claims_to_add": "",
                    "human_notes": "",
                }
            )


def _with_empty_human_review(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row.setdefault(
        "human_review",
        {
            "human_decision__good_bad_unclear": "",
            "answer_quality__good_partial_bad": "",
            "retrieval_quality__good_partial_bad": "",
            "should_have_used_web__yes_no": "",
            "should_refuse__yes_no": "",
            "source_ids_to_add": "",
            "chunk_ids_to_add": "",
            "required_claims_to_add": "",
            "forbidden_claims_to_add": "",
            "human_notes": "",
        },
    )
    return row


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = ["# Venture Metrics Architecture Evaluation", ""]
    lines.append("## Run Metadata")
    lines.append("")
    options = report.get("options") or {}
    generated_at = report.get("generated_at") or "unknown"
    lines.append(f"- Generated at: `{generated_at}`")
    lines.append(f"- Eval questions: `{len(report.get('cases') or [])}`")
    lines.append(f"- Result rows: `{report['summary']['total_rows']}`")
    lines.append(f"- Architectures: `{', '.join(options.get('architectures') or [])}`")
    lines.append(f"- Web fallback enabled: `{bool(options.get('use_web_fallback'))}`")
    lines.append(f"- LLM calls disabled: `{bool(options.get('no_llm'))}`")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(str(report.get("purpose") or ""))
    lines.append("")
    lines.append("## What This Run Shows")
    lines.append("")
    lines.extend(_interpretation_lines(report))
    lines.append("")
    lines.append("## Report Artifacts")
    lines.append("")
    lines.append("- `summary.md`: meeting-readable evaluation summary.")
    lines.append("- `summary.json`: full machine-readable report with cases, checks, and per-answer previews.")
    lines.append("- `architecture_scorecard.csv`: spreadsheet-friendly architecture scorecard.")
    lines.append("- `retrieval_metrics.csv`: retrieval precision/recall/MAP/MRR where labels exist.")
    lines.append("- `rag_judge_scores.csv`: deterministic six-dimension RAG scores.")
    lines.append("- `failures.json`: full failed rows with answer/context diagnostics.")
    lines.append("- `human_review_queue.csv`: rows that need manual review before submission claims.")
    lines.append("- `human_labeling_sheet.csv`: worksheet with blank columns for human labels.")
    lines.append("- `dashboard.html`: plain-language evaluation review board.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Architecture | Pass rate | Avg score | Web used | Avg latency ms |")
    lines.append("|---|---:|---:|---:|---:|")
    for architecture, stats in report["summary"]["by_architecture"].items():
        lines.append(
            f"| {architecture} | {stats['pass_rate']} | {stats['avg_score']} | {stats['web_used']} | {stats['avg_latency_ms']} |"
        )
    lines.append("")
    lines.append("## Category Coverage")
    lines.append("")
    lines.append("| Category | Pass rate | Avg score | Rows |")
    lines.append("|---|---:|---:|---:|")
    for category, stats in report["summary"].get("by_category", {}).items():
        lines.append(f"| {category} | {stats['pass_rate']} | {stats['avg_score']} | {stats['total']} |")
    lines.append("")
    lines.append("## Evaluation Layers")
    lines.append("")
    lines.append("- Tier 0 smoke checks: route intent, expected web use, citation count, and required terms.")
    lines.append("- Tier 1 retrieval metrics: precision/recall/MAP/MRR when a case has labeled relevant source or chunk IDs.")
    lines.append("- Tier 2 RAG dimensions: context relevance, faithfulness, answer relevance, context support, answerability, and self-containment.")
    lines.append("- Human review queue: rows where deterministic scores are low, labels are missing, or confidence is weak.")
    lines.append("")
    lines.append("## RAG Failure Patterns")
    lines.append("")
    rag_patterns = _rag_failure_patterns(report["results"])
    if rag_patterns:
        lines.append("| Dimension | Failures |")
        lines.append("|---|---:|")
        for dimension, count in rag_patterns:
            lines.append(f"| {dimension} | {count} |")
    else:
        lines.append("No RAG dimension failures detected.")
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    failures = [row for row in report["results"] if not row["passed"]]
    if not failures:
        lines.append("No heuristic failures in this run.")
    else:
        for row in failures:
            lines.append(f"- `{row['architecture']}` failed `{row['case_id']}`: {row['question']}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "The RAG dimension scores are deterministic proxies, not yet validated LLM judges. "
        "Use them for structured debugging and regression tracking, then use the human review queue "
        "before making final submission claims."
    )
    return "\n".join(lines) + "\n"


def _interpretation_lines(report: dict[str, Any]) -> list[str]:
    summary = report["summary"]
    architecture_stats = summary.get("by_architecture", {})
    category_stats = summary.get("by_category", {})
    lines: list[str] = []
    if architecture_stats:
        best_architecture, best_stats = max(
            architecture_stats.items(),
            key=lambda item: (item[1].get("pass_rate", 0), item[1].get("avg_score", 0)),
        )
        lines.append(
            f"- Best overall result in this run: `{best_architecture}` "
            f"with pass rate `{best_stats['pass_rate']}` and average score `{best_stats['avg_score']}`."
        )
    web_failures = [
        row
        for row in report["results"]
        for check in row.get("checks", [])
        if check.get("name") == "web_used" and not check.get("passed") and check.get("expected") is True
    ]
    if web_failures:
        lines.append(
            f"- Web fallback is still failing: `{len(web_failures)}` expected-web checks did not use web search."
        )
    zero_categories = [category for category, stats in category_stats.items() if stats.get("pass_rate") == 0]
    if zero_categories:
        lines.append("- Zero-pass categories: `" + "`, `".join(zero_categories) + "`.")
    if not lines:
        lines.append("- No major heuristic failure pattern was detected in this run.")
    lines.append(
        "- This report is for architecture comparison, regression tracking, and submission evidence; final claims still need human review of flagged rows."
    )
    return lines


def _rag_failure_patterns(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        for dimension, score in (row.get("rag_scores") or {}).items():
            if not score.get("passed"):
                counts[dimension] = counts.get(dimension, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def _check(name: str, passed: bool, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "actual": actual, "expected": expected}


def _short(text: str, *, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."
