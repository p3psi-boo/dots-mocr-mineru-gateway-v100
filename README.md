# dots.mocr vLLM Gateway

基于 vLLM 运行 [`dots-studio/dots.mocr`](https://www.modelscope.cn/models/dots-studio/dots.mocr) 的 FastAPI 网关。对外提供原生版面 OCR 接口，以及 MinerU 协议 v2 兼容层。

参考部署环境为单卡 NVIDIA V100 16 GB + vLLM 0.11.2。模型路径、端口、并发与 GPU 参数均通过环境变量配置，不绑定固定目录。

## 简介

### 定位

本仓库解决两类接入需求：

1. **原生布局 OCR**：单页 PDF/图片 → 结构化 block JSON（坐标、类别、文本）。
2. **MinerU 协议兼容**：以 MinerU API v2 的路由与响应形态，对接已有客户端或 WebUI，底层推理仍为 dots.mocr。

不包含 MinerU 自有 pipeline 模型，也不做 Office 格式转换。

### 架构

```text
客户端
  │
  ▼ :8000（生产经 Nginx；本地/API 容器可直接 :8010 / :8000）
FastAPI 网关
  ├── POST /v1/ocr/layout          原生 OCR
  └── MinerU 协议 v2               /file_parse、/tasks 等
          │
          ▼ :8001
      vLLM + dots.mocr
```

运行时由三个独立进程组成：vLLM（模型服务）、FastAPI 网关（校验、分页、调用 vLLM、JSON 修复与 MinerU 映射）、Nginx（生产环境公网监听，可选）。Docker Compose 模式下 vLLM 仅在内网暴露，对外只发布网关端口。

V100 上已验证的 vLLM 配置要点：解码器 attention 使用 Triton（SM70 不支持 XFormers paged decoding），视觉编码器使用 XFormers，FP16，默认 4 路并发序列。详见 [docs/architecture.md](docs/architecture.md)。

### 环境要求

| 项 | 说明 |
|---|---|
| 平台 | x86_64 Linux |
| GPU | NVIDIA GPU 及与所选 PyTorch/vLLM 版本匹配的驱动 |
| Python | 网关 3.10–3.13；仓库 flake / `.python-version` 固定 3.12 |
| 开发环境 | 推荐 [Nix](https://nixos.org/) flakes；亦可自行安装 uv 与 Node.js 24 |
| 生产 | systemd + Nginx（模板随仓库提供） |
| 磁盘 | 模型权重约 6 GB，另需缓存与编译产物空间 |

## 使用教程

### 1. 获取代码与配置

```bash
git clone REPO_URL dotocrm
cd dotocrm
cp .env.example .env
chmod 600 .env
```

至少设置：

```dotenv
VLLM_API_KEY=generate-a-random-internal-key
PUBLIC_API_KEY=generate-a-random-public-key
DOTOCRM_MODEL_PATH=/opt/dotocrm/models/dots.mocr
```

完整变量说明见 [.env.example](.env.example)。

### 2. 安装依赖

使用 Nix（推荐）：

```bash
nix develop          # 或 direnv allow
./scripts/bootstrap.sh              # 仅网关
./scripts/bootstrap.sh --with-vllm  # 网关 + 已验证的 vLLM 运行时
```

无 Nix 时安装 [uv](https://docs.astral.sh/uv/) 与 Node.js 24 后执行相同 bootstrap 脚本。

### 3. 下载模型

```bash
./scripts/download-model.sh
```

默认从 ModelScope 拉取 `dots-studio/dots.mocr`。可通过 `MODELSCOPE_MODEL_ID` 或 `DOTOCRM_MODEL_PATH` 指向已有快照。

### 4. 本地运行

终端 1 — vLLM：

```bash
set -a; source .env; set +a
./scripts/run-vllm.sh
```

终端 2 — 网关：

```bash
set -a; source .env; set +a
./scripts/run-api.sh
```

默认监听 `[::]:8010`。客户端可直接访问 8010，或通过 Nginx 暴露 8000。

健康检查：

```bash
./scripts/healthcheck.sh
```

### 5. Docker Compose 部署

```bash
cp .env.docker.example .env.docker
chmod 600 .env.docker
./scripts/docker-up.sh
./scripts/docker-smoke-test.sh
```

拓扑：`主机 :8000 → api :8000 → vllm :8001`（vLLM 不对外映射）。V100 上模型冷启动约 90–120 秒，Compose 会等待 vLLM 健康后再启动 API。详见 [docs/docker.md](docs/docker.md)。

### 6. 生产部署（systemd）

在目标路径（如 `/opt/dotocrm`）执行：

```bash
sudo apt-get install -y nginx
./scripts/bootstrap.sh --with-vllm
./scripts/download-model.sh
DOTOCRM_USER="$USER" ./scripts/install-systemd.sh
./scripts/install-nginx.sh
sudo systemctl start dotocrm-vllm dotocrm-api
./scripts/healthcheck.sh
```

服务模板按当前仓库路径渲染，不要求固定安装在 `/opt/dotocrm`。

### 7. 调用示例

**原生版面 OCR**（需 `X-API-Key`）：

```bash
curl -X POST http://HOST:8000/v1/ocr/layout \
  -H 'X-API-Key: TOKEN' \
  -F 'file=@page.png'
```

响应含页面尺寸、有序 block、原图像素坐标、`complete` 状态、用量、耗时及解析告警。

**MinerU 同步解析**：

```bash
curl -X POST http://HOST:8000/file_parse \
  -F 'files=@document.pdf' \
  -F 'return_md=true' \
  -F 'return_content_list=true'
```

**MinerU 异步任务**：

```bash
curl -X POST http://HOST:8000/tasks \
  -F 'files=@document.pdf' \
  -F 'return_md=true'
```

### 8. WebUI

浏览器访问网关根路径（如 `http://HOST:8000/`）。内置 SvelteKit SPA，通过 MinerU 异步任务 API 完成上传、排队、结果预览；任务 ID 存 localStorage，原件与结果存 IndexedDB。

前端开发：

```bash
make web-install
make web-dev
```

Vite 开发服务器将 MinerU API 代理至 `127.0.0.1:8000`。

## 能力

### 原生 OCR（`/v1/ocr/layout`）

- 单页 PDF 或图片 → layout block JSON
- 支持 13 类版面元素（Title、Text、Table、Formula、Picture 等）
- 坐标映射回上传页原始像素
- 流式生成中的重复循环检测与截断（`OCR_LOOP_GUARD_CHARS`）
- 可选 API Key 鉴权（`PUBLIC_API_KEY` 为空则关闭）

### MinerU 协议 v2

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 协议版本、并发与任务统计 |
| POST | `/file_parse` | 同步提交并等待结果 |
| POST | `/tasks` | 异步提交，返回 202 + task_id |
| GET | `/tasks/{task_id}` | 任务状态 |
| GET | `/tasks/{task_id}/result` | 202 / 409 / 最终结果 |

**输入**：PDF；PNG、JPEG、WebP、BMP、TIFF。默认单请求最多 8 个文件、单文件 15 MiB、PDF 最多 64 页窗口。接受 MinerU 常用表单字段（`return_md`、`start_page_id` 等）；`backend` 等字段仅回显，推理始终走配置的 dots.mocr。

**输出**：Markdown、`content_list`、`middle_json`、`model_output`、提取图片 data URL、MinerU 风格 ZIP 包。映射规则见 [docs/mineru-compat.md](docs/mineru-compat.md)。

### WebUI

- 拖拽上传 PDF/图片，MinerU 解析选项与页码范围
- 队列与处理状态轮询、本地任务历史
- 原文与 JSON 驱动的 Markdown 对照预览、表格 CSV 导出、JSON 树、OpenAPI 参考、结构化事件日志

### 并发与限制

- GPU 请求由进程级信号量限制（`OCR_MAX_INFLIGHT`，默认 4，需与 `VLLM_MAX_NUM_SEQS` 一致）
- MinerU 异步任务并发默认同上；任务结果默认保留 24 小时
- 任务状态存于内存，API 进程重启后丢失；生产建议单 worker（`DOTOCRM_API_WORKERS=1`）
- 兼容层不加载 MinerU pipeline / hybrid / VLM 权重，不做 Office 转换与 MinerU 后处理流水线

### 配置分组（摘要）

| 前缀 | 用途 |
|---|---|
| `VLLM_*` | 模型服务 URL、密钥、引擎参数 |
| `DOTOCRM_API_*` | 网关监听、代理信任 |
| `OCR_*` | 图像像素预算、输出 token、超时、并发、循环防护 |
| `MINERU_*` | 任务保留、文件数、页窗口 |
| `DOTOCRM_MODEL_PATH` / `DOTOCRM_CACHE_DIR` | 模型与缓存路径 |

## 开发

### 日常命令

```bash
./scripts/bootstrap.sh
uv sync
make lint      # ruff check
make test      # pytest
make format    # ruff format
```

Web 前端：

```bash
make web-check
make web-build
```

Docker：

```bash
make docker-up
make docker-test
make docker-down
```

### 目录结构

```text
src/dotmocr_api/     Python 网关包
web/                  SvelteKit WebUI
deploy/systemd/       systemd 安装模板
deploy/nginx/         Nginx 模板
docker/               API 镜像构建
compose*.yaml         完整栈 / 仅 API 迁移测试
scripts/              引导、模型、运行、安装、健康检查
tests/                单元测试与 MinerU 兼容测试
docs/                 架构、Docker、MinerU 兼容说明
```

### 文档索引

- [docs/architecture.md](docs/architecture.md) — 进程划分、请求流、V100 后端选型
- [docs/docker.md](docs/docker.md) — 容器部署、GPU 验证、api-only 模式
- [docs/mineru-compat.md](docs/mineru-compat.md) — 协议字段、输出形态、与完整 MinerU 的差异

OpenAPI：`GET /openapi.json`；FastAPI 交互文档：`/docs`。
