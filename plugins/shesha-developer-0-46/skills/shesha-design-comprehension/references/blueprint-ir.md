# Layout blueprint IR

The intermediate representation that carries a screen's placement from design to build. One file per screen: `$RUN_DIR/blueprints/<screen>.blueprint.md`.

## Why hybrid Markdown (not pure JSON/YAML)

The blueprint has two audiences. A **human** reviews and approves placement at the planning gate — they read Markdown, not a 24-deep JSON tree. A **builder** (`shesha-form-edit`) consumes it as a requirements brief — archetype + layout spec + bindings is exactly the input it already takes. So the doc is human-readable Markdown **headings/prose**, with the machine-precise parts isolated in **three fenced code blocks per region**:

- ` ```layout-tree ` — the container tree: regions → sections → flex-row splits → split children → fields, with explicit child counts and per-child native widths.
- ` ```bindings ` — a table mapping each label to its entity property, component type and datatype.
- ` ```assertions ` — the placement contract: the statements the verification loop re-measures against.

Pure JSON would be unreviewable; pure prose is the thing that drifts. The fenced blocks recover everything the machine needs without making the whole doc machine-only.

## Document structure

```
# Blueprint — <screen-slug>
Screen identity:  <human name + where it lives>
Entity (modelType, resolve live):  <Entity>   ·   Form identity:  <module> / <form-name>
Archetype:  <one of the 8 — see below>  [+ variant note]
Fidelity tier:  A | B | C        Confidence:  high | medium | low
Viewport captured:  <w>x<h>      Source:  <probe file / source path / screenshot>

## Region N — <name>  (recipe: <design-system recipe>)
```layout-tree …``` 
(prose notes about this region if helpful)

## Bindings
```bindings …```

## Assertions  (placement contract — verified by verification-loop.md)
```assertions …```
```

## The eight archetypes (target vocabulary)

The blueprint's `Archetype` must be one of the eight canonical shapes, so the conductor picks the right builder and the builder picks the right seed:
`record-detail` · `hub` · `list-card` · `capture` · `dashboard` · `solution-map` · `wizard` · `inline-card`.

**Which builder each archetype routes to** (set in `shesha-claude-designer` SKILL.md Step 4a — walk the STRICT preference order):

| # | Archetype / variant | Builder | Source of components |
|---|---|---|---|
| 1 | `list-card` (table) | **`create-crud-form`** | `sample-patient-table.json` |
| 1 | `list-card` (datalist of cards) | **`create-crud-form`** | `sample-appointment-list.json` + `sample-appointment-list-subform.json` (PAIR) |
| 1 | `capture` (in-modal create) | **`create-crud-form`** | `sample-patient-create.json` |
| 1 | `record-detail` | **`create-crud-form`** | `sample-patient-details.json` |
| 1 | `inline-card` (row-template mini-card) | **`create-crud-form`** | `sample-patient-subform.json` |
| 2 | `dashboard` · `hub` · `wizard` · `solution-map` (Shesha-form-designer-expressible with EXISTING components) | **`shesha-form-edit`** | blocks + patterns (`shesha-form-edit/references/archetypes.md`) using existing form-designer toolbox |
| 3 | Any archetype — form-shaped but **MISSING a component** (a specific chart, a rating input, an image annotator, a Kanban card, a signature pad, etc.). Mark the blueprint `Archetype: <shape> — form-config with new component <componentName>` | **`create-custom-component`** THEN **`shesha-form-edit`** | new designer component in a package (enterprise / reporting / workflow), then a form-config that uses it — **stays on the form-configuration road** |
| 4 (LAST RESORT) | Any archetype — **`custom-page` variant** with a named uncoverable capability (drag-and-drop UIs, integration consoles, marketing landing pages, bespoke data browsers with capabilities that couldn't have been a component). Mark the blueprint `Archetype: <shape> — custom-page variant · reason: <specific-capability>` | `create-custom-page` | plain React + Ant Design; scaffolds `src/screens/<name>/index.tsx` + Next.js route. **Bypasses framework guarantees — use only when the missing capability genuinely cannot be a component.** |

**Preference order — form-configs beat custom pages every time.** A Shesha form-configuration plugs into the framework's data-loader / permissions / validation / dynamic-CRUD / versioning / import-export automatically. A custom React page reimplements every one of those responsibilities by hand. When the blueprint calls for something the existing form-designer can't express, first ask: **is the gap a missing COMPONENT or a missing PARADIGM?** A missing component (a chart type, a rating input, a bespoke calendar cell) → build it via `create-custom-component`, use it inside a form-config. A missing paradigm (an entire drag-and-drop workflow, an integration console with terminal semantics, a marketing landing page with hero + copy + CTAs) → falls to `create-custom-page` and the blueprint header names the paradigm.

**Canonical CRUD ships in the canonical Shesha aesthetic — no styling overlay.** The `create-crud-form` seeds bake in a specific look (grey `#fafafa` pageShell, white cards with the canonical soft shadow, radius-4 corners, blue accents, avatar circles, pill `refListStatus` cells, specific paddings by role); every screenshot in `create-crud-form/assets/screenshots/` shows exactly what a canonical build ships. **That aesthetic IS the design**, and `shesha-design-system` is NOT invoked on these builds — no theme overlay, no visual audit, no `design-critic`. If your blueprint uses a `list-card` / `capture` / `record-detail` / `inline-card` archetype AND the user's brand is genuinely incompatible with the canonical Shesha look, treat the archetype as non-canonical for this project and route to preference 2 or 3 (form-config with brand overlay).

