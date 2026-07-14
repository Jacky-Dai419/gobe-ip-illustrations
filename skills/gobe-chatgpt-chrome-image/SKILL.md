---
name: gobe-chatgpt-chrome-image
description: Upload local reference images, submit one prompt, batch-generate up to 10 images, download them, and clean up the task through the user's logged-in ChatGPT Web session in Chrome via the bundled OpenCLI browser bridge. Use for browser-based ChatGPT image generation, replaceable IP references, multi-image article illustration, cover and summary images, recoverable manifests, or true post-download thread deletion without the OpenAI API.
---

# GOBE ChatGPT Chrome Image

## Purpose

Use this skill as the low-level browser atom: local reference images and one complete prompt in, one logged-in ChatGPT Web task out, followed by local downloads and a manifest. Leave article structure, image roles, and final layout to higher-level skills.

## Workflow

1. Run the doctor before the first live job:

```bash
python3 <skill-dir>/scripts/chatgpt_chrome_image.py doctor
```

2. Run one batch from a prompt file. The browser atom preserves the response/reasoning setting already chosen by the user, explicitly enters ChatGPT's image-creation mode, and then attaches all reference images before the prompt is sent:

```bash
python3 <skill-dir>/scripts/chatgpt_chrome_image.py run \
  --prompt-file /abs/path/to/prompt.md \
  --plan-file /abs/path/to/visual-plan.json \
  --reference-dir /abs/path/to/references/ip \
  --output-dir /abs/path/to/images \
  --prefix article-001 \
  --timeout 3600 \
  --limit 10 \
  --delete-chatgpt-thread \
  --json
```

3. Use repeatable `--reference-image` for explicit files and repeatable `--reference-dir` for recursive folders. Compatible formats are PNG, JPG, JPEG, and WEBP; `originals/` folders are skipped.

4. Use `--wechat-cover` only when the first downloaded image must also become a 900x383 WeChat cover.

5. Clean up an already-finished task and write a receipt when needed:

```bash
python3 <skill-dir>/scripts/chatgpt_chrome_image.py cleanup \
  --thread-url https://chatgpt.com/c/<conversation-id> \
  --action delete \
  --receipt /abs/path/to/thread-cleanup.json
```

## Rules

- Treat one run as one browser task. Put all numbered assets for the article into one prompt and keep the total at 10 or fewer.
- ChatGPT may render a completed multi-image response as one large main image plus a vertical thumbnail filmstrip. Count and download unique GPT original-image resources from the whole Assistant image group; do not infer the batch size from the single large image alone or reject 48px rendered thumbnails whose natural images are full resolution.
- Start a new ChatGPT task by default, preserve the user's current model/reasoning setting, explicitly select “创建图片 / Create image”, upload the full reference group once, and send the complete prompt once.
- Do not change the model or reasoning level in automation. That setting is user-managed; this Skill is responsible only for the image workflow.
- Do not claim success unless the manifest has `status: "downloaded"`, the downloaded image count equals the requested or planned count, and requested cleanup has `thread_cleanup.ok: true`.
- Preserve the manifest beside the downloaded images; upstream skills should read it instead of scraping terminal text.
- `--hide-chatgpt-thread` hides the task. `--delete-chatgpt-thread` performs a real permanent deletion only after the complete planned image count has been downloaded; an incomplete batch must remain available for later download or recovery. The current browser implementation uses trusted native clicks for the official menu and confirmation controls.
- Do not add visual inspection, scoring, OCR, identity checks, or retry prompts. Waiting for upload/generation/download and reporting technical failure are allowed.
- If the doctor reports the Chrome Bridge is disconnected, stop the live job and return a pending/blocked state to the upstream workflow.

## References

- Read `references/output-contract.md` before changing manifest fields or consuming this skill from another skill.
