"""Grok Review MCP Server (shared tooling, consumed via the .tools submodule).

Bridge to xAI's Grok models for visual content workflows: send images and
video concepts plus context, get back generated images, generated video,
or vision-based analysis. Useful for generating cover graphics for case
studies / blog posts on the portfolio site, vision-analysing rendered
resume / cover-letter PDFs, and ideating social-media visuals for outreach.

Tools:
- grok_generate_image: text-to-image generation (returns saved file paths).
- grok_analyze_image: vision analysis of one or more images (returns text).
- grok_generate_video: video generation from concept + optional reference images.
- grok_multimodal_chat: free-form chat with mixed text + image input.

Configuration (via project root .env or system environment):
- XAI_API_KEY (required)
- XAI_BASE_URL    (default: https://api.x.ai/v1)
- GROK_TEXT_MODEL    (default: grok-4.3)
- GROK_VISION_MODEL  (default: grok-4.3)
- GROK_IMAGE_MODEL   (default: grok-imagine-image)
- GROK_VIDEO_MODEL   (default: grok-imagine-video)
- GROK_IMAGE_PATH    (default: /images/generations) appended to XAI_BASE_URL
- GROK_VIDEO_PATH    (default: /videos/generations) appended to XAI_BASE_URL
- GROK_OUTPUT_DIR    (default: docs/grok-output)
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from functools import lru_cache
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("grok-review")

_SERVER_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _find_project_root() -> Path:
    current = _SERVER_DIR
    for _ in range(10):
        if (current / ".mcp.json").exists():
            return current
        current = current.parent
    return _SERVER_DIR.parent.parent


try:
    from dotenv import load_dotenv

    load_dotenv(_find_project_root() / ".env", override=True)
except ImportError:
    pass

XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")

DEFAULT_TEXT_MODEL = os.environ.get("GROK_TEXT_MODEL", "grok-4.3")
DEFAULT_VISION_MODEL = os.environ.get("GROK_VISION_MODEL", "grok-4.3")
DEFAULT_IMAGE_MODEL = os.environ.get("GROK_IMAGE_MODEL", "grok-imagine-image")
DEFAULT_VIDEO_MODEL = os.environ.get("GROK_VIDEO_MODEL", "grok-imagine-video")
IMAGE_PATH = os.environ.get("GROK_IMAGE_PATH", "/images/generations")
VIDEO_PATH = os.environ.get("GROK_VIDEO_PATH", "/videos/generations")

DEFAULT_OUTPUT_DIR = os.environ.get("GROK_OUTPUT_DIR", "docs/grok-output")

MISSING_API_KEY_ERROR = "ERROR: XAI_API_KEY environment variable is not set."

REQUEST_TIMEOUT = 300.0
TEMPERATURE = 0.7
MAX_TOKENS = 4096

MAX_PROMPT_CHARS = 8000
MAX_N_IMAGES = 10
MIN_VIDEO_SECONDS = 1
MAX_VIDEO_SECONDS = 60
MAX_ERROR_BODY_CHARS = 200
SLUG_LIMIT = 40


def _resolve_output_dir(output_dir: str) -> Path:
    out = Path(output_dir)
    if not out.is_absolute():
        out = _find_project_root() / out
    out.mkdir(parents=True, exist_ok=True)
    return out


def _resolve_input_path(p: str) -> tuple[Path | None, str | None]:
    """Resolve a user-supplied file path and enforce containment.

    The path must resolve to a file inside the project root. This blocks
    accidental exfiltration of arbitrary host files (e.g. credentials,
    SSH keys) to xAI when a tool caller passes an absolute path.

    Returns ``(path, None)`` on success or ``(None, error_message)`` on
    failure.
    """
    target = Path(p)
    if not target.is_absolute():
        target = _find_project_root() / target
    try:
        resolved = target.resolve(strict=False)
    except OSError as e:
        return None, f"path resolution failed for {p}: {e}"

    project_root = _find_project_root().resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return None, (
            f"path must be inside the project root; refusing to read {resolved} "
            f"(project root: {project_root})"
        )
    return resolved, None


def _encode_image_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(image_path.name)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _safe_slug(text: str, limit: int = SLUG_LIMIT) -> str:
    keep: list[str] = []
    for ch in text.lower():
        if len(keep) >= limit:
            break
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_":
            keep.append("-")
    slug = "".join(keep).strip("-")
    return slug or "grok"


def _http_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }


def _format_http_error(e: httpx.HTTPStatusError) -> str:
    """Format a provider HTTP error without echoing the request prompt back.

    `e.response.text` may include parts of the prompt the user sent (some
    providers reflect input in error JSON). We surface only status + a
    short generic snippet so prompt content does not leak via tool output.
    """
    status = e.response.status_code
    if status == 429:
        return "ERROR: xAI rate limit exceeded. Wait and retry."
    if status == 401:
        return "ERROR: Invalid XAI_API_KEY."
    if status == 404:
        return f"ERROR: xAI endpoint not found ({str(e.request.url)}). Check XAI_BASE_URL / model name."
    snippet = e.response.text[:MAX_ERROR_BODY_CHARS].replace("\n", " ")
    return f"ERROR: xAI API returned HTTP {status}: {snippet}"


def _check_prompt(prompt: str, field: str = "prompt") -> str | None:
    if not prompt or not prompt.strip():
        return f"ERROR: {field} is empty."
    if len(prompt) > MAX_PROMPT_CHARS:
        return f"ERROR: {field} too long ({len(prompt)} > {MAX_PROMPT_CHARS} chars)."
    return None


def _extract_text(data: dict[str, object]) -> str:
    """Pull message content out of an OpenAI-shaped chat response.

    Handles the case where the provider returns ``content: null`` (e.g.
    when only a tool call was emitted) — coerces to a readable placeholder
    rather than the literal string ``"None"``.
    """
    try:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return f"ERROR: no choices in response: {str(data)[:300]}"
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return f"ERROR: unexpected message shape: {str(choices[0])[:300]}"
        content = message.get("content")
        if content is None:
            return "[empty response — provider returned content: null]"
        return str(content)
    except (KeyError, IndexError, TypeError, AttributeError):
        return f"ERROR: unexpected response shape: {str(data)[:300]}"


def _project_relative(path: Path) -> str:
    try:
        return path.relative_to(_find_project_root()).as_posix()
    except ValueError:
        return str(path)


def _resolve_image_paths_to_data_urls(
    paths: list[str],
) -> tuple[list[str] | None, str | None]:
    """Resolve user-supplied image paths and encode each as a data URL.

    Returns ``(urls, None)`` on success or ``(None, error)`` on the first
    failure. Centralised here so each tool function doesn't need its own
    nested loop with repeated error handling.
    """
    urls: list[str] = []
    for p in paths:
        path, path_err = _resolve_input_path(p)
        if path_err is not None or path is None:
            return None, f"ERROR: {path_err}"
        if not path.exists() or not path.is_file():
            return None, f"ERROR: image not found: {p}"
        try:
            urls.append(_encode_image_data_url(path))
        except OSError as e:
            return None, f"ERROR: failed to read {path}: {e}"
    return urls, None


def _format_save_summary(
    op_label: str,
    model: str,
    items: list[object],
    saved: list[str],
    errors: list[str],
    revised: list[str],
) -> str:
    """Build the standard "N saved, M errors out of K returned" report."""
    parts = [
        f"Grok {op_label} generation: {len(saved)} saved, "
        f"{len(errors)} error(s) out of {len(items)} returned (model: {model}).",
    ]
    if saved:
        parts.append("Saved:")
        parts.extend(saved)
    if errors:
        parts.append("Errors:")
        parts.extend(errors)
    if revised:
        parts.append("Revised prompts:")
        parts.extend(revised)
    return "\n".join(parts)


async def _post_xai(
    url: str,
    payload: dict[str, object],
    op_label: str,
) -> tuple[dict[str, object] | None, str | None]:
    """POST a JSON payload to xAI and normalise the error surface.

    Centralises the timeout / status-error / generic-error try/except block
    so each tool function just has one if-check instead of three exception
    branches. Returns ``(json_dict, None)`` on success or ``(None, error)``
    on any failure.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(url, headers=_http_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return None, f"ERROR: xAI {op_label} response was not a JSON object."
            return data, None
        except httpx.TimeoutException:
            return None, f"ERROR: xAI {op_label} request timed out after {REQUEST_TIMEOUT}s."
        except httpx.HTTPStatusError as e:
            return None, _format_http_error(e)
        except (httpx.HTTPError, ValueError) as e:
            return None, f"ERROR: xAI {op_label} request failed: {e}"


async def _save_response_items(
    items: list[object],
    dl: httpx.AsyncClient,
    out_dir: Path,
    stamp: str,
    slug: str,
    ext: str,
    *,
    b64_keys: tuple[str, ...] = ("b64_json",),
    url_keys: tuple[str, ...] = ("url",),
) -> tuple[list[str], list[str], list[str]]:
    """Iterate provider response items and persist each binary payload.

    Returns ``(saved, errors, revised)`` lists ready to be folded into a
    summary string. Centralised so each tool function does not repeat the
    enumerate/decode/write/append boilerplate.
    """
    saved: list[str] = []
    errors: list[str] = []
    revised: list[str] = []

    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"[{i}] response item not a dict")
            continue
        revised_prompt = item.get("revised_prompt")
        if isinstance(revised_prompt, str):
            revised.append(f"[{i}] {revised_prompt}")
        raw, err_msg = await _decode_b64_or_download(
            item, dl, b64_keys=b64_keys, url_keys=url_keys
        )
        if err_msg is not None or raw is None:
            errors.append(f"[{i}] {err_msg}")
            continue
        path = out_dir / f"{stamp}-{slug}-{i}.{ext}"
        try:
            path.write_bytes(raw)
        except OSError as e:
            errors.append(f"[{i}] write failed: {e}")
            continue
        saved.append(f"[{i}] {_project_relative(path)}")

    return saved, errors, revised


