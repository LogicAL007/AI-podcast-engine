COMPOSE := docker compose
DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help setup secrets build up dev down logs lint format typecheck test check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-12s %s\n", $$1, $$2}'

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
