# Venture Metrics Prototype Progress

Use this file as the handoff note between chats. Keep it short and factual.

## Current Direction

- Pause chatbot/agent work for now.
- Build the project structure and evidence pipeline step by step.
- Use Tavily as the current local extraction path, but keep it replaceable.
- Use DeepSeek as the first LLM provider target, through a provider adapter.
- New requirement: the eventual system must work from mainland China. Do not hardcode Google/OpenAI/Tavily-only assumptions into the core pipeline.
- New requirement: build a proper web UI and plan for deployment, not only a local Streamlit demo.

## Completed

- Read and followed `agents.md`.
- Created initial Python package structure.
- Added `.env.example` for DeepSeek and Tavily.
- Built Excel profiler.
- Built URL extraction helpers.
- Built SQLite raw Excel ingestion.
- Built initial source registry from unique Excel URLs.
- Built Tavily-first source fetcher.
- Created markdown document store at `venture_metrics_agent/data/documents/`.
- Fetched all registered source attempts through Tavily Extract.
- Built local chunk/FTS retrieval index.
- Added local internal-evidence query agent with DeepSeek-compatible provider adapter.
- Added CLI scripts for index build and local question answering.
- Added tests for URL extraction, profiling, and source classification.
- Created local `.venv` and installed current dependencies.

## Generated Artifacts

- `venture_metrics_agent/data/processed/excel_profile_report.json`
- `venture_metrics_agent/data/processed/excel_profile_summary.json`
- `venture_metrics_agent/data/processed/venture_metrics.db`
- `venture_metrics_agent/data/processed/source_registry.csv`
- `venture_metrics_agent/data/documents/source_*.md`

## Latest Counts

- Excel files: 9
- Sheets: 25
- Rows: 661
- URL occurrences: 686
- Source registry records: 674
- Source status:
  - `fetched`: 600
  - `failed`: 74
  - `pending`: 0
- Documents stored:
  - Markdown files: 600
  - SQLite `documents` rows: 600
- Retrieval index:
  - Chunks: 3,559

## Directory Status

- `venture_metrics_agent/app/` exists.
- `venture_metrics_agent/ingestion/` exists.
- `venture_metrics_agent/retrieval/` exists.
- `venture_metrics_agent/llm/` exists.
- `venture_metrics_agent/ui/` exists.
- `venture_metrics_agent/data/raw/` exists.
- `venture_metrics_agent/data/processed/` exists.
- `venture_metrics_agent/data/indexes/` exists.
- `scripts/` exists.
- `tests/` exists.
- `venture_metrics_agent/data/documents/` is where extracted website documents are written.

## Next Small Step

Do not jump into the full agent yet.

Current next step:

1. Improve answer synthesis once DeepSeek is reachable from the local environment.
2. Add web fallback through a replaceable search adapter.
3. Replace the earlier Streamlit-only assumption with a real web app path: FastAPI backend plus a proper frontend.
4. Define deployment resources: China-accessible LLM/search providers, mainland-capable hosting, domain/ICP path, storage, monitoring, and secrets.
5. Failed URLs are preserved in `sources.status = failed` with `error_message`; inspect retry candidates later.

## Notes

- Keep future changes small.
- Avoid overbuilding.
- Prefer one working pipeline stage at a time.
- For mainland China compatibility, treat Tavily as a development extractor, not a required production dependency. The production path should support China-accessible search/extraction and LLM providers through adapters.
- For UI, use Streamlit only for quick internal debugging if needed. The user-facing product should be a proper frontend, likely Next.js or another conventional web app, backed by FastAPI.
- Deployment planning is now in scope. A mainland China deployment will likely require a China-accessible cloud provider and ICP filing for a public domain.
