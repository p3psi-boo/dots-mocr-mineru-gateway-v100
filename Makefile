.PHONY: install install-vllm dev test lint format health docker-up docker-down docker-test

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

docker-up:
	./scripts/docker-up.sh

docker-down:
	./scripts/docker-down.sh

docker-test:
	./scripts/docker-smoke-test.sh
