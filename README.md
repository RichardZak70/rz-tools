# rz-tools

Shared developer tooling for the `richardzak.com` repository family: the MCP
servers and reusable Claude Code configuration that both
[`rz-website`](https://github.com/RichardZak70/rz-website) (public Astro site)
and `rz-work` (private Python career pipeline) consume.

This repo is the third of three that the `RZ-Opportunity-Engine` monolith was
split into on 2026-06-09:

| Repo | Purpose | Visibility |
| ---- | ------- | ---------- |
| `rz-website` | Public Astro site at richardzak.com | Public |
| `rz-work` | Private Python pipeline — resume / cover-letter / LinkedIn / CRM | Private |
| `rz-tools` (this repo) | MCP servers + shared Claude Code config | Public |

## Layout

```text
rz-tools/
├─ mcp-servers/
│  ├─ grok-review/         # xAI Grok — image / video generation + vision analysis
│  ├─ openai-review/       # OpenAI — review a code snippet (no project context)
│  └─ openai-file-review/  # OpenAI — review a whole file with project context
└─ claude/                 # Shared Claude Code config consumed by both child repos
   ├─ agents/              # Cross-cutting agents (none yet; repo-specific agents stay home)
   ├─ commands/            # /mcp, /grok-review
   └─ hooks/               # check-line-endings, check-no-emojis, markdown-lint
```

## MCP servers

All three are stdio MCP servers (Python, `mcp` + `httpx` + `python-dotenv`).
Each locates the **consuming repo root** by walking up from its own location to
the nearest directory containing a `.mcp.json`, falling back to two levels up.
This makes them work identically whether checked out at a repo root or nested
inside a `.tools/` submodule.

| Server | Tool(s) | Credentials |
| ------ | ------- | ----------- |
| `grok-review` | image / video generation, vision analysis | `XAI_API_KEY` |
| `openai-review` | `openai_review(code, context, language, focus)` — snippet review | `OPENAI_API_KEY` |
| `openai-file-review` | `openai_file_review(file_path)` — full-file review with auto-loaded project context | `OPENAI_API_KEY` |

Credentials are read from the **consuming repo's** `.env` (or the process
environment via `${VAR}` substitution in that repo's `.mcp.json`). See
[.env.example](.env.example) for the full variable list.

## Consumption pattern

Both child repos add this repo as a git submodule under `.tools/` and reference
the servers from their own `.mcp.json`:

```jsonc
// rz-website/.mcp.json or rz-work/.mcp.json
{
  "mcpServers": {
    "openai-file-review": {
      "type": "stdio",
      "command": "python",
      "args": [".tools/mcp-servers/openai-file-review/server.py"],
      "env": { "OPENAI_API_KEY": "${OPENAI_API_KEY}" }
    }
  }
}
```

Cloning a repo that uses the submodule:

```bash
git clone --recurse-submodules <repo-url>
# or, in an existing clone:
git submodule update --init --recursive
```

Install each server's dependencies once:

```bash
pip install -r mcp-servers/openai-file-review/requirements.txt
```

Cross-cutting slash commands (`/mcp`, `/grok-review`) and generic hooks live
under `claude/`; consuming repos symlink or copy the pieces they need into their
own `.claude/`.

## Notes

- No secrets are committed here. `.env` is gitignored; only `.env.example` ships.
- `claude/agents/` is intentionally empty — every current agent is scoped to one
  child repo and lives there. Add an agent here only when both repos use it.
