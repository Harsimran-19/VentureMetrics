# Project: Venture Metrics Perplexity-like Prototype
# Purpose: Use this as the agent prompt/spec inside the editor.
# Mode: Plan-first implementation. Do not overbuild.

You are an engineering agent building the first prototype for the Venture Metrics AI chatbot.

The user has a Google Drive folder containing 9 Excel files. Some files have multiple sheets. Sheet formats are unknown and may not follow the same column structure. Many rows contain links to articles, reports, policy pages, websites, or other public sources.

The goal is NOT to build the final product. The goal is to build a working prototype that proves this workflow:

User question
→ search indexed internal/sample data first
→ if internal evidence is missing or weak, search public web sources
→ extract and compare sources
→ answer with citations, confidence level, and unresolved gaps
→ store useful new sources for future reuse

This should feel like a lightweight Perplexity-style research assistant, but focused on Venture Metrics data.

---

## 1. Core Product Behaviour

The chatbot must follow this order:

1. Search indexed Excel-derived sources first.
2. Search indexed article/document content extracted from the Excel links.
3. Only use web search fallback when internal evidence is missing, incomplete, outdated, or weak.
4. Return answers with source citations.
5. Show a confidence label:
   - High
   - Medium
   - Low
   - Insufficient evidence
6. Store useful external sources into a source registry.

Do not answer important factual questions only from model memory.

---

## 2. Important Design Principle

The Excel files are not the final knowledge base.

They are the source map.

The real knowledge base should be created from:

- raw Excel rows,
- links found inside Excel rows,
- extracted article/report/page content,
- source metadata,
- future web fallback results.

So the prototype should not only “chat with Excel.”
It should turn Excel links into an indexed evidence library.

---

## 3. High-Level Architecture

Google Drive Excel files
→ Excel profiler
→ raw row store
→ URL extraction
→ source registry
→ article/document fetcher
→ text extraction and cleaning
→ chunking and embeddings
→ vector database
→ chat agent
→ cited answer with confidence

Recommended prototype stack:

- Backend: FastAPI
- UI: proper web frontend for the user-facing product; Streamlit only for quick internal debugging if useful
- Excel parsing: pandas + openpyxl
- URL extraction: regex + flexible column detection
- Content extraction: trafilatura first
- Browser fallback: Playwright only when needed
- Vector database: Chroma for fastest setup, Qdrant if already preferred
- Structured database: SQLite for very fast local prototype OR PostgreSQL/Supabase if already available
- RAG framework: LlamaIndex or LangChain
- Search fallback: Tavily, Bing, SerpAPI, or a replaceable custom adapter
- LLM layer: provider adapter, not hardcoded

Use a provider adapter so the model can later switch to Qwen, Hunyuan, ERNIE, GLM, Kimi, DeepSeek, or another OpenAI-compatible provider.

For mainland China usage, the default production-minded path should be:

- LLM: DeepSeek, Qwen, Hunyuan, ERNIE, GLM, Kimi, or another reachable OpenAI-compatible endpoint.
- Embeddings: provider adapter with a local/self-hosted fallback where possible.
- Search fallback: adapter interface that can support Baidu/Bing/Sogou/360/search APIs or a manually configured enterprise search source.
- Extraction: normal HTTP/PDF extraction first, then browser rendering only when necessary.
- Storage/indexing: local SQLite/Chroma for prototype; avoid managed services that cannot be reached from the target environment unless explicitly configured.

---

## 4. Non-Goals

Do not build these in the first prototype:

- polished production UI
- full GBA startup database
- perfect entity resolution
- login/auth
- payment/subscription
- admin panel
- public mainland deployment as a first prototype task, unless the user explicitly moves deployment into scope
- full compliance/legal memo
- advanced data visualization
- automated crawling of the entire web

The first prototype is successful if it can ingest the sample Excel files, fetch content from links, answer from indexed evidence, cite sources, use web fallback, and mark confidence.

Important mainland China constraint:

