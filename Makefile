.PHONY: install install-vllm dev test lint format health web-install web-dev web-check web-build docker-up docker-down docker-test shell

shell:
	nix develop

install:
	./scripts/bootstrap.sh

install-vllm:
	./scripts/bootstrap.sh --with-vllm

dev:
	uv sync

test:
	uv run pytest

lint:
	ruff check src tests

format:
	ruff format src tests

health:
	./scripts/healthcheck.sh

web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

web-check:
	cd web && npm run check

web-build:
	cd web && npm run build

docker-up:
	./scripts/docker-up.sh

docker-down:
	./scripts/docker-down.sh

docker-test:
	./scripts/docker-smoke-test.sh
