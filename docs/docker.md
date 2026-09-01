# Docker deployment

The Compose deployment runs two containers:

```text
host :8000 -> api :8000 -> vllm :8001
```

Only the API port is published. The vLLM port is exposed only on the private
Compose network. The API image also builds and serves the SvelteKit WebUI at
the gateway root URL.

## Prerequisites

- Docker Engine with the Compose plugin
- NVIDIA Container Toolkit
- A driver compatible with the CUDA runtime in `vllm/vllm-openai:v0.11.2`
- The dots.mocr model already present on the host

Verify GPU access before starting:

```bash
docker run --rm --gpus all \
  docker.1ms.run/nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi
```

## Configuration

```bash
cp .env.docker.example .env.docker
chmod 600 .env.docker
```

Set both API keys and verify these host paths:

```dotenv
DOTOCRM_MODEL_PATH=/opt/dotocrm/models/dots.mocr
DOTOCRM_CACHE_DIR=/opt/dotocrm/cache
```

The example defaults to mainland China mirrors for Docker Hub, npm, and Python
packages. Replace `VLLM_IMAGE`, `PYTHON_IMAGE`, `NODE_IMAGE`, `NPM_REGISTRY`,
or `UV_INDEX_URL` if a different registry or package index is preferred.

## Start and verify

```bash
./scripts/docker-up.sh
docker compose --env-file .env.docker ps
./scripts/docker-smoke-test.sh
```

Model startup on a V100 takes roughly 90–120 seconds. Compose waits for vLLM's
health check before starting the API container.

Stop the stack with:

```bash
./scripts/docker-down.sh
```

## API-only migration test

`compose.api-only.yaml` starts only the gateway and connects it to an existing
host vLLM process on port 8001. It uses host networking and publishes the test
gateway on port 18000 by default.

```bash
export DOTOCRM_ENV_FILE=/opt/dotocrm/.env
docker compose \
  --env-file "$DOTOCRM_ENV_FILE" \
  -f compose.api-only.yaml \
  up --detach --build

curl http://127.0.0.1:18000/healthz
```

This mode is intended for migration testing; the full `compose.yaml` keeps the
model service private to the Compose network.

## V100 settings

The Compose service retains the known-good host deployment settings:

- vLLM 0.11.2
- FP16
- decoder attention backend: Triton
- multimodal encoder attention backend: XFormers
- two concurrent sequences
- 0.88 GPU memory utilization
- no prefix cache
