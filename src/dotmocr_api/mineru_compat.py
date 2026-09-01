from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import time
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import orjson
import pymupdf as fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image

from . import __version__

PROTOCOL_VERSION = 2
COMPAT_VERSION = f"dots.mocr-mineru-compat-{__version__}"
MAX_CONCURRENT_REQUESTS = 2
PROCESSING_WINDOW_SIZE = int(os.getenv("MINERU_PROCESSING_WINDOW_SIZE", "64"))
TASK_RETENTION_SECONDS = int(os.getenv("MINERU_TASK_RETENTION_SECONDS", "86400"))
MAX_FILES_PER_REQUEST = int(os.getenv("MINERU_MAX_FILES", "8"))

InferLayout = Callable[..., Awaitable[dict[str, Any]]]
DecodeImage = Callable[[bytes], Image.Image]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> float:
    if not value:
        return time.time()
    return datetime.fromisoformat(value).timestamp()


def json_text(value: Any) -> str:
    return orjson.dumps(value).decode("utf-8")


def json_response(content: Any, status_code: int = 200) -> Response:
    return Response(
        content=orjson.dumps(content),
        media_type="application/json",
        status_code=status_code,
    )


def safe_stem(filename: str, fallback: str) -> str:
    stem = Path(filename).stem.strip()
    stem = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", stem)
    stem = stem.strip(" ._")
    return stem[:120] or fallback


def unique_stems(names: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    output: list[str] = []
    for name in names:
        key = name.casefold()
        counts[key] = counts.get(key, 0) + 1
        number = counts[key]
        output.append(name if number == 1 else f"{name}__upload_{number}")
    return output


@dataclass(slots=True)
class ParseOptions:
    lang_list: list[str]
    backend: str
    effort: str
    parse_method: str
    formula_enable: bool
    table_enable: bool
    image_analysis: bool
    server_url: str | None
    return_md: bool
    return_middle_json: bool
    return_model_output: bool
    return_content_list: bool
    return_images: bool
    response_format_zip: bool
    return_original_file: bool
    client_side_output_generation: bool
    start_page_id: int
    end_page_id: int


@dataclass(slots=True)
class UploadAsset:
    original_name: str
    stem: str
    suffix: str
    content: bytes


@dataclass(slots=True)
class FileArtifacts:
    stem: str
    markdown: str
    middle_json: dict[str, Any]
    model_output: list[dict[str, Any]]
    content_list: list[dict[str, Any]]
    images: dict[str, str]


@dataclass(slots=True)
class ParseTask:
    task_id: str
    options: ParseOptions
    assets: list[UploadAsset]
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    submit_order: int = 0
    artifacts: dict[str, FileArtifacts] = field(default_factory=dict)
    done: asyncio.Event = field(default_factory=asyncio.Event)

    def status_payload(
        self,
        request: Request,
        queued_ahead: int | None = None,
    ) -> dict[str, Any]:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get(
            "x-forwarded-host",
            request.headers.get("host", request.url.netloc),
        )
        base_url = f"{scheme}://{host}".rstrip("/")
        payload: dict[str, Any] = {
            "task_id": self.task_id,
            "status": self.status,
            "backend": self.options.backend,
            "file_names": [asset.stem for asset in self.assets],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "status_url": f"{base_url}/tasks/{self.task_id}",
            "result_url": f"{base_url}/tasks/{self.task_id}/result",
        }
        if queued_ahead is not None:
            payload["queued_ahead"] = queued_ahead
        return payload


async def parse_request_options(
    files: Annotated[
        list[UploadFile],
        File(description="Upload PDF or image files for parsing"),
    ],
    lang_list: Annotated[list[str], Form()] = ["ch"],
    backend: Annotated[str, Form()] = "pipeline",
    effort: Annotated[str, Form()] = "medium",
    parse_method: Annotated[str, Form()] = "auto",
    formula_enable: Annotated[bool, Form()] = True,
    table_enable: Annotated[bool, Form()] = True,
    image_analysis: Annotated[bool, Form()] = True,
    server_url: Annotated[str | None, Form()] = None,
    return_md: Annotated[bool, Form()] = True,
    return_middle_json: Annotated[bool, Form()] = False,
    return_model_output: Annotated[bool, Form()] = False,
    return_content_list: Annotated[bool, Form()] = False,
    return_images: Annotated[bool, Form()] = False,
    response_format_zip: Annotated[bool, Form()] = False,
    return_original_file: Annotated[bool, Form()] = False,
    client_side_output_generation: Annotated[bool, Form()] = False,
    start_page_id: Annotated[int, Form()] = 0,
    end_page_id: Annotated[int, Form()] = 99999,
) -> tuple[list[UploadFile], ParseOptions]:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_FILES_PER_REQUEST} files are allowed",
        )
    if parse_method not in {"auto", "txt", "ocr"}:
        raise HTTPException(status_code=400, detail="Invalid parse_method")
    if start_page_id < 0 or end_page_id < start_page_id:
        raise HTTPException(status_code=400, detail="Invalid page range")

    if client_side_output_generation:
        return_md = False
        return_middle_json = True
        return_model_output = True
        return_content_list = False
        return_images = True

    return files, ParseOptions(
        lang_list=lang_list or ["ch"],
        backend=backend,
        effort=effort,
        parse_method=parse_method,
        formula_enable=formula_enable,
        table_enable=table_enable,
        image_analysis=image_analysis,
        server_url=server_url,
        return_md=return_md,
        return_middle_json=return_middle_json,
        return_model_output=return_model_output,
        return_content_list=return_content_list,
        return_images=return_images,
        response_format_zip=response_format_zip,
        return_original_file=return_original_file and response_format_zip,
        client_side_output_generation=client_side_output_generation,
        start_page_id=start_page_id,
        end_page_id=end_page_id,
    )


