"""OpenAI File Review MCP Server for RZ-Opportunity-Engine.

Sends a target file to OpenAI together with project context (root CLAUDE.md,
modular .claude/CLAUDE.md, master PRD, project architecture, workflow, and
status documents) for a comprehensive review. Supports Python, YAML, Markdown,
LaTeX/Jinja templates, JSON, TOML, TypeScript / TSX / Astro (for the
`website/` static site), HTML/CSS, shell / batch / PowerShell scripts, and
Jupyter notebooks.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("openai-file-review")

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

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = os.environ.get("OPENAI_REVIEW_MODEL", "gpt-5.4-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
REQUEST_TIMEOUT = 180.0
MAX_TOKENS = 16384
TEMPERATURE = 0.2

CONTEXT_FILES = {
    "Project Instructions (root)": PROJECT_ROOT / "CLAUDE.md",
    "Project Instructions (.claude)": PROJECT_ROOT / ".claude" / "CLAUDE.md",
    "Code Style Rules": PROJECT_ROOT / ".claude" / "rules" / "code-style.md",
    "Security Rules": PROJECT_ROOT / ".claude" / "rules" / "security.md",
    "Documentation Rules": PROJECT_ROOT / ".claude" / "rules" / "documentation.md",
    "Product Requirements (master)": PROJECT_ROOT / "docs" / "PRD.md",
    "Architecture": PROJECT_ROOT / "docs" / "PROJECT.md",
    "Workflow": PROJECT_ROOT / "docs" / "WORKFLOW.md",
    "Status": PROJECT_ROOT / "docs" / "STATUS.md",
}

PYTHON_EXTENSIONS = {".py"}
TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
ASTRO_EXTENSIONS = {".astro"}
MARKDOWN_EXTENSIONS = {".md", ".mdx"}
YAML_EXTENSIONS = {".yml", ".yaml"}
JSON_EXTENSIONS = {".json", ".jsonc"}
NOTEBOOK_EXTENSIONS = {".ipynb"}
CONFIG_EXTENSIONS = {".toml", ".ini", ".cfg"}
SHELL_EXTENSIONS = {".cmd", ".bat", ".sh", ".ps1"}
HTML_EXTENSIONS = {".html", ".htm"}
CSS_EXTENSIONS = {".css", ".scss", ".sass"}
LATEX_EXTENSIONS = {".tex", ".jinja", ".j2"}
TEXT_EXTENSIONS = {".txt"}
DOCKER_EXTENSIONS = {"dockerfile", "Dockerfile"}

ALL_SUPPORTED = (
    PYTHON_EXTENSIONS
    | TS_EXTENSIONS
    | ASTRO_EXTENSIONS
    | MARKDOWN_EXTENSIONS
    | YAML_EXTENSIONS
    | JSON_EXTENSIONS
    | NOTEBOOK_EXTENSIONS
    | CONFIG_EXTENSIONS
    | SHELL_EXTENSIONS
    | HTML_EXTENSIONS
    | CSS_EXTENSIONS
    | LATEX_EXTENSIONS
    | TEXT_EXTENSIONS
    | DOCKER_EXTENSIONS
)

SYSTEM_PROMPT_PYTHON = """\
You are a senior Python engineer reviewing code for RZ-Opportunity-Engine — \
a three-phase career positioning system targeting $400K+ USD agentic-AI and \
executive opportunities for a Canadian (USMCA/TN-eligible) operator. Stack: \
Python 3.11 with Poetry, Pydantic V2 (strict field validation), strict mypy \
(disallow_untyped_defs, no_implicit_optional, warn_unused_ignores, \
plugins=pydantic.mypy), ruff (E/W/F/I/B/C4/UP/ARG/SIM), pytest with \
pytest-asyncio and pytest-cov, Jinja2 with LaTeX-safe delimiters \
(`((( )))` / `((% %))` / `((# #))`), httpx async clients for job-source \
adapters (LinkedIn, Wellfound, Toptal, Arc.dev, Otta), SQLAlchemy 2.0 for \
CRM persistence, Click CLI exposed via Poetry entry points (rz-validate, \
rz-scan, rz-render, rz-crm, rz-linkedin, rz-github).

