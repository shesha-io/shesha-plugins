---
name: shesha-design-comprehension
description: Use when a Shesha form must match a specific visual design and container/component placement keeps drifting — columns, nesting, tabs, or grouping landing in the wrong place. Also use to diagnose why an already-built form doesn't match its design. Turns a design source (readable HTML/JSX, a runnable prototype, or screenshots/PDF) into a measured, annotated layout blueprint — or, when there is no design source, derives the same blueprint from the screen's archetype and the resolved brand tokens (Tier D) — and verifies a built Shesha form against it by measurement. Invoked by shesha-claude-designer once per screen; pairs with shesha-form-edit (structure) and shesha-design-system (style).
---

# Shesha Design Comprehension

## Overview

**Core principle: placement is measured, not guessed.** When a form is built from a *prose* description of a design ("a header, then a two-column body, then related panels"), the builder has to re-imagine where every container sits — so columns, nesting depth, tab assignment and grouping drift. This skill removes the guessing: it produces a **layout blueprint** — a hybrid-Markdown intermediate representation that carries the *exact* container tree, flex-row split-child counts, native widths, tab keys and field bindings — and then **verifies the built Shesha form against that blueprint by re-measuring the rendered DOM**. The blueprint is a placement *contract*, and the verification loop enforces it.

This is the layer between "I have a design" and "build the form". It does **not** author form JSON, pick colours, or push — it tells the builder *exactly what to build where*, and checks that it did.

## When to use

- Before building a Shesha form/page from any concrete design (the design source can be readable HTML/JSX source, a runnable prototype/app, or just screenshots/a PDF).
- When a built form "doesn't line up with the design" — wrong columns, panels in the wrong place, a rail that collapsed, tabs merged, fields stacked that should be side-by-side.
- Whenever `shesha-claude-designer` is realising a multi-screen build — it calls this skill once per screen to produce blueprints before delegating the build. **This includes runs with no design source**, where the blueprint is derived from the screen's archetype and the brand tokens (**Tier D**, see [blueprint-ir.md](references/blueprint-ir.md)) rather than measured. The blueprint is worth writing either way: it is the specification the builder works from and the contract the verification loop re-measures, and with no design to compare against, structural drift is *harder* to spot, not easier.

**Do NOT use** to author component structure/CRUD (that is `shesha-form-edit`), to apply colours/theme (that is `shesha-design-system`), or for a **single** form with no design intent at all ("add a sector dropdown") — that goes straight to `shesha-form-edit`.

## The three things this skill produces

1. A **layout blueprint** per screen — `$RUN_DIR/blueprints/<screen>.blueprint.md`. Format spec + worked example: [references/blueprint-ir.md](references/blueprint-ir.md).
2. A **capture** of the design's real layout — via one of three fidelity tiers (source / runnable / screenshot). How, and where markitdown fits: [references/capture-pipeline.md](references/capture-pipeline.md).
3. A **placement verification** of the built form against the blueprint. Method + the routed-fix loop: [references/verification-loop.md](references/verification-loop.md).

## The pipeline (what to do)

```dot
digraph { rankdir=LR;
  ingest [label="detect\nfidelity tier"];
  capture [label="capture layout\n(probe / source / vision)"];
  blueprint [label="write\nblueprint.md"];
  build [label="shesha-form-edit\nbuilds from blueprint"];
  verify [label="re-probe built form\ndiff vs assertions"];
  ingest -> capture -> blueprint -> build -> verify;
  verify -> build [label="mismatch →\nrouted fix"];
}
```

