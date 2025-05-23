.PHONY: help install dev-install lint type-check test build run stop clean

help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make dev-install  - Install development dependencies"
	@echo "  make lint         - Run ruff linter"
	@echo "  make type-check   - Run mypy type checker"
	@echo "  make test         - Run tests"
	@echo "  make build        - Build Docker image"
	@echo "  make run          - Run with docker-compose"
	@echo "  make stop         - Stop docker-compose"
	@echo "  make clean        - Clean up generated files"

install:
	uv pip sync requirements.txt

dev-install:
	uv pip install -e ".[dev]"

lint:
	uv run ruff check src tests
	uv run ruff format src tests

type-check:
	uv run mypy src

test:
	uv run pytest

build:
	docker build -t docker-logfire:latest .

run:
	docker-compose up -d

stop:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build *.egg-info