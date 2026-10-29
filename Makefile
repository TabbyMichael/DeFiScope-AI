# DeFiScope AI - monorepo task runner.
# Thin wrappers over the per-workspace tools so common flows run from the repo
# root. Run `make help` for the target list.

API := services/api
WEB := apps/web

.DEFAULT_GOAL := help
.PHONY: help

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Setup --------------------------------------------------------------------

install: api-install web-install ## Install deps for both workspaces

api-install: ## Install backend deps (uv)
	@cd $(API) && uv sync

web-install: ## Install frontend deps (npm)
	@cd $(WEB) && npm install

# --- Dev ----------------------------------------------------------------------

api-dev: ## Run the API with autoreload (http://localhost:8000)
	@cd $(API) && uv run uvicorn app.main:app --port 8000 --reload

web-dev: ## Run the web dev server (http://localhost:3000)
	@cd $(WEB) && npm run dev

compose: ## Build and start the full stack (api + web + Postgres)
	@docker compose up --build

tunnel: ## Publish the running app on a public Cloudflare URL (share externally)
	@bash scripts/tunnel.sh

# --- Quality ------------------------------------------------------------------

lint: ## Lint backend (ruff) + frontend (eslint)
	@cd $(API) && uv run ruff check .
	@cd $(WEB) && npm run lint

format: ## Auto-format + fix backend (ruff)
	@cd $(API) && uv run ruff check --fix . && uv run ruff format .

typecheck: ## Typecheck the frontend
	@cd $(WEB) && npm run typecheck

test: ## Run backend (pytest) + frontend (vitest) tests
	@cd $(API) && uv run pytest
	@cd $(WEB) && npm test

e2e: ## Run Playwright e2e (needs the full stack up: make compose)
	@cd $(WEB) && npm run test:e2e

check: lint typecheck test ## Lint + typecheck + test

build: ## Build the production frontend
	@cd $(WEB) && npm run build

# --- Codegen ------------------------------------------------------------------

openapi: ## Regenerate services/api/openapi.json from the FastAPI app
	@cd $(API) && uv run python scripts/export_openapi.py

gen-types: openapi ## Regenerate openapi.json + frontend lib/api-types.ts
	@cd $(WEB) && npm run gen:types

# --- Database (Alembic) -------------------------------------------------------

db-upgrade: ## Apply migrations to head (DEFISCOPE_DATABASE_URL selects the DB)
	@cd $(API) && uv run alembic upgrade head

db-revision: ## Autogenerate a migration (usage: make db-revision m="add foo")
	@cd $(API) && uv run alembic revision --autogenerate -m "$(m)"

db-status: ## Show current Alembic migration revision
	@cd $(API) && uv run alembic current

# --- Cleanup ------------------------------------------------------------------

clean: ## Remove build artifacts and caches
	@rm -rf $(WEB)/.next $(WEB)/coverage
	@find $(API) -type d -name __pycache__ -prune -exec rm -rf {} +
	@rm -f $(API)/*.db
