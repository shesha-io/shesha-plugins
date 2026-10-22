# Capture pipeline — design source → measured layout

Detect the fidelity tier, run the matching extractor, then narrate its output into the [blueprint IR](blueprint-ir.md). The extractor carries *placement*; markitdown only ever carries *content*.

## Detect the fidelity tier

| Tier | You have | Placement signal | Confidence |
|---|---|---|---|
| **A** | Readable source — un-minified HTML/JSX/CSS, a component kit | Parse grid templates / flex props directly (gold) | high |
| **B** | A runnable prototype/app (even an offline single-file bundle) | Render it, probe the DOM (`layout-probe.js`) | high |
| **C** | Screenshots / PDF / images only | Vision-read the image; markitdown for content | low–medium |

A design often offers several tiers (e.g. a runnable bundle **and** a source zip). Prefer A for structure, use B to confirm by measurement, fall to C only when nothing else exists.

## Tier A — readable source

The placement is explicit in the source; read it, don't infer it.

- **Grid templates** are the gold signal: `gridTemplateColumns: 'minmax(0,1fr) 332px'` → a 2-cell split, second fixed 332px; arrays like `['40px','56px','150px','1fr','150px','150px','40px']` → a 7-cell row with those native widths. Copy these straight into `layout-tree` `row=[…]` as native units (px / `fill` / `1fr`) — each cell maps to a flex-container child sized via `desktop.dimensions.width`. Do NOT normalise to a 24-unit grid or use the Shesha `columns` component.
- **flex props** (`flex:1`, `display:'grid'`, `flexDirection`) → row vs column, fill behaviour.
- **component shapes** (`<Card title icon>` + `<CountBadge>`; `EditableText`/paste handlers) → which archetype (related-panel rail, capture table).
- **bindings** from props (`view.realisesUseCases`, `view.requiredApis`).
- **markitdown role (A):** convert any mixed spec docs alongside the source — a domain-model `.md`, a requirements `.docx`/`.pdf` — into a content/label outline used to *name* fields and cross-check the bindings table. It does not read layout here; the source does.

## Tier B — runnable prototype (the offline RS app is Tier B)

Render each screen and measure the rendered DOM.

1. **Serve & open.** A `file://` bundle is blocked in most browser tools and a minified single-file bundle can't be parsed statically — serve the folder over HTTP (`python -m http.server <port>`) and navigate to it with whichever browser tool the session has (Chrome extension, Playwright MCP). Pin the viewport first (1440×900).
2. **Navigate** to each screen (hash routes like `#/views`, then click a row into the detail).
3. **Probe.** `node scripts/layout-probe.js --emit-eval --screen <name>` prints the in-page expression; evaluate it with the browser tool's JS evaluator and save the result to `$RUN_DIR/probes/<screen>.design.layout.json` so it is a file, not context. (A design prototype is not a Shesha form, so it has no `data-sha-c-*` attributes — the generic layer carries the signal.)
4. **Read the signal.** The probe's `multiColumnContainers` array gives, per container: `columnCount`, `columnEdges`, `childWidths`. Record widths in native units (px / `fill` / `1fr`) for `row=[…]` — do NOT normalise to `/24`. One screenshot per screen (`browser_take_screenshot`) for a visual cross-check — never one per element.
5. **markitdown role (B):** optionally caption that single screenshot for a prose content/section outline that labels the measured boxes — secondary to the measurement.

Worked numbers from a pilot (grant-application view-detail screen): the probe returned `cols=2 widths=[962,332]` for the body (→ `row=[fill, 332px]`: left fills `calc(100% - 356px)`, rail fixed 332px) and `cols=6` for the KIB — see [blueprint-ir.md](blueprint-ir.md) for how those become the blueprint.

## Tier C — screenshots / PDF only (lowest fidelity)

1. **markitdown role (C — largest, still content):** `convert_to_markdown` on the PDF/image → a Markdown content outline (headings, lists, tables, labels). This is the field/section inventory.
2. **Vision-read the image for spatial layout** the outline can't carry: which fields share a row, the left/right split, where panels sit, tab strips. Record column counts from what you see.
3. Stamp the blueprint **Confidence: low** and lean hard on the verification loop — the re-probe of the *built* form is the safety net that catches what vision misread.

## markitdown invocation (reference)

- MCP: `mcp__markitdown__convert_to_markdown { uri: "file:///abs/path" | "http://…" | "data:…" }`.
- It flattens 2-D layout (strips CSS/classes/grid/positioning). Never read its output as placement — only as content/labels/section order. This boundary is the whole reason the probe exists.

## Output of this stage

Per screen: a saved `*.layout.json` (Tier B) and/or parsed source notes (Tier A) and/or a content outline (Tier C) — plus the screenshot. These feed directly into authoring `<screen>.blueprint.md`.
