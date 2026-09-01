.PHONY: install install-vllm dev test lint format health

install:
	./scripts/bootstrap.sh

install-vllm:
	./scripts/bootstrap.sh --with-vllm

dev:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

health:
	./scripts/healthcheck.sh
