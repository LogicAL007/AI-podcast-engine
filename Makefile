COMPOSE := docker compose
DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help api bench-db notebook-test notebook-clean setup secrets build up dev down logs lint format typecheck test check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-12s %s\n", $$1, $$2}'

api:  ## Run the API locally with auto-reload (needs Postgres, Redis and S3 up)
	uvicorn podcast_engine.api.main:app --reload

bench-db:  ## Start a throwaway pgvector database for evaluation/ on localhost:55433
	docker start podcast-bench-pg 2>/dev/null || docker run -d --name podcast-bench-pg \
		-e POSTGRES_USER=podcast -e POSTGRES_PASSWORD=bench -e POSTGRES_DB=podcast \
		-p 127.0.0.1:55433:5432 -v "$(CURDIR)/db/init:/docker-entrypoint-initdb.d:ro" pgvector/pgvector:pg16

notebook-test:  ## Execute notebooks/podcast_flow.ipynb offline and check the flow
	pytest -m notebook --no-cov

notebook-clean:  ## Strip outputs (including audio) from the notebook before committing it
	python -c "import nbformat as n; p='notebooks/podcast_flow.ipynb'; nb=n.read(p, as_version=4); [c.update(outputs=[], execution_count=None) for c in nb.cells if c.cell_type=='code']; n.write(nb, p)"

setup:  ## Install Python dev dependencies and git hooks
	python -m pip install -e ".[api,dev]"
	pre-commit install

secrets:  ## Create empty secret files (fill them in before running stages)
	@for f in llm_api_key tts_api_key; do test -f secrets/$$f.txt || : > secrets/$$f.txt; done
	@test -f .env || cp .env.example .env

build:  ## Build every image
	$(COMPOSE) build

up: secrets  ## Start the full stack
	$(COMPOSE) up -d

dev: secrets  ## Start the stack with source mounted
	$(DEV) up -d --build

down:  ## Stop the stack (volumes are kept)
	$(COMPOSE) down

logs:  ## Follow logs
	$(COMPOSE) logs -f --tail=100

lint:  ## Ruff lint and format check
	ruff check .
	ruff format --check .

format:  ## Auto-format
	ruff check --fix .
	ruff format .

typecheck:  ## mypy (strict)
	mypy

test:  ## Unit tests
	pytest tests/unit

check: lint typecheck test  ## Everything CI runs
