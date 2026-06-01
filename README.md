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

Each user message is exported as its own Langfuse trace. The browser UI sends a stable `session_id` for the active chat, and Langfuse groups those per-message traces under one session. Use the Langfuse Sessions view, or filter traces by the same session id, when you want to inspect a full chat.

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

Do not manually set `PORT=8000` on Railway unless the public domain target port is also set to `8000`. The preferred setup is to leave `PORT` undefined in Railway so Railway injects the correct value and the startup script binds to it. Railway's 502 "Application failed to respond" error usually means the service is listening on a different host/port than the edge proxy expects.

If Railway shows a 502 while logs say the app is running:

- Confirm the log says `Research prototype UI running at http://0.0.0.0:<PORT>`.
- In Railway, open the service domain settings and make sure the target port matches that logged port.
- If you copied `.env.example`, remove any manually configured `PORT` variable from Railway and redeploy.
- Use `/api/status` as a lightweight health check path.

### Zeabur (Recommended for Mainland China)

Zeabur is a PaaS similar to Railway that is highly optimized for Asia-Pacific routing, making it an excellent choice for serving users in mainland China.

#### Signup & Verification for Developers in India (+91)
1. Sign up on [Zeabur](https://zeabur.com) using your GitHub account.
2. When deploying your first service, Zeabur requires account verification.
3. **Verification Options:**
   - **Credit Card (Instant):** Verify using a credit card (supports international Visa/Mastercard/Amex/etc., no Chinese card required).
   - **Phone Verification (+91):** If you choose phone verification, enter your +91 Indian phone number.
   - **Manual Activation Bypass:** If the SMS code does not arrive or the form returns an error due to regional restrictions, email **contact@zeabur.com** or post on the [Zeabur Community Forum](https://zeabur.com/docs/en/help/community). The support team regularly activates accounts manually for developers facing regional SMS issues.

#### Deployment Steps
1. Click **New Project** in your Zeabur dashboard.
2. Select your GitHub repository and choose the target branch. Zeabur will automatically detect the root `Dockerfile` and start building.
3. Choose a deployment region close to mainland China:
   - **GCP Taiwan** (Asia-East) or **AWS Tokyo** (Asia-Northeast) for optimal latency.
   - **AWS Singapore** (Asia-Southeast) as an alternative.
4. Add these environment variables under the service settings:
   ```bash
   HOST=0.0.0.0
   DB_PATH=/data/venture_metrics.db
   LLM_API_KEY=your_deepseek_api_key
   LLM_BASE_URL=https://api.deepseek.com
   LLM_MODEL=deepseek-chat
   TAVILY_API_KEY=your_tavily_api_key
   ```
5. Attach a persistent volume to store the SQLite database:
   - Under service settings, go to **Volumes**.
   - Click **Add Volume** and set the mount path to `/data`.
6. Set up a domain:
   - Under the **Domains** tab, click **Generate Domain** to get a free `*.zeabur.app` subdomain (which is highly reachable in China) or bind your own custom domain.

---

### Koyeb (Alternative PaaS)

Koyeb is a developer-friendly PaaS with built-in persistent volumes and Asia regions.

#### Signup & Verification for Developers in India (+91)
1. Sign up on [Koyeb](https://koyeb.com) using GitHub or email.
2. Koyeb uses automated bot detection. If automatic verification succeeds, no card or phone number is required.
3. If flagged for verification, Koyeb will ask you to link a credit card. It does **not** force phone number verification.

#### Deployment Steps
1. Create a new service and select **GitHub** as the deployment method.
2. Select your repository and configure it to build using **Docker**.
3. Choose **Tokyo** (`tyo`) or **Singapore** (`sin`) as the deployment region.
4. Add the required environment variables (same as Zeabur/Railway above).
5. Attach a persistent volume with a mount path of `/data`.
6. Define port `8000` as the HTTP port for the web service.

---

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
