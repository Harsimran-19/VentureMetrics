# Venture Metrics Prototype

Lightweight local prototype for a Venture Metrics research assistant. The first milestone is the Excel profiler because the source files have unknown sheet formats.

## Current Scope

- Reads every Excel file and sheet in `document_sources/`.
- Scans every cell for URLs.
- Detects likely title, category, region, and notes columns with flexible English/Chinese hints.
- Preserves sample raw rows for traceability.
- Writes a full profiling report and compact summary.
- Fetches source content into local markdown documents.
- Chunks and indexes fetched documents in SQLite FTS.
- Runs a local internal-evidence agent with citations.
- Stores local agent telemetry in SQLite for sessions, messages, runs, reasoning steps, retrieval events, citations, feedback, and eval records.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Profile Excel Sources

```bash
python scripts/profile_excels.py document_sources
```

Outputs:

- `venture_metrics_agent/data/processed/excel_profile_report.json`
- `venture_metrics_agent/data/processed/excel_profile_summary.json`

## Ingest Raw Rows And Source Registry

```bash
python scripts/ingest_excels.py document_sources --rebuild
```

Output database:

- `venture_metrics_agent/data/processed/venture_metrics.db`
- `venture_metrics_agent/data/processed/source_registry.csv`

## Fetch Documents With Tavily

Tavily is the current development extractor for source URLs. It is replaceable because the deployed system must support mainland China-compatible providers.

```bash
python scripts/fetch_sources.py --limit 25 --batch-size 5
```

Fetch all remaining pending sources in one command:

```bash
python scripts/fetch_sources.py --limit 1000 --batch-size 5
```

Outputs:

- Markdown documents in `venture_metrics_agent/data/documents/`
- Extracted text rows in the SQLite `documents` table
- Updated source statuses in `source_registry.csv`

## Build The Local Retrieval Index

```bash
PYTHONPATH=. python scripts/build_index.py --rebuild
```

Current local run created 3,559 chunks from 600 fetched documents.

## Ask The Local Agent

With DeepSeek configured in `.env`, the agent calls the OpenAI-compatible DeepSeek API. If DeepSeek is unavailable locally, it still returns an extractive answer with retrieved evidence and citations.

```bash
PYTHONPATH=. python scripts/query_agent.py "Which sources are related to Hong Kong entrepreneurship support?"
```

Useful local demo questions:

```bash
PYTHONPATH=. python scripts/query_agent.py "Which sources mention startup funding or grants?"
PYTHONPATH=. python scripts/query_agent.py "Which sources are official government or university sources?"
PYTHONPATH=. python scripts/query_agent.py "What data gaps exist in the current sample files?"
```

## Test The Reasoning Controller

The reasoning path is a reasoning-first test harness. It routes the message before using tools, then decides whether to inspect the local corpus or use web search. This is separate from the legacy linear agent so both can be compared.

```bash
PYTHONPATH=. python scripts/query_reasoning_agent.py --no-llm "hi"
PYTHONPATH=. python scripts/query_reasoning_agent.py --no-llm --no-web "Which sources mention startup funding or grants?"
```

When web search is used, the reasoning path stores useful web results into the local source registry and index for reuse. For throwaway tests, disable that mutation:

```bash
PYTHONPATH=. python scripts/query_reasoning_agent.py --no-llm --no-remember-web "What are the latest Hong Kong startup grants?"
```

Compare both architectures on the same question:

```bash
PYTHONPATH=. python scripts/compare_agents.py --no-llm "hi"
PYTHONPATH=. python scripts/compare_agents.py --no-llm --no-web --no-remember-web "Which sources mention startup funding or grants?"
```

The reasoning response includes a `reasoning_trace` with structured route, plan, tool, observation, and verification decisions. Raw chain-of-thought is not exposed.

Run the fixed reasoning eval suite against a temporary database copy:

```bash
PYTHONPATH=. python scripts/run_reasoning_eval.py
make eval
```

By default, web search is simulated so the eval does not require network access or mutate source data. `make eval` records the scored eval summary into the local observability tables.

## Inspect Local Observability

Every agent query still writes the legacy `query_logs` row, but it also writes a richer local telemetry record into SQLite. This local schema is the source of truth; Langfuse is available as an optional exporter, and Opik can be added later if needed.

```bash
make telemetry-status
PYTHONPATH=. python scripts/telemetry_status.py --json
```

Tracked tables include:

- `chat_sessions`
- `chat_messages`
- `agent_runs`
- `agent_run_steps`
- `retrieval_events`
- `retrieval_event_results`
- `answer_citations`
- `user_feedback`
- `eval_cases`
- `eval_runs`
- `eval_results`

### Optional Langfuse Export

Langfuse is supported as a best-effort dashboard sink. A failed Langfuse export does not break the local agent or SQLite telemetry.

Install dependencies, then set:

```bash
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_ENVIRONMENT=local
LANGFUSE_RELEASE=prototype
```

Then run:

```bash
make reasoning-query QUESTION='Which sources mention startup funding or grants?'
make telemetry-status
```

`make telemetry-status` reports whether Langfuse is enabled, configured, and whether the SDK is installed.

## Run The Local Web UI

```bash
PYTHONPATH=. python scripts/serve_agent.py --port 8000
```

Open `http://127.0.0.1:8000`. The web UI uses the same local agent and DeepSeek adapter as the CLI.

## Deploy

This app is a long-running Python server with a local SQLite database. The practical demo host is Railway.

Vercel is a bad fit for the current app because it runs Python as serverless functions with a read-only filesystem outside writable `/tmp`, so the local SQLite file is not a stable deployment target. DigitalOcean App Platform is also a poor fit for the current SQLite setup because App Platform instances do not provide persistent local storage.

Railway is the best fit for the current codebase because it supports long-running web services and persistent volumes.

### Railway

The repository now includes:

- `Dockerfile`
- `.dockerignore`
- `scripts/start_server.sh`

Deploy steps:

1. Push the repo to GitHub.
2. Create a new Railway project from the GitHub repo.
3. Railway will detect the `Dockerfile` and build the service automatically.
4. In Railway, add these environment variables:

```bash
HOST=0.0.0.0
DB_PATH=/data/venture_metrics.db
LLM_API_KEY=...
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
TAVILY_API_KEY=...
```

5. Attach a Railway volume and mount it at `/data`.
6. Deploy the service.

The startup script copies the bundled demo database into `DB_PATH` on first boot if the mounted volume is empty. After that, the Railway volume keeps the SQLite file across restarts and redeploys.

### Local Docker Run

```bash
docker build -t venture-metrics .
docker run --rm -p 8000:8000 \
  -e HOST=0.0.0.0 \
  -e DB_PATH=/data/venture_metrics.db \
  -v "$(pwd)/.deploy-data:/data" \
  venture-metrics
```

Then open `http://127.0.0.1:8000`.

## Deployment Direction

- Local first: SQLite + FTS + DeepSeek adapter.
- Demo deployment: Railway with a mounted volume for SQLite.
- User-facing UI: proper web frontend backed by FastAPI remains the next architecture step.
- Mainland production path needs a China-accessible cloud/provider plan and likely ICP filing for a public mainland-hosted domain.
- Keep LLM, embeddings, search, and extraction behind adapters so DeepSeek and mainland-compatible alternatives can be swapped.

## Tests

```bash
PYTHONPATH=. pytest
```

## Next Steps

1. Improve answer synthesis once DeepSeek can be reached from the local environment.
2. Add web fallback through a replaceable search adapter.
3. Add FastAPI endpoints for query/source stats.
4. Build the proper frontend.
5. Package for demo deployment.
