from dotocrm_api.app import normalize_blocks, parse_blocks, smart_resize


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
