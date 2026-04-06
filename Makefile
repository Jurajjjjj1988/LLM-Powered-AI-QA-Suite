# Common dev commands — run from repo root

.PHONY: lint format test check install

install:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

test:
	pytest -v --tb=short

check: lint test
	@echo "All checks passed"
