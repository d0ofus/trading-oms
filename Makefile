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
	@$(PYTHON) -m pytest $(PYTEST_ARGS) $(BACKEND_DIR)/tests/test_workspace_api.py

test-replay:
	@$(PYTHON) -m pytest $(PYTEST_ARGS) $(BACKEND_DIR)/tests/test_workspace_market.py

test-chaos:
	@$(PYTHON) -m pytest $(PYTEST_ARGS) $(BACKEND_DIR)/tests/test_resilience.py $(BACKEND_DIR)/tests/test_workspace_chaos.py $(BACKEND_DIR)/tests/test_workspace_protection.py

test-e2e:
	@$(NPM) --prefix $(FRONTEND_DIR) run build
	@$(NPM) --prefix $(FRONTEND_DIR) run test:e2e

security-check:
	@$(PYTHON) scripts/verify_repo.py
	@$(PYTHON) scripts/secret_scan.py
	@$(PYTHON) -m pip_audit --disable-pip --no-deps -r backend/requirements-lock.txt
	@$(NPM) --prefix $(FRONTEND_DIR) audit --audit-level=low

verify: format lint typecheck test test-e2e security-check
	@$(NPM) --prefix $(FRONTEND_DIR) run format:check
	@$(PYTHON) -m trading_oms_backend.workspace.verification
	@echo "verify: ok"
