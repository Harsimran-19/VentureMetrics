# Venture Metrics — Current Architecture

> Last updated: 2026-06-03  
> Status: **Working prototype + reasoning controller** — pipeline complete, UI live, LLM/web fallback adapter-ready, reasoning-first path under test.

---

## Architecture Classification

The current product is **not a full Recursive Language Model (RLM)** implementation.

The accurate architecture label is:

```text
Internal-first RAG with an RLM-inspired deterministic research controller.
```

In practical terms:

- **RAG is implemented** as the evidence infrastructure: Excel source map, source registry, fetched documents, chunks, SQLite FTS retrieval, citations, and answer synthesis.
- **RLM is not fully implemented** because there is no persistent REPL, no model-written code loop over the corpus, and no recursive worker model calls.
- **The reasoning controller is RLM-inspired** because it routes, plans, selects tools, observes, verifies, and answers instead of blindly retrieving context for every message.
- **The controller is deterministic/branching**, not true ReAct. Python decides the tool flow; the LLM does not drive a Thought/Action/Observation loop.

For a detailed terminology breakdown, see [ARCHITECTURE_TAXONOMY.md](ARCHITECTURE_TAXONOMY.md).

---

## Overview

Venture Metrics is a Perplexity-style research assistant focused on GBA/Hong Kong startup and venture data.
It ingests Excel files from Google Drive, builds an evidence library from the URLs inside those files, and answers questions with cited sources and a confidence label.

The system is designed to be **mainland China compatible** from the start:
- No hard dependency on OpenAI, Google, or Tavily in the core pipeline.
- Every external call (LLM, search, extraction) goes through an adapter that can be swapped.
- Storage and indexing are fully local (SQLite + FTS5).

---

## Data Flow

```
Google Drive Excel files (document_sources/)
        │
        ▼
 [Excel Profiler]          — scans all sheets, detects columns, extracts URLs
        │
        ▼
  [Raw Excel Ingestion]    — stores every row as raw JSON in SQLite
        │
        ▼
  [Source Registry]        — deduplicates URLs, classifies source type + reliability
        │
        ▼
  [Fetcher]                — calls Tavily Extract API to pull page content
        │
        ▼
  [Document Store]         — saves markdown files + rows in SQLite documents table
        │
        ▼
  [Chunker + FTS Index]    — splits docs into overlapping chunks, inserts into SQLite FTS5
        │
        ▼
  [Research Agent]
     ├── Internal retrieval via FTS5 (BM25 + LIKE fallback)
     ├── Evidence scorer → confidence: High / Medium / Low / Insufficient
     ├── Web fallback via Tavily Search (only when internal evidence is insufficient)
     └── LLM synthesis via DeepSeek-compatible adapter (or extractive fallback)
        │
        ▼
  [Local Web UI]           — ThreadingHTTPServer serving HTML+JS SPA at localhost:8000
```

## Reasoning Direction

The original agent is a linear retrieval pipeline. The experimental reasoning path moves toward a reasoning-first architecture where retrieval and web search are tools, not automatic steps.

```
User message
        │
        ▼
 [Router]                  — casual/help/clarification/research/current/external
        │
        ├── no research ──▶ Direct response, no tools
        │
        ▼
 [reasoning Controller]          — creates a structured research plan
        │
        ▼
 [Tool Loop]
     ├── Internal corpus search tool
     ├── Web search tool, gated by route + evidence state
     └── Evidence verifier
        │
        ▼
 [Answer Synthesis]        — cited answer, confidence, gaps, trace
```

The current implementation lives in `venture_metrics_agent/reasoning/`:

| Module | Role |
|---|---|
| `router.py` | Classifies messages before tool use. Greetings and help questions do not retrieve or search. |
| `workspace.py` | Stores structured route/plan/tool/observation/verification steps as `reasoning_trace`. |
| `planner.py` | Generates bounded internal-search query variants for the reasoning loop. |
| `tools.py` | Exposes local corpus search and web search as controller-selected tools. |
| `verifier.py` | Filters weak/off-topic evidence before confidence, web escalation, and final citations. |
| `web_memory.py` | Persists controlled web-search results into `sources`, `documents`, local markdown, and FTS chunks. |
| `eval_runner.py` | Runs fixed reasoning eval cases on a temporary DB copy and compares against the legacy agent. |
| `controller.py` | Orchestrates route → plan → act → observe → verify → answer. |