1. **Detect the fidelity tier** of the design source — readable source (A, best), runnable app (B), screenshots/PDF only (C). [capture-pipeline.md](references/capture-pipeline.md).
2. **Capture the layout.** For a runnable design or any rendered page, use the measurement instrument [scripts/layout-probe.js](scripts/layout-probe.js): it walks the DOM at a **pinned viewport** and emits column counts, spans, nesting and row grouping per container. On a built Shesha 0.46 form it anchors on the `data-sha-c-id / -name / -type / -property-name` attributes every live component wrapper carries (`shaSplits`, `tabPanes`, `components`), not on antd class names. For readable source, parse the grid templates directly. For screenshots/PDF, normalise content with markitdown and read spatial layout from the image.
3. **Write the blueprint** — narrate the captured signal into [blueprint-ir.md](references/blueprint-ir.md) format: a human-reviewable Markdown doc with three fenced machine blocks per region — `layout-tree`, `bindings`, `assertions`.
4. **Hand the blueprint to `shesha-form-edit`** as the build's requirements (archetype + seed selection + column spans + per-field binding). **REQUIRED PARTNER:** `shesha-developer-0-46:shesha-form-edit` builds the structure.
5. **Verify by measurement.** Re-probe the built (saved — 0.46 has no Draft/Live publish step), table→details-navigated Shesha form; diff actual placement against the blueprint's `assertions`; route concrete mismatches back to `shesha-form-edit`. [verification-loop.md](references/verification-loop.md).

## How markitdown fits (one layer, not the engine)

markitdown (MCP `convert_to_markdown`, or the CLI) **flattens 2-D layout by design** — it strips CSS, classes, grid columns and positioning, turning a two-column row into two sequential lines. So it is **never** the source of placement. Its real jobs: (a) **source-normalisation** — convert mixed design inputs (a PDF spec, a `.docx`, a domain-model `.md`, a `.pptx`) into a clean content/label/section outline used to *name* fields and cross-check bindings; (b) **screenshot caption** — a prose content outline of an image. Spatial intent always comes from the probe (B), the parsed source grid templates (A), or vision-reading the image (C). Treating markitdown as the layout engine reproduces the exact flattening bug this skill exists to fix.

## Quick reference — the layout probe

| Use | Command |
|---|---|
| Print the in-page payload | `node scripts/layout-probe.js --emit-eval --screen <name> [--sha-only]`, then evaluate the printed expression with any in-page JS tool (Chrome extension `javascript_tool`, Playwright MCP `browser_evaluate`, DevTools) and save the returned JSON under `$RUN_DIR/probes/` |
| Run locally (CI / playwright installed) | `node scripts/layout-probe.js --url <url> --screen <name> --out <file>.json [--sha-only]` |
| Read the signal (built Shesha form) | `shaSplits[]` = split-cell membership per parent (cells with `colIndex`, `x`, `w`); `tabPanes[]` = which sha components sit in which tab (works for inactive tabs); `components[]` = every wrapper with `parentShaId`, `tab`, `layout`, and `doubleShrinkSuspect`; `placeholders[]` = Empty / not-registered renderers |
| Read the signal (design prototype, not Shesha) | `multiColumnContainers[]` (+ `childWidths`) = split-child count + widths per container; record widths in native units (px/fr/%) |

