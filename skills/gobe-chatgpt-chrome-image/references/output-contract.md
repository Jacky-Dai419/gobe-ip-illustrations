# Output Contract

The atomic image script writes one JSON manifest per run:

`<output-dir>/<prefix>-chatgpt-web-manifest.json`

Core fields:

- `status`: `ready`, `downloaded`, `downloaded_cleanup_failed`, or `failed`.
- `prompt_path`: prompt file used for the live job.
- `prompt_sha256`: hash for reproducibility.
- `bridge_status`: result of the bundled OpenCLI bridge status command.
- `reference_images`: absolute reference paths and content hashes.
- `reference_upload`: files attached to the logged-in ChatGPT Web composer.
- `before_state` / `final_state`: technical browser state around the batch.
- `download_payload`: parsed JSON from the bundled OpenCLI bridge download command.
- `downloaded_files`: absolute paths saved locally.
- `wechat_cover_files`: normalized 900x383 PNG files when `--wechat-cover` is used.
- `thread_url`: ChatGPT conversation URL when detected.
- `thread_cleanup`: requested action, attempted state, result, and conversation ID.
- `duration_seconds`: wall-clock duration for the run.

Consumer rules:

- When a visual plan is supplied, downloads are renamed in plan order. Treat this as mechanical mapping, not image review.
- A ChatGPT multi-image gallery may expose one large image and the remaining originals through small filmstrip thumbnails. Consumers must deduplicate the GPT original-image URLs inside the Assistant turn and treat the natural dimensions as authoritative; rendered thumbnail dimensions are not a reason to discard an asset.
- Use `downloaded_files[0]` as the primary image unless a higher-level role plan says otherwise.
- For WeChat official-account covers, prefer `wechat_cover_files[0]` over the raw download.
- If requested cleanup is not `ok`, do not mark the whole task successful even when images were downloaded.
- Never hide or delete a task before the downloaded image count equals the requested or planned count. On an incomplete batch, record `thread_cleanup.attempted: false` and preserve the task for recovery.
- Do not use this manifest to add visual QA, OCR, style scoring, or automatic re-generation.
