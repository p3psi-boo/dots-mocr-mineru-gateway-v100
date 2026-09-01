#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${DOTOCRM_CACHE_DIR:-$ROOT/cache}"
MODEL_PATH="${DOTOCRM_MODEL_PATH:-$ROOT/models/dots.mocr}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
# vLLM 0.11.2 XFormers paged decode requires SM80. Triton retains V100/SM70 support.
export VLLM_ATTENTION_BACKEND="${VLLM_ATTENTION_BACKEND:-TRITON_ATTN}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export HF_HOME="${HF_HOME:-$CACHE_DIR/huggingface}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$CACHE_DIR}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$CACHE_DIR/triton}"

mkdir -p "$HF_HOME" "$TRITON_CACHE_DIR"

exec "$ROOT/.venv/bin/vllm" serve "$MODEL_PATH" \
  --served-model-name "${VLLM_MODEL:-dots-mocr}" \
  --host "${DOTOCRM_VLLM_HOST:-::}" \
  --port "${DOTOCRM_VLLM_PORT:-8001}" \
  --api-key "${VLLM_API_KEY:?VLLM_API_KEY is required}" \
  --dtype half \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.88}" \
  --max-model-len "${VLLM_MAX_MODEL_LEN:-16384}" \
  --max-num-seqs "${VLLM_MAX_NUM_SEQS:-2}" \
  --max-num-batched-tokens "${VLLM_MAX_BATCHED_TOKENS:-8192}" \
  --enable-chunked-prefill \
  --no-enable-prefix-caching \
  --limit-mm-per-prompt '{"image":1}' \
  --mm-encoder-attn-backend XFORMERS \
  --chat-template-content-format string \
  --generation-config vllm \
  --trust-remote-code