async def load_uploads(
    files: list[UploadFile],
    max_upload_bytes: int,
) -> list[UploadAsset]:
    pending: list[tuple[str, str, bytes]] = []
    for index, upload in enumerate(files):
        original_name = Path(upload.filename or f"upload-{index + 1}").name
        content = await upload.read(max_upload_bytes + 1)
        await upload.close()
        if not content:
            raise HTTPException(
                status_code=400, detail=f"Empty upload: {original_name}"
            )
        if len(content) > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload is too large: {original_name}",
            )
        suffix = Path(original_name).suffix.lower()
        if content.startswith(b"%PDF-"):
            suffix = ".pdf"
        elif suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            suffix = ".image"
        pending.append(
            (
                original_name,
                safe_stem(original_name, f"file_{index + 1}"),
                content,
            )
        )

    stems = unique_stems([item[1] for item in pending])
    return [
        UploadAsset(
            original_name=original_name,
            stem=stem,
            suffix=(
                ".pdf"
                if content.startswith(b"%PDF-")
                else Path(original_name).suffix.lower() or ".image"
            ),
            content=content,
        )
        for (original_name, _, content), stem in zip(pending, stems)
    ]


def pdf_page_count(content: bytes) -> int:
    try:
        with fitz.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("Encrypted PDF is not supported")
            return document.page_count
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError("Invalid PDF") from exc


def render_pdf_page(content: bytes, page_index: int) -> Image.Image:
    try:
        with fitz.open(stream=content, filetype="pdf") as document:
            page = document.load_page(page_index)
            rect = page.rect
            zoom = 2.0
            projected_pixels = rect.width * rect.height * zoom * zoom
            if projected_pixels > 6_000_000:
                zoom *= (6_000_000 / projected_pixels) ** 0.5
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Could not render PDF page {page_index}") from exc


def normalized_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    return [
        max(0, min(1000, round(bbox[0] * 1000 / width))),
        max(0, min(1000, round(bbox[1] * 1000 / height))),
        max(0, min(1000, round(bbox[2] * 1000 / width))),
        max(0, min(1000, round(bbox[3] * 1000 / height))),
    ]


def image_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(
        "ascii"
    )


def markdown_for_block(block: dict[str, Any], image_path: str | None) -> str:
    category = block["category"]
    text = str(block.get("text", "")).strip()
    if category == "Title":
        return f"# {text}" if text else ""
    if category == "Section-header":
        return f"## {text}" if text else ""
    if category == "List-item":
        return text if text.startswith(("- ", "* ", "+ ")) else f"- {text}"
    if category == "Formula":
        return f"$$\n{text}\n$$" if text else ""
    if category == "Picture":
        return f"![]({image_path})" if image_path else ""
    return text


