COMPOSE := docker compose
DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help api openapi web-client test-312 bench-db notebook-test notebook-clean setup secrets build up dev down logs lint format typecheck test check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-12s %s\n", $$1, $$2}'

api:  ## Run the API locally with auto-reload (needs Postgres, Redis and S3 up)
	uvicorn podcast_engine.api.main:app --reload

openapi:  ## Write web/openapi.json, the API description the web client is typed from
	python -c "import json; from podcast_engine.api.main import create_app; print(json.dumps(create_app().openapi(), indent=2))" > web/openapi.json

web-client: openapi  ## Regenerate the web app's API types (web/src/api/schema.d.ts)
	cd web && npm run gen:api

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
	@for f in llm_api_key tts_api_key vault_app_token; do test -f secrets/$$f.txt || : > secrets/$$f.txt; done
	@test -f secrets/vault-ca.pem || : > secrets/vault-ca.pem
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

test-312:  ## Unit tests on Python 3.12, the images' version (3.14 hides some bugs), in Docker
	tar --exclude=.venv --exclude=.venv-cloning --exclude=node_modules --exclude=.git \
		--exclude=evaluation/results --exclude=web --exclude=data --exclude=assets -cf - . 2>/dev/null \
	| docker run --rm -i python:3.12-slim sh -c 'mkdir /w && cd /w && tar -xf - 2>/dev/null \
		&& pip install -q --root-user-action=ignore -e ".[api,ingest,llm,anthropic,voice,assemble,publish,tls,dev]" \
		&& python -m pytest tests/unit -q --no-cov -p no:cacheprovider'

check: lint typecheck test  ## Everything CI runs
