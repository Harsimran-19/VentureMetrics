#!/usr/bin/env python3
"""Build a simple standalone HTML review board for architecture evals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", default="reports/evaluations/latest/summary.json")
    parser.add_argument("--output", default="reports/evaluations/latest/dashboard.html")
    args = parser.parse_args()

    report_path = Path(args.report_json)
    output_path = Path(args.output)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render(report), encoding="utf-8")
    print(output_path)


def render(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    options = report.get("options") or {}
    results = list(report.get("results") or [])
    human_review = [row for row in results if row.get("needs_human_review")]
    best = _best_architecture(summary)
    rag_failures = _rag_failure_counts(results)
    unlabeled_cases = _unlabeled_cases(report)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Venture Metrics Evaluation Review Board</title>
  <style>
    body {{
      margin: 0;
      background: #f7f7f4;
      color: #202420;
      font-family: Arial, Helvetica, sans-serif;
      letter-spacing: 0;
      line-height: 1.45;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 22px 48px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
    }}
    h2 {{
      margin: 30px 0 10px;
      font-size: 20px;
      border-bottom: 2px solid #d6d8d1;
      padding-bottom: 6px;
    }}
    h3 {{
      margin: 18px 0 8px;
      font-size: 16px;
    }}
    p {{ margin: 8px 0; }}
    .muted {{ color: #626b63; }}
    .box {{
      background: #fff;
      border: 1px solid #d6d8d1;
      border-radius: 6px;
      padding: 14px 16px;
      margin: 12px 0;
    }}
    .warning {{
      border-left: 5px solid #b76b1f;
    }}
    .ok {{
      border-left: 5px solid #287347;
    }}
    .bad {{
      border-left: 5px solid #b54a3d;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: #fff;
      border: 1px solid #d6d8d1;
      border-radius: 6px;
      padding: 12px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
      margin-bottom: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      margin: 10px 0 22px;
      font-size: 14px;
    }}
    th, td {{
      border: 1px solid #d6d8d1;
      padding: 8px 9px;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: #eceee8;
      font-weight: 700;
    }}
    .pass {{ color: #287347; font-weight: 700; }}
    .fail {{ color: #b54a3d; font-weight: 700; }}
    .review {{ color: #b76b1f; font-weight: 700; }}
    code {{
      background: #eceee8;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    ul {{ margin-top: 8px; }}
    li {{ margin: 5px 0; }}
    @media (max-width: 780px) {{
      .grid {{ grid-template-columns: 1fr; }}
      main {{ padding: 20px 12px; }}
      table {{ font-size: 12px; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Venture Metrics Evaluation Review Board</h1>
  <p class="muted">Generated at {_esc(report.get("generated_at"))}. This page is meant to be read directly, not decoded from CSV files.</p>

  <div class="box warning">
    <h3>Plain-English Verdict</h3>
    <p><strong>Do not select a final production architecture yet.</strong></p>
    <p>The pipeline structure now follows the evaluation roadmap closely, but the current results still require human labeling and evaluator validation before they can support final submission claims.</p>
    <p>Current best score: <strong>{_esc(best[0]) if best else "n/a"}</strong>{f" with average score {_fmt(best[1].get('avg_score'))}" if best else ""}.</p>
  </div>

  <div class="grid">
    {_metric("Questions", len(report.get("cases") or []), "research cases")}
    {_metric("Architecture Rows", summary.get("total_rows", len(results)), "architecture x question")}
    {_metric("Human Review Rows", len(human_review), "must be checked")}
    {_metric("Unlabeled Cases", len(unlabeled_cases), "need source/chunk labels")}
  </div>

  <h2>1. Does This Match The Article?</h2>
  <div class="box ok">
    <p><strong>Architecture alignment: about 80%.</strong> The shape is right: dataset, harness, code evaluators, retrieval metrics, RAG Q/C/A scoring, report artifacts, and a human review queue.</p>
    <p><strong>Validation maturity: about 55%.</strong> The missing parts are exactly where I need you: human labels, judge calibration, and evaluator agreement checks.</p>
  </div>
  {_alignment_table()}

  <h2>2. What Needs Your Review Now?</h2>
  <div class="box warning">
    <p><strong>Human labeling is needed now.</strong> That is the next article-required step. Without your labels, the system can produce structured reports but cannot honestly claim the evaluators are trusted.</p>
    <p>Review these files in this order:</p>
    <ul>
      <li><code>reports/evaluations/latest/human_review_queue.csv</code> - rows that need judgment.</li>
      <li><code>reports/evaluations/latest/failures.json</code> - full answer/context details.</li>
      <li><code>eval_cases/architecture_research_v2.json</code> - where labels should be added.</li>
    </ul>
  </div>
  {_unlabeled_table(unlabeled_cases)}

  <h2>3. Architecture Scores</h2>
  {_architecture_table(summary)}

  <h2>4. Category Scores</h2>
  {_category_table(summary)}

  <h2>5. RAG Failure Reasons</h2>
  {_rag_failure_table(rag_failures)}

  <h2>6. Most Important Failed Rows</h2>
  {_failure_table(results)}

  <h2>7. How To Run This Again</h2>
  <div class="box">
    <p>Run the full evaluation and regenerate this page:</p>
    <p><code>make arch-eval</code></p>
    <p>Open this page:</p>
    <p><code>open reports/evaluations/latest/dashboard.html</code></p>
  </div>

  <h2>8. Submission Use</h2>
  <div class="box">
    <p>Use this HTML page as the readable evaluation board. Use <code>summary.md</code> for the written narrative. Use the CSV and JSON files only as evidence attachments.</p>
    <p>Do not claim “best architecture selected” until the human labels are added and the evaluator validation step is complete.</p>
  </div>
</main>
</body>
</html>
"""


