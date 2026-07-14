#!/usr/bin/env python3
"""Drive logged-in ChatGPT Web for reference-image batch generation and download."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from PIL import Image
except Exception:  # pragma: no cover - only needed for optional cover fitting.
    Image = None  # type: ignore[assignment]


BRIDGE_SCRIPT = Path(__file__).with_name("chatgpt_web_bridge.mjs")
UPLOAD_HELPER = Path(__file__).with_name("opencli_upload_files.mjs")
CHATGPT_HOME = "https://chatgpt.com/"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
IGNORED_REFERENCE_DIRS = {"originals", "__pycache__"}


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def shorten(value: str | None, limit: int = 4000) -> str:
    return (value or "")[-limit:]


def command_result(result: subprocess.CompletedProcess[str], limit: int = 4000) -> dict[str, Any]:
    return {
        "returncode": result.returncode,
        "stdout": shorten(result.stdout, limit),
        "stderr": shorten(result.stderr, limit),
    }


def parse_json_maybe(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value.strip())
    except Exception:
        return None


def run_process(command: Sequence[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(item) for item in command],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def node_binary() -> str:
    return os.environ.get("NODE_BIN") or shutil.which("node") or "node"


def opencli_binary() -> str | None:
    return os.environ.get("OPENCLI_BIN") or shutil.which("opencli")


def bridge_command(*args: str) -> list[str]:
    return [node_binary(), str(BRIDGE_SCRIPT), "ui-chatgpt", *args]


def run_opencli(args: Sequence[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    executable = opencli_binary()
    if not executable:
        return subprocess.CompletedProcess(list(args), 127, "", "opencli is not available on PATH")
    return run_process([executable, *args], timeout=timeout)


def browser_native_click(selector: str) -> dict[str, Any]:
    tabs_result = run_opencli(["browser", "tab", "list"], timeout=30)
    tabs = parse_json_maybe(tabs_result.stdout)
    page = None
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict) and "chatgpt.com" in str(tab.get("url") or ""):
                page = tab.get("page")
                break
    selector_json = json.dumps(selector)
    rect_js = f'''(()=>{{
      const element = [...document.querySelectorAll({selector_json})].find(candidate => {{
        const rect = candidate.getBoundingClientRect();
        const style = getComputedStyle(candidate);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' &&
          style.display !== 'none' && style.pointerEvents !== 'none' && Number(style.opacity || 1) > 0;
      }});
      if (!element) return null;
      element.scrollIntoView({{block:'center', inline:'center'}});
      const rect = element.getBoundingClientRect();
      return {{x:rect.left + rect.width / 2, y:rect.top + rect.height / 2}};
    }})()'''
    rect_result = run_opencli(["browser", "eval", rect_js], timeout=30)
    rect = parse_json_maybe(rect_result.stdout)
    if not isinstance(rect, dict) or rect.get("x") is None or rect.get("y") is None:
        return {"ok": False, "selector": selector, "error": "native click target unavailable"}

    def cdp(method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "id": f"gobe_cleanup_{int(time.time() * 1000)}_{method}",
            "action": "cdp",
            "session": "default",
            "surface": "browser",
            "workspace": "default",
            "cdpMethod": method,
            "cdpParams": params,
        }
        if page:
            payload["page"] = page
        request = urllib.request.Request(
            "http://127.0.0.1:19825/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-OpenCLI": "1"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    point = {"x": round(float(rect["x"])), "y": round(float(rect["y"]))}
    pressed = cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "button": "left", "clickCount": 1, **point})
    released = cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": "left", "clickCount": 1, **point})
    return {
        "ok": bool(pressed.get("ok") and released.get("ok")),
        "selector": selector,
        "point": point,
        "page": page,
    }


def bridge_status(timeout: int = 20) -> dict[str, Any]:
    if not BRIDGE_SCRIPT.exists():
        return {"connected": False, "ok": False, "error": f"bridge script not found: {BRIDGE_SCRIPT}"}
    if not shutil.which(node_binary()) and not Path(node_binary()).exists():
        return {"connected": False, "ok": False, "error": "node is not available"}
    if not opencli_binary():
        return {"connected": False, "ok": False, "error": "opencli is not available on PATH"}
    try:
        result = run_process(bridge_command("status"), timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"connected": False, "ok": False, "error": f"bridge status timed out after {timeout}s"}
    text = f"{result.stdout}\n{result.stderr}"
    return {
        "connected": "Browser Bridge: connected" in text,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "text": text.strip(),
    }


def load_prompt(args: argparse.Namespace, output_dir: Path) -> tuple[str, Path]:
    if bool(args.prompt) == bool(args.prompt_file):
        raise RuntimeError("Provide exactly one of --prompt or --prompt-file.")
    if args.prompt_file:
        prompt_path = Path(args.prompt_file).expanduser().resolve()
        return prompt_path.read_text(encoding="utf-8"), prompt_path
    prompt_text = str(args.prompt).strip()
    if not prompt_text:
        raise RuntimeError("--prompt cannot be empty.")
    prompt_path = output_dir / f"{args.prefix}-prompt.md"
    prompt_path.write_text(prompt_text.rstrip() + "\n", encoding="utf-8")
    return prompt_text, prompt_path


def discover_reference_images(files: Iterable[str], directories: Iterable[str]) -> list[Path]:
    candidates: list[Path] = []
    for raw in files:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
            candidates.append(path)
        else:
            raise RuntimeError(f"Unsupported or missing reference image: {path}")
    for raw in directories:
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            raise RuntimeError(f"Reference directory not found: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if any(part in IGNORED_REFERENCE_DIRS for part in path.relative_to(root).parts[:-1]):
                continue
            if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                candidates.append(path.resolve())

    output: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        fingerprint = sha256_path(path)
        if fingerprint not in seen:
            seen.add(fingerprint)
            output.append(path)
    return output


def load_plan(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Plan JSON must be an object.")
    return payload


def planned_filenames(plan: dict[str, Any] | None) -> list[str]:
    if not plan:
        return []
    names: list[str] = []
    for index, asset in enumerate(plan.get("assets", []), start=1):
        raw = str(asset.get("filename") or f"generated-{index:02d}.png")
        names.append(Path(raw).name)
    return names


def expected_count(args: argparse.Namespace, plan: dict[str, Any] | None) -> int:
    value = args.expected_count
    if value is None and plan:
        value = plan.get("total_count") or len(plan.get("assets", []))
    value = int(value or args.limit)
    if not 1 <= value <= 10:
        raise RuntimeError("A ChatGPT Web batch must request between 1 and 10 images.")
    return value


def open_new_chat() -> dict[str, Any]:
    result = run_process(
        bridge_command("open", CHATGPT_HOME, "--no-focus"), timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to open ChatGPT Web: {shorten(result.stderr or result.stdout, 1000)}")
    return command_result(result)


def select_batch_response_mode() -> dict[str, Any]:
    read_js = r'''(() => {
      const pills = [...document.querySelectorAll('button.__composer-pill[aria-haspopup="menu"]')]
        .filter(button => {
          const rect = button.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        });
      return {current:(pills[0]?.innerText || pills[0]?.textContent || '').trim()};
    })()'''
    current_result = run_opencli(["browser", "eval", read_js], timeout=30)
    current = parse_json_maybe(current_result.stdout)
    if isinstance(current, dict) and current.get("current") == "Pro":
        return {"ok": True, "label": current.get("current"), "already_active": True}

    menu_probe = run_opencli(
        ["browser", "eval", "[...document.querySelectorAll('[role=menuitemradio]')].some(item => { const r=item.getBoundingClientRect(); return r.width > 0 && r.height > 0; })"],
        timeout=30,
    )
    menu_is_open = parse_json_maybe(menu_probe.stdout) is True
    if not menu_is_open:
        opened = browser_native_click('button.__composer-pill[aria-haspopup="menu"]')
        if not opened.get("ok"):
            raise RuntimeError(f"Unable to open ChatGPT response-mode menu: {opened}")
        time.sleep(0.6)
    mark_js = r'''(() => {
      const options = [...document.querySelectorAll('[role="menuitemradio"]')].filter(item => {
        const rect = item.getBoundingClientRect();
        const style = getComputedStyle(item);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden';
      });
      const target = options.find(item => (item.innerText || item.textContent || '').trim().split('\n')[0] === 'Pro');
      if (!target) return {ok:false, labels:options.map(item => (item.innerText || '').trim())};
      target.setAttribute('data-gobe-batch-response-mode', 'true');
      return {ok:true, label:(target.innerText || target.textContent || '').trim()};
    })()'''
    marked_result = run_opencli(["browser", "eval", mark_js], timeout=30)
    marked = parse_json_maybe(marked_result.stdout)
    if not isinstance(marked, dict) or not marked.get("ok"):
        raise RuntimeError(f"ChatGPT batch response mode is unavailable: {marked}")
    selected = browser_native_click('[data-gobe-batch-response-mode="true"]')
    if not selected.get("ok"):
        raise RuntimeError(f"Unable to select ChatGPT batch response mode: {selected}")
    time.sleep(0.8)
    verify_result = run_opencli(["browser", "eval", read_js], timeout=30)
    verify = parse_json_maybe(verify_result.stdout)
    label = verify.get("current") if isinstance(verify, dict) else None
    if label != "Pro":
        raise RuntimeError(f"ChatGPT batch response mode did not become active: {verify}")
    return {"ok": True, "label": label, "already_active": False}


def select_image_mode() -> dict[str, Any]:
    preflight_js = r'''(() => {
      const textarea = document.querySelector('textarea[name="prompt-textarea"]');
      const placeholder = textarea?.getAttribute('placeholder') || '';
      const composer = document.querySelector('#prompt-textarea');
      const composerText = composer?.textContent || '';
      return {
        ok: true,
        active: /图片|image/i.test(placeholder) || /创建图片|生成图片|create image/i.test(composerText),
        placeholder
      };
    })()'''
    preflight = run_opencli(["browser", "eval", preflight_js], timeout=30)
    preflight_payload = parse_json_maybe(preflight.stdout)
    if isinstance(preflight_payload, dict) and preflight_payload.get("active"):
        return {"ok": True, "label": "创建图片", "already_active": True}

    mark_js = r'''(() => {
      const labels = ['创建图片', '生成图片', 'Create image'];
      const candidates = [...document.querySelectorAll('button, [role="menuitem"], [tabindex="0"]')]
        .filter((item) => {
          const rect = item.getBoundingClientRect();
          const style = getComputedStyle(item);
          const text = (item.innerText || item.textContent || '').trim();
          return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' &&
            style.display !== 'none' && labels.includes(text);
        });
      const target = candidates[0];
      if (!target) return {ok:false, labels:[]};
      target.setAttribute('data-gobe-create-image-mode', 'true');
      return {ok:true, label:(target.innerText || target.textContent || '').trim()};
    })()'''

    marked = run_opencli(["browser", "eval", mark_js], timeout=30)
    payload = parse_json_maybe(marked.stdout)
    if not isinstance(payload, dict) or not payload.get("ok"):
        click = browser_native_click("#composer-plus-btn")
        if not click.get("ok"):
            raise RuntimeError(f"Unable to open ChatGPT tools menu: {click}")
        time.sleep(1.0)
        marked = run_opencli(["browser", "eval", mark_js], timeout=30)
        payload = parse_json_maybe(marked.stdout)
    if marked.returncode != 0 or not isinstance(payload, dict) or not payload.get("ok"):
        detail = shorten(marked.stdout or marked.stderr, 1000)
        raise RuntimeError(f"Unable to select ChatGPT image mode: {detail}")

    selected = run_opencli(
        ["browser", "click", '[data-gobe-create-image-mode="true"]', "--nth", "0"],
        timeout=30,
    )
    if selected.returncode != 0:
        raise RuntimeError(f"Unable to select ChatGPT image mode: {shorten(selected.stderr or selected.stdout, 1000)}")
    time.sleep(1.0)
    verified = run_opencli(["browser", "eval", preflight_js], timeout=30)
    verified_payload = parse_json_maybe(verified.stdout)
    if not isinstance(verified_payload, dict) or not verified_payload.get("active"):
        raise RuntimeError(f"ChatGPT image mode did not become active: {verified_payload}")
    return {"ok": True, "label": payload.get("label") or "创建图片", "already_active": False}


def upload_reference_images(paths: Sequence[Path]) -> dict[str, Any]:
    if not paths:
        return {"ok": True, "count": 0, "files": []}
    if not UPLOAD_HELPER.exists():
        raise RuntimeError(f"Upload helper not found: {UPLOAD_HELPER}")
    result = run_process(
        [node_binary(), str(UPLOAD_HELPER), "#upload-files", *[str(path) for path in paths]],
        timeout=max(120, len(paths) * 60),
    )
    payload = parse_json_maybe(result.stdout)
    if result.returncode != 0 or not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"Reference upload failed: {shorten(result.stderr or result.stdout, 1500)}")
    return payload


def chatgpt_state() -> dict[str, Any]:
    result = run_process(
        bridge_command("read", "--json", "--current", "--no-focus"),
        timeout=45,
    )
    payload = parse_json_maybe(result.stdout)
    if result.returncode != 0 or not isinstance(payload, dict):
        raise RuntimeError(f"Unable to read ChatGPT state: {shorten(result.stderr or result.stdout, 1000)}")
    return payload


def send_prompt(prompt_path: Path) -> dict[str, Any]:
    result = run_process(
        bridge_command(
            "send",
            "--prompt-file",
            str(prompt_path),
            "--current",
            "--no-focus",
        ),
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Prompt submission failed: {shorten(result.stderr or result.stdout, 1500)}")
    payload = command_result(result)
    time.sleep(0.8)
    probe_js = r'''(() => {
      const composer = document.querySelector('#prompt-textarea');
      const text = (composer?.innerText || composer?.textContent || '').trim();
      const send = document.querySelector('button[data-testid="send-button"], #composer-submit-button');
      return {promptLength:text.length, sendAvailable:!!send};
    })()'''
    probe = run_opencli(["browser", "eval", probe_js], timeout=30)
    probe_payload = parse_json_maybe(probe.stdout)
    payload["post_enter_probe"] = probe_payload
    if isinstance(probe_payload, dict) and probe_payload.get("promptLength", 0) > 0:
        attempts: list[dict[str, Any]] = []
        verify_payload = probe_payload
        for _ in range(15):
            click = run_opencli(
                ["browser", "click", 'button[data-testid="send-button"], #composer-submit-button', "--nth", "0"],
                timeout=30,
            )
            attempts.append(command_result(click, 1200))
            if click.returncode != 0:
                break
            time.sleep(2.0)
            verify = run_opencli(["browser", "eval", probe_js], timeout=30)
            verify_payload = parse_json_maybe(verify.stdout)
            if isinstance(verify_payload, dict) and verify_payload.get("promptLength", 0) == 0:
                break
        payload["send_button_fallback"] = attempts
        payload["post_click_probe"] = verify_payload
        if not isinstance(verify_payload, dict) or verify_payload.get("promptLength", 0) > 0:
            raise RuntimeError("Prompt remained in the ChatGPT composer after the send-button click.")
    return payload


def wait_for_batch(before: dict[str, Any], expected: int, timeout: int, settle_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    last = before
    complete_count = int(before.get("imageCount") or 0)
    complete_since: float | None = None
    while time.time() < deadline:
        time.sleep(5)
        last = chatgpt_state()
        count = int(last.get("imageCount") or 0)
        busy = bool(last.get("busy"))
        if count >= expected and not busy:
            if count != complete_count:
                complete_count = count
                complete_since = time.time()
            elif complete_since is None:
                complete_since = time.time()
            elif time.time() - complete_since >= settle_seconds:
                return last
        else:
            complete_count = count
            complete_since = None
    return last


def download_images(output_dir: Path, prefix: str, limit: int) -> tuple[dict[str, Any], list[Path]]:
    result = run_process(
        bridge_command(
            "download-images",
            "--output-dir",
            str(output_dir),
            "--prefix",
            prefix,
            "--limit",
            str(limit),
            "--json",
            "--no-focus",
        ),
        timeout=max(120, limit * 45),
    )
    payload = parse_json_maybe(result.stdout)
    if result.returncode != 0 or not isinstance(payload, dict):
        raise RuntimeError(f"Image download failed: {shorten(result.stderr or result.stdout, 1500)}")
    files = [Path(item["file"]).resolve() for item in payload.get("saved", []) if item.get("file")]
    return payload, files


def select_planned_downloads(payload: dict[str, Any], names: Sequence[str]) -> list[Path]:
    records = [item for item in payload.get("saved", []) if item.get("file")]
    if not names:
        return [Path(item["file"]).resolve() for item in records]

    by_alt: dict[str, dict[str, Any]] = {}
    for item in records:
        alt_name = Path(str(item.get("alt") or "")).name
        if alt_name and alt_name not in by_alt:
            by_alt[alt_name] = item
    if all(Path(name).name in by_alt for name in names):
        selected_records = [by_alt[Path(name).name] for name in names]
        selection_method = "exact generated-image alt filenames"
    else:
        selected_records = records[: len(names)]
        selection_method = "first planned-count downloads"

    selected_paths = {str(Path(item["file"]).resolve()) for item in selected_records}
    ignored: list[str] = []
    for item in records:
        path = Path(item["file"]).resolve()
        if str(path) not in selected_paths:
            ignored.append(str(path))
            path.unlink(missing_ok=True)
    payload["plan_selection"] = {
        "method": selection_method,
        "selected_count": len(selected_records),
        "ignored_files": ignored,
    }
    return [Path(item["file"]).resolve() for item in selected_records]


def unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / Path(filename).name
    if not candidate.exists():
        return candidate
    version = 2
    while True:
        candidate = directory / f"{Path(filename).stem}-v{version}{Path(filename).suffix}"
        if not candidate.exists():
            return candidate
        version += 1


def apply_plan_filenames(files: Sequence[Path], names: Sequence[str], output_dir: Path) -> list[Path]:
    renamed: list[Path] = []
    for index, source in enumerate(files):
        if index >= len(names):
            renamed.append(source)
            continue
        wanted = Path(names[index])
        suffix = source.suffix or wanted.suffix or ".png"
        destination = unique_destination(output_dir, f"{wanted.stem}{suffix}")
        source.rename(destination)
        renamed.append(destination.resolve())
    return renamed


def normalize_wechat_cover(source: Path) -> Path:
    if Image is None:
        raise RuntimeError("Pillow is required for --wechat-cover.")
    target = source.with_name(source.stem + "-wechat-900x383.png")
    image = Image.open(source).convert("RGB")
    target_ratio = 900 / 383
    source_ratio = image.width / image.height
    if source_ratio > target_ratio:
        width = int(image.height * target_ratio)
        left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    elif source_ratio < target_ratio:
        height = int(image.width / target_ratio)
        top = (image.height - height) // 2
        image = image.crop((0, top, image.width, top + height))
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    image.resize((900, 383), resample).save(target, "PNG")
    return target.resolve()


def parse_conversation_id(thread_url: str | None) -> str | None:
    match = re.search(r"/c/([0-9a-fA-F-]+)", thread_url or "")
    return match.group(1) if match else None


def cleanup_thread(thread_url: str | None, action: str) -> dict[str, Any]:
    conversation_id = parse_conversation_id(thread_url)
    if not conversation_id:
        return {"attempted": True, "action": action, "ok": False, "error": "conversation id unavailable"}
    open_timeout = None
    current = run_opencli(["browser", "eval", "location.href"], timeout=30)
    already_open = current.returncode == 0 and conversation_id in current.stdout
    if not already_open:
        try:
            opened = run_opencli(["browser", "open", str(thread_url)], timeout=45)
        except subprocess.TimeoutExpired as error:
            open_timeout = str(error)
            opened = None
        if opened is None or opened.returncode != 0:
            current = run_opencli(["browser", "eval", "location.href"], timeout=30)
            if current.returncode != 0 or conversation_id not in current.stdout:
                return {
                    "attempted": True,
                    "action": action,
                    "ok": False,
                    "error": "unable to open thread",
                    "open_timeout": open_timeout,
                }
    time.sleep(1.5)

    if action == "delete":
        steps: list[dict[str, Any]] = []
        ui_error = None
        for selector in (
            'button[data-testid="conversation-options-button"]',
            '[data-testid="delete-chat-menu-item"]',
            '[data-testid="delete-conversation-confirm-button"]',
        ):
            native = browser_native_click(selector)
            steps.append(native)
            step_ok = bool(native.get("ok"))
            if not step_ok:
                ui_error = f"ChatGPT delete control unavailable: {selector}"
                break
            time.sleep(0.8)
        if ui_error is None:
            return {
                "attempted": True,
                "action": action,
                "ok": True,
                "conversation_id": conversation_id,
                "method": "ChatGPT Web delete menu and confirmation dialog",
                "ui_steps": steps,
            }

        return {
            "attempted": True,
            "action": action,
            "ok": False,
            "conversation_id": conversation_id,
            "method": "ChatGPT Web delete menu and confirmation dialog",
            "ui_steps": steps,
            "error": ui_error,
        }

    method = "PATCH"
    body = "{ is_visible: false }"
    js = r'''(()=>{
      window.__gobeThreadCleanup = {done:false, ok:false};
      (async()=>{
        try {
          const headers = {'Accept':'application/json','Content-Type':'application/json'};
          const init = {method:__METHOD__, credentials:'include', headers};
          if (__BODY__ !== null) init.body = JSON.stringify(__BODY__);
          const response = await fetch('/backend-api/conversation/__ID__', init);
          const responseText = await response.text().catch(()=>'');
          window.__gobeThreadCleanup = {
            done:true,
            ok:response.ok || response.status === 404,
            status:response.status,
            error:(response.ok || response.status === 404) ? null : responseText.slice(0,500)
          };
        } catch (error) {
          window.__gobeThreadCleanup = {done:true, ok:false, status:0, error:String(error)};
        }
      })();
      return {started:true};
    })()'''
    js = js.replace("__METHOD__", json.dumps(method)).replace("__BODY__", body).replace("__ID__", conversation_id)
    evaluated = run_opencli(["browser", "eval", js], timeout=45)
    if evaluated.returncode != 0:
        return {"attempted": True, "action": action, "ok": False, "error": "cleanup command failed"}
    payload: dict[str, Any] | None = None
    meta = None
    for _ in range(20):
        time.sleep(0.5)
        meta = run_opencli(
            ["browser", "eval", "JSON.stringify(window.__gobeThreadCleanup || {})"], timeout=30
        )
        payload = parse_json_maybe(meta.stdout)
        if isinstance(payload, dict) and payload.get("done"):
            break
    if not isinstance(payload, dict):
        payload = {"ok": False, "error": shorten((meta.stderr or meta.stdout) if meta else "", 500)}
    payload.update({"attempted": True, "action": action, "conversation_id": conversation_id})
    payload["method"] = "ChatGPT Web authenticated hide request"
    return payload


def request_summary(
    args: argparse.Namespace,
    prompt_path: Path,
    prompt_text: str,
    references: Sequence[Path],
    plan: dict[str, Any] | None,
    output_dir: Path,
    expected: int,
) -> dict[str, Any]:
    return {
        "mode": "logged-in ChatGPT Web through Chrome Bridge",
        "prompt_path": str(prompt_path),
        "prompt_sha256": sha256_text(prompt_text),
        "plan_path": str(Path(args.plan_file).expanduser().resolve()) if args.plan_file else None,
        "planned_filenames": planned_filenames(plan),
        "reference_images": [{"path": str(path), "sha256": sha256_path(path)} for path in references],
        "expected_image_count": expected,
        "download_limit": args.limit,
        "output_dir": str(output_dir),
        "cleanup_requested": "delete" if args.delete_chatgpt_thread else "hide" if args.hide_chatgpt_thread else None,
        "visual_review": "not performed",
    }


def run_image_job(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started = time.time()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{args.prefix}-chatgpt-web-manifest.json"
    manifest: dict[str, Any] = {"status": "started", "created_at": iso_now()}

    try:
        prompt_text, prompt_path = load_prompt(args, output_dir)
        plan = load_plan(args.plan_file)
        references = discover_reference_images(args.reference_image, args.reference_dir)
        expected = expected_count(args, plan)
        manifest.update(request_summary(args, prompt_path, prompt_text, references, plan, output_dir, expected))

        if args.dry_run:
            manifest["bridge_status"] = {"checked": False, "reason": "dry-run"}
            manifest["status"] = "ready"
            return 0, manifest

        bridge = bridge_status()
        manifest["bridge_status"] = bridge
        if not bridge.get("connected"):
            raise RuntimeError(bridge.get("error") or "Chrome Bridge is not connected")

        if not args.current_chat:
            manifest["open_chat"] = open_new_chat()
        manifest["response_mode"] = {
            "ok": True,
            "label": "preserved",
            "source": "user-managed ChatGPT Web setting",
        }
        manifest["image_mode"] = select_image_mode()
        manifest["reference_upload"] = upload_reference_images(references)
        if references:
            time.sleep(args.upload_wait)

        before = chatgpt_state()
        manifest["before_state"] = before
        manifest["send_command"] = send_prompt(prompt_path)
        final_state = wait_for_batch(before, expected, args.timeout, args.settle_seconds)
        manifest["final_state"] = final_state
        manifest["thread_url"] = final_state.get("url")

        payload, downloaded = download_images(output_dir, args.prefix, args.limit)
        manifest["download_payload"] = payload
        names = planned_filenames(plan)
        downloaded = select_planned_downloads(payload, names)
        downloaded = apply_plan_filenames(downloaded, names, output_dir)
        manifest["downloaded_files"] = [str(path) for path in downloaded]

        if args.wechat_cover and downloaded:
            manifest["wechat_cover_files"] = [str(normalize_wechat_cover(downloaded[0]))]

        if not downloaded:
            raise RuntimeError("ChatGPT Web returned no downloadable image files.")

        if len(downloaded) != expected:
            manifest["thread_cleanup"] = {
                "attempted": False,
                "ok": None,
                "reason": "planned image count is incomplete; preserve the ChatGPT thread",
            }
            raise RuntimeError(
                f"ChatGPT Web returned {len(downloaded)} planned images; expected {expected}. "
                "The batch did not complete, so the ChatGPT thread was preserved."
            )

        cleanup_action = "delete" if args.delete_chatgpt_thread else "hide" if args.hide_chatgpt_thread else None
        if cleanup_action:
            cleanup = cleanup_thread(str(manifest.get("thread_url") or payload.get("url") or ""), cleanup_action)
            manifest["thread_cleanup"] = cleanup
            if not cleanup.get("ok"):
                manifest["status"] = "downloaded_cleanup_failed"
                raise RuntimeError(f"Images downloaded, but ChatGPT thread {cleanup_action} failed.")
        else:
            manifest["thread_cleanup"] = {"attempted": False, "ok": None}

        manifest["status"] = "downloaded"
        return 0, manifest
    except Exception as error:
        if manifest.get("status") == "started":
            manifest["status"] = "failed"
        manifest["error"] = str(error)
        return 1, manifest
    finally:
        manifest["duration_seconds"] = round(time.time() - started, 2)
        manifest["updated_at"] = iso_now()
        write_json(manifest_path, manifest)


def doctor_command(args: argparse.Namespace) -> int:
    status = bridge_status(args.timeout)
    status["bridge_script"] = {"path": str(BRIDGE_SCRIPT), "exists": BRIDGE_SCRIPT.exists()}
    status["upload_helper"] = {"path": str(UPLOAD_HELPER), "exists": UPLOAD_HELPER.exists()}
    status["opencli"] = {"path": opencli_binary(), "available": bool(opencli_binary())}
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get("connected") and BRIDGE_SCRIPT.exists() and UPLOAD_HELPER.exists() else 2


def cleanup_command(args: argparse.Namespace) -> int:
    result = cleanup_thread(args.thread_url, args.action)
    result.update({"thread_url": args.thread_url, "created_at": iso_now()})
    if args.receipt:
        write_json(Path(args.receipt).expanduser().resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def run_command(args: argparse.Namespace) -> int:
    code, manifest = run_image_job(args)
    if args.json or args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"{manifest.get('status')}: {manifest.get('output_dir')}")
        if manifest.get("error"):
            print(f"error: {manifest['error']}", file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and download images through logged-in ChatGPT Web.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check Chrome Bridge and upload-helper readiness.")
    doctor.add_argument("--timeout", type=int, default=20)
    doctor.set_defaults(func=doctor_command)

    cleanup = sub.add_parser("cleanup", help="Hide or permanently delete one ChatGPT Web task.")
    cleanup.add_argument("--thread-url", required=True)
    cleanup.add_argument("--action", choices=("hide", "delete"), default="delete")
    cleanup.add_argument("--receipt", help="Optional JSON receipt path.")
    cleanup.set_defaults(func=cleanup_command)

    run = sub.add_parser("run", help="Upload references, submit one batch prompt, and download images.")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Prompt text; a copy is saved in the output directory.")
    source.add_argument("--prompt-file", help="Complete batch prompt file.")
    run.add_argument("--plan-file", help="Optional visual-plan JSON for expected count and output filenames.")
    run.add_argument("--reference-image", action="append", default=[], help="Reference image; repeat as needed.")
    run.add_argument("--reference-dir", action="append", default=[], help="Recursive reference directory; repeat as needed.")
    run.add_argument("--output-dir", required=True, help="Directory for downloads and manifest.")
    run.add_argument("--prefix", default="chatgpt-image", help="Download and manifest prefix.")
    run.add_argument("--expected-count", type=int, help="Expected batch size, 1-10; plan total_count is used by default.")
    run.add_argument("--limit", type=int, default=10, choices=range(1, 11), metavar="1-10")
    run.add_argument("--timeout", type=int, default=3600, help="Maximum generation wait in seconds.")
    run.add_argument("--settle-seconds", type=int, default=20, help="Quiet period after images appear before download.")
    run.add_argument("--upload-wait", type=int, default=8, help="Seconds to let ChatGPT finish reference uploads.")
    run.add_argument("--current-chat", action="store_true", help="Use the current browser conversation instead of a new chat.")
    run.add_argument("--wechat-cover", action="store_true", help="Fit the first image to 900x383 after download.")
    cleanup = run.add_mutually_exclusive_group()
    cleanup.add_argument("--hide-chatgpt-thread", action="store_true", help="Hide the thread after successful download.")
    cleanup.add_argument("--delete-chatgpt-thread", action="store_true", help="Permanently delete the thread after successful download.")
    run.add_argument("--dry-run", action="store_true", help="Resolve inputs and write a ready manifest without browser actions.")
    run.add_argument("--json", action="store_true", help="Print the manifest JSON.")
    run.set_defaults(func=run_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
