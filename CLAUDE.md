# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

`rz-tools` holds the shared developer tooling for the `richardzak.com`
repository family: the MCP servers and reusable Claude Code configuration that
both `rz-website` (public Astro site) and `rz-work` (private Python pipeline)
consume. It is the third repo from the `RZ-Opportunity-Engine` split on
2026-06-09 (predecessor tag `pre-split-2026-06-09`).

This repo owns: MCP servers, cross-cutting slash commands, and generic hooks.
It does **not** own application code, content, or deploy config — those live in
the child repos.

## Companion Repositories

| Repo | Purpose | Visibility |
| ---- | ------- | ---------- |
| `rz-website` | Public Astro site at richardzak.com | Public |
| `rz-work` | Private Python pipeline — resume / cover-letter / LinkedIn / CRM | Private |
| `rz-tools` (this repo) | MCP servers + shared Claude Code config | Public |

## Layout

```text
mcp-servers/
  grok-review/         # xAI Grok — image / video generation + vision analysis
  openai-review/       # OpenAI — review a code snippet (no project context)
  openai-file-review/  # OpenAI — review a whole file with project context
claude/
  agents/              # Cross-cutting agents only (none yet)
  commands/            # /mcp, /grok-review
  hooks/               # check-line-endings, check-no-emojis, markdown-lint
```

## How the servers resolve the project root

Each server walks up from its own file location to the nearest directory
containing a `.mcp.json`, falling back to two levels up (the directory holding
`mcp-servers/`). This is the single mechanism that lets a server work both at a
repo root (the old monolith) and nested inside a `.tools/` submodule, where the
consuming repo root sits one level above `.tools/`.

Implications when editing servers:

- Do **not** add a `.mcp.json` at the root of this repo — it would shadow the
  walk-up and make servers resolve their own root instead of the consuming
  repo's.
- `.env` loading and (for `openai-file-review`) the auto-loaded `CONTEXT_FILES`
  both key off this resolved root, so they must use `_find_project_root()` /
  `PROJECT_ROOT`, never a hard-coded `parent.parent`.

## Conventions

- **No emojis** anywhere — source, markup, docs, commit messages.
- **120-char line length** for code and Markdown.
- **Conventional commits**: `type(scope): description`. Scopes: `mcp`,
  `commands`, `hooks`, `agents`, `docs`, `deps`.
- **No secrets committed.** `.env` is gitignored; only `.env.example` ships.
- Match the surrounding code's style when editing a server.

## Development

Target interpreter: **Python 3.14** (currently `C:\Python314\python.exe` on
this machine). 3.11 is the supported floor — both run the server stack
(`mcp >= 1.0`, `httpx >= 0.28`, `python-dotenv >= 1.0`) without changes.
`.mcp.json` uses `"command": "python"` so whatever `python` resolves to on
PATH is what runs the server; verify with `python --version` if you change
your interpreter.

```bash
# Install one server's deps (covers all three — the requirements files match)
pip install -r mcp-servers/openai-file-review/requirements.txt

# Syntax-check a server
python -c "import ast; ast.parse(open('mcp-servers/openai-file-review/server.py', encoding='utf-8').read())"
```

## Credential resolution

`.mcp.json` in each consuming repo references credentials via `${VAR}`. The
MCP client expands those from the **process environment** before launching
the server; inside the server, `python-dotenv` then loads the consuming
repo's `.env` with `override=False`. Net effect: a populated process /
system env wins over an empty `.env` line, so a system-wide `OPENAI_API_KEY`
is used automatically — no `.env` edit needed. A key absent from both is
unset, and the server returns `ERROR: <VAR> environment variable is not
set.` (Verified end-to-end on this machine: system `OPENAI_API_KEY`
propagates through all three repos and a live `openai-review` call
succeeds.)

## Notes

- The server prompts and the `/mcp` + `/grok-review` command docs were
  generalised away from the monolith name and its `website/` layout — they now
  read as shared tooling and describe `rz-website` (Astro at the repo root) and
  `rz-work` (Python pipeline) accurately. The per-file-type review guidance is
  intentionally specific to whichever repo reviews that file type.
- `claude/commands/mcp.md` is the shared baseline. A consuming repo may keep a
  tailored copy with repo-specific auto-implement rules.
- `claude/agents/` is empty by design. Promote an agent here only when both
  child repos genuinely share it.
