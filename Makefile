.DEFAULT_GOAL := help

SAM_DIR := SAM-UVA-App-Integrations
PYTHON    := python3
PYTEST    := $(PYTHON) -m pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║          UVA-App-Integrations  —  SAM Python Project         ║"
	@echo "║          AWS: AppSync · DynamoDB Streams · SNS · IAM         ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "  Usage:  make <target>"
	@echo ""
	@echo "  ── Dependencies ─────────────────────────────────────────────"
	@echo "  install           Install all production requirements.txt files"
	@echo "  install-test      Install test dependencies (test/requirements-test.txt)"
	@echo "  install-all       Install production + test dependencies"
	@echo ""
	@echo "  ── Code Quality ─────────────────────────────────────────────"
	@echo "  lint              Run flake8 (max-line-length=120)"
	@echo "  format            Run black (line-length=120)"
	@echo ""
	@echo "  ── Testing ──────────────────────────────────────────────────"
	@echo "  test              Run integration + e2e (prod + local) suites"
	@echo "  test-integration  Run mocked integration tests (no Docker/AWS needed)"
	@echo "  test-e2e          Run real e2e against BOTH targets (prod + local)"
	@echo "  test-e2e-prod     Run real e2e against PRODUCTION (api.makesens.co, signed)"
	@echo "  test-e2e-local    Run real e2e against LOCAL (sam local start-api :3031)"
	@echo "  test-coverage     Run tests and generate HTML + terminal coverage report"
	@echo "  test-single       Run a single test file  (usage: make test-single FILE=<path>)"
	@echo ""
	@echo "  ── SAM / AWS ────────────────────────────────────────────────"
	@echo "  build             sam build (inside $(SAM_DIR)/)"
	@echo "  validate          sam validate --lint"
	@echo "  local-api         Start sam local API with dev env vars"
	@echo "  deploy-dev        sam deploy --config-env dev"
	@echo "  deploy-prod       sam deploy --config-env prod (no confirmation)"
	@echo ""
	@echo "  ── Maintenance ──────────────────────────────────────────────"
	@echo "  clean             Remove __pycache__, .pytest_cache, *.pyc, htmlcov, .coverage"
	@echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: install
install:
	@echo ">>> Installing all production requirements..."
	find . -name "requirements.txt" -not -path "*/test/*" -exec pip install -r {} \;

.PHONY: install-test
install-test:
	@echo ">>> Installing test requirements..."
	pip install -r test/requirements-test.txt

.PHONY: install-all
install-all: install install-test

# ──────────────────────────────────────────────────────────────────────────────
# Code Quality
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	@echo ">>> Running flake8..."
	$(PYTHON) -m flake8 --max-line-length=120 --exclude=.aws-sam,node_modules,__pycache__ .

.PHONY: format
format:
	@echo ">>> Running black..."
	$(PYTHON) -m black --line-length 120 .

# ──────────────────────────────────────────────────────────────────────────────
# Testing
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: test
test: test-integration test-e2e

.PHONY: test-integration
test-integration:
	@echo ">>> Running integration tests (mocked datastore, no Docker/AWS)..."
	$(PYTEST) test/integration/ -v --tb=short

# Real e2e against BOTH targets: production (signed) then local (sam local).
.PHONY: test-e2e
test-e2e: test-e2e-prod test-e2e-local

# Production: SigV4-signed GETs against the live api.makesens.co main endpoint.
# Read-only — no sam, no Docker. E2E_BASE_URL selects the prod base URL and the
# client auto-signs because the host is not localhost.
PROD_E2E_URL := https://api.makesens.co/internal/uva-integration-main

.PHONY: test-e2e-prod
test-e2e-prod:
	@echo ">>> Running real e2e against PRODUCTION ($(PROD_E2E_URL))..."
	@echo ">>> Exporting AWS SSO credentials for SigV4 signing..."
	@eval "$$(aws configure export-credentials --format env)"; \
	export AWS_DEFAULT_REGION=us-east-1; \
	E2E_BASE_URL=$(PROD_E2E_URL) $(PYTEST) test/e2e -v --tb=short

# Local: build + start sam local start-api on :3031 (Lambda in Docker calling the
# SAME main AppSync as prod), run the suite unsigned against 127.0.0.1, tear down.
# The conftest's api_base_url fixture owns the sam lifecycle as one command.
.PHONY: test-e2e-local
test-e2e-local:
	@echo ">>> Running real e2e against LOCAL (sam local start-api :3031)..."
	@echo ">>> Exporting AWS SSO credentials into the environment for sam local..."
	@eval "$$(aws configure export-credentials --format env)"; \
	export AWS_DEFAULT_REGION=us-east-1; \
	E2E_BASE_URL=http://127.0.0.1:3031 $(PYTEST) test/e2e -v --tb=short

.PHONY: test-coverage
test-coverage:
	@echo ">>> Running tests with coverage..."
	$(PYTEST) test/integration/ -v --tb=short --cov=. --cov-report=html --cov-report=term-missing

.PHONY: test-single
test-single:
ifndef FILE
	$(error FILE is not set. Usage: make test-single FILE=test/integration/test_xxx.py)
endif
	@echo ">>> Running single test: $(FILE)"
	$(PYTEST) $(FILE) -v

# ──────────────────────────────────────────────────────────────────────────────
# SAM / AWS
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: build
build:
	@echo ">>> Building SAM application..."
	cd $(SAM_DIR) && sam build

.PHONY: validate
validate:
	@echo ">>> Validating SAM template..."
	cd $(SAM_DIR) && sam validate --lint

.PHONY: local-api
local-api:
	@echo ">>> Starting SAM local API (dev)..."
	cd $(SAM_DIR) && sam local start-api \
		--env-vars parameters.json \
		--warm-containers EAGER

.PHONY: deploy-dev
deploy-dev:
	@echo ">>> Deploying to dev..."
	cd $(SAM_DIR) && sam deploy --config-env dev

.PHONY: deploy-prod
deploy-prod:
	@echo ">>> Deploying to prod (no confirmation)..."
	cd $(SAM_DIR) && sam deploy --config-env prod --no-confirm-changeset

# ──────────────────────────────────────────────────────────────────────────────
# Maintenance
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo ">>> Cleaning build artefacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf htmlcov .coverage 2>/dev/null; true
	@echo ">>> Done."