You will receive:
1. The complete Python source file to review.
2. The root and .claude CLAUDE.md instructions plus the modular rule files.
3. The master PRD, architecture, workflow, and status documents.

Review across these dimensions with severity ratings (Critical / Warning / \
Info), line numbers, and concrete fixes.

## 1. Correctness & Edge Cases
Logic errors, off-by-one, unhandled None, encoding (explicit utf-8 on \
file reads / writes), race conditions, file-existence assumptions, async \
gather-vs-sequence misuse, missing await, async context-manager leaks.

## 2. Security
No hardcoded secrets — read from `.env` via python-dotenv or via os.environ. \
API keys live in `OE_API_KEY_*` / `OPENAI_API_KEY` / `XAI_API_KEY` env vars; \
never in code or YAML. No eval/exec, no subprocess(shell=True) on \
user-controlled data, validate file paths to prevent traversal. All httpx \
clients must set timeouts. Job-source adapters must respect TOS and \
robots.txt and use official APIs only. Sensitive files (credentials.json, \
*.pem, *.key, secrets.yaml, .env, CLAUDE.local.md) must never be committed.

## 3. Type Hints & Pydantic V2
Full type hints on every public function (mypy strict). Pydantic V2 \
patterns: `model_validate`, `model_dump`, `Field(..., description=...)`, \
`@field_validator`, `ConfigDict(strict=True)`. No `dict[str, Any]` where a \
named model would do. Discriminated unions via `Field(discriminator=...)` \
when the data is polymorphic.

## 4. Error Handling
Explicit exception types (no bare `except:` or `except Exception:` without \
re-raise / logging). MCP tools and CLI scripts should return error strings \
or exit codes rather than raising through the tool / CLI boundary. \
Pre-commit / hook scripts must respect the PostToolUse / PreToolUse \
contract and exit-code semantics — see `.claude/CLAUDE.md`.

## 5. Magic Numbers & Constants
Numeric literals other than 0, 1, -1 must be named constants in \
`src/core/constants.py`. Canonical commercial facts already live there: \
`MIN_HOURLY_RATE = 150`, `MIN_FTE_SALARY = 400_000`, \
`SCORE_IMMEDIATE_ALERT = 0.90`, `TN_ELIGIBILITY_STATEMENT`. Flag any new \
magic number that should join them.

## 6. Refactoring & Reuse
Code duplication, overly complex functions, long parameter lists. Reuse \
stdlib or existing helpers (`src/core/models/`, `src/core/templates/engine.py`, \
`src/core/job_sources/<adapter>.py`, `src/core/crm/models.py`) rather \
than reinventing. The `RoleClusterConfig` and `OpportunityScore` models \
are the canonical scoring surface — do not duplicate scoring math.

## 7. Conventions
No emojis in code, comments, or docstrings. Placeholder format is \
`::UPPERCASE::` (e.g. `::PROJECT_KEY::`). 120-character line limit. \
Windows portability: forward slashes in path strings, no Unix-only commands \
in subprocess calls — primary dev environment is Windows 11. snake_case \
names, UPPER_SNAKE_CASE constants. Docstrings on every public function and \
class — these become the MCP tool API spec when the function is decorated \
with `@mcp.tool()`.

## 8. Suitability
For job-source adapters under `src/core/job_sources/`: must implement the \
adapter protocol (`fetch_jobs` returning `list[JobPosting]`) and normalise \
into the shared `JobPosting` model. For template-engine users: must use the \
LaTeX-safe Jinja2 delimiters and rendered output must include the TN \
eligibility statement for every resume / cover letter. For MCP servers: \
must use FastMCP and `@mcp.tool()`-decorated functions that return strings.

End with a brief **Summary** rating: Excellent / Good / Needs Work / Major \
Issues, plus a prioritised top-5 list of improvements.\
"""

SYSTEM_PROMPT_YAML = """\
You are a senior engineer reviewing a YAML data file for RZ-Opportunity-Engine. \
YAML in this repo is the canonical source of truth for consolidated resume \
content (`data/consolidated_resume.yaml`), skills taxonomy, role-cluster \
scoring configuration (`config/clusters/*.yaml`), job-source configuration \
(`config/sources.yaml`), and pipeline settings. Pydantic V2 models in \
`src/core/models/` validate every file on load via `rz-validate`.

