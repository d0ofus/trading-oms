.PHONY: format lint typecheck test test-integration test-replay test-chaos test-e2e security-check verify

PYTHON ?= python

format:
	@echo "format: placeholder until backend/frontend skeleton exists"

lint:
	@echo "lint: placeholder until backend/frontend skeleton exists"
	@$(PYTHON) scripts/verify_repo.py

typecheck:
	@echo "typecheck: placeholder until backend/frontend skeleton exists"

test:
	@echo "test: placeholder until backend/frontend skeleton exists"

test-integration:
	@echo "test-integration: placeholder until integration tests exist"

test-replay:
	@echo "test-replay: placeholder until replay engine exists"

test-chaos:
	@echo "test-chaos: placeholder until chaos tests exist"

test-e2e:
	@echo "test-e2e: placeholder until e2e tests exist"

security-check:
	@echo "security-check: minimal scaffold checks"
	@$(PYTHON) scripts/verify_repo.py

verify: format lint typecheck test test-integration test-replay test-chaos test-e2e security-check
	@echo "verify: ok"