Run it directly:

```bash
PYTHONPATH=. python scripts/query_reasoning_agent.py --no-llm "hi"
PYTHONPATH=. python scripts/query_reasoning_agent.py --no-llm --no-web "Which sources mention startup funding or grants?"
```

Use `--no-remember-web` during throwaway tests if a web-enabled run should not mutate the local source registry.

Run the fixed eval suite:

```bash
PYTHONPATH=. python scripts/run_reasoning_eval.py
```

The default eval uses simulated web evidence so it is deterministic and does not require network access.

Compare it with the legacy path:

```bash
PYTHONPATH=. python scripts/compare_agents.py --no-llm "hi"
```

The old retrieval system is currently used only as the implementation behind the internal corpus search tool. The experiment is to validate whether the reasoning controller should replace the linear agent as the product brain.

This is a bridge architecture, not full RLM. A true RLM experiment would add a persistent read-only execution environment, model-written corpus inspection code, recursive worker calls, and explicit stopping/guardrail primitives.

---

## Directory Structure

```
VentureMetrics/
├── venture_metrics_agent/
│   ├── app/
│   │   └── config.py                 # Project paths (root, DB, documents dir)
│   ├── ingestion/
│   │   ├── excel_profiler.py         # Profile all Excel files/sheets
│   │   ├── excel_ingest.py           # Raw row ingestion + source registry upsert
│   │   ├── url_extractor.py          # Regex URL extraction + normalisation
│   │   ├── source_registry.py        # SQLite schema, URL canonicalisation, source classification
│   │   └── fetcher.py                # Tavily Extract fetcher → document store
│   ├── retrieval/
│   │   ├── chunker.py                # Document chunking + FTS5 index build
│   │   ├── retriever.py              # FTS5 BM25 + LIKE fallback retrieval
│   │   ├── evidence_scorer.py        # Confidence scoring based on source quality
│   │   ├── web_search.py             # Tavily Search adapter (replaceable)
│   │   └── agent.py                  # Orchestration: retrieve → score → fallback → answer
│   ├── llm/
│   │   ├── provider.py               # OpenAI-compatible HTTP adapter (DeepSeek default)
│   │   └── prompts.py                # System prompt + answer generation prompt
│   ├── ui/
│   │   └── local_server.py           # ThreadingHTTPServer + embedded HTML/JS SPA
│   └── data/
│       ├── raw/                      # (reserved for raw file copies)
│       ├── processed/
│       │   ├── venture_metrics.db    # Main SQLite database
│       │   ├── source_registry.csv   # Exported source registry
│       │   ├── excel_profile_report.json
│       │   └── excel_profile_summary.json
│       ├── documents/                # source_000001.md … source_N.md (fetched content)
│       └── indexes/                  # (reserved for future vector store)
├── document_sources/                 # Input Excel files (9 files from Google Drive)
├── scripts/
│   ├── profile_excels.py             # CLI: run Excel profiler
│   ├── ingest_excels.py              # CLI: ingest Excel rows + source registry
│   ├── fetch_sources.py              # CLI: fetch pending sources via Tavily Extract
│   ├── build_index.py                # CLI: chunk documents + build FTS index
│   ├── query_agent.py                # CLI: ask a question from the terminal
│   ├── serve_agent.py                # CLI: start the local web UI
│   └── start_server.sh               # Docker entrypoint shell script
├── tests/
│   ├── test_excel_profiler.py
│   ├── test_url_extraction.py
│   └── test_source_registry.py
├── Dockerfile                        # python:3.14-slim, exposes port 8000
├── .env / .env.example               # LLM_* and TAVILY_API_KEY
├── requirements.txt                  # pandas, openpyxl, pytest
├── agents.md                         # Full product spec / agent rules
├── PROJECT_PROGRESS.md               # Handoff notes between sessions
└── ARCHITECTURE.md                   # This file
```

---

## Module Responsibilities

### `ingestion/`

