# Tracking And Evaluation Research

Last updated: 2026-06-02

## Goal

Add a serious tracking and evaluation layer to Venture Metrics before further UI/deployment work.

The system should record what users ask, what the agent retrieved, what it answered, which sources it cited, whether web fallback was used, how long each stage took, and whether the result was good enough. This becomes the basis for debugging, demos, user testing, and future model/retrieval improvement.

## Research Summary

### Opik

Opik is an open-source LLM observability and evaluation platform by Comet. Its docs position it around tracing LLM calls, tool invocations, agent steps, test suites from traces, production monitoring, feedback scores, latency, cost, hallucination, context recall, relevance, and prompt optimization.

Useful fit:
- Strong evaluation orientation.
- Explicitly supports traces, tool calls, and agent steps.
- Useful later for prompt optimization and regression suites.
- Self-hosting is available.

Risk for us:
- Adds another service dependency.
- Mainland accessibility depends on where we host it.
- Direct integration now may slow the two-day submission path.

Reference: https://www.comet.com/docs/opik/

### Langfuse

Langfuse is an open-source LLM observability platform with traces, sessions, users, scores, prompt management, datasets, and evaluations. Self-hosting uses Docker and production deployments include Postgres, ClickHouse, Redis/Valkey, and S3/blob storage.

Useful fit:
- Mature trace/session model.
- Strong dashboard and annotation workflow.
- Self-hostable and can run inside a private network.
- Supports OpenTelemetry-oriented observability.

Risk for us:
- Production self-hosting is heavier than the current prototype.
- Full stack is too large for the immediate deadline.
- For China deployment, all backing services must be hosted in an accessible region/provider.

Reference: https://langfuse.com/self-hosting

### OpenTelemetry GenAI

OpenTelemetry has GenAI semantic conventions for model spans, agent spans, events, metrics, and exceptions. The GenAI conventions are still in development, so they are useful as a naming guide but should not become a hard dependency yet.

Useful fit:
- Vendor-neutral.
- Makes future export to observability tools easier.
- Good vocabulary for run/span/event data.

Risk for us:
- More infrastructure than we need for the immediate prototype.
- Current GenAI conventions are still marked development.

Reference: https://opentelemetry.io/docs/specs/semconv/gen-ai/

## Recommended Direction

Use a DB-first tracking layer now, with optional exporters later.

That means:
- Store all sessions, messages, runs, tool calls, retrieval results, citations, feedback, and eval scores in our own database first.
- Keep SQLite as the local default.
- Add Postgres compatibility behind `DATABASE_URL` later, so we can use Neon for quick demos or Tencent Cloud / Alibaba Cloud / Huawei Cloud / self-hosted Postgres for mainland-compatible deployment.
- Keep India compatibility in the same design: Neon or another global/Postgres provider may be useful for India-facing demos, while Chinese providers may carry policy or reachability risk in India.
- Do not make DeepSeek, Tavily, Neon, Opik, or Langfuse mandatory. They should be replaceable implementation choices.
- Add an adapter boundary for Langfuse or Opik later, not as the source of truth.

This gives us:
- Full data ownership.
- No dependency on blocked external SaaS.
- Easier demo and debugging.
- A way to run different provider stacks for China, India, and global demos without changing agent logic.
- A clean migration path to hosted observability tools.

## Proposed Telemetry Model

### `chat_sessions`

One row per user/browser/demo session.

Fields:
- `id`
- `session_id`
- `user_label`
- `client_metadata_json`
- `created_at`
- `updated_at`

### `chat_messages`

One row per user or assistant message.

Fields:
- `id`
- `session_id`
- `role`
- `content`
- `created_at`

### `agent_runs`

One row per answered user question.

Fields:
- `id`
- `run_id`
- `session_id`
- `question`
- `answer`
- `confidence`
- `source_mode`
- `used_web_fallback`
- `route_intent`
- `latency_ms`
- `llm_provider`
- `llm_model`
- `error_message`
- `created_at`

### `agent_run_steps`

Structured trace steps for route, plan, internal search, web search, verification, synthesis, and logging.

Fields:
- `id`
- `run_id`
- `step_index`
- `phase`
- `decision`
- `tool`
- `reason`
- `observation_json`
- `latency_ms`
- `created_at`

### `retrieval_events`

