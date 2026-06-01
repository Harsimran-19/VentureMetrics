PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/python -m pip
DB ?= venture_metrics_agent/data/processed/venture_metrics.db
EXCEL_DIR ?= document_sources
DOCS_DIR ?= venture_metrics_agent/data/documents
PORT ?= 8000
HOST ?= 127.0.0.1
IMAGE ?= venture-metrics
QUESTION ?= Which sources mention startup funding or grants?

.PHONY: help setup profile ingest fetch index test eval query reasoning-query compare serve docker-build docker-run status telemetry-status

help:
	@echo "Venture Metrics commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup              Create .venv and install requirements"
	@echo ""
	@echo "Data pipeline:"
	@echo "  make profile            Profile Excel files"
	@echo "  make ingest             Ingest Excel rows and source registry"
	@echo "  make fetch              Fetch pending sources via Tavily"
	@echo "  make index              Build/rebuild local FTS index"
	@echo "  make status             Show local database counts"
	@echo "  make telemetry-status   Show local observability counts"
	@echo ""
	@echo "Agent:"
	@echo "  make serve              Run local web UI"
	@echo "  make query              Ask legacy RAG agent; override QUESTION='...'"
	@echo "  make reasoning-query    Ask reasoning agent without LLM/web mutation"
	@echo "  make compare            Compare legacy and reasoning agents"
	@echo ""
	@echo "Quality:"
	@echo "  make test               Run pytest"
	@echo "  make eval               Run reasoning eval suite"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build       Build Docker image"
	@echo "  make docker-run         Run Docker image on PORT"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

profile:
	$(PYTHON) scripts/profile_excels.py $(EXCEL_DIR)

ingest:
	$(PYTHON) scripts/ingest_excels.py $(EXCEL_DIR) --db $(DB)

fetch:
	$(PYTHON) scripts/fetch_sources.py --db $(DB) --documents-dir $(DOCS_DIR) --limit 25 --batch-size 5

index:
	$(PYTHON) scripts/build_index.py --db $(DB) --rebuild

status:
	sqlite3 $(DB) "select 'excel_files', count(*) from excel_files union all select 'excel_sheets', count(*) from excel_sheets union all select 'raw_rows', count(*) from raw_rows union all select 'sources', count(*) from sources union all select 'documents', count(*) from documents union all select 'chunks', count(*) from chunks union all select 'query_logs', count(*) from query_logs;"

telemetry-status:
	$(PYTHON) scripts/telemetry_status.py --db $(DB)

test:
	$(PYTHON) -m pytest -q

eval:
	$(PYTHON) scripts/run_reasoning_eval.py --db $(DB) --record

query:
	$(PYTHON) scripts/query_agent.py --db $(DB) "$(QUESTION)"

reasoning-query:
	$(PYTHON) scripts/query_reasoning_agent.py --db $(DB) --no-llm --no-web --no-remember-web "$(QUESTION)"

compare:
	$(PYTHON) scripts/compare_agents.py --db $(DB) --no-llm --no-web --no-remember-web "$(QUESTION)"

serve:
	$(PYTHON) scripts/serve_agent.py --host $(HOST) --port $(PORT) --db $(DB)

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p $(PORT):8000 -e HOST=0.0.0.0 -e DB_PATH=/data/venture_metrics.db -v "$$(pwd)/.deploy-data:/data" $(IMAGE)