- Public mainland deployment is still not required for the first prototype.
- However, the architecture must be mainland-compatible from the start.
- Do not hardcode providers that may be unavailable or unreliable from mainland China.
- Keep LLM, embedding, search, web fetch, and extraction behind adapters.
- Prefer provider options that can run from mainland China or can be self-hosted/on-premise.
- Treat Tavily and other external web-search APIs as replaceable prototype adapters, not core product dependencies.
- Validate provider/network availability from the target mainland environment before demo or deployment decisions.
- If deployment is brought into scope, plan for cloud hosting, domain, ICP filing where required, secrets management, storage/backups, logging, and provider quotas.

---

## 5. Step-by-Step Build Plan

### Step 1: Create Excel Profiler

Build a script/service that reads all Excel files and all sheets.

It should output:

- file name
- sheet name
- column names
- row count
- detected URL columns
- number of URLs
- sample rows
- empty column ratio
- duplicate URL count

Do not assume fixed columns.

Use flexible detection:

- scan every cell for URLs
- detect likely title columns using names like title, name, article, report, topic, 标题, 名称, 项目, 文件
- detect category columns using names like category, type, sector, region, city, 分类, 类型, 地区, 城市
- preserve the full row as raw JSON

Output a profiling report before building ingestion logic.

### Step 2: Build Raw Excel Ingestion

For every row in every sheet, store:

- raw_row_id
- file_name
- sheet_name
- row_number
- original_row_json
- detected_title
- detected_category
- detected_region
- detected_notes
- detected_urls
- created_at

Keep raw data unchanged for traceability.

### Step 3: Build Source Registry

Every unique URL becomes one source record.

Source registry fields:

- source_id
- url
- canonical_url
- source_domain
- title_from_excel
- title_from_page
- source_type
- reliability_label
- status: pending / fetched / failed / blocked / skipped
- original_file_name
- original_sheet_name
- original_row_number
- fetched_at
- content_hash
- error_message

Source type should be detected from domain and page content where possible:

- government
- university
- science_park
- incubator
- company
- investor
- media
- report
- database
- unknown

### Step 4: Fetch and Extract Content

For each source URL:

1. Try normal HTTP fetch.
2. Use trafilatura/readability extraction.
3. If the URL is a PDF, download and parse PDF text.
4. If extraction fails and the page is JavaScript-heavy, optionally use Playwright.
5. If the URL is dead or blocked, mark status and keep the URL in the registry.
6. Do not silently drop failed URLs.

For each fetched source, store:

- title
- extracted_text
- published_date if available
- fetched_at
- language
- source_domain
- content_hash
- extraction_method
- status
- failure reason if any

### Step 5: Chunk and Index

Chunk extracted content for retrieval.

Each chunk must keep metadata:

- chunk_id
- source_id
- url
- source_domain
- source_type
- reliability_label
- title
- file_name
- sheet_name
- row_number
- chunk_index
- text
- token_count or character_count

Chunking guidance:

- target 500–900 tokens per chunk
- overlap 80–150 tokens
- keep title/source metadata attached
- avoid embedding empty or extremely short chunks

### Step 6: Build Internal Retrieval

When the user asks a question:

1. Embed the query.
2. Search vector database.
3. Retrieve top chunks.
4. Optionally rerank if reranker is available.
5. Evaluate evidence quality.

Evidence is acceptable when:

- retrieved chunks are relevant to the question,
- at least one credible source exists,
- the answer can be grounded in retrieved text,
- source metadata is available.

### Step 7: Add Evidence Sufficiency Check

Before generating the final answer, the agent should decide:

- Is internal evidence enough?
- Is it weak?
- Is it missing?
- Is it conflicting?
- Is the question asking for current/latest data?

If internal evidence is not enough, trigger web fallback.

Basic internal evidence scoring:

- +2 if official/government/university/science park source
- +1 if company/investor official source
- +1 if multiple independent sources agree
- +1 if source is recent for dynamic facts
- -1 if source is unknown
- -1 if source is old for current-data question
- -2 if sources conflict

