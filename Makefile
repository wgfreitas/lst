# LST — developer workflow automation.
# Activate the virtualenv first: `source .venv/bin/activate`.
# Recipes are tab-indented per GNU make convention.

.PHONY: help install test lint format typecheck run clean
.DEFAULT_GOAL := help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in editable mode with dev dependencies
	pip install -e '.[dev]'

test: ## Run the test suite with coverage
	pytest

lint: ## Lint sources with ruff (check only)
	ruff check .

format: ## Format sources with ruff
	ruff format .

typecheck: ## Run static type checking on the package
	mypy src

run: ## Show the CLI help screen
	lst --help

clean: ## Remove build artifacts and tool caches
	rm -rf build dist *.egg-info src/*.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
