# Design ingestion — find the source, detect the tier, extract tokens

This step answers *where the design is and how to read it*, and extracts the **token set** (for theming) and the **screen list** (for planning). It deliberately does NOT produce the per-screen layout — that is the job of `shesha-design-comprehension` (Step 2), which measures placement. Keep the two separate: ingestion normalises and inventories; comprehension measures.

## Source types & how to read each

- **Readable source** (un-minified HTML/JSX/CSS, a component kit): read the token file (CSS variables / a `tokens.*`/`colors_and_type.css`) and the screen components. This is the richest source for both tokens and (later) Tier-A comprehension.
- **Runnable prototype / app** (incl. an offline single-file bundle): **serve it over HTTP** (`python -m http.server`) and open it in the browser — a `file://` bundle is blocked and a minified bundle can't be parsed statically. Navigate the screens; capture one screenshot each for the inventory.
- **Figma / screenshot set / PDF**: read the images; for mixed docs use markitdown to get a content/label outline. Ask the user for token values you can't sample.

## What to extract here

1. **Token set** → hand to `shesha-design-system` as a theme file: palette (brand/accent/surfaces/lines/ink/semantic/badge), type (family/scale/weights/line-heights), spacing/radius/shadow, and the **status lifecycle** (the ordered status set + colours).
2. **Screen inventory** — per screen: a name, its type (dashboard/list/detail/create-edit/dialog), the entity it concerns, and any chrome notes (rail/header/record-bar). Just enough to *plan* and to drive comprehension — not the column-level layout.

## markitdown's role here (content only)

markitdown (`mcp__markitdown__convert_to_markdown`) normalises mixed inputs (a PDF/`.docx`/`.pptx` spec, a domain-model `.md`) into a clean content/label/section outline used to name screens and fields. It **flattens layout** — never read its output as placement. Spatial layout is measured later by `shesha-design-comprehension`.

## Output of this step

- A token set persisted as a `shesha-design-system` theme file (`assets/themes/<brand>.tokens.json`).
- A screen inventory (names + types + entities) written to **`$RUN_DIR/screen-inventory.json`** and used by Step 3 planning. Persist it rather than carrying it in context: it is the input to the per-screen fan-out, and a run that loses it has to re-ingest the whole design.
- **For the layout blueprint that drives placement, REQUIRED: `shesha-developer-0-46:shesha-design-comprehension`** — run it per screen (Step 2) on the same source.