See [create-crud-form/SKILL.md](../../create-crud-form/SKILL.md) for the CRUD archetype table, [shesha-form-edit/references/archetypes.md](../../shesha-form-edit/references/archetypes.md) for the non-canonical Shesha-form archetypes' shape, `create-custom-component` (shesha-developer plugin, not bundled here) for how to widen the toolbox with a new component, and `create-custom-page` (shesha-developer plugin, not bundled here) for the last-resort React page scaffold.

## Fidelity tiers — including "there is no design"

| Tier | Source | Where the layout comes from |
|---|---|---|
| A | readable HTML/JSX/CSS | parsed source |
| B | runnable prototype | probed DOM (`layout-probe.js`) |
| C | screenshots / PDF | read images; content outline only, never placement |
| **D** | **none — prose brief only** | **the archetype's default shape in `archetypes.md`, plus the resolved brand tokens** |

**Tier D is a first-class path, not a degraded one.** A prose brief ("a bookings list, a create dialog, a details page") names three archetypes, and each carries a known-good structure — so the build is specified, just not *measured*. Write the blueprint exactly as for any other tier; the `layout-tree` comes from the archetype's default shape rather than from a probe.

What Tier D must be honest about:

- **Stamp `Fidelity tier: D (no design source; derived from archetype + <brand> tokens)` and `Confidence: derived`.** Never claim a tier you didn't have a source for.
- **Its `assertions` are self-consistency checks, not evidence of matching anyone's design** — there is no design to match. They still earn their place: they catch the split collapsing, the rail landing under the main column, a tab losing its children. Mark the block `assertions (derived — archetype default, not a measured design)` so nobody reads a Tier D pass as "matches the mockup".
- **`Source:` names the archetype and brand file**, e.g. `archetypes.md#record-detail + shesha.tokens.json`, so the provenance is inspectable.
- If the user later supplies a real design, re-comprehend at Tier A/B — do not retrofit measurements onto a derived blueprint.

## `layout-tree` grammar

Indentation = nesting (DOM depth). Each line: `<node-name>  <kind> [attributes]`.

- **kind**: `region | container | row | card | tabs | tab | datatable | datalist | field | text | buttonGroup | chip`. A `row` is a flex-row split — a `container` that builds with `display:"flex"` + `flexDirection:"row"` + `gap`; its children are split cells, each its own `container`.
- **`row` attributes**: `row=[a,b,…]` listing each child's native size (`1fr` / `fill` for a filling cell, `<n>px` for a fixed cell, e.g. `row=[1fr, 332px]` or `row=[fill, 332px]`), plus optionally `gap=<px>`, `align=start|center|stretch`. Each child of the row maps to a `container` sized via **`desktop.dimensions.width`**: a fixed cell → `width:"<n>px"` with matching `minWidth`/`maxWidth` (exact px: safe on 0.46); a `fill`/`1fr` cell → **`width:"100%"` + `minWidth:"0px"`** beside a fixed-px sibling (the 0.46 default). A `calc(100% - <fixed+gap>px)` fill width is also valid but is applied to both the `sha-component` wrapper and the container inside it on 0.46, so it must be proven with the probe's `doubleShrinkSuspect` check. The row container itself MUST carry `display:"flex"` (or the children stack full-width) + `flexDirection:"row"` + the `gap`.
- **component names**: give every region/cell/panel a stable camelCase `componentName` in the tree (`bodySplit`, `railColumn`, `kibStrip`); assertions and the 0.46 probe address components by `data-sha-c-name`, which is that `componentName`.
- **fixed-width cell**: write `row=[fill, 332px]` — keep the native fixed px so the builder sets a fixed rail width (`width:"332px"`, `minWidth`/`maxWidth` `"332px"`) and the diff can reason structurally.
- **field/text/chip**: append `← <Entity>.<property>` for a binding, and `(recipe: <name>)` for the design-system recipe.