def content_item_for_block(
    block: dict[str, Any],
    *,
    page_index: int,
    page_width: int,
    page_height: int,
    image_path: str | None,
) -> dict[str, Any] | None:
    category = block["category"]
    text = str(block.get("text", ""))
    item: dict[str, Any] = {
        "bbox": normalized_bbox(block["bbox"], page_width, page_height),
        "page_idx": page_index,
    }
    if category in {"Title", "Section-header", "Text", "Caption"}:
        item.update(type="text", text=text)
        if category == "Title":
            item["text_level"] = 1
        elif category == "Section-header":
            item["text_level"] = 2
    elif category == "Table":
        item.update(type="table", table_body=text)
    elif category == "Formula":
        item.update(type="equation", text=text)
    elif category == "List-item":
        item.update(type="list", sub_type="text", list_items=[text])
    elif category == "Picture":
        item.update(type="image", img_path=image_path or "")
    elif category == "Page-header":
        item.update(type="header", text=text)
    elif category == "Page-footer":
        item.update(type="footer", text=text)
    elif category == "Footnote":
        item.update(type="page_footnote", text=text)
    else:
        item.update(type="text", text=text)
    return item


def middle_block(block: dict[str, Any]) -> dict[str, Any]:
    category = block["category"]
    type_map = {
        "Title": "title",
        "Section-header": "title",
        "Text": "text",
        "Caption": "text",
        "Table": "table",
        "Formula": "equation",
        "List-item": "list",
        "Picture": "image",
        "Page-header": "header",
        "Page-footer": "footer",
        "Footnote": "page_footnote",
    }
    block_type = type_map.get(category, "text")
    content = str(block.get("text", ""))
    span: dict[str, Any] = {
        "bbox": block["bbox"],
        "type": block_type,
        "content": content,
    }
    return {
        "type": block_type,
        "bbox": block["bbox"],
        "lines": [{"bbox": block["bbox"], "spans": [span]}],
    }


def convert_page(
    *,
    stem: str,
    image: Image.Image,
    page_index: int,
    inference: dict[str, Any],
    options: ParseOptions,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, str]]:
    markdown_parts: list[str] = []
    content_list: list[dict[str, Any]] = []
    para_blocks: list[dict[str, Any]] = []
    discarded_blocks: list[dict[str, Any]] = []
    images: dict[str, str] = {}
    model_blocks: list[dict[str, Any]] = []

    for block in inference["blocks"]:
        category = block["category"]
        if category == "Formula" and not options.formula_enable:
            category = "Text"
        if category == "Table" and not options.table_enable:
            category = "Text"
        effective = {**block, "category": category}
        model_blocks.append(effective)

        path: str | None = None
        if category == "Picture" and options.image_analysis:
            x1, y1, x2, y2 = effective["bbox"]
            if x2 > x1 and y2 > y1:
                path = f"images/{stem}_p{page_index + 1}_{effective['id']}.png"
                images[Path(path).name] = image_data_url(image.crop((x1, y1, x2, y2)))

        markdown = markdown_for_block(effective, path)
        if markdown:
            markdown_parts.append(markdown)
        content_item = content_item_for_block(
            effective,
            page_index=page_index,
            page_width=image.width,
            page_height=image.height,
            image_path=path,
        )
        if content_item:
            content_list.append(content_item)
        target = (
            discarded_blocks
            if category in {"Page-header", "Page-footer", "Footnote"}
            else para_blocks
        )
        target.append(middle_block(effective))

    middle_page = {
        "page_idx": page_index,
        "page_size": [image.width, image.height],
        "para_blocks": para_blocks,
        "discarded_blocks": discarded_blocks,
    }
    model_page = {
        "page_idx": page_index,
        "width": image.width,
        "height": image.height,
        "blocks": model_blocks,
        "complete": inference.get("complete", True),
        "warnings": inference.get("warnings", []),
    }
    return "\n\n".join(markdown_parts), content_list, middle_page, model_page, images


async def process_asset(
    asset: UploadAsset,
    options: ParseOptions,
    infer_layout_image: InferLayout,
    decode_image: DecodeImage,
) -> FileArtifacts:
    is_pdf = asset.content.startswith(b"%PDF-")
    if is_pdf:
        page_count = await asyncio.to_thread(pdf_page_count, asset.content)
        last_page = min(options.end_page_id, page_count - 1)
        page_indices = list(range(options.start_page_id, last_page + 1))
        if len(page_indices) > PROCESSING_WINDOW_SIZE:
            raise ValueError(
                f"Selected page range exceeds {PROCESSING_WINDOW_SIZE} pages"
            )
    else:
        page_indices = [0] if options.start_page_id == 0 else []

    if not page_indices:
        raise ValueError("Selected page range contains no pages")

    markdown_pages: list[str] = []
    content_list: list[dict[str, Any]] = []
    middle_pages: list[dict[str, Any]] = []
    model_pages: list[dict[str, Any]] = []
    images: dict[str, str] = {}

    for page_index in page_indices:
        if is_pdf:
            image = await asyncio.to_thread(render_pdf_page, asset.content, page_index)
        else:
            try:
                image = decode_image(asset.content)
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported file type: {asset.original_name}"
                ) from exc

        inference = await infer_layout_image(
            image,
            request_id=f"mineru_{uuid.uuid4().hex}",
        )
        markdown, page_content, middle_page, model_page, page_images = convert_page(
            stem=asset.stem,
            image=image,
            page_index=page_index,
            inference=inference,
            options=options,
        )
        if markdown:
            markdown_pages.append(markdown)
        content_list.extend(page_content)
        middle_pages.append(middle_page)
        model_pages.append(model_page)
        images.update(page_images)

    return FileArtifacts(
        stem=asset.stem,
        markdown="\n\n".join(markdown_pages),
        middle_json={
            "pdf_info": middle_pages,
            "_backend": "dots.mocr-vllm",
        },
        model_output=model_pages,
        content_list=content_list,
        images=images,
    )