| Module | Role |
|---|---|
| `excel_profiler.py` | Reads all `.xlsx/.xlsm/.xls` files, profiles every sheet: column names, row count, URL counts, empty-column ratio, sample rows. Outputs JSON report. |
| `url_extractor.py` | Regex-based URL extraction from any cell value. Normalises trailing punctuation and `www.` prefixes. Works on arbitrary row formats. |
| `excel_ingest.py` | Iterates every file/sheet/row. Stores raw JSON rows in `raw_rows`. Upserts unique URLs into `sources` with initial classification. Exports CSV registry. |
| `source_registry.py` | Defines the SQLite schema (all 7 tables). Canonicalises URLs (strips fragments, normalises case). Classifies source type and reliability from domain heuristics. |
| `fetcher.py` | Calls Tavily Extract API in batches of 5. Writes `source_XXXXXX.md` markdown files with YAML front-matter. Inserts `documents` rows. Marks sources as `fetched / failed / skipped`. |

### `retrieval/`

| Module | Role |
|---|---|
| `chunker.py` | Splits documents into ~3,600-char chunks with 500-char overlap. Inserts into `chunks` table and `chunks_fts` virtual table (SQLite FTS5). |
| `retriever.py` | Two-stage search: FTS5 BM25 first, LIKE-based term scoring fallback. Returns `RetrievalResult` dataclasses with full source metadata. |
| `evidence_scorer.py` | Scores retrieved chunks by source type and reliability. Returns `EvidenceAssessment` with confidence label and `needs_web_fallback` flag. |
| `web_search.py` | Tavily Search adapter. Converts results to `WebResult` dataclasses. Raises `RuntimeError` if API key is missing (gracefully caught by agent). |
| `agent.py` | Main orchestrator. Calls retriever → scorer → web fallback → LLM or extractive synthesis. Logs every query to `query_logs`. Returns structured JSON answer. |

### `llm/`

| Module | Role |
|---|---|
| `provider.py` | HTTP adapter for any OpenAI-compatible `/chat/completions` endpoint. Reads `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, and `LLM_REASONING_MODEL` from `.env`. Default: DeepSeek chat + DeepSeek reasoner. |
| `prompts.py` | Research, routing, contextualization, and answer prompts. Chat history is used for both routing and answer synthesis. |

### `ui/`

| Module | Role |
|---|---|
| `local_server.py` | Python stdlib `ThreadingHTTPServer`. Serves a single-file HTML/JS SPA. Two API endpoints: `GET /api/status` and `POST /api/query`. No external frontend framework or build step. |

---

## Database Schema (SQLite)

```
excel_files       — one row per uploaded Excel file
excel_sheets      — one row per sheet in each file
raw_rows          — one row per Excel data row, full JSON preserved
sources           — one row per unique URL (source registry)
documents         — one row per fetched+extracted page
chunks            — text chunks linked to documents and sources
chunks_fts        — SQLite FTS5 virtual table (BM25 index over chunks)
query_logs        — every answered question logged with citations and confidence
```

**Key relationships:**
- `raw_rows → excel_files, excel_sheets`
- `sources` are extracted from `raw_rows`
- `documents → sources`
- `chunks → documents, sources`
- `chunks_fts` mirrors `chunks` for full-text search

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve the HTML/JS SPA |
| `GET` | `/api/status` | Return document, chunk, source, and failed-URL counts |
| `POST` | `/api/query` | Accept `{question, top_k, use_web_fallback, history}`, return full answer JSON |

### Answer Response Shape

```json
{
  "answer": "...",
  "confidence": "High | Medium | Low | Insufficient evidence",
  "source_mode": "internal_only | internal_plus_web | web_only | insufficient",
  "citations": [
    { "title": "...", "url": "...", "source_type": "...", "reliability": "..." }
  ],
  "gaps": ["..."],
  "used_web_fallback": true,
  "retrieved_evidence": [...],
  "web_evidence": [...]
}
```

---

## External Dependencies

| Dependency | Used For | Replaceable? |
|---|---|---|
| **Tavily Extract** (`api.tavily.com/extract`) | Fetching page content from Excel URLs | Yes — swap `fetcher.py` |
| **Tavily Search** (`api.tavily.com/search`) | Web fallback when internal evidence is insufficient | Yes — swap `web_search.py` |
| **DeepSeek** (OpenAI-compatible API) | LLM answer synthesis | Yes — any OpenAI-compatible endpoint via `LLM_BASE_URL` |
| **pandas + openpyxl** | Excel parsing | No — core dependency |
| **SQLite FTS5** | Full-text search index | No — built into Python stdlib sqlite3 |

> All external API calls use Python stdlib `urllib` only — no third-party HTTP client required.

---

## Environment Variables

```env
# LLM (any OpenAI-compatible provider)
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
LLM_REASONING_MODEL=deepseek-reasoner

