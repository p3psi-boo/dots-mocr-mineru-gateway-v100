from dotmocr_api.app import app, normalize_blocks, parse_blocks, smart_resize


def test_smart_resize_respects_factor_and_pixel_budget():
    height, width = smart_resize(4000, 3000, max_pixels=2_200_000)

    assert height % 28 == 0
    assert width % 28 == 0
    assert height * width <= 2_200_000


def test_parse_blocks_accepts_fenced_wrapper():
    blocks, repaired = parse_blocks(
        '```json\n{"blocks":[{"bbox":[1,2,3,4],"category":"Text","text":"ok"}]}\n```'
    )

    assert repaired is False
    assert blocks[0]["text"] == "ok"


def test_normalize_blocks_maps_coordinates_and_rejects_invalid_entries():
    blocks, warnings = normalize_blocks(
        [
            {"bbox": [10, 20, 100, 200], "category": "Text", "text": "hello"},
            {"bbox": [1, 2, 1, 9], "category": "Text", "text": "empty"},
        ],
        original_width=200,
        original_height=400,
        input_width=100,
        input_height=200,
    )

    assert blocks == [
        {
            "id": "b0",
            "order": 0,
            "category": "Text",
            "bbox": [20, 40, 200, 400],
            "text": "hello",
        }
    ]
    assert warnings == ["block 1: empty bbox"]


def test_openapi_document_describes_public_endpoints_and_api_key():
    document = app.openapi()

    assert document["info"]["title"] == "dots.mocr Layout OCR API"
    assert document["info"]["summary"]
    assert "/v1/ocr/layout" in document["paths"]
    assert "/tasks" in document["paths"]
    assert document["paths"]["/v1/ocr/layout"]["post"]["security"] == [
        {"GatewayApiKey": []}
    ]
    assert document["components"]["securitySchemes"]["GatewayApiKey"]["name"] == (
        "X-API-Key"
    )


def test_find_repetition_period_detects_short_and_block_loops():
    from dotmocr_api.app import find_repetition_period, trim_repetition

    prefix = '{"blocks":[{"bbox":[1,2,3,4],"category":"Text","text":"'

    short_loop = prefix + "| " * 600
    assert find_repetition_period(short_loop, 1024) == 2

    block = '{"bbox":[10,20,30,40],"category":"Text","text":"' + "x" * 400 + '"},'
    block_loop = prefix + block * 3
    assert find_repetition_period(block_loop, 1024) == len(block)
    assert trim_repetition(block_loop, len(block)) == prefix + block

    # Real content: distinct blocks never repeat exactly.
    distinct = prefix + "".join(
        f'{{"bbox":[{i},{i},{i + 5},{i + 5}],"category":"Text","text":"row {i}"}},'
        for i in range(200)
    )
    assert find_repetition_period(distinct, 1024) is None
    assert find_repetition_period("short", 1024) is None
    assert find_repetition_period(short_loop, 0) is None


def test_stream_completion_aborts_on_repetition_loop():
    import asyncio
    import json as std_json

    import httpx

    from dotmocr_api.app import stream_completion

    def sse(delta=None, finish_reason=None, usage=None):
        payload = {"choices": []}
        if delta is not None or finish_reason is not None:
            payload["choices"] = [
                {"delta": {"content": delta}, "finish_reason": finish_reason}
            ]
        if usage is not None:
            payload["usage"] = usage
        return f"data: {std_json.dumps(payload)}\n\n".encode()

    sent = {"chunks": 0}

    async def looping_body():
        yield sse('{"blocks":[{"bbox":[1,2,3,4],"category":"Text","text":"')
        while True:
            sent["chunks"] += 1
            yield sse("| |")
            if sent["chunks"] > 5000:
                return

    async def normal_body():
        yield sse('{"blocks":[]}')
        yield sse("", "stop")
        yield sse(usage={"prompt_tokens": 3, "completion_tokens": 2})
        yield b"data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        mode = request.headers["X-Mode"]
        body = looping_body() if mode == "loop" else normal_body()
        return httpx.Response(200, content=body)

    async def run(mode: str):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await stream_completion(
                client,
                "http://model/v1/chat/completions",
                headers={"X-Mode": mode},
                body={},
            )

    looped = asyncio.run(run("loop"))
    assert looped.loop_period == 3
    assert looped.finish_reason is None
    assert looped.content.endswith('"text":"| |')
    # The stream was closed long before the producer ran dry.
    assert sent["chunks"] < 1000

    normal = asyncio.run(run("normal"))
    assert normal.loop_period is None
    assert normal.finish_reason == "stop"
    assert normal.content == '{"blocks":[]}'
    assert normal.usage == {"prompt_tokens": 3, "completion_tokens": 2}