Review across these dimensions with severity ratings (Critical / Warning / \
Info), line numbers, and concrete fixes:

## 1. Correctness
Valid YAML 1.2 syntax. Lowercase `true` / `false` (never True/False/yes/no). \
Quote ambiguous scalars (phone numbers, dates that start with a digit, \
strings that look like booleans). 2-space indentation. Document start \
marker `---` for multi-document files.

## 2. Schema Conformance
Every field must exist in the matching Pydantic model. No unknown fields. \
Required fields populated. Enum values match. Cluster scoring weights sum \
correctly. Skills reference real entries in the taxonomy. Job-source \
adapter names match the adapter classes under `src/core/job_sources/`.

## 3. Completeness
Resume YAML covers every cluster the resume targets (agentic_ai, \
fractional_cto, technical_advisor, fte_executive). Every Experience entry \
has a date range, role, company, achievements, and cluster tags. Every \
project lists tech stack and outcome. The TN eligibility statement is \
present where the rendered template will need it.

## 4. Consistency
Same units throughout (USD vs CAD, hourly vs daily, FTE vs contract). \
Naming consistent with the taxonomy. Same date format (ISO 8601: \
YYYY-MM or YYYY-MM-DD). No duplicate skills or duplicate cluster IDs. \
Cross-references between YAML files resolve (e.g. cluster IDs in resume \
match cluster files; skill IDs match the taxonomy).

## 5. Security
No secrets, no API keys, no PII beyond what's intentional for the resume. \
No production database URLs or hostnames. No personal addresses or phone \
numbers in committed files.

## 6. Best Practices
Anchor / alias only when it materially helps maintenance. Comments \
explain non-obvious choices. Multiline strings use `|` (literal block) or \
`>` (folded) appropriately. Lists ordered intentionally (chronological / \
priority).

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_MARKDOWN = """\
You are a senior technical writer reviewing a Markdown document for the \
RZ-Opportunity-Engine project. Docs live under `docs/` (PRD.md, PROJECT.md, \
WORKFLOW.md, STATUS.md, PROFILE.md, AGENTIC_EXPERIENCE.md, WEBSITE.md, \
Resume) and at the repo root (CLAUDE.md, README.md). The project uses \
markdownlint for structural lint and Vale for prose. ATX-style headings \
required. 120-character line limit.

Review across these dimensions with severity ratings (Critical / Warning / \
Info), line numbers, and concrete fixes.

## 1. Structure & Formatting
ATX heading hierarchy (no skipped levels). List spacing, table alignment, \
link validity. Unique headings within each document. Code fences declare a \
language. Sensible line length (target 120, hard-wrap prose).

## 2. Clarity & Precision
No hedging, no marketing fluff. PRD / workflow / status docs are precise \
about what is true today vs what is planned. Be specific: "use 2-space \
indentation", not "format properly". Cross-references to other docs use \
relative paths.

## 3. Technical Accuracy
Stack references match the actual code (Python 3.11 + Poetry + Pydantic V2 \
+ strict mypy + ruff + pytest + Jinja2 + httpx + SQLAlchemy 2.0 + Click; \
Astro 5 + Tailwind 3 + MDX for the website). Command examples actually \
work (`poetry run rz-validate`, `poetry run rz-scan`, `poetry run rz-render`, \
`poetry run rz-crm`, etc). Constants match `src/core/constants.py` \
(MIN_HOURLY_RATE=$150, MIN_FTE_SALARY=$400K). The TN eligibility statement \
is referenced where resume / cover-letter generation is discussed.

## 4. Completeness
No placeholder text, no unfilled TODOs in shipped docs, no broken \
cross-references. Milestone tracker in STATUS.md reflects current state.

## 5. Consistency
Terminology consistent across docs (Opportunity, OpportunityScore, \
RoleCluster, agentic AI, fractional CTO, technical advisor, FTE executive; \
USMCA/TN, not "TN visa"). Capitalisation, naming. No emojis. \
`::UPPERCASE::` for placeholders.

## 6. Suitability
Fitness for purpose. PRD.md is the source of truth for requirements; \
PROJECT.md is the architecture specification; WORKFLOW.md is pipeline + \
validation; STATUS.md is the milestone tracker. Sub-doc vs master: PRD \
remains authoritative for scope and success metrics; other docs win for \
their domain (PROJECT for architecture, WORKFLOW for pipeline execution).

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_CONFIG = """\
You are a senior engineer reviewing a configuration file for the \
RZ-Opportunity-Engine project. Configs in this repo cover Poetry / \
pyproject.toml, ruff, mypy, pytest, yamllint, markdownlint, Vale, Astro / \
Vite (under `website/`), TypeScript tsconfig (under `website/`), the \
Claude Code `.claude/settings.json`, GitHub Actions workflows, and the \
`.mcp.json` MCP server registry.

