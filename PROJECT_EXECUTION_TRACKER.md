# Venture Metrics Execution Tracker

Last updated: 2026-06-02

## Submission Objective

Deliver a presentation-ready Venture Metrics AI research prototype that proves:

- Excel/source-map ingestion.
- Evidence library creation.
- Cited AI answers.
- Confidence and gaps.
- Internal evidence first.
- Controlled web fallback.
- Usage tracking and evaluation.
- Mainland-compatible architecture direction.

The target is not a full production platform yet. The target is a credible v0.1 system that shows the project can become TEA's strategic innovation and entrepreneurship data infrastructure.

## Current Status

- [x] Excel profiler.
- [x] Raw Excel ingestion.
- [x] URL extraction.
- [x] Source registry.
- [x] Tavily-based source extraction.
- [x] Markdown document store.
- [x] SQLite database.
- [x] SQLite FTS index.
- [x] Legacy internal RAG agent.
- [x] Reasoning controller.
- [x] Basic local web UI.
- [x] Tests passing locally.
- [ ] Strong tracking and evaluation.
- [ ] Better retrieval quality.
- [ ] Better confidence calibration.
- [ ] Better UI polish.
- [ ] Mainland-compatible deployment plan.

## Immediate Priority: Tracking And Evaluation

### Phase 1: Local Product Telemetry

- [x] Add `chat_sessions` table.
- [x] Add `chat_messages` table.
- [x] Add `agent_runs` table.
- [x] Add `agent_run_steps` table.
- [x] Add `retrieval_events` table.
- [x] Add `retrieval_event_results` table.
- [x] Add `answer_citations` table.
- [x] Add `user_feedback` table.
- [x] Generate browser/session ID in UI.
- [x] Log user messages.
- [x] Log assistant messages.
- [x] Log route decisions.
- [x] Log reasoning trace.
- [x] Log retrieved chunks and accepted/rejected status.
- [x] Log citations.
- [x] Log web fallback decisions and errors.
- [ ] Log latency.
- [ ] Add feedback buttons in UI.
- [ ] Add `/api/feedback`.
- [x] Add a local report command for recent runs.

### Phase 2: Evaluation Harness

- [ ] Add eval case seed file.
- [ ] Expand eval suite to 20-30 project-specific prompts.
- [ ] Add deterministic route/source-mode/citation checks.
- [ ] Add retrieval relevance checks.
- [ ] Add confidence calibration checks.
- [x] Store eval runs in DB.
- [x] Store eval results in DB.
- [x] Add pass/fail summary CLI.
- [x] Add `make eval`.
- [ ] Add demo-ready eval report export.

### Phase 3: Observability Adapter

- [ ] Keep local DB telemetry as source of truth.
- [x] Add telemetry sink interface.
- [x] Add optional Langfuse exporter.
- [ ] Add optional Opik exporter.
- [ ] Add optional OpenTelemetry-compatible event naming.
- [ ] Make all external observability optional via env vars.

## AI Quality Improvements

- [ ] Improve retrieval query rewriting.
- [ ] Add official-source preference for policy/funding questions.
- [ ] Reject generic navigation/menu chunks.
- [ ] Reduce `High` confidence when accepted evidence is mostly low reliability.
- [ ] Require stronger region matching for Hong Kong/Shenzhen/GBA questions.
- [ ] Add source-type filters for government/university/science-park questions.
- [ ] Add citation support checks.
- [ ] Add web fallback only when evidence is genuinely weak/current/external.
- [ ] Add answer style cleanup for extractive fallback.
- [ ] Add LLM-as-judge evaluation later through provider adapter.

## UI Improvements

- [ ] Add persistent session ID.
- [ ] Add feedback buttons.
- [ ] Add answer run metadata in source drawer.
- [ ] Add clearer source drawer.
- [ ] Add evaluation/admin page or local report view.
- [ ] Improve mobile layout.
- [ ] Improve loading and error states.
- [ ] Hide internal trace from normal users.
- [ ] Add demo prompts grouped by use case.
- [ ] Avoid external fonts/CDNs for mainland compatibility.

## Database And Deployment Direction

- [ ] Keep SQLite default for local demos.
- [ ] Add `DATABASE_URL` support.
- [ ] Add Postgres-compatible storage layer.
- [ ] Test Neon for fast public demo if acceptable.
- [ ] Keep China-hosted Postgres option open for mainland deployment.
- [ ] Validate database/provider reachability from mainland China.
- [ ] Validate database/provider reachability from India.
- [ ] Keep DeepSeek/OpenAI-compatible provider adapter.
- [ ] Keep at least one India-safe/global LLM provider path available.
- [ ] Keep search provider adapter.
- [ ] Add Baidu/Bing/Sogou/360-compatible search path later.
- [ ] Add India-safe/global search fallback path.
- [ ] Avoid hard dependency on Vercel-only deployment.
- [ ] Evaluate Railway/HK/Singapore demo hosting.
- [ ] For mainland public launch, plan ICP/domain/cloud/secrets/backups/logging.
- [ ] For India-facing launch, avoid Chinese-only hard dependencies and validate policy/data restrictions.

## Makefile And Developer Experience

- [x] Add Makefile.
- [ ] Add README section for Makefile.
- [ ] Add one-command local demo flow.
- [ ] Add one-command eval.
- [ ] Add one-command Docker run.
- [ ] Add deployment notes.

## Suggested Two-Day Submission Checklist

- [x] Tracking tables implemented.
- [ ] UI records session and feedback.
- [ ] Recent run report works.
- [ ] Eval suite expanded and runnable.
- [ ] Retrieval overconfidence reduced.
- [ ] README updated with exact demo commands.
- [ ] Demo script finalized.
- [ ] Known limitations documented honestly.
- [ ] Presentation story aligned to TEA strategic platform vision.