# Web fallback + extraction
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-...
```

The system degrades gracefully:
- **No `LLM_API_KEY`** → extractive (non-LLM) answer synthesis is used automatically.
- **No `TAVILY_API_KEY`** → web fallback is skipped; gap is noted in the response.

---

## Confidence Scoring Logic

```
Base score = 0
+2  source type is government / university / science_park
+1  source type is company / investor
+1  multiple independent sources (≥2 unique sources)
-1  all sources are low / unknown reliability
-1  question asks for current/latest data

Score ≥ 3  →  High      (sufficient, no web fallback)
Score ≥ 1  →  Medium    (sufficient, no web fallback)
Score < 1  →  Low       (insufficient, triggers web fallback)
No results →  Insufficient evidence (triggers web fallback)
```

Web fallback is also forced if the question contains current-data keywords: `latest`, `current`, `today`, `recent`, `2026`, `now`, `最新`, `目前`, `今年`.

---

## Source Classification

Domain heuristics applied at ingestion time to every URL:

| Pattern match | Source type | Reliability |
|---|---|---|
| `gov`, `policy`, `grant` | government | very_high |
| `edu`, `hku`, `cuhk`, `cityu`, `polyu`, `hkust`, `university` | university | high |
| `hkstp`, `cyberport`, `sciencepark` | science_park | high |
| `vc`, `venture`, `capital`, `invest`, `fund` | investor | medium_high |
| `crunchbase`, `pitchbook`, `cbinsights` | database | medium |
| `report`, `whitepaper`, `pdf` | report | medium |
| `news`, `media`, `reuters`, `bloomberg`, `scmp` | media | medium |
| *(no match)* | unknown | low |

Classification is stored at source-registry time and can be corrected manually later.

---

## Current Data Snapshot

| Metric | Count |
|---|---|
| Excel files | 9 |
| Sheets | 25 |
| Rows | 661 |
| URL occurrences | 686 |
| Unique source records | 674 |
| Fetched successfully | 600 |
| Failed / blocked | 74 |
| Documents stored | 600 |
| FTS chunks | 3,559 |

---

## Running Locally

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Copy and fill in API keys
cp .env.example .env

# 3. (Skip if DB already built) Run pipeline
python scripts/ingest_excels.py
python scripts/fetch_sources.py
python scripts/build_index.py

# 4. Start the UI
PYTHONPATH=. .venv/bin/python scripts/serve_agent.py
# → http://127.0.0.1:8000
```

### Docker

```bash
docker build -t venture-metrics .
docker run -p 8000:8000 \
  -e LLM_API_KEY=sk-... \
  -e TAVILY_API_KEY=tvly-... \
  venture-metrics
```

---

## Known Gaps / Next Steps

1. **LLM reachability** — DeepSeek must be reachable from the deployment environment. For mainland China, validate connectivity before demo.
2. **Web fallback** — Tavily is a development adapter. A China-accessible search API (Baidu/Bing/360) must be wired through the same `web_search.py` interface for production.
3. **Extraction** — Tavily Extract is used; no Playwright/PDF fallback yet. Failed URLs (74) could be retried with a browser-render path.
4. **No vector embeddings** — retrieval is BM25 FTS5 only. Dense vector search (Chroma/Qdrant) is planned but not built.
5. **UI** — the current SPA is a single embedded Python string. A proper Next.js frontend backed by FastAPI is the planned production path.
6. **Deployment** — no CI/CD, domain, ICP filing, or managed secrets. Planned once the frontend is production-ready.
7. **Source type correction** — domain heuristics can misclassify. A manual review workflow is not yet built.

---

## Mainland China Compatibility Status

| Concern | Current status |
|---|---|
| LLM provider | ✅ Adapter-based; DeepSeek is China-accessible |
| Embedding provider | ⚠️ Not built yet; plan as local/self-hosted |
| Web search | ⚠️ Tavily only (not guaranteed from mainland); adapter is replaceable |
| Content extraction | ⚠️ Tavily Extract only; replaceable |
| Storage | ✅ SQLite — fully local, no managed service |
| UI server | ✅ stdlib only, no external CDN dependencies |
| ICP filing | ❌ Not started; required for public mainland domain |