Pin **one** viewport (default 1440x900) for *both* capture and verification. Probe output is structural — assert on split-child **membership / grouping / nesting depth / tab label**, never absolute pixels. Address components in assertions by their **`data-sha-c-name`** (the component's `componentName`), which is stable across rebuilds, not by DOM position or antd classes.

### Selectors that survive antd 6 (0.46)

| Need | Use | Do not use (antd 5 / 0.45) |
|---|---|---|
| A specific Shesha component | `[data-sha-c-name="x"]`, `[data-sha-c-type="tabs"]`, `[data-sha-c-property-name="p"]` | hashed `css-xxxx` classes, DOM index paths |
| Tab panel | `[role="tabpanel"]` (label via `aria-labelledby`) | `.ant-tabs-tabpane` |
| Tab body wrappers (only if you must) | `.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content` | `.ant-tabs-content-holder > .ant-tabs-content > .ant-tabs-tabpane` |
| Tab nav | `.ant-tabs-nav`, `.ant-tabs-tab`, `.ant-tabs-tab-active` (unchanged) | — |
| Collapse body / title | `.ant-collapse-body`, `.ant-collapse-title` | `.ant-collapse-content-box`, `.ant-collapse-header-text` |
| Modal body | `.ant-modal-body` (unchanged); container is `.ant-modal-container` | `.ant-modal-content` as the surface |
| Form item parts | `.ant-form-item-label`, `-control`, `-control-input` (unchanged) | — |
| Container box vs padding box | outer `.sha-components-container` (dimensions, border, background, shadow, margin); inner `.sha-components-container-inner` (padding, display, gap, overflow) | assuming the outer div only carries dimensions |

Source: antd 6.6.4 / @rc-component/tabs 1.13.0 / @rc-component/collapse 1.2.0 in the 0.46 starter's `node_modules`, and `knownFormComponent.tsx` (the wrapper attributes) in release-0.46.0.

## Non-negotiables

- **Measure, don't guess.** Every split-child count / span in a blueprint must come from a probe measurement, a parsed source grid template, or (Tier C only) explicit vision reading — never from prose intuition. Stamp the blueprint with its fidelity tier and confidence.
- **The blueprint is a contract.** Whatever the `assertions` block states MUST be re-verified after the build. A blueprint without verification is just a prettier prose brief.
- **Express splits as flex-container children — NEVER the Shesha `columns` component.** A split is built as a `container` with `display:"flex"` + `flexDirection:"row"` + a `gap` (every flex container MUST set `display:"flex"` or `flexDirection`/`gap` are inert and children stack full-width). Record spans in **native units (px/fr/%)** and map each split child to that child container's **`desktop.dimensions.width`** — the lever that reaches the child's outer `div.sha-component` wrapper. A fixed rail = `width:"332px"` with matching `minWidth`/`maxWidth` (an exact px width: the wrapper becomes `fit-content` and the container takes the px, so it cannot double-apply). **A filling main column: prefer `width:"100%"` + `minWidth:"0px"` next to a fixed rail on 0.46**; a `calc(100% - <rail+gap>px)` width is non-exact, so the 0.46 source applies it to BOTH the wrapper and the container inside it (`getFullSizeWrapperDimensions` / `getFullSizeComponentDimensions` in `stylingUtils.ts`), which can narrow the column twice. If you do use `calc`, the probe's `doubleShrinkSuspect` flag and a wrapper-vs-inner width comparison must come back clean. Per-child `customStyle:{flex:…}` is **INERT** for outer sizing — do NOT express spans as `customStyle flex`, and never as a `columns` component. The diff asserts cluster membership / grouping / nesting depth / tab label — never pixels.
- **Stay in your lane.** Produce blueprints + verification verdicts. Never author form JSON, never set colours, never push — route those to `shesha-form-edit` and `shesha-design-system`.
- **One viewport.** Never compare measurements taken at different viewports; record the viewport in every capture.

## Common mistakes

- **Reading markitdown output as layout.** It is reading-order, not placement. Use it for content/labels only.
- **Selecting by antd 5 class names.** `.ant-tabs-tabpane` / `.ant-tabs-content-holder` / `.ant-collapse-content-box` match nothing on antd 6; anchor on `data-sha-c-*` and `role="tabpanel"`.
- **Reading a hidden component as 'rendered but invisible'.** 0.46 does not mount `hidden`/`visible:false` components at all (`configurableFormItemLive.tsx`), so an absent wrapper in the probe is expected for those, and a hidden `htmlRender` style carrier never injects CSS.
- **Parsing the compiled/offline single-file bundle.** A minified app bundle yields gibberish — *run* it (Tier B) and probe the rendered DOM, or read the un-minified source (Tier A).
- **Asserting pixels.** Responsive reflow and the pixel↔`calc()`/% width mapping make pixel asserts brittle. Assert membership/grouping/depth/tab.
- **Skipping the re-probe.** If you don't measure the built form, you haven't verified placement — you've only re-described it.

## Relationship to the other skills

| Concern | Skill |
|---|---|
| Ingest design, plan screens, orchestrate, verify end-to-end | `shesha-developer-0-46:shesha-claude-designer` (calls this skill per screen) |
| **Comprehend a design → measured layout blueprint + placement verification** | **this skill** |
| Build correct structure, CRUD, validate, push | `shesha-developer-0-46:shesha-form-edit` |
| Map tokens → app theme + per-component v7 style blocks | `shesha-developer-0-46:shesha-design-system` |