Review across these dimensions with severity ratings:

## 1. Correctness
Valid syntax, correct keys / values, no typos, proper types.

## 2. Completeness
Missing recommended settings; missing entries that the code expects \
(Poetry entry points must match `scripts/<name>.py:main`; ruff selected \
rules; mypy strict-mode flags; pytest paths / markers). For `.mcp.json`: \
all referenced server scripts must exist and env-var references must be \
defined in `.env.example`.

## 3. Consistency
Consistent with sibling configs (pyproject.toml ruff section vs \
.yamllint.yaml; pytest config vs test layout). No contradictory settings \
or duplicated definitions across files.

## 4. Security
Exposed secrets, overly permissive permissions, disabled safety checks, \
secret names accidentally placed in public config. `.env` must never be \
committed; only `.env.example` (placeholders only). `.claude/settings.local.json` \
must remain local (gitignored).

## 5. Best Practices
Tool-specific best practices, sensible defaults, well-organised. 120-char \
line limit for Python, TypeScript, YAML.

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_LATEX = """\
You are a senior typesetting engineer reviewing a LaTeX / Jinja template \
for the RZ-Opportunity-Engine project. Templates live under \
`templates/resumes/*.tex.jinja`, `templates/cover_letters/*.tex.jinja`, \
and `templates/emails/*.txt.jinja`. They are rendered by \
`src/core/templates/engine.py` (Jinja2 with LaTeX-safe delimiters — \
`((( )))` for variables, `((% %))` for blocks, `((# #))` for comments) \
into `.tex` output, then compiled with XeLaTeX into PDFs landing in \
`output/resumes/<cluster>/<cluster>.pdf` or \
`output/cover_letters/cover_letter_<cluster>_<company>_<date>.pdf`.

Review across these dimensions with severity ratings:

## 1. Correctness
Valid LaTeX once rendered. Balanced braces / environments. No \
double-escaping where the Jinja layer already escapes. Unicode characters \
work under XeLaTeX (the project uses XeLaTeX specifically for Unicode \
support). No `\\input{}` of files that won't exist at compile time.

## 2. Template Hygiene
Use the project's LaTeX-safe delimiters consistently — never `{{ }}` or \
`{% %}` (those collide with LaTeX). Variables match the ResumeProfile / \
Experience / Project / Cluster fields exposed by `src/core/models/`. \
Conditional sections (`((% if ... %))`) handle missing / empty data \
without producing an empty bullet, empty section heading, or dangling \
comma.

## 3. Content Contract
Every resume template MUST include the TN eligibility statement \
(`TN_ELIGIBILITY_STATEMENT` from `src/core/constants.py`). Every \
cluster-specific template surfaces the experience tagged for that cluster \
only. No PII beyond the resume profile (email, phone, location). No \
placeholders left like `::UPPERCASE::` in shipped output — those must be \
substituted at render time.

## 4. Typography
Consistent font sizing, spacing, page margins. Section ordering matches \
the cluster's intended emphasis (Agentic AI Developer leads with MCP / \
LLM work; Fractional CTO leads with executive scope; Technical Advisor \
leads with due-diligence experience; FTE Executive leads with P&L / team \
scale). Date formatting consistent (e.g. "Jan 2024 -- Present"). Hyphens \
vs en-dashes vs em-dashes used correctly.

## 5. Maintainability
Macros for repeated structures (experience entry, project entry). \
Comments (`((# #))`) where the typography decision is non-obvious. No \
hard-coded literal content that should come from `data/consolidated_resume.yaml`.

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_TYPESCRIPT = """\
You are a senior frontend engineer reviewing TypeScript / Astro / JavaScript \
code for the RZ-Opportunity-Engine `website/` directory — a static \
career-portfolio site for richardzak.com built with Astro 5, Tailwind CSS 3, \
and MDX content collections. The site surfaces the operator's services, \
case studies, blog posts, and a resume page; all content authoring goes \
through MDX under `website/src/content/`. SEO + structured data \
(Person / Organization / BreadcrumbList / BlogPosting / WebSite JSON-LD), \
sitemap, robots.txt, llms.txt are part of the build.

