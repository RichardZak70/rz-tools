# /grok-review — xAI Grok Visual Workflows

Send images and video concepts plus context to Grok via the
`grok-review` MCP server, and get back generated images, generated video,
or vision-based analysis.

This is the visual-content companion to `/mcp` (which is the OpenAI
file-review bridge). Code / data / docs review stays on `/mcp`; visual
generation / analysis goes here. Typical uses across the rz-website and
rz-work repos:

- Generate hero / cover graphics for case studies and blog posts on the
  rz-website portfolio.
- Vision-analyse rendered resume / cover-letter PDFs (after PDF-to-image
  rasterisation) to flag layout regressions.
- Ideate visuals for outreach campaigns.

## Usage

```text
/grok-review <action> <args>
```

The `action` selects which MCP tool to invoke. Tools are also callable
directly without the slash command (handy when chaining or running in
parallel from a sub-agent).

| Action    | MCP tool                                 | Purpose                                                       |
| --------- | ---------------------------------------- | ------------------------------------------------------------- |
| `image`   | `mcp__grok-review__grok_generate_image`  | Generate image(s) from a text prompt                          |
| `analyze` | `mcp__grok-review__grok_analyze_image`   | Vision analysis of one or more local images                   |
| `chat`    | `mcp__grok-review__grok_multimodal_chat` | Free-form text + image input → text out (concept brainstorm)  |
| `video`   | `mcp__grok-review__grok_generate_video`  | Generate a video from a concept (+ optional reference frames) |

Default output directory for generated assets: `docs/grok-output/`
(override via `GROK_OUTPUT_DIR`).

## Examples

```text
# 1. Generate a hero graphic for a new agentic-AI case study
/grok-review image "Editorial hero illustration for a senior engineering executive's career portfolio: clean isometric depiction of an agentic AI workflow — three autonomous agents coordinating through MCP tool calls on a dark navy gradient, restrained accent colour, minimalist, photoreal lighting, no text, 16:9" n=3

# 2. Vision analysis on the rendered resume PDF (rasterised to PNG)
/grok-review analyze "output/resumes/agentic_ai/preview-page1.png" prompt="Audit this resume page for layout regressions vs an executive resume standard. Score each axis (hierarchy, density, whitespace, alignment, typography, readability at print resolution) 0–10. Flag any text that wraps awkwardly."

# 3. Brainstorm cover-letter visual treatment using the website hero as reference
/grok-review chat "Sketch three visual treatments for a cover-letter header banner that matches the richardzak.com brand. Each treatment: one sentence on palette, one on imagery, one on typography." images="public/og-default.png"

# 4. Generate a 10-second clip for a LinkedIn outreach post
/grok-review video "Slow-zoom on a code editor showing an MCP tool definition resolving to a green check; subtle particle field; ends on a clean wordmark slot." duration=10 aspect_ratio=16:9
```

## Direct Tool Calls

```text
mcp__grok-review__grok_generate_image(
    prompt="...",
    n=2,
    output_dir="docs/grok-output",
    model="grok-imagine-image"
)

mcp__grok-review__grok_analyze_image(
    image_paths=["output/resumes/agentic_ai/preview-page1.png"],
    prompt="Flag any layout issues, text-wrap anomalies, or typography inconsistencies on this resume page.",
    model="grok-4.3"
)

mcp__grok-review__grok_multimodal_chat(
    prompt="Combine these moodboards into a single visual brief for the case-study cover.",
    image_paths=["public/og-default.png"],
    system="You are a senior brand designer for an executive engineering portfolio (richardzak.com). Restrained, technical, credible. Dark navy + one accent.",
    model="grok-4.3"
)

mcp__grok-review__grok_generate_video(
    concept="...",
    reference_image_paths=["public/og-default.png"],
    duration_seconds=5,
    aspect_ratio="16:9",
    output_dir="docs/grok-output",
    model="grok-imagine-video"
)
```

## Workflow — Iterate, Save, Promote

1. **Generate or analyze** with the appropriate action.
2. **Inspect the output** in `docs/grok-output/`. Re-prompt with revised
   wording until the asset matches intent.
3. **Promote** the chosen file into its production location:
   - Case-study / blog cover graphics → `public/covers/<slug>.png`
   - Open-Graph / Twitter-Card images → `public/og/<route>.png`
   - Add or update the `<img alt="...">` text wherever the asset is
     referenced in the MDX / Astro component
4. **Refresh derived assets** if the source changes: regenerate the
   sitemap and Open-Graph routes via the website build (`npm run build`
   in rz-website).

## Configuration

The MCP server reads its configuration in this priority order:

1. **System environment** — your shell PATH / OS environment.
2. **Project `.env`** — auto-loaded via `python-dotenv`.

Variables (all optional except `XAI_API_KEY`):

| Variable            | Default               | Purpose                                       |
| ------------------- | --------------------- | --------------------------------------------- |
| `XAI_API_KEY`       | _(required)_          | Bearer token for `api.x.ai`                   |
| `XAI_BASE_URL`      | `https://api.x.ai/v1` | Override for proxies / regional endpoints     |
| `GROK_TEXT_MODEL`   | `grok-4.3`            | Default text-only model                       |
| `GROK_VISION_MODEL` | `grok-4.3`            | Default vision model (analyze / chat actions) |
| `GROK_IMAGE_MODEL`  | `grok-imagine-image`  | Default text-to-image model                   |
| `GROK_VIDEO_MODEL`  | `grok-imagine-video`  | Default video generation model                |
| `GROK_IMAGE_PATH`   | `/images/generations` | Path appended to `XAI_BASE_URL` for image gen |
| `GROK_VIDEO_PATH`   | `/videos/generations` | Path appended to `XAI_BASE_URL` for video     |
| `GROK_OUTPUT_DIR`   | `docs/grok-output`    | Where saved PNGs / MP4s land (gitignored)     |

See `.env.example` for the template block.

## Output Contract

- **Image generation** — PNGs saved to `output_dir`, named
  `<timestamp>-<prompt-slug>-<n>.png`. Tool returns a summary line
  (`N saved, M error(s) out of K returned`) followed by saved paths,
  per-item errors, and any provider-revised prompts.
- **Vision analysis / chat** — Tool returns the model's text response
  verbatim. If the provider returns `content: null` (e.g. tool-call-only
  response), you'll get an `[empty response — provider returned content:
null]` placeholder rather than the literal string `"None"`.
- **Video generation** — MP4s saved to `output_dir`, named
  `<timestamp>-<concept-slug>-<n>.mp4`. Same `N saved, M error(s)`
  summary as image generation. If your account / endpoint doesn't yet
  support video, the tool returns a clean error (HTTP 404 or empty
  payload).

## Path Containment (Security)

Every file path passed to `grok_analyze_image`, `grok_multimodal_chat`,
or `grok_generate_video` must resolve to a file inside the project root.
Absolute paths outside the repository (e.g. `C:\Users\...`,
`~/.ssh/id_rsa`) are rejected with `ERROR: path must be inside the
project root`. This prevents accidental exfiltration of host files to
xAI when chained from another tool's output.

Prompts and concepts are capped at 8000 characters; longer inputs are
rejected up front rather than silently truncated by the provider.

## Error Handling

The server returns plain-text strings starting with `ERROR:` on failure
(missing key, rate limit, HTTP error, decode failure, missing input
file). It never raises through the MCP boundary, matching the repo's
exception-handling standard for tooling.

## Related Commands

- `/mcp` — OpenAI file review (code / data / docs review)
- `/quality-file <file>` — local fast quality check on a single file
- `/quality` — Full project quality gate
