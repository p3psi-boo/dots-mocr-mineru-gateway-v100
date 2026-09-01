from __future__ import annotations

import asyncio
import base64
import hmac
import io
import math
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
import orjson
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from json_repair import repair_json
from PIL import Image, ImageOps, UnidentifiedImageError

from . import __version__

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://[::1]:8001")
VLLM_MODEL = os.getenv("VLLM_MODEL", "dots-mocr")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "replace-this-key")

PUBLIC_API_KEY = os.getenv("PUBLIC_API_KEY", "")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.getenv("OCR_MAX_PIXELS", "2200000"))
MAX_OUTPUT_TOKENS = int(os.getenv("OCR_MAX_OUTPUT_TOKENS", "8192"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("OCR_TIMEOUT_SECONDS", "240"))

IMAGE_FACTOR = 28
MIN_IMAGE_PIXELS = 3136
MAX_INFLIGHT = 2

Image.MAX_IMAGE_PIXELS = 80_000_000

GPU_SEMAPHORE = asyncio.Semaphore(MAX_INFLIGHT)

ALLOWED_CATEGORIES = {
    "Caption",
    "Footnote",
    "Formula",
    "List-item",
    "Page-footer",
    "Page-header",
    "Picture",
    "Section-header",
    "Table",
    "Text",
    "Title",
    "Other",
    "Unknown",
}

LAYOUT_PROMPT = """
Extract all layout blocks from this document image.

Return JSON only. The preferred top-level value is an array of block objects.

Each block must contain:
- bbox: [x1, y1, x2, y2]
- category: one of Caption, Footnote, Formula, List-item,
  Page-footer, Page-header, Picture, Section-header, Table,
  Text, or Title
- text: recognized content, except Picture may omit it

Keep blocks in human reading order.
Keep the original language and do not translate.
Represent formulas as LaTeX.
Represent tables as HTML.
Represent other text as Markdown.
Do not add explanations or Markdown code fences.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0),
        limits=httpx.Limits(
            max_connections=8,
            max_keepalive_connections=4,
        ),
    )

    yield

    await app.state.http.aclose()


app = FastAPI(
    title="dots.mocr Layout OCR API",
    version=__version__,
    lifespan=lifespan,
)


async def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if not PUBLIC_API_KEY:
        return

    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key")

    if not hmac.compare_digest(x_api_key, PUBLIC_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


def round_by_factor(value: int, factor: int) -> int:
    return round(value / factor) * factor


def floor_by_factor(value: float, factor: int) -> int:
    return math.floor(value / factor) * factor


def ceil_by_factor(value: float, factor: int) -> int:
    return math.ceil(value / factor) * factor


def smart_resize(
    height: int,
    width: int,
    *,
    max_pixels: int,
    min_pixels: int = MIN_IMAGE_PIXELS,
    factor: int = IMAGE_FACTOR,
) -> tuple[int, int]:
    if height <= 0 or width <= 0:
        raise ValueError("Invalid image dimensions")

    ratio = max(height, width) / min(height, width)

    if ratio > 200:
        raise ValueError("Image aspect ratio exceeds 200:1")

    resized_height = max(factor, round_by_factor(height, factor))
    resized_width = max(factor, round_by_factor(width, factor))

    if resized_height * resized_width > max_pixels:
        scale = math.sqrt((height * width) / max_pixels)

        resized_height = max(
            factor,
            floor_by_factor(height / scale, factor),
        )
        resized_width = max(
            factor,
            floor_by_factor(width / scale, factor),
        )

    elif resized_height * resized_width < min_pixels:
        scale = math.sqrt(min_pixels / (height * width))

        resized_height = ceil_by_factor(height * scale, factor)
        resized_width = ceil_by_factor(width * scale, factor)

    # Rounding may exceed max_pixels by one factor step.
    if resized_height * resized_width > max_pixels:
        scale = math.sqrt((resized_height * resized_width) / max_pixels)

        resized_height = max(
            factor,
            floor_by_factor(resized_height / scale, factor),
        )
        resized_width = max(
            factor,
            floor_by_factor(resized_width / scale, factor),
        )

    return resized_height, resized_width


def decode_image(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)

            if "A" in image.getbands():
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                return background

            return image.convert("RGB")

    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("Unsupported or invalid image") from exc


def prepare_model_image(
    original: Image.Image,
) -> tuple[Image.Image, str]:
    input_height, input_width = smart_resize(
        original.height,
        original.width,
        max_pixels=MAX_IMAGE_PIXELS,
    )

    if (input_width, input_height) == original.size:
        model_image = original
    else:
        model_image = original.resize(
            (input_width, input_height),
            Image.Resampling.LANCZOS,
        )

    buffer = io.BytesIO()

    # JPEG reduces local HTTP and base64 overhead.
    # Change to PNG for maximum text fidelity.
    model_image.save(
        buffer,
        format="JPEG",
        quality=90,
        optimize=False,
    )

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    data_url = f"data:image/jpeg;base64,{encoded}"

    return model_image, data_url


def strip_code_fence(text: str) -> str:
    stripped = text.strip()

    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()

    if lines:
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def parse_blocks(text: str) -> tuple[list[dict[str, Any]], bool]:
    candidate = strip_code_fence(text)
    repaired = False

    try:
        parsed: Any = orjson.loads(candidate)
    except orjson.JSONDecodeError:
        parsed = repair_json(candidate, return_objects=True)
        repaired = True

        if isinstance(parsed, str):
            parsed = orjson.loads(parsed)

    if isinstance(parsed, list):
        return parsed, repaired

    if isinstance(parsed, dict):
        # A single block object.
        if "bbox" in parsed and "category" in parsed:
            return [parsed], repaired

        # Accept common wrapper names.
        for key in ("blocks", "elements", "layout", "cells"):
            value = parsed.get(key)

            if isinstance(value, list):
                return value, repaired

    raise ValueError("Model output is not a layout JSON array")


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def normalize_blocks(
    raw_blocks: list[dict[str, Any]],
    *,
    original_width: int,
    original_height: int,
    input_width: int,
    input_height: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    blocks: list[dict[str, Any]] = []
    warnings: list[str] = []

    scale_x = original_width / input_width
    scale_y = original_height / input_height

    for source_index, raw_block in enumerate(raw_blocks):
        if not isinstance(raw_block, dict):
            warnings.append(f"block {source_index}: not an object")
            continue

        bbox = raw_block.get("bbox")

        if not isinstance(bbox, list) or len(bbox) != 4:
            warnings.append(f"block {source_index}: invalid bbox")
            continue

        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            warnings.append(f"block {source_index}: non-numeric bbox")
            continue

        mapped_bbox = [
            clamp(round(x1 * scale_x), 0, original_width),
            clamp(round(y1 * scale_y), 0, original_height),
            clamp(round(x2 * scale_x), 0, original_width),
            clamp(round(y2 * scale_y), 0, original_height),
        ]

        if mapped_bbox[2] <= mapped_bbox[0] or mapped_bbox[3] <= mapped_bbox[1]:
            warnings.append(f"block {source_index}: empty bbox")
            continue

        source_category = str(raw_block.get("category", "Unknown")).strip()

        if source_category in ALLOWED_CATEGORIES:
            category = source_category
        else:
            category = "Unknown"
            warnings.append(
                f"block {source_index}: unknown category {source_category!r}"
            )

        block: dict[str, Any] = {
            "id": f"b{len(blocks)}",
            "order": len(blocks),
            "category": category,
            "bbox": mapped_bbox,
        }

        if category != "Picture":
            text = raw_block.get("text", "")

            if text is None:
                text = ""
            elif not isinstance(text, str):
                text = orjson.dumps(text).decode("utf-8")

            block["text"] = text

        blocks.append(block)

    return blocks, warnings[:50]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    try:
        response = await app.state.http.get(f"{VLLM_BASE_URL}/health")
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="vLLM is unavailable",
        ) from exc

    return {"status": "ok"}


@app.post(
    "/v1/ocr/layout",
    dependencies=[Depends(require_api_key)],
)
async def ocr_layout(
    file: UploadFile = File(...),
) -> Response:
    upload = await file.read(MAX_UPLOAD_BYTES + 1)

    if not upload:
        raise HTTPException(status_code=400, detail="Empty upload")

    if len(upload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Upload is too large",
        )

    try:
        original = decode_image(upload)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    result = await infer_layout_image(original)

    return Response(
        content=orjson.dumps(result),
        media_type="application/json",
        headers={"X-Request-ID": result["request_id"]},
    )


async def infer_layout_image(
    original: Image.Image,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Run one already-decoded page through the shared dots.mocr backend."""
    total_started = time.perf_counter()
    request_id = request_id or f"ocr_{uuid.uuid4().hex}"

    model_image, image_data_url = prepare_model_image(original)

    request_body = {
        "model": VLLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url,
                        },
                    },
                    {
                        "type": "text",
                        "text": ("<|img|><|imgpad|><|endofimg|>" + LAYOUT_PROMPT),
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {VLLM_API_KEY}",
        "X-Request-ID": request_id,
    }

    queue_started = time.perf_counter()

    async with GPU_SEMAPHORE:
        queue_ms = round((time.perf_counter() - queue_started) * 1000)

        model_started = time.perf_counter()

        try:
            response = await app.state.http.post(
                f"{VLLM_BASE_URL}/v1/chat/completions",
                headers=headers,
                json=request_body,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail="Model request timed out",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail="Could not reach model server",
            ) from exc

        model_ms = round((time.perf_counter() - model_started) * 1000)

    if response.status_code >= 400:
        detail = response.text[:500]

        raise HTTPException(
            status_code=502,
            detail=f"vLLM error: {detail}",
        )

    try:
        completion = orjson.loads(response.content)
        choice = completion["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError, orjson.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Invalid vLLM response",
        ) from exc

    if not isinstance(content, str):
        raise HTTPException(
            status_code=502,
            detail="Model content is not text",
        )

    try:
        raw_blocks, repaired = parse_blocks(content)
        blocks, warnings = normalize_blocks(
            raw_blocks,
            original_width=original.width,
            original_height=original.height,
            input_width=model_image.width,
            input_height=model_image.height,
        )
    except (ValueError, TypeError, orjson.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Model returned unparseable layout JSON",
        ) from exc

    if repaired:
        warnings.append("model_json_repaired")

    complete = finish_reason != "length"

    if not complete:
        warnings.append("output_truncated")

    total_ms = round((time.perf_counter() - total_started) * 1000)

    result = {
        "request_id": request_id,
        "model": VLLM_MODEL,
        "complete": complete,
        "page": {
            "index": 0,
            "width": original.width,
            "height": original.height,
            "model_input_width": model_image.width,
            "model_input_height": model_image.height,
            "bbox_space": "original_pixels",
        },
        "blocks": blocks,
        "usage": completion.get("usage"),
        "timing_ms": {
            "queue": queue_ms,
            "model": model_ms,
            "total": total_ms,
        },
        "warnings": warnings,
    }

    return result


# Imported after infer_layout_image is defined to keep the compatibility layer
# independent from the core OCR implementation.
from .mineru_compat import create_mineru_router  # noqa: E402

app.include_router(
    create_mineru_router(
        infer_layout_image=infer_layout_image,
        decode_image=decode_image,
        max_upload_bytes=MAX_UPLOAD_BYTES,
    )
)