def _alignment_table() -> str:
    rows = [
        ("Development optimization", "Implemented", "Run architecture experiments on a fixed dataset."),
        ("Regression before merge", "Implemented", "Same command can be used after architecture or prompt changes."),
        ("Production monitoring", "Partial", "Telemetry exists, but live sampling policies are not active yet."),
        ("Dataset growth by error analysis", "Implemented", "Human review queue feeds back into versioned eval cases."),
        ("Code-based evaluators", "Implemented", "Smoke checks, retrieval metrics, deterministic RAG proxies."),
        ("RAG Q/C/A metrics", "Implemented as proxies", "Six dimensions are reported for every architecture answer."),
        ("Evaluate the evaluator", "Missing / needs you", "Requires human labels and judge calibration."),
        ("Calibrated LLM judges", "Missing", "Next after human-labeled examples exist."),
    ]
    return _table(["Article Requirement", "Status", "Project Implementation"], rows)


def _architecture_table(summary: dict[str, Any]) -> str:
    rows = []
    for name, stats in (summary.get("by_architecture") or {}).items():
        rows.append(
            (
                name,
                _pct(stats.get("pass_rate")),
                _fmt(stats.get("avg_score")),
                str(stats.get("web_used", 0)),
                f"{_fmt(stats.get('avg_latency_ms'), 1)} ms",
            )
        )
    return _table(["Architecture", "Pass Rate", "Average Score", "Web Used", "Avg Latency"], rows)


def _category_table(summary: dict[str, Any]) -> str:
    rows = []
    for name, stats in (summary.get("by_category") or {}).items():
        rows.append((name, _pct(stats.get("pass_rate")), _fmt(stats.get("avg_score")), str(stats.get("total", 0))))
    return _table(["Category", "Pass Rate", "Average Score", "Rows"], rows)


def _rag_failure_table(counts: list[tuple[str, int]]) -> str:
    if not counts:
        return '<div class="box ok">No RAG dimension failures were detected.</div>'
    return _table(["RAG Dimension", "Failure Count"], [(name, str(count)) for name, count in counts])


def _failure_table(results: list[dict[str, Any]]) -> str:
    failures = [row for row in results if not row.get("passed")]
    failures = sorted(failures, key=lambda row: (row.get("overall_score") or 0.0))[:18]
    rows = []
    for row in failures:
        reasons = "; ".join((row.get("failure_reasons") or [])[:3])
        rows.append(
            (
                row.get("case_id"),
                row.get("architecture"),
                _fmt(row.get("overall_score")),
                row.get("question"),
                reasons,
            )
        )
    return _table(["Case", "Architecture", "Score", "Question", "Main Failure Reasons"], rows)


def _unlabeled_table(cases: list[dict[str, Any]]) -> str:
    rows = []
    for case in cases:
        rows.append((case.get("id"), case.get("category"), case.get("question"), "Add relevant_source_ids or relevant_chunk_ids"))
    return _table(["Case", "Category", "Question", "Human Task"], rows[:30])


def _metric(label: str, value: Any, note: str) -> str:
    return f'<div class="metric"><strong>{_esc(value)}</strong><span class="muted">{_esc(label)}<br>{_esc(note)}</span></div>'


def _table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _best_architecture(summary: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    items = list((summary.get("by_architecture") or {}).items())
    if not items:
        return None
    return max(items, key=lambda item: (item[1].get("avg_score") or 0.0, item[1].get("pass_rate") or 0.0))


def _rag_failure_counts(results: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in results:
        for name, score in (row.get("rag_scores") or {}).items():
            if not score.get("passed"):
                counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def _unlabeled_cases(report: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    for case in report.get("cases") or []:
        if not case.get("unanswerable") and not case.get("relevant_source_ids") and not case.get("relevant_chunk_ids"):
            cases.append(case)
    return cases


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return str(value)


def _esc(value: Any) -> str:
    text = str(value if value is not None else "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


if __name__ == "__main__":
    main()
