# /mcp — OpenAI File Review

Send Python, YAML, Markdown, JSON, TOML, LaTeX/Jinja, TypeScript / Astro,
HTML/CSS, shell, or notebook files to OpenAI for comprehensive review with
full project context (the consuming repo's root + `.claude` `CLAUDE.md`,
modular rule files, and any PRD / architecture / workflow / status docs),
then implement findings as each review returns.

This is shared tooling (lives in `rz-tools`, consumed via the `.tools`
submodule). The server picks the review prompt from the file extension and
loads context from whichever repo invokes it (`rz-website` or `rz-work`), so
the same command works in both. A consuming repo may keep a tailored copy of
this command with repo-specific auto-implement rules; this file is the shared
baseline.

## Usage

```text
/mcp <file-path> [file-path-2] [file-path-3] ...
/mcp src/components/Hero.astro
/mcp src/content/config.ts src/layouts/BaseLayout.astro
/mcp src/core/models/job.py scripts/scan_jobs.py
/mcp data/consolidated_resume.yaml
```

Accepts one or more file paths or glob patterns. All files are reviewed in
parallel via the `mcp__openai-file-review__openai_file_review` tool.

## Project Context Auto-Loaded

Each review includes whatever the consuming repo provides at these paths
(missing files are simply skipped):

- `CLAUDE.md` (root) — project overview, conventions, architecture
- `.claude/CLAUDE.md` — modular memory structure and hooks
- `.claude/rules/*.md` — code-style, security, documentation rules
- `docs/PRD.md` — product requirements (source of truth)
- `docs/PROJECT.md` — architecture specification
- `docs/WORKFLOW.md` — execution and validation
- `docs/STATUS.md` — milestone tracker

The server (`.tools/mcp-servers/openai-file-review/server.py`) resolves the
consuming repo root by walking up to the nearest `.mcp.json`, then selects the
review prompt from the file extension.

## Workflow — Parallel Review, Immediate Implementation

### Step 1: Launch ALL reviews as background agents (single message)

For EACH file, launch a background `Agent` that calls the MCP tool:

```text
mcp__openai-file-review__openai_file_review(file_path="<file-path>")
```

Launch them all in ONE message with `run_in_background: true` so the
reviews run concurrently.

Immediately tell the user:

> Sent N files for OpenAI review:
>
> - `src/components/Hero.astro`
> - `src/content/config.ts`
>
> Implementing fixes as each review returns.

### Step 2: Implement findings as each review returns

**Behavioural rules:**

1. **Act on each notification IMMEDIATELY** — do not batch.
2. **Process one file at a time** — announce, show findings, fix, repeat.
3. **Never defer implementation** — if you write "I'll do this next", stop
   and use Edit right now instead.
4. **Overlap is expected** — finish current file's fixes, then start next.

For each completed review:

**2a. Announce return:**

> Review returned: `src/components/Hero.astro` (3 of 7 complete)
> Rating: **Good** — 1 Critical, 3 Warning, 5 Info

**2b. Show Critical and Warning findings** (skip Info unless asked).

**2c. Implement fixes via Edit tool** — apply Critical and Warning fixes
without confirmation for the low-risk, mechanical finding types listed below.
Ask first for the higher-risk categories.

**2d. Move to next completed review** or report how many remain in flight.

### Step 3: Summary table after all reviews done

```markdown
| File                       | Rating    | Critical | Warning | Info | Fixes Applied |
| -------------------------- | --------- | -------- | ------- | ---- | ------------- |
| `src/components/Hero.astro`| Good      | 1        | 3       | 5    | 4             |
| `src/content/config.ts`    | Excellent | 0        | 1       | 2    | 1             |
```

List any deferred findings that need user input.

## Review Dimensions by File Type

The server selects the prompt automatically from file extension:

| Extension                                | Type                  | Focus                                                                                                                                              |
| ---------------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.py`                                    | Python                | 8 — correctness, security, type hints + Pydantic V2, error handling, magic numbers, refactoring, conventions, suitability (adapters / MCP / CLI)   |
| `.yml`, `.yaml`                          | YAML data             | 6 — correctness, schema conformance, completeness, consistency, security, best practices                                                           |
| `.md`, `.mdx`                            | Markdown              | 6 — structure, clarity, technical accuracy, completeness, consistency, suitability                                                                 |
| `.tex`, `.jinja`, `.j2`                  | LaTeX / Jinja         | 5 — correctness, template hygiene (delimiters + variable contract), content contract (TN statement), typography, maintainability                   |
| `.ts`, `.tsx`, `.astro`, `.js`           | Astro / TypeScript    | 6 — Astro idioms, type safety, SEO + JSON-LD, accessibility, performance, content & maintainability                                                |
| `.json`, `.toml`, `.ini`, `.cfg`         | Config                | 5 — correctness, completeness, consistency, security, best practices                                                                               |
| `.ipynb`                                 | Notebook              | 5 — code quality, analysis, narrative, reproducibility, suitability                                                                                |
| `.cmd`, `.bat`, `.sh`, `.ps1`            | Shell                 | 5 — correctness, robustness, security, portability, clarity                                                                                        |
| `.html`, `.css`                          | HTML/CSS              | 5 — semantics, a11y, theming, performance, maintainability                                                                                         |

## Auto-Implement Rules

These finding types are implemented WITHOUT asking (apply the form appropriate
to the file's language):

- Magic numbers → extract to the repo's constants module (Python:
  `src/core/constants.py`; web: `src/config.ts` or a tokens file)
- Missing type hints / unjustified `any`; replace loose dicts with a typed
  model (Pydantic V2 in Python; an interface / Zod schema in TypeScript)
- Add a `timeout=` to every HTTP client construction
- Replace bare `except:` / empty `catch` with explicit handling
- Add structured error handling at tool / CLI / island boundaries (return error
  strings or codes rather than raising through the boundary)
- Linter violations — ruff / mypy (Python), `astro check` / `tsc` (web),
  yamllint, markdownlint, Vale
- Unused imports / variables
- Remove emojis from code, comments, and documentation
- Enforce the 120-character line limit
- YAML: lowercase `true` / `false`; quote ambiguous scalars (dates starting
  with a digit, phone numbers)
- Add the TN eligibility statement to resume / cover-letter surfaces that lack
  it (both repos care about this — see the consuming repo's CLAUDE.md)

These finding types REQUIRE user confirmation:

- Algorithmic or business-logic changes (e.g. scoring math, cluster weights)
- Content changes (resume/profile data in `rz-work`; published page copy in
  `rz-website`)
- Architecture shifts, public API / adapter contract changes, or template
  delimiter changes
- Major refactors spanning multiple modules
- Data-model changes that affect on-disk persistence

## Configuration

The MCP server reads `OPENAI_API_KEY` from the consuming repo's `.env` (or the
`${OPENAI_API_KEY}` substitution in that repo's `.mcp.json`). Default model is
`gpt-5.4-mini`; override with `OPENAI_REVIEW_MODEL` or pass `model="gpt-5.4"`
in a direct tool call. See the consuming repo's `.env.example` for the template.

## Direct Tool Use

The `/mcp` slash command wraps the file-review workflow. The same MCP
tools can be invoked directly:

- `mcp__openai-review__openai_review(code, context, language, focus)` —
  send a snippet (no project context loaded)
- `mcp__openai-file-review__openai_file_review(file_path)` —
  send a whole file with full project context

## Related Commands

- `/grok-review` — Visual-content companion (image / video / vision)
