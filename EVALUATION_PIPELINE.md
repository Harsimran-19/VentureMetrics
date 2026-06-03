# Venture Metrics Evaluation Pipeline

> Last updated: 2026-06-03  
> Purpose: define how Venture Metrics evaluates architecture choices such as RAG, CAG-inspired source packs, ReAct-style loops, plan-and-execute workflows, and RLM-inspired experiments.

## Product Purpose

Venture Metrics is a cited research assistant for Excel-derived startup, university, commercialization, policy, funding, incubator, talent, and ecosystem sources.

The app must:

- search internal Venture Metrics evidence first,
- use public web fallback when internal evidence is missing, weak, stale, or outside scope,
- cite factual claims,
- label confidence,
- show unresolved gaps,
- avoid hallucinating answers when evidence is insufficient,
- support normal conversation without forcing every message into retrieval.

## Evaluation Principle

Product chat uses **one active architecture at a time**.

Benchmarking is separate:

```text
Fixed question set
-> run every architecture on the same questions
-> score outputs with deterministic checks and later LLM judges
-> produce report
-> choose production architecture from evidence
```

This avoids confusing product mode with benchmark mode.

## What Is Implemented Now

The structured evaluation implementation now lives in:

```text
venture_metrics_agent/evaluation/runner.py
venture_metrics_agent/evaluation/retrieval_metrics.py
venture_metrics_agent/evaluation/rag_dimensions.py
eval_cases/architecture_core_v1.json
scripts/run_architecture_eval.py
```

The current implementation has three layers:

| Layer | Status | What it means |
|---|---|---|
| Tier 0 smoke checks | Implemented | Deterministic route/web/citation/required-term checks. Useful for CI and quick regressions. |
| Tier 1 retrieval metrics | Implemented when labels exist | Computes `Precision@K`, `Recall@K`, `MAP@K`, and `MRR@K` from labeled source/chunk IDs. |
| Tier 2 RAG dimensions | Implemented as deterministic proxies | Scores context relevance, faithfulness, answer relevance, context support, answerability, and self-containment. |

Important: Tier 2 currently uses deterministic proxy evaluators. They create the correct report structure and catch obvious failures, but they are not yet validated LLM judges. Treat them as structured debugging signals until human validation and judge calibration are added.

## Evals Roadmap Applied To This App

The Decoding AI evals roadmap maps cleanly to Venture Metrics:

| Layer | Venture Metrics implementation |
|---|---|
| Development optimization | Run focused eval subsets while improving one architecture or one failure class. |
| Regression before merge | Run the full 20-question benchmark before accepting architecture/prompt/tool changes. |
| Production monitoring | Sample live traces by route, low confidence, failed web fallback, long conversations, and user feedback. |
| Dataset growth | Start with 20 questions, then add failed real traces through error analysis. |
| Evaluator design | Prefer deterministic checks first; add LLM judges only for nuanced answer quality. |
| RAG-specific eval | Track question/context/answer relationships: relevance, faithfulness, context support, answerability, self-containment. |

## Current Benchmark Dataset

The default Python benchmark lives in `venture_metrics_agent/evaluation/runner.py`.

The current serious research dataset lives in:

```text
eval_cases/architecture_research_v2.json
```

Use the JSON dataset for serious evaluation runs because it is easier to label and revise without changing Python code.

