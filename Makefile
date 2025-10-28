# Makefile

.PHONY: ruff mypy test clean clean-all version

PYPI_TOKEN := $(shell type .pypi_token 2>nul || echo "")
TEST_PYPI_TOKEN := $(shell type .test_pypi_token 2>nul || echo "")

version:
	@uv version

ruff:
	@echo "Running ruff format on src, tests, and example..."
	@uv run ruff format src tests example
	@echo "Running ruff check on src"
	@uv run ruff check src

mypy:
	@echo "Running mypy..."
	@uv run mypy

vulture:
	@echo "Running vulture..."
	@uv run vulture

format: ruff mypy vulture

test:
	@echo "Running plugin tests..."
	@uv run python -u -m pytest tests/

typeguard:
	@echo "Running typeguard..."
	@uv run python -u -m pytest tests/ --typeguard-packages=tests/

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
	@echo "Cleaning up build artifacts..."
	@if exist build rmdir /s /q build
	@if exist dist rmdir /s /q dist
	@if exist .venv rmdir /s /q .venv
	@if exist *.egg-info rmdir /s /q *.egg-info
	@if exist .coverage del .coverage
	@if exist htmlcov rmdir /s /q htmlcov
	@if exist coverage.xml del coverage.xml
	@if exist .pytest_cache rmdir /s /q .pytest_cache
	@if exist __pycache__ rmdir /s /q __pycache__

build:
	@echo "Building plugin..."
	@uv sync
	@uv build

pipeline-local: format clean test cover typeguard test-example test-example-parallel

pipeline: format test cover typeguard test-example test-example-parallel

publish: pipeline build
	@echo "Publishing plugin..."
	@uv publish --token $(PYPI_TOKEN)

publish-test:
	@echo "Publishing plugin to test PyPI..."
	@echo //$(TEST_PYPI_TOKEN)//
	@uv publish --token $(TEST_PYPI_TOKEN) --index testpypi

verify-publish:
	@echo "Verifying plugin was published to PyPI..."
	@uv run --with pytest-api-cov --no-project -- python -c "import pytest_api_cov; print(f'Plugin verified successfully. Version: {pytest_api_cov.__version__}')"