Review across these dimensions with severity ratings (Critical / Warning / \
Info), line numbers, and concrete fixes.

## 1. Astro Idioms
Server-only logic in the frontmatter; client-only logic in `<script>` \
islands or `client:*` directives. Use `getStaticPaths()` for dynamic \
routes. Content collections via `defineCollection` + Zod schemas under \
`website/src/content/config.ts`. Prefer static rendering — only hydrate \
when an island truly needs interactivity.

## 2. Type Safety
TypeScript strict mode. No `any` without a justification comment. Content \
collection types come from Zod schemas. `Astro.props` typed via the \
component's interface or generic. No unchecked indexed access.

## 3. SEO & Structured Data
Every page sets `<title>` + meta description + canonical URL + Open Graph \
+ Twitter Card via the shared layout. JSON-LD blocks (Person, \
Organization, BreadcrumbList, BlogPosting, WebSite) are valid against \
schema.org. Sitemap regenerates on build. robots.txt and llms.txt stay in \
sync with the route surface.

## 4. Accessibility (WCAG 2.2 AA)
Semantic landmarks (`<main>`, `<nav>`, `<header>`, `<footer>`), heading \
hierarchy with no skipped levels, alt text on every `<img>`, ARIA labels \
on icon-only buttons, visible focus styles, color contrast in both light \
and dark themes (if applicable).

## 5. Performance
Static-first; avoid client-side hydration unless needed. Self-host fonts \
(no external font requests). Optimise images via Astro's `<Image>` \
component. Tailwind purges unused classes via the JIT compiler.

## 6. Content & Maintainability
MDX frontmatter conforms to the content collection schema. No \
hard-coded URLs that should come from `website/src/config.ts` or env. \
Components live under `website/src/components/`; shared layouts under \
`website/src/layouts/`. The TN eligibility statement appears on the \
resume page where applicable.

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_NOTEBOOK = """\
You are a senior engineer reviewing a Jupyter notebook in the \
RZ-Opportunity-Engine project. Notebooks are typically used for ad-hoc \
analysis of scraped job data, market heatmaps, or skill-gap analyses.

Review across these dimensions with severity ratings:

## 1. Code Quality
PEP 8, proper imports, magic numbers extracted to constants, type hints \
where practical.

## 2. Analysis Logic
Correctness of calculations, statistical methods, data transformations. \
Reuse models from `src/core/models/` rather than redefining shapes inside \
the notebook.

## 3. Narrative Flow
Clear markdown cells, proper heading hierarchy, conclusions documented.

## 4. Reproducibility
No hardcoded absolute paths (use project-relative paths). Seed values for \
random operations. Cell execution order is linear top-to-bottom.

## 5. Suitability
Alignment with project goals. If the notebook produces an artefact that \
should be regenerable, it belongs as a script under `scripts/`.

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_SHELL = """\
You are a senior engineer reviewing a shell / batch / PowerShell script \
for the RZ-Opportunity-Engine project on Windows. The primary dev \
environment is Windows 11, so portability matters. Scripts typically \
wrap Poetry commands, XeLaTeX compilation, or job-source orchestration.

