.PHONY: help test test-verbose test-coverage install install-dev clean lint format type-check

help:
	@echo "Available commands:"
	@echo "  test          Run tests"
	@echo "  test-verbose  Run tests with verbose output"
	@echo "  test-coverage Run tests with coverage report"
	@echo "  install       Install package"
	@echo "  install-dev   Install package with development dependencies"
	@echo "  clean         Clean up temporary files"
	@echo "  lint          Run linting"
	@echo "  format        Format code"
	@echo "  type-check    Run type checking with mypy"

test:
	python -m pytest tests/

test-verbose:
	python -m pytest tests/ -v

test-coverage:
	python -m pytest tests/ --cov=migration_lock_checker --cov-report=html --cov-report=term

install:
	pip install .

install-dev:
	pip install .[dev]

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf htmlcov/
	rm -rf .coverage

lint:
	ruff check migration_lock_checker/ tests/

format:
	ruff format migration_lock_checker/ tests/

type-check:
	mypy migration_lock_checker/

run-tests:
	python tests/run_tests.py