Use simple thresholds:

- High: strong official or corroborated evidence
- Medium: credible but incomplete evidence
- Low: weak/single/uncertain evidence
- Insufficient: no reliable evidence

### Step 8: Add Web Fallback

Use web fallback only when needed.

Triggers:

- no relevant internal chunks found
- internal sources are too weak
- question asks for current/latest information
- user asks about something outside indexed data
- internal sources conflict and need verification

Web fallback process:

1. Generate search query from user question.
2. Search via Tavily/Bing/SerpAPI/custom adapter.
3. Prefer official sources.
4. Fetch/extract top results when possible.
5. Store useful results in source registry.
6. Index fetched content for future reuse.
7. Answer with citations.

Do not use Tavily for links already present in Excel unless:
- direct fetch failed,
- URL is dead,
- alternative source is needed,
- page content is not extractable.

### Step 9: Generate Answer

Answer format:

- direct answer first
- concise explanation
- citations/source list
- confidence label
- data gaps if any

Answer should not be verbose.

Example output shape:

{
  "answer": "...",
  "confidence": "Medium",
  "source_mode": "internal_only | internal_plus_web | web_only | insufficient",
  "citations": [
    {
      "title": "...",
      "url": "...",
      "source_type": "government",
      "reliability": "high"
    }
  ],
  "gaps": [
    "Internal dataset does not include full funding data for this topic."
  ]
}

### Step 10: Build Simple UI

Use a proper web frontend for the product UI. Streamlit may be used only as a temporary internal debugging UI if it speeds up pipeline testing.

UI should show:

- question input
- answer
- confidence label
- citations
- source mode
- retrieved evidence snippets
- whether web fallback was used
- indexed source count
- failed URL count

Do not spend time on polish.

---

## 6. Suggested Project Structure

venture_metrics_agent/
  app/
    main.py
    config.py
    schemas.py
  ingestion/
    excel_profiler.py
    excel_ingest.py
    url_extractor.py
    source_registry.py
    fetcher.py
    text_extractor.py
    chunker.py
    indexer.py
  retrieval/
    vector_store.py
    retriever.py
    evidence_scorer.py
    web_search.py
  llm/
    provider.py
    prompts.py
  ui/
    streamlit_app.py
  data/
    raw/
    processed/
    indexes/
  tests/
    test_excel_profiler.py
    test_url_extraction.py
    test_retrieval.py
  scripts/
    profile_excels.py
    ingest_excels.py
    fetch_sources.py
    build_index.py
  README.md
  .env.example

Adjust structure if an existing repo already exists.

---

## 7. Data Model

Use SQLite locally if speed matters. Use PostgreSQL/Supabase if already configured.

### Table: excel_files

- id
- file_name
- file_path
- uploaded_at
- sheet_count
- profile_json

### Table: excel_sheets

- id
- file_id
- sheet_name
- row_count
- columns_json
- detected_url_count

### Table: raw_rows

- id
- file_id
- sheet_id
- row_number
- original_row_json
- detected_title
- detected_category
- detected_region
- detected_notes
- detected_urls_json

### Table: sources

- id
- url
- canonical_url
- source_domain
- source_type
- reliability_label
- status
- title_from_excel
- title_from_page
- original_file_name
- original_sheet_name
- original_row_number
- fetched_at
- content_hash
- error_message

### Table: documents

- id
- source_id
- title
- text
- language
- published_date
- fetched_at
- extraction_method
- metadata_json

### Table: chunks

- id
- document_id
- source_id
- chunk_index
- text
- metadata_json
- embedding_id

### Table: query_logs

- id
- question
- answer
- confidence
- source_mode
- used_web_fallback
- citations_json
- created_at

---

## 8. Source Reliability Rules

Reliability ranking:

1. Very high
   - government registry
   - official government policy/grant page
   - official filing
2. High
   - university official page
   - science park official page
   - incubator official page
3. Medium-high
   - investor official portfolio
   - company official website
4. Medium
   - reputable database
   - known report source
   - reputable news article