Review with severity ratings across:

## 1. Correctness
Syntax, correct commands, path handling (forward slashes in cross-platform \
paths), exit-code handling.

## 2. Robustness
Missing error handling, unquoted variables (especially paths with spaces — \
common on Windows), missing existence checks before file operations.

## 3. Security
Command injection risks, hardcoded credentials, unsafe temp files. Secrets \
sourced from `.env` only.

## 4. Portability
PowerShell vs cmd vs bash idioms used correctly for the file extension. \
Line endings: `.cmd` / `.bat` / `.ps1` should be CRLF; `.sh` should be LF.

## 5. Clarity
Comments explaining intent, descriptive variable names, script purpose \
documented at the top.

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_HTML_CSS = """\
You are a senior frontend engineer reviewing HTML / CSS for the \
RZ-Opportunity-Engine `website/` directory. The site is built with Astro 5 \
and Tailwind CSS 3 (the JIT-compiled `tailwind.config.cjs` is the source \
of truth for the design system). Brand voice: executive, technical, \
credible.

Review with severity ratings across:

## 1. Semantic Markup / Selectors
Proper landmarks, headings, form labels. CSS specificity reasonable. \
Avoid id selectors for styling.

## 2. Accessibility (WCAG 2.2 AA)
Color contrast, focus indicators, touch-target size (44x44 minimum), \
prefers-reduced-motion respect, alt text on images, lang attribute on \
`<html>`.

## 3. Theming Consistency
Tailwind utility classes preferred over raw CSS for design tokens. \
Design tokens (colours, spacing, typography scale) live in \
`website/tailwind.config.cjs` — no inline hex codes that bypass the \
token system.

## 4. Performance
Avoid layout thrash, oversized images, render-blocking CSS, unused \
selectors. Self-hosted fonts (no external font requests).

## 5. Maintainability
Tailwind utility usage vs raw CSS, component scoping, design-token \
alignment.

End with a **Summary** rating and top-3 improvements.\
"""

SYSTEM_PROMPT_TEXT = """\
You are a senior technical reviewer examining a plain text file in the \
RZ-Opportunity-Engine project.

Review for: completeness, accuracy, formatting consistency, and fitness \
for purpose. Provide findings with severity ratings.

End with a **Summary** rating and top-3 improvements.\
"""


def _get_system_prompt(suffix: str) -> str:
    """Return the appropriate system prompt for a file extension or filename."""
    if suffix in PYTHON_EXTENSIONS:
        return SYSTEM_PROMPT_PYTHON
    if suffix in TS_EXTENSIONS or suffix in ASTRO_EXTENSIONS:
        return SYSTEM_PROMPT_TYPESCRIPT
    if suffix in MARKDOWN_EXTENSIONS:
        return SYSTEM_PROMPT_MARKDOWN
    if suffix in YAML_EXTENSIONS:
        return SYSTEM_PROMPT_YAML
    if suffix in JSON_EXTENSIONS or suffix in CONFIG_EXTENSIONS:
        return SYSTEM_PROMPT_CONFIG
    if suffix in LATEX_EXTENSIONS:
        return SYSTEM_PROMPT_LATEX
    if suffix in NOTEBOOK_EXTENSIONS:
        return SYSTEM_PROMPT_NOTEBOOK
    if suffix in SHELL_EXTENSIONS or suffix in DOCKER_EXTENSIONS:
        return SYSTEM_PROMPT_SHELL
    if suffix in HTML_EXTENSIONS or suffix in CSS_EXTENSIONS:
        return SYSTEM_PROMPT_HTML_CSS
    return SYSTEM_PROMPT_TEXT


def _read_file(path: Path, label: str) -> str:
    """Read a text file and return its contents wrapped with a labelled header."""
    try:
        content = path.read_text(encoding="utf-8")
        return f"--- {label} ({path.name}) ---\n{content}\n--- End {label} ---"
    except FileNotFoundError:
        return f"--- {label} ---\n[FILE NOT FOUND: {path}]\n--- End {label} ---"
    except OSError as e:
        return f"--- {label} ---\n[READ ERROR: {e}]\n--- End {label} ---"