| ID | Category | Question |
|---|---|---|
| `casual_hi` | casual | hi |
| `casual_social` | casual | how are you? |
| `system_capability` | capability | What can you do for Venture Metrics? |
| `vague_research` | clarification | research this |
| `internal_hk_support` | internal_answerable | Which sources are related to Hong Kong entrepreneurship support? |
| `official_hk_startup_support` | official_sources | Where can a founder get official startup support in Hong Kong, including government programmes, science parks, and incubators? |
| `hk_university_spinouts` | university_commercialization | Which Hong Kong universities provide spinout, technology transfer, or incubator support for founders? |
| `patent_ip_support` | commercialization | What patent, intellectual property, or commercialization support is available in Hong Kong for startups or university-linked founders? |
| `gba_ecosystem_connectors` | ecosystem | Which associations, alliances, or ecosystem organisations could help a startup build connections across Hong Kong and Shenzhen? |
| `startup_hiring_channels` | talent | Which hiring platforms, labour portals, or talent programmes look most relevant for startup recruitment in Hong Kong, the UK, and Canada? |
| `source_library_overview` | source_audit | What topics are covered in the current Venture Metrics source library? |
| `official_sources_audit` | source_audit | Which sources appear to be official government, university, science park, or incubator sources? |
| `funding_mentions` | funding | Which sources mention startup funding, grants, funds, or competition-based programmes? |
| `latest_hk_grants` | current_web_needed | What are the latest Hong Kong startup grants? |
| `shenzhen_policy_support` | shenzhen_policy | What do the Shenzhen policy sources say about startup subsidies, talent support, and commercialising research? |
| `hk_shenzhen_compare` | comparison | Compare the startup support options mentioned for Hong Kong and Shenzhen, including policy, funding, and ecosystem support. |
| `mainland_benchmark` | weak_internal_or_web | Which mainland university incubators or science parks look most relevant as benchmarks for commercialization and startup support? |
| `internal_only_request` | internal_only | What answer can you give from internal Venture Metrics sources only about Hong Kong entrepreneurship support? |
| `outside_corpus_global_latest` | external_current | What are the latest startup visa changes in France? |
| `data_gaps` | gap_analysis | What data gaps exist in the current sample files for comparing Hong Kong and Shenzhen startup support? |

## Current Evaluators

The smoke layer uses deterministic checks:

| Evaluator | What it checks |
|---|---|
| Intent check | Did the router classify casual/help/current/internal/clarification correctly? |
| Web-use check | Did the architecture attempt web when required, and avoid web when not required? |
| Citation count | Did the answer provide at least the expected number of citations? |
| Required terms | Does the answer mention required entities such as Hong Kong, Shenzhen, grant, university? |
| Latency | How long did the architecture take? |
| Tool calls | How many internal/web tool calls were used? |

These checks are not the final quality judge. They are the stable regression layer.

## RAG Dimension Evaluators

Every architecture output is scored on the six question/context/answer relationships:

| Dimension | Code name | What it diagnoses |
|---|---|---|
| `C|Q` | `context_relevance` | Did retrieved context address the question? |
| `A|C` | `faithfulness` | Did the answer stay grounded in retrieved context? |
| `A|Q` | `answer_relevance` | Did the answer solve the actual user question? |
| `C|A` | `context_support` | Does the context contain enough support for answer claims? |
| `Q|C` | `answerability` | Should the system answer, use web, or refuse? |
| `Q|A` | `self_containment` | Can the answer stand alone without the original question? |

These scores are written to:

```text
reports/evaluations/runs/<timestamp>/rag_judge_scores.csv
```

## Next Evaluators To Add

Add app-level evaluators in this order:

| Evaluator | Type | Reason |
|---|---|---|
| Citation validity | deterministic | Each cited URL should exist and correspond to source cards. |
| Source mode correctness | deterministic | Internal-only, web-only, internal+web, or insufficient should match evidence. |
| Context relevance | deterministic + LLM judge | Retrieved evidence should match the question. |
| Faithfulness | LLM judge | Answer should not introduce claims unsupported by cited sources. |
| Context support | LLM judge | Evidence should be sufficient for the answer, not merely related. |
| Answer relevance | LLM judge | Answer should solve the user’s actual question. |
| Gap honesty | LLM judge | Missing data should be disclosed without over-refusal. |
| Conversation quality | human + LLM judge | Casual and follow-up turns should feel natural. |

## Run Commands

List architectures:

```bash
PYTHONPATH=. .venv/bin/python scripts/query_architecture.py --list
```

Run one active architecture:

```bash
PYTHONPATH=. .venv/bin/python scripts/query_architecture.py \
  --architecture coverage_rag \
  "Compare the startup support options mentioned for Hong Kong and Shenzhen."
```

Run the full benchmark:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_architecture_eval.py \
  --cases eval_cases/architecture_research_v2.json \
  --quiet
```

Run the structured submission-style benchmark:

```bash
make arch-eval
```

This uses:

```text
eval_cases/architecture_research_v2.json
```

Run with a custom architecture subset:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_architecture_eval.py \
  --cases eval_cases/architecture_core_v1.json \
  --architecture deterministic_controller \
  --architecture coverage_rag \
  --architecture plan_execute \
  --quiet
```

Run a focused optimization subset with custom JSON cases:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_architecture_eval.py \
  --cases eval_cases/shenzhen_comparison.json \
  --architecture coverage_rag \
  --architecture plan_execute \
  --quiet