5. Low
   - blog
   - social media
   - unknown site
6. Avoid
   - uncited source
   - inaccessible source
   - pages with unclear origin

Domain heuristics examples:

- gov, government domains → government
- edu, university domains, hku, cuhk, cityu → university
- hkstp, cyberport, science park domains → science_park
- known VC domains or portfolio pages → investor
- news domains → media
- company homepage → company
- unknown domain → unknown

Do not rely only on domain. Store the detected type but allow manual correction later.

---

## 9. Agent Prompts

### 9.1 System Prompt for Chat Agent

You are the Venture Metrics research assistant. Your job is to answer questions using indexed Venture Metrics sources and verified public sources.

Rules:
- Use internal indexed evidence first.
- Do not answer important factual claims from memory alone.
- If internal evidence is insufficient, use web fallback if available.
- Prefer official, primary, and recent sources.
- Cite sources for factual claims.
- If sources conflict, explain the conflict.
- If evidence is weak, mark confidence as Low or Insufficient.
- Do not invent missing data.
- Keep answers concise and useful.
- Always include confidence level and source mode.

Output format:
- Answer
- Confidence
- Sources
- Data gaps / caveats

### 9.2 Evidence Sufficiency Prompt

Given the user question and retrieved evidence, decide whether the evidence is enough to answer.

Return JSON:
{
  "is_sufficient": true/false,
  "confidence": "High | Medium | Low | Insufficient",
  "reason": "...",
  "needs_web_fallback": true/false,
  "missing_information": ["..."],
  "best_sources": ["source_id"]
}

Criteria:
- Is the evidence relevant?
- Is it from reliable sources?
- Is it recent enough?
- Are there multiple sources if the claim is important?
- Are there conflicts?

### 9.3 Web Search Query Prompt

Convert the user question into 1-3 search queries.

Rules:
- Prefer official sources.
- Include region/context terms when relevant.
- Avoid vague queries.
- For Venture Metrics topics, include GBA / Hong Kong / Shenzhen / Greater Bay Area when useful.
- If searching for policy, include government/grant/program terms.

Return JSON:
{
  "queries": ["...", "..."],
  "preferred_source_types": ["government", "university", "science_park", "company", "investor", "media"]
}

### 9.4 Answer Generation Prompt

Use the evidence below to answer the user question.

Rules:
- Answer only with supported facts.
- Cite each important claim.
- If the evidence is partial, say so.
- If the evidence conflicts, say so.
- Do not mention internal chain-of-thought.
- Keep the answer short.

Return JSON:
{
  "answer": "...",
  "confidence": "High | Medium | Low | Insufficient",
  "source_mode": "internal_only | internal_plus_web | web_only | insufficient",
  "citations": [
    {
      "title": "...",
      "url": "...",
      "source_type": "...",
      "reliability": "..."
    }
  ],
  "gaps": ["..."]
}

---

## 10. API Design

### POST /ingest/excel-folder

Input:
{
  "folder_path": "path/to/excel/files"
}

Output:
{
  "files_processed": 9,
  "sheets_processed": 0,
  "rows_processed": 0,
  "urls_detected": 0,
  "duplicate_urls": 0
}

### POST /sources/fetch

Input:
{
  "limit": 50,
  "retry_failed": false
}

Output:
{
  "fetched": 0,
  "failed": 0,
  "blocked": 0,
  "skipped": 0
}

### POST /index/build

Input:
{
  "rebuild": false
}

Output:
{
  "documents_indexed": 0,
  "chunks_indexed": 0
}

### POST /query

Input:
{
  "question": "...",
  "use_web_fallback": true,
  "top_k": 8
}

Output:
{
  "answer": "...",
  "confidence": "Medium",
  "source_mode": "internal_plus_web",
  "citations": [],
  "gaps": [],
  "used_web_fallback": true
}

### GET /sources

Output:
{
  "total": 0,
  "fetched": 0,
  "failed": 0,
  "by_source_type": {},
  "by_reliability": {}
}

---