class TaskManager:
    def __init__(
        self,
        infer_layout_image: InferLayout,
        decode_image: DecodeImage,
    ) -> None:
        self.infer_layout_image = infer_layout_image
        self.decode_image = decode_image
        self.tasks: dict[str, ParseTask] = {}
        self._order = 0
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    def cleanup(self) -> None:
        now = time.time()
        expired = [
            task_id
            for task_id, task in self.tasks.items()
            if task.status in {"completed", "failed"}
            and now - parse_iso(task.completed_at) >= TASK_RETENTION_SECONDS
        ]
        for task_id in expired:
            self.tasks.pop(task_id, None)

    def submit(self, options: ParseOptions, assets: list[UploadAsset]) -> ParseTask:
        self.cleanup()
        self._order += 1
        task = ParseTask(
            task_id=str(uuid.uuid4()),
            options=options,
            assets=assets,
            submit_order=self._order,
        )
        self.tasks[task.task_id] = task
        asyncio.create_task(self._run(task), name=f"mineru-compat-{task.task_id}")
        return task

    async def _run(self, task: ParseTask) -> None:
        try:
            async with self._semaphore:
                task.status = "processing"
                task.started_at = utc_now_iso()
                for asset in task.assets:
                    artifact = await process_asset(
                        asset,
                        task.options,
                        self.infer_layout_image,
                        self.decode_image,
                    )
                    task.artifacts[asset.stem] = artifact
                task.status = "completed"
        except asyncio.CancelledError:
            task.status = "failed"
            task.error = "Task cancelled"
            raise
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
        finally:
            task.completed_at = utc_now_iso()
            task.done.set()

    def queued_ahead(self, task: ParseTask) -> int:
        if task.status != "pending":
            return 0
        return sum(
            other.status == "pending" and other.submit_order < task.submit_order
            for other in self.tasks.values()
        )

    def stats(self) -> dict[str, int]:
        self.cleanup()
        return {
            state: sum(task.status == state for task in self.tasks.values())
            for state in ("pending", "processing", "completed", "failed")
        }


def public_results(task: ParseTask) -> dict[str, dict[str, Any]]:
    options = task.options
    results: dict[str, dict[str, Any]] = {}
    for asset in task.assets:
        artifact = task.artifacts.get(asset.stem)
        data: dict[str, Any] = {}
        if artifact is not None:
            if options.return_md:
                data["md_content"] = artifact.markdown
            if options.return_middle_json:
                data["middle_json"] = json_text(artifact.middle_json)
            if options.return_model_output:
                data["model_output"] = json_text(artifact.model_output)
            if options.return_content_list:
                data["content_list"] = json_text(artifact.content_list)
            if options.return_images:
                data["images"] = artifact.images
        results[asset.stem] = data
    return results


def result_zip(task: ParseTask) -> bytes:
    buffer = io.BytesIO()
    options = task.options
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for asset in task.assets:
            artifact = task.artifacts.get(asset.stem)
            if artifact is None:
                continue
            root = f"{asset.stem}/vlm"
            if options.return_md:
                archive.writestr(f"{root}/{asset.stem}.md", artifact.markdown)
            if options.return_middle_json:
                archive.writestr(
                    f"{root}/{asset.stem}_middle.json",
                    json_text(artifact.middle_json),
                )
            if options.return_model_output:
                archive.writestr(
                    f"{root}/{asset.stem}_model.json",
                    json_text(artifact.model_output),
                )
            if options.return_content_list:
                archive.writestr(
                    f"{root}/{asset.stem}_content_list.json",
                    json_text(artifact.content_list),
                )
            if options.return_images:
                for name, data_url in artifact.images.items():
                    archive.writestr(
                        f"{root}/images/{name}",
                        base64.b64decode(data_url.partition(",")[2]),
                    )
            if options.return_original_file:
                suffix = asset.suffix if asset.suffix.startswith(".") else ".bin"
                archive.writestr(
                    f"{root}/{asset.stem}_origin{suffix}",
                    asset.content,
                )
    return buffer.getvalue()