## Native-width recording rules

- Measure child widths within their container (probe `multiColumnContainers[].childWidths`) and record them in **native units** (px for fixed cells, `fill`/`1fr` for the filling cell) in `row=[…]`. Do NOT normalise to a 24-unit grid and do NOT use the Shesha `columns` component.
- A **fixed-width** cell (rail, icon column, action column) is recorded as its native px and builds to a `container` with `width:"<n>px"` (+ `minWidth`/`maxWidth`). The filling sibling builds to `width:"100%"` + `minWidth:"0px"` (0.46 default; `calc(100% - <fixed+gap>px)` only if the probe shows it is not double-applied).
- A sub-pixel/handle cell (e.g. a 16px drag handle) keeps its small fixed px (`16px`) — never collapse it to 0; the builder needs a real fixed cell.

## Worked example — `view-detail` (measured, Tier A/B, 1440×900)

Grounded in the live probe of the design's *Grant Application Form* view-detail screen: body split measured `widths=[962,332]` → `row=[fill, 332px]` (left fills the row — `width:"100%"`, rail fixed at **332px**, gap 24); KIB measured 6 equal cells; header content split `[fill, 332px]`-style; requirement rows `[handle 16px / content fill]`.

````markdown
# Blueprint — view-detail
Screen identity:  View Detail — the per-View record page (Views list → row → detail)
Entity (modelType, resolve live):  ViewDefinition    ·    Form identity:  Shesha.RequirementsStudio / view-definition-details
Archetype:  record-detail — Variant B (wide capture/attributes left + count-badged related-panel rail right)
Fidelity tier:  B (runnable design, probed)    Confidence:  high
Viewport captured:  1440x900    Source:  probes/view-detail.design.layout.json

## Region 1 — Header band  (recipe: page-title-band)
```layout-tree
region: header-band            container col
  ├─ breadcrumb                text  "Project / Module / Views / {name}"        (recipe: breadcrumb)
  ├─ title-row                 row  row=[fill, auto] gap=16 align=center   (flex: display:flex+flexDirection:row)
  │   ├─ title-block (cell 1)  container col   width:"100%" minWidth:"0px" (fill)
  │   │   ├─ title             text  ← ViewDefinition.name                       (recipe: page-title)
  │   │   ├─ status-chip       chip  ← ViewDefinition.status                     (recipe: status-chip)
  │   │   └─ subtitle          text  ← ViewDefinition.description                (recipe: subtitle)
  │   └─ actions (cell 2)      buttonGroup  [Mockup | Trace]   (fixed/auto-width cell, right-aligned)  (recipe: ghost-link-actions)
```

## Region 2 — Key Info Bar (KIB)  (recipe: kib-strip)
```layout-tree
region: kib                    row  row=[1fr,1fr,1fr,1fr,1fr,1fr]  native=6-equal  gap=<g> align=stretch   (flex: display:flex+flexDirection:row; each cell width≈"calc((100% - 5*<g>px)/6)" — equal-N cells need calc or a % per cell; verify with the probe)
  ├─ Module                    field  micro-label + value ← ViewDefinition.module
  ├─ Release                   field  ← ViewDefinition.release
  ├─ View Type                 field  ← ViewDefinition.viewType
  ├─ Central Entity            field  ← ViewDefinition.centralEntity
  ├─ Mockup                    field  ← ViewDefinition.mockupStatus
  └─ Completeness              field  progress + % ← ViewDefinition.completeness
```