## 11. Prototype Demo Flow

Demo sequence:

1. Show Excel profiler output:
   - 9 files detected
   - sheet count
   - URL count
   - failed/duplicate count

2. Show source registry:
   - source URL
   - title
   - source type
   - status
   - reliability

3. Ask an internal-data question:
   - should answer from indexed sources

4. Ask a question with weak/missing internal evidence:
   - should trigger web fallback

5. Show final answer:
   - answer
   - confidence
   - citations
   - evidence snippets
   - source mode

6. Show that new web source was stored in source registry.

---

## 12. Test Questions

Use these for prototype testing. Replace with real domain questions after inspecting the Excel data.

1. What topics are covered in the uploaded source files?
2. Which sources mention startup funding or grants?
3. Which sources are related to Hong Kong entrepreneurship support?
4. Which sources mention incubators or science parks?
5. Which sources are official government or university sources?
6. What information do we have about GBA entrepreneurship policies?
7. What sources discuss university innovation or spin-offs?
8. What sources discuss startup competitions, courses, or events?
9. Which sources appear to be low-confidence or need manual verification?
10. What answer can you give from internal sources only?
11. What answer requires web fallback?
12. Find sources related to funding programmes for startups in Hong Kong.
13. Find sources related to Shenzhen science parks or incubators.
14. Compare two sources that mention the same topic.
15. What data gaps exist in the current sample files?

Acceptance criteria:
- The system should not hallucinate answers to questions not covered by evidence.
- It should clearly say when internal data is insufficient.
- It should cite sources for factual claims.
- It should use web fallback only when needed.
- It should store useful external sources.

---

## 13. Implementation Priorities

Priority 1:
- Excel profiler
- URL extraction
- source registry
- content fetching
- indexing
- internal Q&A with citations

Priority 2:
- evidence sufficiency check
- web fallback
- confidence labels
- Streamlit UI

Priority 3:
- browser fallback with Playwright
- PDF parsing
- source type classification improvements
- reranking
- Chinese query support

Priority 4:
- structured database search
- admin review workflow
- manual source correction
- production deployment planning

---

## 14. Handling Unknown Excel Formats

Do not assume sheet schemas.

Approach:
- read all sheets as raw dataframes
- normalize column names
- scan every cell for URLs
- preserve original row JSON
- infer possible title/category/notes columns
- generate a profile report
- allow manual mapping later

The first output should be an Excel/profile summary, not the chatbot.

If the Excel files are messy, that is expected. The system should still extract URLs and preserve traceability.

---

## 15. What To Ask The User Only If Blocked

Avoid unnecessary questions. Make reasonable defaults.

Ask only if required:
- Where are the Excel files located locally?
- Which LLM/search API keys are available?
- Should the prototype use SQLite or Supabase?
- Is Streamlit acceptable for the first demo?
- Are there any files that must not be indexed?

Do not ask for exact Excel format before building the profiler. The profiler exists to discover formats.

---

## 16. Final Delivery Package

Deliver:

1. Working local prototype
2. README with setup steps
3. Excel profiling report
4. Source registry export
5. Indexed source count and failed URL count
6. Demo questions and answers
7. Notes on limitations and next steps

Keep the delivery practical. Do not create long strategy documents unless explicitly requested.

---

## 17. Coding Style

- Keep code modular.
- Add clear logging.
- Do not silently fail.
- Store failure reasons.
- Keep all source traceability.
- Use environment variables for API keys.
- Add .env.example.
- Write simple tests for URL extraction and Excel profiling.
- Prefer working prototype over perfect architecture.

---

## 18. Definition of Done

The prototype is done when:

- it can read all Excel files and sheets,
- it extracts URLs from unknown sheet formats,
- it creates a source registry,
- it fetches and extracts content from reachable URLs,
- it chunks and indexes content,
- it answers questions using indexed evidence,
- it cites sources,
- it uses web fallback when internal evidence is insufficient,
- it labels confidence,
- it shows basic results in a UI,
- it logs failed URLs and extraction issues.
