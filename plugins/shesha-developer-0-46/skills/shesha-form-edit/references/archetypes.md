# Archetypes — the eight screen shapes

The shared vocabulary between `shesha-design-comprehension` (which names a screen's archetype in its blueprint), `shesha-claude-designer` (which plans `{archetype, blocks[], recipes[]}`) and this skill (which picks the seed and composes the blocks).

Two jobs:

1. **With a design source** — the archetype tells you which seed to start from; the blueprint's measured `layout-tree` overrides the seed's own body.
2. **Without a design source** — the archetype's **default shape** below *is* the layout. A prose brief ("a bookings list, a create dialog, a details page") names three archetypes, and each one carries a known-good structure, so the build is not improvised. See `shesha-claude-designer` SKILL.md Step 1b.

The default shapes are the house style, not a ceiling. A user's explicit instruction always wins.

## Choosing

| The screen is… | Archetype |
|---|---|
| one record, its attributes, and its related collections | `record-detail` |
| many records in a column grid | `list-card` (table variant) |
| many records as cards/tiles | `list-card` (card variant) |
| a form for creating or editing one record | `capture` |
| a landing page routing into other areas | `hub` |
| metrics, charts and summary tiles | `dashboard` |
| a multi-step sequence with progress | `wizard` |
| a small repeated unit rendered inside a list | `inline-card` |
| a graph/matrix of entities and their relationships | `solution-map` |

When two fit, prefer the one whose **primary action** matches the user's verb: "review a booking" → `record-detail`; "book a flight" → `capture`.

## Every page-level archetype starts with the page shell

Before the archetype's own shape: the only root component is the **page-shell card** (`assets/blocks/page-shell.block.json` — `hideHeading`, `className: "sha-page"`, no border), and the archetype's default shape goes inside its `content.components`. This applies to `record-detail`, `list-card`, `hub`, `dashboard`, `wizard` and `solution-map`. It does **not** apply to `capture` when built as a dialog, or to `inline-card`, since neither is a page. Spec: [components/containers.md](components/containers.md) "page shell".

Type, spacing and surface values come **baked into the blocks** ([block-library.md](block-library.md)) — compose them and the shape arrives styled. Don't hand-type values into a form: the app theme is overridden per-key by any breakpoint block, so freehand styling is where fidelity leaks. If a block lacks a value, change its overlay in `shesha-design-system/assets/block-styles/` and re-bake.

## The eight

Seed sizes are given because several are very large — **open them with `Grep`/offset for the fragment you need, never read one wholesale** (`rs-detail-with-header.json` alone is ~755 KB). Prefer composing from `assets/blocks/` where a block exists; that is ~600 lines instead of tens of thousands.

### `record-detail`
One record in depth. **Seed:** `rs-detail-with-header.json` (755 KB) or `employee-detail-without-child-tables.json` (395 KB) when there are no child collections.
**Blocks:** `page-header-band` → `meta-strip` → `flex-split-main-rail` (`rail-panel`, `rail-label-value-row`, `card-with-header-strip`, `status-pill`).
**Default shape:** header band (breadcrumb, title, status chip, Edit/Save/Cancel right-aligned) → key-info strip of 4–6 equal cells → body as a flex row: fill column for the primary content, fixed 332 px rail for attributes and related panels. `editMode: "inherited"`, lifecycle buttons per [components/actions.md](components/actions.md).
**Every content group in that body is a `card`** — headed where it needs a title, `hideHeading: true` where it doesn't — with `container`s only *inside* cards for layout. This sentence used to be missing, and a real run built the whole screen from 56 containers and no cards. Surfaces rule: [components/detail-page-pattern.md](components/detail-page-pattern.md).

### `list-card`
Many records. Two variants — **build the one the user's noun names** ("table"/"grid" vs "list"/"cards"); see [components/data-tables.md](components/data-tables.md).
**Seed:** table → `rs-table.json` (134 KB) or `employee-table.json` (122 KB); cards → `entity-datalist.json` (4.6 KB).
**Blocks:** `requirement-datalist-row` for a row-template list; `rail-panel` for a count-badged embedded list.
**Default shape:** page title → toolbar row (quick search left, primary Add right) → `dataContext`-wrapped `datatable`/`datalist` → pager. Add opens a `capture` dialog; row opens the `record-detail`. On the card variant, click-through goes on `datalist.onListItemClick` — **never a button inside the row template** ([data-tables.md](components/data-tables.md)).

### `capture`
Create or edit one record. **Seed:** dialog → `rs-create-dialog.json` (196 KB); full page → `standalone-create.json` (7.9 KB, the lean one — prefer it).
**Default shape:** fields grouped by meaning with a `sectionSeparator` per group once past ~5 inputs, a `validationErrors` component above the action row, and one `buttonGroup` holding Submit plus an exit (Back/Cancel). `editMode: "editable"`. The Submit/exit pair is the floor, not an extra.

### `inline-card`
The repeated unit inside a `list-card` or rail panel — published as its own Table-type form. **Seed:** `entity-card.json` (11 KB); inline-editable rows → `inline-editable-table.json` (28 KB).
**Default shape:** one compact card, name-mode bound text, status chip on its own row, `dimensions: fit-content`, single-line ellipsis on long text. Runtime rules in [data-tables.md](components/data-tables.md) — this archetype has the most runtime traps of the eight.

### `dashboard`
Metrics and summary. **Seed:** `assets/patterns/dashboard.json` (21 KB, minified).
**Default shape:** page title → a flex row of equal stat tiles → below, a flex row splitting charts from a recent-activity list. Tiles are real surfaces (card + hairline), never floating numbers.

### `hub`
A landing page routing elsewhere. **No dedicated seed — compose.**
**Blocks:** `card-with-header-strip` per area, in a wrapping flex row.
**Default shape:** page title + one-line purpose → a wrapping row of navigation cards, each a title, one-line description and a count or primary action. Every card is a `Navigate`.

### `wizard`
A multi-step sequence. **No dedicated seed — compose** from `capture` per step.
**Default shape:** header with step indicator → the active step's fields in a single column → footer `buttonGroup` (Back / Next, Submit on the final step). Keep cross-step state in `contexts.appContext`, never `globalState` ([shared-state.md](components/shared-state.md)).

### `solution-map`
Entities and their relationships as a matrix or graph. **No dedicated seed — compose.** The rarest of the eight, and the one most likely to need a custom page instead of a form — if the interaction is genuinely graph-like, say so rather than forcing it into form components (`shesha-developer:create-custom-page`).

## Cross-linking a set

Most briefs name a set, not a screen. The default wiring:

```
list-card ──(Add button, Show Dialog)──► capture
    │
    └──(row action / onListItemClick)──► record-detail ──(Edit)──► in-place lifecycle
```

Build in the order `capture` → `record-detail` → `list-card`, so each form a button references already exists when the referencing form is pushed. **Every referenced form must exist before the form pointing at it goes live** — a `formId` naming a form nobody created renders an empty list with no error, and `scripts/verify-artifact.mjs` fails the push on exactly this.