One row per retrieval operation.

Fields:
- `id`
- `run_id`
- `query`
- `top_k`
- `result_count`
- `accepted_count`
- `rejected_count`
- `latency_ms`
- `created_at`

### `retrieval_event_results`

One row per retrieved chunk/result.

Fields:
- `id`
- `retrieval_event_id`
- `chunk_id`
- `source_id`
- `rank`
- `score`
- `accepted`
- `reject_reason`
- `source_type`
- `reliability_label`
- `snippet`

### `answer_citations`

Normalized citations actually shown to the user.

Fields:
- `id`
- `run_id`
- `source_id`
- `title`
- `url`
- `source_type`
- `reliability_label`
- `rank`

### `user_feedback`

Feedback from UI buttons or later reviewers.

Fields:
- `id`
- `run_id`
- `session_id`
- `rating`
- `label`
- `comment`
- `created_at`

### `eval_cases`

Versioned evaluation prompts.

Fields:
- `id`
- `case_id`
- `question`
- `category`
- `expected_intent`
- `expected_source_mode`
- `min_citations`
- `must_use_web`
- `must_not_use_web`
- `required_source_types_json`
- `notes`
- `active`

### `eval_runs`

One execution of the eval suite.

Fields:
- `id`
- `eval_run_id`
- `agent_version`
- `model`
- `started_at`
- `finished_at`
- `summary_json`

### `eval_results`

Per-case score result.

Fields:
- `id`
- `eval_run_id`
- `case_id`
- `passed`
- `scores_json`
- `response_json`
- `failure_reasons_json`
- `created_at`

## Evaluation Strategy

### Deterministic Checks

Use these first because they are fast and stable:
- Route correctness.
- Source mode correctness.
- Web fallback used only when expected.
- Minimum citation count.
- No citations for casual/system-help turns.
- Confidence is not `High` when all accepted evidence is low-reliability.
- Answer says insufficient when no accepted evidence exists.
- Accepted evidence must include at least two meaningful query-term overlaps or a trusted source/domain match.

### Retrieval Quality Checks

Track:
- Accepted versus rejected retrieval result ratio.
- Number of unique sources.
- Source type distribution.
- Whether top results match the requested region.
- Whether high-confidence answers rely on official/university/science-park sources.

### Answer Quality Checks

Start with heuristic checks:
- Answer is non-empty.
- Citations exist for factual research answers.
- Citations map to retrieved/web evidence.
- No implementation details in user-facing answer.
- Gaps are present when confidence is Low or Insufficient.

Later add LLM-as-judge:
- Faithfulness.
- Context relevance.
- Answer relevance.
- Completeness.
- Citation support.

Use DeepSeek/Qwen-compatible judge adapters for China compatibility.

## Implementation Plan

### Phase 1: Local Tracking

- Add schema migration helpers for tracking tables.
- Generate stable `session_id` in UI.
- Generate stable `run_id` per query.
- Store every user/assistant message.
- Store route, trace, retrieval, citations, gaps, and timings.
- Add feedback buttons in UI.
- Add `/api/feedback`.
- Add `/api/runs` or CLI report for demo review.

### Phase 2: Eval Harness

- Add `eval_cases` seed file.
- Expand current reasoning evals to 20-30 project-specific cases.
- Store eval run results in DB.
- Add `make eval`.
- Add regression summary: pass rate, failed cases, web-use correctness, citation correctness, average latency.

### Phase 3: Observability Adapter

- Add an exporter interface:
  - `LocalTelemetrySink`
  - `LangfuseTelemetrySink`
  - `OpikTelemetrySink`
  - `OpenTelemetrySink`
- Keep local DB as source of truth.
- Enable external tracing only with env vars.

### Phase 4: Postgres Compatibility

- Introduce `DATABASE_URL`.
- Keep SQLite default for local.
- Add Postgres-compatible schema path.
- Test with Neon for demo if needed.
- For mainland deployment, keep provider swappable to China-hosted Postgres.

## Recommendation For The Next Commit

Build Phase 1 first:

1. Add tracking tables to SQLite schema.
2. Add a small telemetry module.
3. Instrument `answer_question_reasoning`.
4. Add UI session ID and feedback buttons.
5. Add a CLI report command.

This will immediately improve demo credibility and give us real data from testers.
