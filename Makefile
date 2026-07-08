.PHONY: format lint typecheck test test-integration test-replay test-chaos test-e2e security-check verify

PYTHON ?= python
NPM ?= npm
BACKEND_DIR ?= backend
FRONTEND_DIR ?= frontend
PYTEST_BASETEMP ?= .pytest-tmp
PYTEST_ARGS ?= -p no:cacheprovider --basetemp $(PYTEST_BASETEMP)

format:
	@$(PYTHON) -m ruff format --check $(BACKEND_DIR)/src $(BACKEND_DIR)/tests

lint:
	@$(PYTHON) scripts/verify_repo.py
	@$(PYTHON) -m ruff check $(BACKEND_DIR)/src $(BACKEND_DIR)/tests
	@$(NPM) --prefix $(FRONTEND_DIR) run lint

typecheck:
	@$(PYTHON) -m compileall -q $(BACKEND_DIR)/src $(BACKEND_DIR)/tests
	@$(NPM) --prefix $(FRONTEND_DIR) run typecheck

test:
	@$(PYTHON) -m pytest $(PYTEST_ARGS) $(BACKEND_DIR)/tests
	@$(NPM) --prefix $(FRONTEND_DIR) run test

test-integration:
	@echo "test-integration: placeholder until integration tests exist"

test-replay:
	@echo "test-replay: placeholder until replay engine exists"

test-chaos:
	@$(PYTHON) -m pytest $(PYTEST_ARGS) $(BACKEND_DIR)/tests/test_resilience.py

test-e2e:
	@echo "test-e2e: placeholder until e2e tests exist"

security-check:
	@echo "security-check: minimal scaffold checks"
	@$(PYTHON) scripts/verify_repo.py

verify: format lint typecheck test test-integration test-replay test-chaos test-e2e security-check
	@echo "verify: ok"