def _read_notebook(path: Path, label: str) -> str:
    """Extract cells from a Jupyter notebook as readable text."""
    try:
        raw = path.read_text(encoding="utf-8")
        nb = json.loads(raw)
        parts: list[str] = []
        for i, cell in enumerate(nb.get("cells", [])):
            cell_type = cell.get("cell_type", "unknown")
            source = "".join(cell.get("source", []))
            parts.append(f"[Cell {i + 1} -- {cell_type}]")
            parts.append(source)
            parts.append("")
        content = "\n".join(parts)
        return f"--- {label} ({path.name}) ---\n{content}\n--- End {label} ---"
    except Exception as e:
        return f"--- {label} ---\n[NOTEBOOK READ ERROR: {e}]\n--- End {label} ---"


def _read_any(path: Path, label: str) -> str:
    """Read any supported file type with the appropriate extraction method."""
    suffix = path.suffix.lower()
    if suffix in NOTEBOOK_EXTENSIONS:
        return _read_notebook(path, label)
    return _read_file(path, label)


def _resolve_target(file_path: str, project_root: Path) -> tuple[Path | None, str | None]:
    """Resolve a target path, ensuring it exists. Returns (path, error)."""
    target = Path(file_path)
    if not target.is_absolute():
        target = project_root / target
    target = target.resolve()
    if not target.exists():
        return None, f"ERROR: File not found: {target}"
    return target, None


def _classify_file_type(target: Path) -> tuple[str, str | None]:
    """Determine the file-type key used for prompt selection. Returns (file_type, error)."""
    file_type = target.name if target.name in DOCKER_EXTENSIONS else target.suffix.lower()
    if file_type not in ALL_SUPPORTED:
        supported_list = ", ".join(sorted(ALL_SUPPORTED))
        return file_type, f"ERROR: Unsupported file type '{file_type}'. Supported: {supported_list}"
    return file_type, None


def _build_context_parts(project_root: Path) -> list[str]:
    parts: list[str] = []
    for label, ctx_path in CONTEXT_FILES.items():
        resolved = (project_root / ctx_path) if not ctx_path.is_absolute() else ctx_path
        parts.append(_read_file(resolved.resolve(), label))
    return parts


@mcp.tool()
async def openai_file_review(
    file_path: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Send a file to OpenAI for comprehensive review with project context.

    Reads the target file along with RZ-Opportunity-Engine's CLAUDE.md
    (root + .claude), modular rule files, master PRD, architecture,
    workflow, and status documents, then sends everything to the specified
    OpenAI model. Supports Python, YAML, Markdown, JSON, TOML, INI,
    LaTeX/Jinja templates, TypeScript / Astro / JS, Jupyter notebooks,
    shell scripts, HTML/CSS, and plain text.

    Args:
        file_path: Path to the file to review (absolute or relative to project root).
        model: OpenAI model to use (default from OPENAI_REVIEW_MODEL or gpt-5.4-mini).

    Returns:
        Structured review findings from OpenAI, grouped by dimension.
    """
    if not OPENAI_API_KEY:
        return "ERROR: OPENAI_API_KEY environment variable is not set."

    project_root = _find_project_root()

    target, target_err = _resolve_target(file_path, project_root)
    if target_err is not None or target is None:
        return target_err or "ERROR: target resolution failed"

    file_type, type_err = _classify_file_type(target)
    if type_err is not None:
        return type_err

    system_prompt = _get_system_prompt(file_type)
    target_content = _read_any(target, "File Under Review")
    context_parts = _build_context_parts(project_root)

    user_message = "\n\n".join(
        [
            f"Review this file: `{target.relative_to(project_root)}`",
            target_content,
            *context_parts,
        ]
    )

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
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": TEMPERATURE,
                    "max_completion_tokens": MAX_TOKENS,
                },
            )
            response.raise_for_status()
            data = response.json()
            result: str = data["choices"][0]["message"]["content"]
            return result
        except httpx.TimeoutException:
            return f"ERROR: OpenAI API request timed out after {REQUEST_TIMEOUT}s."
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
