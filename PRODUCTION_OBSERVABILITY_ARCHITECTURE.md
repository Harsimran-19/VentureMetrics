# Production Observability Architecture

Last updated: 2026-06-02

## Core Position

Tracking, evaluation, and observability are part of the agent system, not an optional dashboard.

For Venture Metrics, the observability layer must answer:

- What did the user ask?
- What route did the agent choose?
- What internal evidence was retrieved?
- What evidence was rejected?
- Was web fallback used?
- Which citations were shown?
- What model/provider generated the answer?
- How long did each stage take?
- Was the answer grounded?
- Did the user or reviewer mark it useful?
- Did a new code/model/prompt change improve or damage performance?

The correct architecture is a layered system:

```text
User / UI
  -> Agent API
  -> Agent Controller
  -> Telemetry SDK inside our code
  -> Local transactional store
  -> Optional observability sink
  -> Evaluation runner
  -> Reporting / dashboards
```

## Neon vs Opik / Langfuse

### Neon

Neon is Postgres. It is good for application data:

- user sessions
- chat messages
- agent runs
- citations
- feedback
- eval case definitions
- eval results
- product analytics summaries

It should be treated as our application system of record when we move beyond local SQLite.

Neon can handle chat history well if we use it correctly:

- Use pooled connections for web/serverless-style traffic.
- Keep write records compact.
- Store large raw trace payloads either compressed, summarized, or in object storage later.
- Keep long analytical dashboards out of hot request paths.
- Put app and database in the same/closest region.

Neon uses PgBouncer for connection pooling and supports many short-lived clients, but the 10,000 client connection number does not mean 10,000 simultaneous active queries. Active transaction capacity is still bounded by the underlying compute and pool size.

### Opik

Opik is an LLM observability/evaluation platform. It is good for:

- trace trees
- spans
- tool calls
- LLM calls
- feedback scores
- experiment runs
- hallucination / relevance / context recall metrics
- prompt and model comparison

It should be treated as an optional LLMOps sink, not the only source of truth.

### Langfuse

Langfuse is also a strong LLM observability platform. It is good for:

- trace/session views
- scores
- prompt management
- datasets
- evals
- production dashboards

Its production architecture is heavier because it separates transactional data from high-volume trace analytics:

- Postgres for transactional data.
- ClickHouse for trace/score analytics.
- Redis/Valkey for queues and cache.
- S3/blob storage for raw ingestion events and attachments.
- Worker process for asynchronous ingestion.

This architecture is a useful reference for our long-term design.

## Recommended Venture Metrics Architecture

### Phase 1: Local DB-First Telemetry

For the immediate prototype:

```text
Agent request
  -> write chat_sessions/chat_messages
  -> run reasoning controller
  -> write agent_runs
  -> write agent_run_steps
  -> write retrieval_events/results
  -> write answer_citations
  -> write user_feedback
  -> run evals from stored cases
```

Use SQLite now because the project already uses it and the deadline is tight.

The important design rule: use schema names and payloads that can migrate cleanly to Postgres.

### Phase 2: Postgres / Neon For Multi-Tester Demo

When multiple people test from a shared link:

```text
Frontend / UI
  -> App server
  -> Postgres-compatible DB
       chat_sessions
       chat_messages
       agent_runs
       agent_run_steps
       retrieval_events
       retrieval_event_results
       answer_citations
       user_feedback
       eval_cases
       eval_runs
       eval_results
```

Neon is acceptable for a fast external demo if:

- The deployment region is close to the app server.
- We use pooled connection string for normal app traffic.
- We use direct connection string for migrations/admin tasks.
- We do not run heavy dashboard queries synchronously during chat.
- We batch or summarize verbose trace payloads.

Mainland note:

- Neon is not the final mainland-China database answer unless reachability is validated from mainland networks.
- The architecture must keep `DATABASE_URL` provider-neutral.
- Later, the same Postgres schema can move to Tencent Cloud, Alibaba Cloud, Huawei Cloud, AWS China partner cloud, or self-hosted Postgres.

### Phase 3: Add Optional LLMOps Sink

After local telemetry works, add a sink interface:

```python
class TelemetrySink:
    def record_run(...)
    def record_step(...)
    def record_retrieval(...)
    def record_feedback(...)
    def flush(...)
```

Implement:

- `LocalDatabaseTelemetrySink`
- `OpikTelemetrySink`
- `LangfuseTelemetrySink`
- `OpenTelemetryTelemetrySink`

Local database remains source of truth. External sinks are mirrors.

### Phase 4: Production Analytics Split

If usage grows:

```text
Postgres
  transactional product state
  sessions/messages/runs/feedback/eval cases

ClickHouse or equivalent OLAP store
  high-volume trace events
  step-level telemetry
  score time series
  latency/cost dashboards

Object storage
  raw trace payloads
  large context snapshots
  exported eval reports

Queue
  async trace ingestion
  online eval jobs
  LLM-as-judge jobs
```

This mirrors the proven Langfuse-style production pattern without forcing that complexity into the current prototype.

## What To Store In Neon/Postgres

Store:

- session IDs
- user messages
- assistant messages
- answer JSON
- route intent
- source mode
- confidence
- web fallback flag
- citations
- feedback
- eval cases/results
- compact step observations
- latency
- model/provider metadata

Avoid storing synchronously in hot Postgres rows:

- giant prompt bodies
- full extracted source documents
- full retrieved context for every query if it is very large
- binary/multimodal artifacts
- raw HTML/PDF payloads

For now, store small snippets and IDs. The documents already live in local markdown and `documents` table.

## What To Store In Opik/Langfuse Later

Mirror:

- full trace tree
- LLM call input/output
- tool call spans
- retrieval spans
- scores
- human feedback
- prompt versions
- model metadata
- experiment results

Do not make them mandatory for the app to work.

## Request Path Performance Rule

The chat request should not wait on slow observability work.

Synchronous:

- create session if missing
- save user message
- save final assistant response
- save compact run metadata

Optional synchronous if fast:

- save reasoning steps
- save citations
- save feedback

Asynchronous later:

- export to Opik/Langfuse
- run LLM-as-judge evaluation
- aggregate dashboards
- write raw trace blobs
- generate reports

## Evaluation Layers

### Layer 1: Unit And Regression Tests

Already present:

- router tests
- verifier tests
- eval runner tests
- ingestion tests

Need more:

- confidence calibration tests
- source relevance tests
- UI API tracking tests

### Layer 2: Deterministic Agent Eval

For each golden question:

- expected route
- expected source mode
- minimum citations
- allowed source types
- web fallback expected/not expected
- confidence ceiling/floor
- required gap behavior

### Layer 3: Retrieval Eval

For each question:

- top-k relevant source IDs if known
- accepted/rejected ratio
- region match
- source type match
- official-source preference
- citation source coverage

### Layer 4: Answer Eval

Heuristic:

- has answer
- has citation
- no internal implementation terms
- confidence/gaps consistent

LLM-as-judge:

- faithfulness
- answer relevance
- context precision
- context recall
- hallucination
- completeness

### Layer 5: Production Online Eval

From real tester traffic:

- sample traces
- run lightweight heuristic scores
- mark bad/uncertain answers for review
- turn bad traces into eval cases
- compare model/prompt/retrieval changes against this suite

## China And India Compatible Design Rules

- Keep DeepSeek/Qwen/OpenAI-compatible provider adapters, but do not make any Chinese provider the only path.
- Keep at least one India-safe/global provider path available for demos, testing, and judging.
- Keep observability self-hostable.
- Keep database provider-neutral through `DATABASE_URL`.
- Do not depend on Google fonts, Vercel-only services, OpenAI-only evals, or SaaS-only tracing.
- For mainland deployment, test actual network reachability before committing to vendor.
- For India deployment or India-based testers, test actual reachability and policy acceptability before committing to Chinese vendors.
- Avoid sending sensitive user or project data to a model/vendor that may be institutionally restricted in either China or India.
- Prefer swappable adapters over hardcoded services:
  - LLM provider adapter.
  - Embedding provider adapter.
  - Web-search provider adapter.
  - Telemetry/export provider adapter.
  - Database URL adapter.
- For public mainland hosting, plan ICP filing, China cloud, domain, secrets, backups, and logs.
- For India-facing hosting, avoid Chinese-only hard dependencies and validate data, procurement, and institutional policy restrictions before a demo.

## Decision

Use Neon/Postgres-style storage for chat history and product telemetry where reachable and acceptable.

Use Langfuse first as the optional dedicated observability, tracing, and eval dashboard.

Keep Opik as a later option if we need deeper prompt optimization or a second eval workflow.

Do not choose between them. They solve different layers:

```text
Neon/Postgres or compatible Postgres = product memory and system of record
Langfuse = first optional LLMOps inspection/evaluation dashboard
Opik = later optional prompt/eval optimization dashboard
Local telemetry layer = vendor-neutral bridge
```

For the next implementation step, keep improving the local telemetry schema and instrumentation. Then add `DATABASE_URL` when hosted multi-user persistence becomes necessary.
