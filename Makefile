-include .env
export
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000

.PHONY: first-run up down fetch-data ingest test-backend test-frontend clean help

help:
	@echo "Lenny Growth Assistant Commands:"
	@echo "  make first-run       - Complete setup: fetch data, build containers, wait for health, ingest"
	@echo "  make fetch-data      - Download transcript repository into ./data"
	@echo "  make up              - Start Docker Compose services in background"
	@echo "  make down            - Stop and remove Docker Compose containers"
	@echo "  make ingest          - Run pgvector transcript ingestion inside backend container"
	@echo "  make test-backend    - Run backend pytest suite inside container"
	@echo "  make test-frontend   - Run frontend vitest suite"

first-run:
	@echo "=== Step 1: Checking environment config ==="
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	@echo "=== Step 2: Fetching podcast transcripts ==="
	python3 scripts/fetch_data.py || python scripts/fetch_data.py
	@echo "=== Step 3: Building and starting Docker containers ==="
	docker compose up -d --build
	@echo "=== Step 4: Waiting for backend service health ==="
	@until docker compose exec -T backend curl -s -f http://localhost:8000/health > /dev/null 2>&1; do \
		echo "Waiting for backend service to become healthy..."; \
		sleep 3; \
	done
	@echo "Backend is healthy!"
	@echo "=== Step 5: Ingesting transcripts into pgvector ==="
	docker compose exec -T backend python -m scripts.ingest
	@echo "=== First-run setup complete! ==="
	@echo "Frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Backend API: http://localhost:$(BACKEND_PORT)"
	@echo "API Docs: http://localhost:$(BACKEND_PORT)/docs"

fetch-data:
	python3 scripts/fetch_data.py || python scripts/fetch_data.py

up:
	docker compose up -d

down:
	docker compose down

ingest:
	docker compose exec -T backend python -m scripts.ingest

test-backend:
	docker compose exec -T backend pytest

test-frontend:
	cd frontend && npm test
