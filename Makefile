# Advanced Supply Chain Automation Platform
# Makefile for common development tasks

.PHONY: help install dev-install test lint format clean docker-up docker-down migrate seed

# Default target
help:
	@echo "Supply Chain Automation Platform - Available Commands:"
	@echo ""
	@echo "  make install       - Install production dependencies"
	@echo "  make dev-install   - Install development dependencies"
	@echo "  make test          - Run test suite"
	@echo "  make test-cov      - Run tests with coverage"
	@echo "  make lint          - Run linter (flake8)"
	@echo "  make format        - Format code (black, isort)"
	@echo "  make type-check    - Run type checker (mypy)"
	@echo "  make clean         - Clean build artifacts"
	@echo "  make docker-up     - Start Docker services"
	@echo "  make docker-down   - Stop Docker services"
	@echo "  make migrate       - Run database migrations"
	@echo "  make seed          - Seed database with sample data"
	@echo "  make docs          - Generate API documentation"
	@echo ""

# Installation
install:
	pip install -r requirements.txt

dev-install: install
	pip install black isort flake8 mypy pytest pytest-asyncio pytest-cov

# Testing
test:
	pytest -v

test-cov:
	pytest --cov=. --cov-report=term-missing --cov-report=html

# Code quality
lint:
	flake8 api core workers integrations tests --max-line-length=100 --extend-ignore=E203

format:
	black api core workers integrations tests --line-length=100
	isort api core workers integrations tests --profile=black

type-check:
	mypy api core workers --ignore-missing-imports

check-all: format lint type-check test
	@echo "All checks passed!"

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete

# Docker commands
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f api
docker-build:
	docker-compose build

docker-clean:
	docker-compose down -v

# Database
migrate:
	alembic upgrade head

seed:
	python scripts/seed_data.py

# Documentation
docs:
	@echo "API Documentation available at: http://localhost:8000/docs"

# Development server
dev:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Celery
worker:
	celery -A workers.celery_app worker --loglevel=info

beat:
	celery -A workers.celery_app beat --loglevel=info

flower:
	celery -A workers.celery_app flower --port=5555
