"""OpenAI Review Bridge MCP Server (shared tooling, consumed via .tools).

Lightweight MCP server that sends a code snippet to OpenAI for an
independent review and returns the critique as a tool result back into
Claude Code's context. Consumed by both rz-website and rz-work.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

_SERVER_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _find_project_root() -> Path:
    """Walk up from server.py to the consuming repo root (marked by .mcp.json).

    Resolves correctly whether this server lives at a repo root (monolith) or
    inside a `.tools/` submodule, where the repo root sits one level above
    `.tools/`. Falls back to two levels up (the directory holding mcp-servers/).
    """
    current = _SERVER_DIR
    for _ in range(10):
        if (current / ".mcp.json").exists():
            return current
        current = current.parent
    return _SERVER_DIR.parent.parent


PROJECT_ROOT = _find_project_root()

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

mcp = FastMCP("openai-review")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = os.environ.get("OPENAI_REVIEW_MODEL", "gpt-5.4-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
REQUEST_TIMEOUT = 120.0
MAX_TOKENS = 8192
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are a senior engineer giving an independent second-opinion review for "
    "the richardzak.com repository family: a public Astro 5 + Tailwind + "
    "TypeScript static site (rz-website) and a private Python pipeline "
    "(rz-work — Pydantic V2, strict mypy, ruff, pytest, Jinja2 with LaTeX-safe "
    "delimiters, XeLaTeX templates, YAML 1.2, httpx async adapters). Adapt your "
    "review to the language and context the caller provides. "
    "Review for: bugs and edge cases; security (no hardcoded secrets — secrets "
    "only via .env / environment variables; no eval/exec or "
    "subprocess(shell=True) on user-controlled data; HTTP clients must set "
    "timeouts; credential files must never be committed); correctness (full "
    "type hints / type safety on public surfaces, validated data models, "
    "explicit exception types — no bare except); performance (avoid waterfall "
    "HTTP calls; batch where possible; stream large files); refactoring "
    "opportunities (code duplication, overly complex functions, long parameter "
    "lists, reuse stdlib / existing helpers rather than reinventing); structured "
    "error handling (MCP tools and scripts return error strings rather than "
    "raising through the boundary; hook scripts respect PreToolUse / "
    "PostToolUse contracts and exit codes); magic numbers (numeric literals "
    "other than 0, 1, -1 should be named constants); no emojis in code or "
    "comments; Windows portability (forward slashes, no Unix-only commands — "
    "primary dev environment is Windows 11); and a 120-character line limit. "
    "Be concise and actionable. Format as a numbered list of findings with "
    "severity (Critical / Warning / Info). If the code looks solid, say so "
    "briefly and note any minor improvements."
)


@mcp.tool()
async def openai_review(
    code: str,
    context: str = "",
    language: str = "",
    focus: str = "",
    model: str = DEFAULT_MODEL,
) -> str:
    """Submit code to OpenAI for an independent review.

    Args:
        code: The source code to review.
        context: Description of what the code does.
        language: Programming language (e.g., 'python', 'yaml', 'markdown', 'tex', 'astro').
        focus: Review focus area (e.g., 'security', 'performance', 'types', 'i18n').
        model: OpenAI model to use (default from OPENAI_REVIEW_MODEL or gpt-5.4-mini).

    Returns:
        Numbered list of findings from OpenAI, or an error message.
    """
    if not OPENAI_API_KEY:
        return "ERROR: OPENAI_API_KEY environment variable is not set."

    user_parts: list[str] = []
    if language:
        user_parts.append(f"Language: {language}")
    if context:
        user_parts.append(f"Context: {context}")
    if focus:
        user_parts.append(f"Focus your review on: {focus}")
    user_parts.append(f"```\n{code}\n```")
    user_message = "\n\n".join(user_parts)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(
                OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": TEMPERATURE,
                    "max_completion_tokens": MAX_TOKENS,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            return f"ERROR: OpenAI API request timed out after {REQUEST_TIMEOUT} seconds."
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                return "ERROR: OpenAI rate limit exceeded. Wait and retry."
            if status == 401:
                return "ERROR: Invalid OPENAI_API_KEY."
            body = e.response.text[:500]
            return f"ERROR: OpenAI API returned HTTP {status}: {body}"
        except Exception as e:
            return f"ERROR: Unexpected failure: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
