import asyncio
import io
import json
import time
import zipfile

import pymupdf
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from dotmocr_api import mineru_compat
from dotmocr_api.app import decode_image
from dotmocr_api.mineru_compat import create_mineru_router


async def fake_inference(image, *, request_id=None):
    return {
        "request_id": request_id or "test",
        "complete": True,
        "warnings": [],
        "blocks": [
            {
                "id": "b0",
                "order": 0,
                "category": "Title",
                "bbox": [10, 10, image.width - 10, 50],
                "text": "Fixture title",
            },
            {
                "id": "b1",
                "order": 1,
                "category": "Table",
                "bbox": [10, 60, image.width - 10, image.height - 10],
                "text": "<table><tr><td>A</td></tr></table>",
            },
        ],
    }


def png_bytes() -> bytes:
    image = Image.new("RGB", (320, 240), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def pdf_bytes(page_count=2) -> bytes:
    document = pymupdf.open()
    for _ in range(page_count):
        document.new_page(width=320, height=240)
    content = document.tobytes()
    document.close()
    return content


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_mineru_router(
            infer_layout_image=fake_inference,
            decode_image=decode_image,
            max_upload_bytes=2_000_000,
        )
    )
    return app


def test_health_matches_mineru_protocol_v2():
    with TestClient(make_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["protocol_version"] == 2
    assert payload["max_concurrent_requests"] == mineru_compat.MAX_CONCURRENT_REQUESTS


def test_sync_file_parse_returns_mineru_shaped_artifacts():
    with TestClient(make_app()) as client:
        response = client.post(
            "/file_parse",
            files={"files": ("fixture.png", png_bytes(), "image/png")},
            data={
                "return_md": "true",
                "return_content_list": "true",
                "return_middle_json": "true",
                "return_model_output": "true",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["status_url"].startswith("http://testserver/tasks/")
    result = payload["results"]["fixture"]
    assert result["md_content"].startswith("# Fixture title")
    assert len(json.loads(result["content_list"])) == 2
    assert len(json.loads(result["middle_json"])["pdf_info"]) == 1
    assert len(json.loads(result["model_output"])) == 1


def test_pdf_page_range_and_async_result():
    with TestClient(make_app()) as client:
        submitted = client.post(
            "/tasks",
            files={"files": ("two-pages.pdf", pdf_bytes(), "application/pdf")},
            data={
                "return_md": "true",
                "return_content_list": "true",
                "start_page_id": "1",
                "end_page_id": "1",
            },
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["task_id"]

        for _ in range(100):
            status = client.get(f"/tasks/{task_id}").json()["status"]
            if status in {"completed", "failed"}:
                break
            time.sleep(0.01)

        response = client.get(f"/tasks/{task_id}/result")

    assert status == "completed"
    assert response.status_code == 200
    content = json.loads(response.json()["results"]["two-pages"]["content_list"])
    assert {item["page_idx"] for item in content} == {1}


def test_zip_response_contains_requested_artifacts_and_original():
    with TestClient(make_app()) as client:
        response = client.post(
            "/file_parse",
            files={"files": ("fixture.png", png_bytes(), "image/png")},
            data={
                "return_md": "true",
                "return_content_list": "true",
                "response_format_zip": "true",
                "return_original_file": "true",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-mineru-task-status"] == "completed"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
    assert "fixture/vlm/fixture.md" in names
    assert "fixture/vlm/fixture_content_list.json" in names
    assert "fixture/vlm/fixture_origin.png" in names


def test_cancel_running_task():
    async def slow_inference(image, *, request_id=None):
        await asyncio.sleep(20)
        return await fake_inference(image, request_id=request_id)

    app = FastAPI()
    app.include_router(
        create_mineru_router(
            infer_layout_image=slow_inference,
            decode_image=decode_image,
            max_upload_bytes=2_000_000,
        )
    )
    with TestClient(app) as client:
        submitted = client.post(
            "/tasks",
            files={"files": ("fixture.png", png_bytes(), "image/png")},
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["task_id"]
        assert client.get(f"/tasks/{task_id}").json()["status"] in {
            "pending",
            "processing",
        }

        cancelled = client.post(f"/tasks/{task_id}/cancel")
        assert cancelled.status_code == 200
        payload = cancelled.json()
        assert payload["status"] == "failed"
        assert payload["error"] == "Task cancelled"

        again = client.post(f"/tasks/{task_id}/cancel")
        assert again.status_code == 409