```

## Report Artifacts

Each report directory contains:

```text
summary.md
summary.json
architecture_scorecard.csv
retrieval_metrics.csv
rag_judge_scores.csv
failures.json
human_review_queue.csv
human_labeling_sheet.csv
dashboard.html
```

Reports are written to timestamped directories:

```text
reports/evaluations/runs/<timestamp>/
```

The most recent run path is stored in:

```text
reports/evaluations/LATEST_RUN.txt
```

The report should be used for:

- architecture selection,
- meeting/presentation evidence,
- failure analysis,
- regression tracking after code changes.

### How To Read The Report

Use `summary.md` first. It is the meeting/submission-readable narrative.

Use `dashboard.html` when you want the full evaluation board in a readable format. It is intentionally plain: one page, no hidden tabs, no chart tricks. It is a standalone local HTML file and can be opened directly:

```bash
open "$(cat reports/evaluations/LATEST_RUN.txt)/dashboard.html"
```

Use `architecture_scorecard.csv` to compare architectures by case. Important columns:

- `overall_score`: weighted score combining smoke checks, retrieval labels when available, and RAG dimension scores.
- `heuristic_score`: old Tier 0 smoke score only.
- `rag_score`: average of the six RAG dimension scores.
- `retrieval_score`: retrieval score when source/chunk labels exist.
- `needs_human_review`: whether this row should be manually checked before making claims.

Use `retrieval_metrics.csv` after adding `relevant_source_ids` or `relevant_chunk_ids` to eval cases. Until labels exist, retrieval metrics will say `has_ground_truth=false`.

Use `rag_judge_scores.csv` to understand failure type. For example:

- many `context_relevance` failures mean retrieval is weak.
- many `faithfulness` or `context_support` failures mean answer synthesis is making claims beyond evidence.
- many `answerability` failures mean the system answers when it should refuse or search web.

Use `human_review_queue.csv` as the diagnostic queue. It shows which rows were flagged and why.

Use `human_labeling_sheet.csv` for actual review. Fill the blank columns:

- `human_decision__good_bad_unclear`: use `good`, `bad`, or `unclear`.
- `answer_quality__good_partial_bad`: whether the final answer is usable.
- `retrieval_quality__good_partial_bad`: whether the retrieved evidence is relevant.
- `should_have_used_web__yes_no`: whether web fallback should have happened.
- `should_refuse__yes_no`: whether the correct behavior was to say insufficient evidence.
- `source_ids_to_add`: source IDs that should count as relevant for this case.
- `chunk_ids_to_add`: chunk IDs that should count as relevant for this case, if known.
- `required_claims_to_add`: claims the answer must include.
- `forbidden_claims_to_add`: claims the answer must not include.
- `human_notes`: any explanation.

## How We Improve The Dataset

The first run will produce many rows in `human_review_queue.csv`. That is expected.

For each important failed row:

1. Open the answer preview and source evidence in `summary.json`.
2. Decide whether the answer is actually good or bad.
3. If retrieval was wrong, add `relevant_source_ids` or `relevant_chunk_ids` to the JSON eval case.
4. If the answer missed a required fact, add it to `required_claims`.
5. If the answer invented something, add it to `forbidden_claims`.
6. Re-run `make arch-eval`.

That is the error-analysis flywheel from the article, adapted to this project.

## Human Labeling Checkpoint

This pipeline should call for human review when:

- many rows are in `human_review_queue.csv`,
- eval cases lack `relevant_source_ids` or `relevant_chunk_ids`,
- deterministic RAG scores flag answerability or faithfulness failures,
- we want to make submission-grade claims about the best architecture.

That checkpoint has been reached. The next step is manual labeling of selected cases in `eval_cases/architecture_research_v2.json`.

## Sources

- Decoding AI, “The AI Evals Roadmap I Wish I Had”  
  https://www.decodingai.com/p/the-ai-evals-roadmap-i-wish-i-had
- Decoding AI, “Integrating AI Evals Into Your AI App”  
  https://www.decodingai.com/p/integrating-ai-evals-into-your-ai-app
- Decoding AI, “How to Build an AI Evals Dataset from Scratch”  
  https://www.decodingai.com/p/build-an-ai-evals-dataset-with-error-analysis
- Decoding AI, “How to Design AI Evaluators That Work”  
  https://www.decodingai.com/p/how-to-design-ai-evaluators-that-catch-failures
- Decoding AI, “RAG Evaluation: The Only 6 Metrics You Need”  
  https://www.decodingai.com/p/rag-evaluation-6-metrics-framework
