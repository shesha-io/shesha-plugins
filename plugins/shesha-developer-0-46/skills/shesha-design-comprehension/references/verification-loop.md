# Verification loop — does the built form match the blueprint?

The mechanism that turns "it renders" into "it's placed where the design put it". The blueprint's `assertions` become a measured pass/fail gate on the built Shesha form, and failures become concrete fixes routed back to `shesha-form-edit`.

Runs as **gate 5a.5** in `shesha-claude-designer` — after structural integrity (5a), before styling (5b). It can also be invoked standalone to diagnose an existing form ("why doesn't this match the design?").

## Procedure (0.46)

1. **Build + save** the form via `shesha-form-edit`. 0.46 has no Draft -> Ready -> Live lifecycle: a saved form is live immediately and revisions are automatic (see `shesha-form-edit` for the write path). Do not wait for a "publish".
2. **Make sure you are measuring the new markup.** The browser keeps a per-item cache keyed by the item's `cacheMd5`, which changes when the markup changes, so a normal reload normally picks up the new form. If a result looks like the previous build, hard-refresh; if it still does, clear the `form` / `form_lookup` IndexedDB stores from a static page (`/favicon.ico`, not in-app — an in-app `deleteDatabase` silently blocks). Do this *before* concluding "the edit had no effect".
3. **Navigate the real path.** Open the form via **table-row -> details**, never a pasted `?id=` (a direct id load can 500 the subtable Crud/Create). Pin the **same viewport** used for capture (1440x900). Wait until the screen has settled (no spinners, no "Loading..." tags) before probing — do not diagnose a sub-form's data context from first paint or a hot-reload capture.
4. **Re-probe.** Run the *same* `scripts/layout-probe.js` against the rendered Shesha form into `$RUN_DIR/probes/<screen>.built-r<n>.layout.json`. Same instrument as capture = comparable numbers. Use `--sha-only` for built forms to keep the file small.
5. **Diff actual vs the blueprint `assertions`** — structurally, not by pixels (next sections).
6. **Route mismatches back to `shesha-form-edit`** as concrete fixes; rebuild -> re-probe -> re-diff until every assertion passes. Cap: 2 cycles, then an honest partial report.

## What to diff (and why it survives the pixel-vs-width-expression gap)

Assert on properties that are stable across the design's pixel grid and Shesha's flex-container widths:

| Dimension | How to measure from the probe | Example assertion |
|---|---|---|
| **Split-cell membership** | `shaSplits[].cells[].colIndex` of the component with that `name` | "both related panels (`relatedPanelUC`, `relatedPanelApi`) are in the RIGHT cell of `bodySplit`" |
| **Row grouping** | components sharing a `rowBand` under one parent | "Details rows are 2-cell, label and control on one row" |
| **Nesting depth / parent** | `components[].parentShaId` chain | "panels are children of `railColumn`, not the page root" |
| **Tab assignment** | `tabPanes[]` entry `label` -> `componentNames`, or `components[].tab.label` | "`endpointsTable` is under the 'Endpoints' tab" |
| **Split ratio (range)** | cell widths from `shaSplits`, with tolerance | "left >= 2.5x right; rail ~ 332px +/- 40" |
| **Rendered, not placeholder** | `placeholders[]` is empty | "no `.ant-empty` placeholder, no 'not registered' renderer" |
| **Mounted** | every asserted `name` is present in `components[]` | "`kibStrip` exists" (a `hidden` component is absent by design on 0.46) |

**Never** assert absolute pixels or exact width expressions — a `minmax(0,1fr) 332px` design grid is *satisfied* by a flex-row split whose main cell fills the row and whose rail cell is a fixed `width:"332px"` (the ratio, not the exact expression, is what matters). Fail only on **wrong cell / wrong parent / wrong tab / ratio out of range / placeholder present**.

## 0.46-specific checks to add to every run

- **Double-applied calc width.** For each split cell whose width is a `calc(...)`, compare `components[].rect.w` (wrapper) with `innerRect.w` (the container inside it). `doubleShrinkSuspect: true` means the width was applied twice. Fix by switching the filling cell to `width:"100%"` + `minWidth:"0px"` beside a fixed-px rail, then re-probe.
- **Migration-injected defaults.** Compare measured values against what the stored markup intended: container `minHeight` 32px, columns `marginBottom` 5, datatable zebra/header fill/row padding, tabs v4 white background + 1px `#f0f0f0` border + radius 8 + padding 16. A placement assertion that fails by a few pixels of height or inset is usually one of these, not a structure fault — route to `shesha-design-system` ("restoring the pre-0.46 look") rather than to `shesha-form-edit`.
- **Placeholders.** `placeholders[]` entries of kind `empty` on an `htmlRender` mean its output was sanitised to nothing (a `<style>`-only renderer); route to `shesha-design-system` (`sanitize:false`, mount it).
- **Tabs.** On antd 6 a tabs style result surfaces as a class on `.ant-tabs-content`; chevron or custom tab CSS must use `.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content` selectors, or `data-sha-c-name` anchors.

## Routed-fix vocabulary (speak `shesha-form-edit`'s language)

A failing assertion becomes an instruction phrased in the builder's terms, e.g.:

> **A2 FAIL** — `relatedPanelApi` measured in cell 0 of `bodySplit` (x~40) but the blueprint asserts the RIGHT rail (cell 1). *Fix:* move that panel's node into the right flex `container` cell; ensure the body row carries `display:"flex"` + `flexDirection:"row"` + `gap`, the main cell has `desktop.dimensions.width:"100%"` + `minWidth:"0px"` and the rail cell has its own `desktop.dimensions.width:"332px"` (+ min/max) — a cell with no width set grows/shrinks freely and can collapse to the left.

> **A4 FAIL** — `Details` rows measured one component per rowBand but the blueprint asserts 2-cell rows. *Fix:* wrap each label+control into a 2-cell flex row — a `container` with `display:"flex"` + `flexDirection:"row"` + `gap` whose two child `container`s each carry a `desktop.dimensions.width` — or use the detail-attributes recipe's label/value row.

Keep each fix to: the failing assertion id, the measured fact (with numbers), the asserted fact, and the structural change in `shesha-form-edit` terms.

## RED -> GREEN (how this skill is validated)

- **RED:** build the pilot from a *prose* brief only (no blueprint) -> probe -> record >=1 failing assertion with numbers (e.g. panels collapse into one column; KIB flattens).
- **GREEN:** build the same screen from the blueprint -> probe -> iterate routed fixes until the *same* assertions all pass.

The RED -> GREEN delta on identical assertions is the proof the layer fixes drift rather than re-describing it.

## Failure modes

- **Stale cache** -> you measure the previous build. Hard-refresh / clear the stores from `/favicon.ico` before concluding anything.
- **Direct `?id=` load** -> 500s on subtables, or renders a partial form. Always navigate table -> details.
- **Different viewport** between capture and verification -> incomparable numbers. Pin one.
- **Responsive collapse** at the test viewport -> if the design is genuinely responsive, capture+verify at the breakpoint the design targets, and say so in the blueprint.
- **Selecting by antd 5 classes** -> empty results on antd 6. Use `data-sha-c-*` / `role="tabpanel"`.
- **Probing a hidden component** -> not mounted on 0.46; "missing" is the correct result.
- **Dispatching a DOM `MouseEvent` to trigger antd `onChange`** -> does nothing; use a real click.
