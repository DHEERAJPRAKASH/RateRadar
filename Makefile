COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help up down build seed test migrate makemigrations logs scrape replay shell fmt env

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — edit secrets before production use")

up: env ## Build + start the whole stack
	$(COMPOSE) up --build

down: ## Stop the stack and remove volumes
	$(COMPOSE) down -v

build: ## Build images
	$(COMPOSE) build

migrate: ## Apply database migrations
	$(COMPOSE) run --rm web python manage.py migrate

makemigrations: ## Generate new migrations
	$(COMPOSE) run --rm web python manage.py makemigrations

seed: ## Load rates_seed.parquet into the database (idempotent)
	$(COMPOSE) run --rm web python manage.py seed_data

scrape: ## Trigger the scrape task once (synchronously)
	$(COMPOSE) run --rm worker python manage.py run_scrape

replay: ## Re-parse failed raw responses
	$(COMPOSE) run --rm web python manage.py replay_failed

test: ## Run the backend test suite
	$(COMPOSE) run --rm -e RUN_MIGRATIONS=0 web pytest

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

shell: ## Open a Django shell
	$(COMPOSE) run --rm web python manage.py shell