async def _decode_b64_or_download(
    item: dict[str, object],
    dl: httpx.AsyncClient,
    *,
    b64_keys: tuple[str, ...] = ("b64_json",),
    url_keys: tuple[str, ...] = ("url",),
) -> tuple[bytes | None, str | None]:
    """Pull a binary payload out of one provider response item.

    Tries each key in ``b64_keys`` (base64) then ``url_keys`` (HTTP download).
    Returns ``(bytes, None)`` on success or ``(None, error)`` on failure.
    """
    b64 = next((item.get(k) for k in b64_keys if isinstance(item.get(k), str)), None)
    if isinstance(b64, str):
        try:
            return base64.b64decode(b64, validate=True), None
        except ValueError as e:
            return None, f"base64 decode failed: {e}"
    url_field = next(
        (item.get(k) for k in url_keys if isinstance(item.get(k), str)), None
    )
    if isinstance(url_field, str):
        try:
            r = await dl.get(url_field)
            r.raise_for_status()
            return r.content, None
        except httpx.HTTPError as e:
            return None, f"download failed for {url_field}: {e}"
    return None, "no b64 or url field in response item"


@mcp.tool()
async def grok_generate_image(
    prompt: str,
    n: int = 1,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    model: str = DEFAULT_IMAGE_MODEL,
) -> str:
    """Generate images from a text prompt using Grok and save them locally.

    Args:
        prompt: Description of the image to generate (max 8000 chars).
        n: Number of images to generate (1-10; provider may cap lower).
        output_dir: Directory (project-relative or absolute) for saved PNGs.
        model: Grok image model to use.

    Returns:
        A summary listing saved file paths plus any per-item errors and
        provider-revised prompts, or an error message.
    """
    if not XAI_API_KEY:
        return MISSING_API_KEY_ERROR
    err = _check_prompt(prompt)
    if err:
        return err
    if n < 1 or n > MAX_N_IMAGES:
        return f"ERROR: n must be between 1 and {MAX_N_IMAGES}."

    out_dir = _resolve_output_dir(output_dir)
    slug = _safe_slug(prompt)
    stamp = _timestamp_slug()

    url = f"{XAI_BASE_URL}{IMAGE_PATH}"
    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "response_format": "b64_json",
    }

    data, err_msg = await _post_xai(url, payload, "image")
    if err_msg is not None or data is None:
        return err_msg or "ERROR: xAI image request returned no data."

    items = data.get("data", [])
    if not isinstance(items, list) or not items:
        return f"ERROR: xAI returned no images. Raw: {str(data)[:300]}"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as dl:
        saved, errors, revised = await _save_response_items(
            items, dl, out_dir, stamp, slug, "png"
        )

    return _format_save_summary("image", model, items, saved, errors, revised)


