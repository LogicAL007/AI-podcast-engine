COMPOSE := docker compose
DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help api openapi web-client test-312 research setup secrets rotate-secret build up dev down voice-host demo-site demo-next demo-reset logs lint format typecheck test check

help:  ## List targets
	@grep -E '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-12s %s\n", $$1, $$2}'

api:  ## Run the API locally with auto-reload (needs Postgres, Redis and S3 up)
	uvicorn podcast_engine.api.main:app --reload

openapi:  ## Write web/openapi.json, the API description the web client is typed from
	python -c "import json; from podcast_engine.api.main import create_app; print(json.dumps(create_app().openapi(), indent=2))" > web/openapi.json

web-client: openapi  ## Regenerate the web app's API types (web/src/api/schema.d.ts)
	cd web && npm run gen:api

research:  ## Research targets (benchmarks, RQ studies, notebooks) are in research/Makefile, kept locally
	@$(MAKE) -C research help 2>/dev/null || echo "research/ is not in this checkout (it is git-ignored)."

setup:  ## Install Python dev dependencies and git hooks
	python -m pip install -e ".[api,dev]"
	pre-commit install

secrets:  ## Create empty secret files (fill them in before running stages)
	@for f in llm_api_key tts_api_key vault_app_token; do test -f secrets/$$f.txt || : > secrets/$$f.txt; done
	@test -f secrets/vault-ca.pem || : > secrets/vault-ca.pem
	@test -f .env || cp .env.example .env

rotate-secret:  ## Store a replaced secret in Vault and restart what reads it: make rotate-secret NAME=llm_api_key
	@case "$(NAME)" in llm_api_key|tts_api_key|smtp_password|google_client_secret|search_api_key) ;; \
		*) echo "NAME must be llm_api_key, tts_api_key, smtp_password, google_client_secret or search_api_key"; exit 1;; esac
	@test -s secrets/$(NAME).txt || { echo "Put the new value in secrets/$(NAME).txt first."; exit 1; }
	@chmod 600 secrets/$(NAME).txt
	$(COMPOSE) run --rm -T vault-init python -m podcast_engine.common.vault_init set $(NAME) < secrets/$(NAME).txt
	@# Secrets are read once at start, so everything that reads them starts again.
	$(COMPOSE) up -d --force-recreate --no-deps api index_plan script_factcheck assemble ingest_publish scheduler voice
	@echo "Stored $(NAME). Now revoke the old value with its provider."

build:  ## Build every image
	$(COMPOSE) build

up: secrets  ## Start the full stack
	$(COMPOSE) up -d

dev: secrets  ## Start the stack with source mounted
	$(DEV) up -d --build

down:  ## Stop the stack (volumes are kept)
	$(COMPOSE) down

voice-host:  ## Voice with cloned voices (Chatterbox) on this Mac's GPU, in place of the voice container
	$(COMPOSE) -f docker-compose.yml -f docker-compose.voice-host.yml up -d --no-deps postgres redis s3
	$(COMPOSE) stop voice
	set -a && . ./.env && set +a && \
	DATABASE_URL=postgresql+psycopg://$$POSTGRES_USER:$$POSTGRES_PASSWORD@localhost:5432/$$POSTGRES_DB \
	REDIS_URL=redis://localhost:6379/0 S3_ENDPOINT_URL=http://localhost:$${VOICE_HOST_S3_PORT:-9010} TTS_BACKEND=chatterbox \
	CONFIG_DIR=$(CURDIR)/config ASSETS_DIR=$(CURDIR)/assets PROMPTS_DIR=$(CURDIR)/prompts \
	DATA_DIR=$(CURDIR)/data/voice-host WORKER_POOL=solo WORKER_CONCURRENCY=1 METRICS_PORT=9101 \
	.venv-cloning/bin/python -m podcast_engine.worker voice

demo-site:  ## Start the demo news site (a source that changes): http://localhost:8095, shows use http://demo-site:8095/
	$(COMPOSE) --profile demo up -d demo-site

demo-next:  ## Publish the demo site's next edition (then press Refresh on the episode)
	@curl -fsS -o /dev/null -X POST http://localhost:8095/next && echo "Next edition is live: http://localhost:8095"

demo-reset:  ## Put the demo site back to edition 1
	@curl -fsS -o /dev/null -X POST http://localhost:8095/reset && echo "Edition 1 is live: http://localhost:8095"

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
		--exclude=research --exclude=web --exclude=data --exclude=assets -cf - . 2>/dev/null \
	| docker run --rm -i python:3.12-slim sh -c 'mkdir /w && cd /w && tar -xf - 2>/dev/null \
		&& pip install -q --root-user-action=ignore -e ".[api,ingest,llm,anthropic,voice,assemble,publish,tls,dev]" \
		&& python -m pytest tests/unit -q --no-cov -p no:cacheprovider'

check: lint typecheck test  ## Everything CI runs
