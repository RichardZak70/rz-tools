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

### Requirements

- **Python 3.14** (tested) — `3.11+` is the supported floor.
- The `python` on PATH must resolve to the interpreter you want the MCP
  client to launch, since `.mcp.json` uses `"command": "python"`.
- Each server depends on `mcp >= 1.0`, `httpx >= 0.28`, and
  `python-dotenv >= 1.0` — install once into the active interpreter:

  ```bash
  pip install -r .tools/mcp-servers/openai-file-review/requirements.txt
  ```

  (The three `requirements.txt` files are identical; one install covers all
  three servers.)

### Credentials

`.mcp.json` references credentials via `${VAR}` substitution, which the MCP
client expands from the **process environment** before launching each
server. Inside the server, `python-dotenv` then loads the consuming repo's
`.env` with `override=False`, so a populated process env wins over an empty
or absent `.env` line. Net effect:

- A key set in your system / user environment (e.g. `OPENAI_API_KEY`) is
  picked up automatically — no `.env` edit needed.
- A key set in `.env` overrides nothing from the system env but populates a
  missing one.
- A key absent from both is unset, and the server returns
  `ERROR: <VAR> environment variable is not set.`

Cross-cutting slash commands (`/mcp`, `/grok-review`) and generic hooks live
under `claude/`; consuming repos symlink or copy the pieces they need into their
own `.claude/`.

## Notes

- No secrets are committed here. `.env` is gitignored; only `.env.example` ships.
- `claude/agents/` is intentionally empty — every current agent is scoped to one
  child repo and lives there. Add an agent here only when both repos use it.
