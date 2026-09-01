# dots.mocr vLLM Gateway

A reusable FastAPI gateway for running
[`dots-studio/dots.mocr`](https://www.modelscope.cn/models/dots-studio/dots.mocr)
on vLLM. It exposes both a native layout OCR endpoint and a MinerU protocol v2
compatibility layer.

The reference deployment is tuned for one NVIDIA V100 16 GB with vLLM 0.11.2,
but runtime paths, ports, model location, limits, and GPU settings are all
environment-driven.

## Features

- One-page layout OCR with normalized block JSON
- PDF and image parsing through MinerU-compatible endpoints
- Synchronous and asynchronous MinerU task APIs
- Markdown, content list, middle JSON, model output, extracted image, and ZIP responses
- API-key protection for the native endpoint
- Concurrency and upload limits suitable for a 16 GB V100
- IPv4 and IPv6 listeners
- Parameterized systemd and Nginx deployment templates
- ModelScope download path for mainland China

## Architecture

```text
client
  │
  ▼ :8000
Nginx
  │
  ▼ :8010
FastAPI gateway
  ├── POST /v1/ocr/layout
  └── MinerU protocol v2
          │
          ▼ :8001
      vLLM + dots.mocr
```

See [docs/architecture.md](docs/architecture.md) for the runtime details.

## Requirements

- Linux
- [uv](https://docs.astral.sh/uv/) for Python and dependency management
- Python 3.10–3.13 for the gateway; `.python-version` selects Python 3.12,
  which is required by the tested vLLM runtime
- NVIDIA GPU and driver supported by the selected PyTorch/vLLM build
- Nginx and systemd for the production deployment
- Approximately 6 GB for model weights, plus Python and compilation caches

## Quick start

### 1. Clone and configure

```bash
git clone REPO_URL dotocrm
cd dotocrm
cp .env.example .env
chmod 600 .env
```

Set at least these values in `.env`:

```dotenv
VLLM_API_KEY=generate-a-random-internal-key
PUBLIC_API_KEY=generate-a-random-public-key
DOTOCRM_MODEL_PATH=/opt/dotocrm/models/dots.mocr
```

### 2. Install uv and create the environment

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If that installer is slow in mainland China:

```bash
python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple uv
```

API only:

```bash
./scripts/bootstrap.sh
```

API plus the tested vLLM runtime:

```bash
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
  ./scripts/bootstrap.sh --with-vllm
```

`uv.lock` pins the complete dependency graph. The bootstrap script creates
`.venv` from that lock and uses Python 3.12 unless overridden with
`DOTOCRM_PYTHON_VERSION`.

### 3. Download dots.mocr through ModelScope

```bash
./scripts/download-model.sh
```

The default model ID is `dots-studio/dots.mocr`. Override it with
`MODELSCOPE_MODEL_ID` or set `DOTOCRM_MODEL_PATH` to use an existing snapshot.

### 4. Run locally

Terminal 1:

```bash
set -a; source .env; set +a
./scripts/run-vllm.sh
```

Terminal 2:

```bash
set -a; source .env; set +a
./scripts/run-api.sh
```

The API listens on `[::]:8010` by default. Point a client directly to 8010 or
install Nginx to expose port 8000.

## Production deployment

Run from the final repository location, for example `/opt/dotocrm`:

```bash
sudo apt-get install -y nginx
./scripts/bootstrap.sh --with-vllm
./scripts/download-model.sh
DOTOCRM_USER="$USER" ./scripts/install-systemd.sh
./scripts/install-nginx.sh
sudo systemctl start dotocrm-vllm dotocrm-api
./scripts/healthcheck.sh
```

The service templates are rendered with the current repository path and chosen
service user. They do not require the repository to live at `/opt/dotocrm`.

## Native layout OCR API

```bash
curl -X POST http://HOST:8000/v1/ocr/layout \
  -H 'X-API-Key: TOKEN' \
  -F 'file=@page.png'
```

The response contains page dimensions, ordered blocks, original-pixel bounding
boxes, completion state, model usage, timings, and parse warnings.

## MinerU-compatible API

Implemented protocol v2 routes:

- `GET /health`
- `POST /file_parse`
- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/result`

Synchronous example:

```bash
curl -X POST http://HOST:8000/file_parse \
  -F 'files=@document.pdf' \
  -F 'return_md=true' \
  -F 'return_content_list=true'
```

Asynchronous example:

```bash
curl -X POST http://HOST:8000/tasks \
  -F 'files=@document.pdf' \
  -F 'return_md=true'
```

The compatibility contract follows MinerU's
[`mineru-api`](https://github.com/opendatalab/MinerU/blob/master/mineru/cli/fast_api.py)
route and response shapes. See
[docs/mineru-compat.md](docs/mineru-compat.md) for supported inputs and options.

## Configuration

All settings are documented in [.env.example](.env.example). Important groups:

- `VLLM_*`: internal model URL, API key, model name, and engine limits
- `DOTOCRM_API_*`: API listener and proxy settings
- `OCR_*`: image size, output token, and request timeout limits
- `MINERU_*`: task retention, file count, and page window
- `DOTOCRM_MODEL_PATH` / `DOTOCRM_CACHE_DIR`: persistent storage locations

## Development

```bash
./scripts/bootstrap.sh
uv sync
make lint
make test
```

## Repository layout

```text
src/dotocrm_api/       Python package
deploy/systemd/        Rendered-at-install systemd templates
deploy/nginx/          Nginx template
scripts/               Bootstrap, model, run, install, and health scripts
tests/                 Unit and API compatibility tests
docs/                  Architecture and compatibility notes
```

## Current scope

The MinerU layer supports PDF and common image files. It maps dots.mocr layout
blocks into MinerU-shaped outputs; it does not run MinerU's pipeline models or
Office conversion stack. Async task state is in memory and is reset when the API
process restarts.
