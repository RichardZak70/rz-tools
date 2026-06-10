# /mcp — OpenAI File Review

Send Python, YAML, Markdown, JSON, TOML, LaTeX/Jinja, TypeScript / Astro,
HTML/CSS, shell, or notebook files to OpenAI for comprehensive review with
full project context (root + `.claude` `CLAUDE.md`, modular rule files,
master PRD, architecture, workflow, status docs from the consuming repo),
then implement findings as each review returns.

## Usage

```text
/mcp <file-path> [file-path-2] [file-path-3] ...
/mcp src/core/models/job.py
/mcp src/core/job_sources/linkedin.py scripts/scan_jobs.py
/mcp templates/resumes/agentic_ai.tex.jinja
/mcp data/consolidated_resume.yaml
```

Accepts one or more file paths or glob patterns. All files are reviewed in
parallel via the `mcp__openai-file-review__openai_file_review` tool.

## Project Context Auto-Loaded

Each review includes:

- `CLAUDE.md` (root) — project overview, conventions, architecture
- `.claude/CLAUDE.md` — modular memory structure and hooks
- `.claude/rules/code-style.md` — language conventions
- `.claude/rules/security.md` — sensitive-file and work-authorization rules
- `.claude/rules/documentation.md` — Markdown and naming conventions
- `docs/PRD.md` — product requirements (source of truth)
- `docs/PROJECT.md` — architecture specification
- `docs/WORKFLOW.md` — pipeline execution and validation
- `docs/STATUS.md` — milestone tracker

The OpenAI server (`mcp-servers/openai-file-review/server.py`) selects the
correct review prompt based on file extension.

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
> - `src/core/models/job.py`
> - `scripts/scan_jobs.py`
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

> Review returned: `src/core/models/job.py` (3 of 7 complete)
> Rating: **Good** — 1 Critical, 3 Warning, 5 Info

**2b. Show Critical and Warning findings** (skip Info unless asked).

**2c. Implement fixes via Edit tool** — apply Critical and Warning fixes
without confirmation for: magic numbers (extract to
`src/core/constants.py`), missing type hints, Pydantic V2 idioms
(`model_validate` / `model_dump` / `Field(...)`), explicit exception
types, structured error handling in MCP tools / CLI commands, async
patterns (timeout on every httpx client, no missing await), ruff
violations, removal of bare `except:`, adding TN eligibility statement to
resume / cover-letter templates that lack it, YAML schema conformance.
Ask first for: algorithmic changes to scoring (`OpportunityScore`,
`RoleClusterConfig`), changes to the resume content in
`data/consolidated_resume.yaml`, architecture shifts, job-source adapter
contract changes.

**2d. Move to next completed review** or report how many remain in flight.

### Step 3: Summary table after all reviews done

```markdown
| File                          | Rating    | Critical | Warning | Info | Fixes Applied |
| ----------------------------- | --------- | -------- | ------- | ---- | ------------- |
| `src/core/models/job.py`      | Good      | 1        | 3       | 5    | 4             |
| `scripts/scan_jobs.py`        | Excellent | 0        | 1       | 2    | 1             |
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

These finding types are implemented WITHOUT asking:

- Magic numbers → extract to `src/core/constants.py` (or `website/src/config.ts`
  for website-side constants); commercial constants already there:
  `MIN_HOURLY_RATE`, `MIN_FTE_SALARY`, `SCORE_IMMEDIATE_ALERT`,
  `TN_ELIGIBILITY_STATEMENT`
- Missing type hints / explicit `any` without justification
- Replace `dict[str, Any]` with a Pydantic V2 model when the shape is known
- Add `timeout=` to every httpx client construction
- Replace bare `except:` / `except Exception:` (without re-raise) with
  explicit exception types
- Add structured try/except returning error strings from MCP tools and CLI
  commands (rather than raising through the boundary)
- ruff / mypy / yamllint / markdownlint violations
- Unused imports / variables
- Add the TN eligibility statement (`TN_ELIGIBILITY_STATEMENT` from
  `src/core/constants.py`) to any resume / cover-letter template that
  lacks it
- Replace `True` / `False` / `yes` / `no` with lowercase `true` / `false`
  in YAML
- Quote ambiguous YAML scalars (dates starting with digits, phone numbers)
- Remove emojis from code, comments, and documentation
- Convert ad-hoc placeholders to the `::UPPERCASE::` format

These finding types REQUIRE user confirmation:

- Algorithmic changes to scoring (`OpportunityScore`, `RoleClusterConfig`,
  cluster weight math)
- Content changes to `data/consolidated_resume.yaml` (experience,
  achievements, dates, employers)
- Architecture shifts (model restructuring, adapter contract changes,
  template engine delimiter changes)
- Job-source adapter contract changes (`fetch_jobs` shape, normalisation)
- Major refactors spanning multiple modules
- CRM data-model changes that affect on-disk persistence

## Configuration

The MCP server reads `OPENAI_API_KEY` from `.env` at the project root.
Default model is `gpt-5.4-mini`; override with `OPENAI_REVIEW_MODEL` env
var or pass `model="gpt-5.4"` / `model="gpt-4o"` in a direct tool call.

See `.env.example` for the template.

## Direct Tool Use

The `/mcp` slash command wraps the file-review workflow. The same MCP
tools can be invoked directly:

- `mcp__openai-review__openai_review(code, context, language, focus)` —
  send a snippet (no project context loaded)
- `mcp__openai-file-review__openai_file_review(file_path)` —
  send a whole file with full project context

## Related Commands

- `/quality-file <file>` — Local fast quality check (ruff + mypy +
  yamllint + markdownlint as applicable) — no API call, use for fast
  iteration
- `/quality` — Full project quality gate
- `/security-check` — Security scan
- `/review` — Self-review pending changes
- `/grok-review` — Visual-content companion (image / video / vision)
