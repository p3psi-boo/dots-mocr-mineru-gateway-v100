# MinerU compatibility

The compatibility layer implements MinerU API protocol version 2 while keeping
dots.mocr as the only inference model.

## Routes

| Method | Path | Behavior |
|---|---|---|
| GET | `/health` | Protocol, concurrency, and task statistics |
| POST | `/file_parse` | Submit and wait for the final result |
| POST | `/tasks` | Submit and return `202` with a task ID |
| GET | `/tasks/{task_id}` | Return task status |
| GET | `/tasks/{task_id}/result` | Return `202`, `409`, or the final result |

## Inputs

Supported uploads:

- PDF
- PNG, JPEG, WebP, BMP, and TIFF images
- Up to eight files per request by default
- Up to 15 MiB per file by default
- Up to 64 selected PDF pages by default

The following MinerU form fields are accepted:

- `lang_list`
- `backend`, `effort`, `parse_method`, `server_url`
- `formula_enable`, `table_enable`, `image_analysis`
- `return_md`, `return_middle_json`, `return_model_output`
- `return_content_list`, `return_images`
- `response_format_zip`, `return_original_file`
- `client_side_output_generation`
- `start_page_id`, `end_page_id`

`backend` is echoed for response compatibility; inference always uses the
configured dots.mocr vLLM endpoint.

## Outputs

- `md_content`: Markdown generated from layout blocks
- `content_list`: flat MinerU-style content list with 0–1000 bounding boxes
- `middle_json`: page-oriented intermediate layout structure
- `model_output`: dots.mocr blocks grouped by page
- `images`: data URLs for extracted picture regions
- ZIP: MinerU-style per-document artifact folders

## Differences from a full MinerU installation

- No MinerU pipeline, hybrid, or MinerU VLM weights are loaded.
- Office files are not converted.
- Advanced paragraph merging and formula/table post-processing use dots.mocr's
  output rather than MinerU's post-processing pipeline.
- Task state is in memory and does not survive an API restart.

The native `/v1/ocr/layout` endpoint supports `X-API-Key`. MinerU protocol
clients do not define this custom header, so the compatibility routes are kept
header-compatible and should be exposed through the intended network boundary.
