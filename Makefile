# Makefile

.PHONY: ruff mypy test

ruff:
	@echo "Running ruff..."
	@uv run ruff format .
	@uv run ruff check .

mypy:
	@echo "Running mypy..."
	@uv run mypy

format: ruff mypy

test:
	@echo "Running plugin tests..."
	@uv run python -u -m pytest tests/

test-example:
	@echo "Running example tests with API coverage..."
	@uv run python -u -m pytest example/tests/ --api-cov-report --api-cov-fail-under=50

test-example-parallel:
	@echo "Running example tests with API coverage in parallel..."
	@uv run python -u -m pytest example/tests/ --api-cov-report --api-cov-fail-under=50 -n 3

cover:
	@echo "Running tests with code coverage..."
	@uv run python -u -m pytest tests/ --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml

clean:
	@echo "Cleaning up..."
	

build:
	@echo "Building plugin..."
	@uv build

publish:
	@echo "Publishing plugin..."
	@uv publish