## Region 3 — Body  (the split that drifts — measured 962/332)
```layout-tree
region: body                   row  row=[fill, 332px] native=[1fr,332px] gap=24 align=start   (flex: display:flex+flexDirection:row+gap:24)
  ├─ LEFT (fill) ─ capture   container col   width:"100%" minWidth:"0px"   (rail is a fixed 332px sibling; gap 24)
  │   └─ requirements-card     card  (header: "View Requirements" + count-badge ← count; filter; Cards/Notepad toggle)
  │       └─ req-list          datalist  ← ViewDefinition.requirements         (capture rows)
  │            row: [handle 16px | seq | category-chip | status-chip | description | refs(UC,endpoint) | delete]
  └─ RIGHT (fixed 332px) ─ rail   container col   width:"332px" minWidth/maxWidth:"332px", gap=16
      ├─ details-card          card "Details"  → rows (label-left / control-right)
      │     fields ← status, viewType, sequence, module, release, centralEntity, mockupStatus
      ├─ panel: Realises Use Cases   card + count-badge + "+"  → datalist ← ViewDefinition.realisesUseCases
      └─ panel: Required End-points  card + count-badge + "+"  → datalist ← ViewDefinition.requiredEndpoints
```

## Bindings
```bindings
label              | entity property        | component              | datatype
View name          | name                   | text (name-mode)       | string
Status             | status                 | refListStatus / chip   | refList
View type          | viewType               | dropdown               | refList
Sequence           | sequence               | numberField            | int
Module             | module                 | entityAutocomplete     | FK → ModuleDefinition
Release            | release                | entityAutocomplete     | FK → ReleaseDefinition
Central Entity     | centralEntity          | entityAutocomplete     | FK → EntityDefinition
Mockup             | mockupStatus           | dropdown               | refList
Requirements       | requirements           | datalist (capture)     | child → ViewRequirement
Realises UseCases  | realisesUseCases       | datalist panel         | M:M → UseCase  (count badge)
Required End-points| requiredEndpoints      | datalist panel         | M:M → ApiDefinition
```

> **Component-column rules the builder must honor (not just placement):** a `datalist panel` / `datalist (capture)` builds a **`datalist` row-template** — NEVER a `datatable` (a related collection drawn as a grid is a defect even though the data is collection-shaped). A rail attribute control (`dropdown` / `entityAutocomplete` rows in a read-only Details summary) is **read-only display** — author it `editMode: "readOnly"`, not `inherited` (which renders blank in the view state). A `refListStatus` is a status **chip**, not a dropdown. Row-template datalists need a fetch **projection** for their nested bindings — see `shesha-form-edit/references/components/data-tables.md` ("cards render empty" trap).

## Assertions  (placement contract — verified by verification-loop.md)
```assertions
A1  body is a 2-column split; left:right width ratio ≈ 18:6 (left ≥ 2.5× right); right rail ≈ 332px fixed
A2  the related panels (relatedPanelUC, relatedPanelApi) are BOTH in the RIGHT cell of bodySplit (same x-cluster as detailsCard), stacked vertically
A3  the requirements list/capture card is in the LEFT column (not the rail)
A4  the "Details" card rows are 2-cell (label + control side by side), not full-width stacked
A5  nesting: the related panels have railColumn as parentShaId, not the page root
A8  no placeholder (Empty / not-registered) is present; every asserted componentName is mounted
A6  the KIB is a single flex row of 6 equal cells directly under the header band
A7  header actions (Mockup, Trace) sit in the header band, right-aligned on the title row
```
````

This one document is simultaneously: the thing a reviewer signs off (prose + tree), the requirements brief the builder works from (archetype → seed `rs-detail-with-header.json`, splits → flex-row `container`s with per-child `desktop.dimensions.width`, bindings → component+propertyName), and the contract the verification loop measures (`assertions` A1–A7).

## Authoring checklist

- [ ] `Archetype` is one of the eight, with a variant note if needed.
- [ ] Every `row` line records native cell widths (`row=[…]`, `fill`/`1fr` + fixed px) and a `gap`; no Shesha `columns` component, no `/24` normalisation. Each cell maps to a `container` sized via `desktop.dimensions.width` (fill → `100%` + `minWidth:0px` beside a fixed-px sibling, fixed → `<n>px`); the row carries `display:"flex"`.
- [ ] Every bound field has `← Entity.property`; every region names its design-system `recipe`.
- [ ] `assertions` cover: split-cell membership, row grouping, nesting depth, tab assignment — the things that drift. No pixel asserts.
- [ ] Fidelity tier + confidence + viewport stamped at the top.