@mcp.tool()
async def grok_analyze_image(
    image_paths: list[str],
    prompt: str = "Describe these images in detail and note anything unusual.",
    model: str = DEFAULT_VISION_MODEL,
) -> str:
    """Analyze one or more local images using Grok's vision model.

    Image paths must resolve to files inside the project root. Absolute
    paths outside the repo are rejected to prevent accidental exfiltration
    of arbitrary host files to xAI.

    Args:
        image_paths: Paths (project-relative or absolute) to image files.
        prompt: Question / instruction for the vision model (max 8000 chars).
        model: Grok vision model to use.

    Returns:
        The model's textual analysis, or an error message.
    """
    if not XAI_API_KEY:
        return MISSING_API_KEY_ERROR
    err = _check_prompt(prompt)
    if err:
        return err
    if not image_paths:
        return "ERROR: image_paths is empty."

    data_urls, resolve_err = _resolve_image_paths_to_data_urls(image_paths)
    if resolve_err is not None or data_urls is None:
        return resolve_err or "ERROR: image resolution failed"

    content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    for data_url in data_urls:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url, "detail": "high"},
            }
        )

    url = f"{XAI_BASE_URL}/chat/completions"
    payload: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    data, err_msg = await _post_xai(url, payload, "vision")
    if err_msg is not None or data is None:
        return err_msg or "ERROR: xAI vision request returned no data."
    return _extract_text(data)