def zip_response(task: ParseTask, request: Request, *, synchronous: bool) -> Response:
    headers = {
        "Content-Disposition": f'attachment; filename="{task.task_id}.zip"',
    }
    if synchronous:
        payload = task.status_payload(request)
        headers.update(
            {
                "X-MinerU-Task-Id": task.task_id,
                "X-MinerU-Task-Status": task.status,
                "X-MinerU-Task-Status-Url": payload["status_url"],
                "X-MinerU-Task-Result-Url": payload["result_url"],
            }
        )
    return Response(result_zip(task), media_type="application/zip", headers=headers)


def json_result_response(
    task: ParseTask,
    request: Request,
    *,
    synchronous: bool,
) -> Response:
    payload: dict[str, Any] = {
        "backend": task.options.backend,
        "version": COMPAT_VERSION,
        "results": public_results(task),
    }
    if synchronous:
        payload = {**task.status_payload(request), **payload}
    return json_response(payload)


def create_mineru_router(
    *,
    infer_layout_image: InferLayout,
    decode_image: DecodeImage,
    max_upload_bytes: int,
) -> APIRouter:
    router = APIRouter(tags=["MinerU compatibility"])
    manager = TaskManager(infer_layout_image, decode_image)

    async def submit_from_form(
        parsed: tuple[list[UploadFile], ParseOptions],
    ) -> ParseTask:
        files, options = parsed
        assets = await load_uploads(files, max_upload_bytes)
        return manager.submit(options, assets)

    @router.get("/health", name="mineru_health")
    async def health() -> dict[str, Any]:
        stats = manager.stats()
        return {
            "status": "healthy",
            "version": COMPAT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "queued_tasks": stats["pending"],
            "processing_tasks": stats["processing"],
            "completed_tasks": stats["completed"],
            "failed_tasks": stats["failed"],
            "max_concurrent_requests": MAX_CONCURRENT_REQUESTS,
            "processing_window_size": PROCESSING_WINDOW_SIZE,
            "task_retention_seconds": TASK_RETENTION_SECONDS,
            "task_cleanup_interval_seconds": 300,
            "model_backend": "dots.mocr-vllm",
        }

    @router.post("/tasks", status_code=202, name="mineru_submit_task")
    async def submit_task(
        request: Request,
        parsed: Annotated[
            tuple[list[UploadFile], ParseOptions],
            Depends(parse_request_options),
        ],
    ) -> Response:
        task = await submit_from_form(parsed)
        payload = task.status_payload(request, manager.queued_ahead(task))
        payload["message"] = "Task submitted successfully"
        return json_response(payload, status_code=202)

    @router.post("/file_parse", name="mineru_file_parse")
    async def file_parse(
        request: Request,
        parsed: Annotated[
            tuple[list[UploadFile], ParseOptions],
            Depends(parse_request_options),
        ],
    ) -> Response:
        task = await submit_from_form(parsed)
        await asyncio.shield(task.done.wait())
        if task.status == "failed":
            return json_response(
                {
                    **task.status_payload(request),
                    "message": "Task execution failed",
                },
                status_code=409,
            )
        if task.options.response_format_zip:
            return zip_response(task, request, synchronous=True)
        return json_result_response(task, request, synchronous=True)

    @router.get("/tasks/{task_id}", name="mineru_task_status")
    async def task_status(task_id: str, request: Request) -> Response:
        manager.cleanup()
        task = manager.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return json_response(task.status_payload(request, manager.queued_ahead(task)))

    @router.get("/tasks/{task_id}/result", name="mineru_task_result")
    async def task_result(task_id: str, request: Request) -> Response:
        manager.cleanup()
        task = manager.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status in {"pending", "processing"}:
            return json_response(
                {
                    **task.status_payload(request, manager.queued_ahead(task)),
                    "message": "Task result is not ready yet",
                },
                status_code=202,
            )
        if task.status == "failed":
            return json_response(
                {
                    **task.status_payload(request),
                    "message": "Task execution failed",
                },
                status_code=409,
            )
        if task.options.response_format_zip:
            return zip_response(task, request, synchronous=False)
        return json_result_response(task, request, synchronous=False)

    return router
