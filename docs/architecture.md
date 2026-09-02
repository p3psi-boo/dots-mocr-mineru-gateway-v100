# Architecture

## Processes

The deployment consists of three independent processes:

1. **vLLM** loads dots.mocr and exposes an OpenAI-compatible API.
2. **FastAPI gateway** validates uploads, resizes pages, calls vLLM, repairs and
   normalizes model JSON, and renders native or MinerU-compatible responses.
3. **Nginx** provides the public IPv4/IPv6 listener and preserves forwarded host
   information used by MinerU task URLs.

No Docker runtime is required.

## V100 backend selection

The tested runtime uses vLLM 0.11.2 on a V100/SM70 GPU:

- decoder attention: `VLLM_ATTENTION_BACKEND=TRITON_ATTN`
- multimodal encoder attention: `--mm-encoder-attn-backend XFORMERS`
- dtype: FP16
- tensor parallel size: 1
- maximum concurrent sequences: 4 (`VLLM_MAX_NUM_SEQS`)
- multimodal processor cache disabled: pages never repeat
- uvicorn access log disabled

vLLM 0.11.2's XFormers paged-decoding operators require SM80, so the decoder
must use Triton on V100. The vision encoder remains on XFormers.

## Request flow

1. The gateway validates upload size and file type.
2. PDFs are rendered one page at a time with PyMuPDF.
3. Images are flattened to RGB, resized to the configured pixel budget, and
   encoded as JPEG for the local vLLM request.
4. dots.mocr returns layout block JSON.
5. The gateway repairs minor JSON syntax errors, validates blocks, and maps
   coordinates back to the uploaded page.
6. The native endpoint returns blocks directly. The compatibility layer builds
   Markdown and MinerU-shaped artifacts.

## State and concurrency

- GPU calls share a process-wide semaphore limited by `OCR_MAX_INFLIGHT`
  (default 4), which must match vLLM's `--max-num-seqs`.
- MinerU tasks use an in-memory task manager; `MINERU_MAX_CONCURRENT_REQUESTS`
  tasks run at once and defaults to `OCR_MAX_INFLIGHT`.
- Completions are streamed. When the output tail becomes an exact repetition
  of at least `OCR_LOOP_GUARD_CHARS` characters, the gateway closes the
  stream so vLLM aborts the request, trims the repeated tail, and returns the
  page with `complete: false` and a `repetition_loop_aborted` warning.
- `OCR_REPETITION_PENALTY` (default 1.0, disabled) is passed to vLLM when
  set; it changes model output, so validate before enabling.
- Completed task artifacts are retained for 24 hours by default.
- Each API process has independent task state; production uses one API worker.