@mcp.tool()
async def grok_multimodal_chat(
    prompt: str,
    image_paths: list[str] | None = None,
    system: str = "",
    model: str = DEFAULT_VISION_MODEL,
) -> str:
    """Free-form multimodal chat with Grok. Send text + optional images, get text back.

    Useful for ideating cover graphics, getting shot lists for case-study
    visuals, drafting outreach captions, or asking Grok to combine multiple
    reference images into a creative brief.

    Image paths must resolve to files inside the project root.

    Args:
        prompt: User instruction or question (max 8000 chars).
        image_paths: Optional list of image file paths (project-relative or absolute).
        system: Optional system message setting tone or role (max 8000 chars).
        model: Grok model. Vision-capable model required if images are passed.

    Returns:
        Grok's text response, or an error message.
    """
    if not XAI_API_KEY:
        return MISSING_API_KEY_ERROR
    err = _check_prompt(prompt)
    if err:
        return err
    if system:
        sys_err = _check_prompt(system, field="system")
        if sys_err:
            return sys_err

    user_content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    if image_paths:
        data_urls, resolve_err = _resolve_image_paths_to_data_urls(image_paths)
        if resolve_err is not None or data_urls is None:
            return resolve_err or "ERROR: image resolution failed"
        for data_url in data_urls:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": "high"},
                }
            )

    messages: list[dict[str, object]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})

    url = f"{XAI_BASE_URL}/chat/completions"
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    data, err_msg = await _post_xai(url, payload, "chat")
    if err_msg is not None or data is None:
        return err_msg or "ERROR: xAI chat request returned no data."
    return _extract_text(data)


@mcp.tool()
async def grok_generate_video(
    concept: str,
    reference_image_paths: list[str] | None = None,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
    output_dir: str = DEFAULT_OUTPUT_DIR,
    model: str = DEFAULT_VIDEO_MODEL,
) -> str:
    """Generate a video from a text concept and optional reference images.

    Posts to ``${XAI_BASE_URL}${GROK_VIDEO_PATH}`` with an OpenAI-images-
    style body. Reference images are sent as a list of data URLs in the
    ``reference_images`` field (matching the convention used by the
    chat-vision endpoint). Saves any returned MP4 (b64_json) or downloads
    any returned URL into ``output_dir``. If xAI's video endpoint is not
    enabled on your key, you'll get a clean HTTP 404 — adjust
    ``GROK_VIDEO_PATH`` / ``GROK_VIDEO_MODEL`` once xAI publishes the spec.

    Reference image paths must resolve to files inside the project root.

    Args:
        concept: Description of the video to generate (max 8000 chars).
        reference_image_paths: Optional reference frames (project-relative or absolute).
        duration_seconds: Requested clip length in seconds (1-60).
        aspect_ratio: Aspect ratio hint (e.g. "16:9", "9:16", "1:1").
        output_dir: Directory (project-relative or absolute) for saved MP4s.
        model: Grok video model identifier.

    Returns:
        Saved file path(s) plus error count and provider notes, or an error.
    """
    if not XAI_API_KEY:
        return MISSING_API_KEY_ERROR
    err = _check_prompt(concept, field="concept")
    if err:
        return err
    if duration_seconds < MIN_VIDEO_SECONDS or duration_seconds > MAX_VIDEO_SECONDS:
        return f"ERROR: duration_seconds must be between {MIN_VIDEO_SECONDS} and {MAX_VIDEO_SECONDS}."

    out_dir = _resolve_output_dir(output_dir)
    slug = _safe_slug(concept)
    stamp = _timestamp_slug()

    reference_image_urls: list[str] = []
    if reference_image_paths:
        urls, resolve_err = _resolve_image_paths_to_data_urls(reference_image_paths)
        if resolve_err is not None or urls is None:
            return resolve_err or "ERROR: reference image resolution failed"
        reference_image_urls = urls

    url = f"{XAI_BASE_URL}{VIDEO_PATH}"
    payload: dict[str, object] = {
        "model": model,
        "prompt": concept,
        "duration_seconds": duration_seconds,
        "aspect_ratio": aspect_ratio,
        "response_format": "b64_json",
    }
    if reference_image_urls:
        payload["reference_images"] = reference_image_urls

    data, err_msg = await _post_xai(url, payload, "video")
    if err_msg is not None or data is None:
        return err_msg or "ERROR: xAI video request returned no data."

    items = data.get("data") or data.get("videos") or []
    if not isinstance(items, list) or not items:
        return (
            "ERROR: xAI returned no video. The video endpoint may not be enabled "
            f"on your key, or the response shape changed.\nRaw: {str(data)[:500]}"
        )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as dl:
        saved, errors, _revised = await _save_response_items(
            items,
            dl,
            out_dir,
            stamp,
            slug,
            "mp4",
            b64_keys=("b64_json", "video_b64"),
            url_keys=("url", "video_url"),
        )

    return _format_save_summary("video", model, items, saved, errors, [])


if __name__ == "__main__":
    mcp.run(transport="stdio")
