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
