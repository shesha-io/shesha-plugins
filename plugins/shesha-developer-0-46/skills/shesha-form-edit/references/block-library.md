# Block library

Authored layout **blocks** — small, parented, version-stamped component subtrees that you
**compose** into a form. Never hand-copy a 25K-line seed — map each blueprint node to a block,
insert its subtree into a named `$slot`, re-stamp ids, fill `$bindings`.

## Blocks now ship pre-styled — there is no separate overlay pass

Every block's paired overlay has been **baked into its subtree as literal values** (44 targets
across 10 blocks, `scripts/bake-overlays.mjs`). Composing a block now yields a styled result
**by construction**. Do not apply the overlay again afterwards; it is already in there.

Why the change: the overlay used to be a second pass applied after composition, and a second
pass is one that gets skipped — which is how forms kept shipping as raw AntD. The app theme
cannot cover for it either: a breakpoint block overrides theme defaults per key, so the AntD
theme only reaches chrome ([app-theme.md](../../shesha-design-system/references/app-theme.md)).

Three silent defects surfaced while baking, all pre-existing:

- **`page-header-band` had no overlay file at all** despite declaring one, so its 7 nodes — the
  title band of every detail page — carried zero styling and always rendered as AntD defaults.
  The overlay is now written.
- **`$role:progressAccent` and `$role:addButtonText`** were referenced by `completeness-bar` and
  `dashed-add-button` but defined nowhere, so the renderer received the literal string
  `"$role:…"` as a colour and fell back. Both roles are now defined and resolved to `#003BB2`.
- `requirement-datalist-row`'s `rowMetaText` target matches no node **by design** — its `$note`
  says it applies to text components the *form* adds at compose time. Advisory targets like this
  stay overlay-only and cannot be baked.

The overlays remain on disk as the record of what a block's styling *means*, and as the input to
the transform. They are no longer needed at build time. Re-run the transform after editing one:

```bash
node scripts/bake-overlays.mjs assets/blocks ../shesha-design-system/assets/block-styles ../shesha-design-system/assets/themes/shesha.tokens.json --apply
```

It is idempotent, refuses to write unless every target resolves and node counts are unchanged,
and fails loudly on an unresolvable `$role`. Literal hexes in blocks make `validate-blocks.js`
emit colour WARNs — that is the recorded trade, not a defect to re-tokenise.

Blocks live in `assets/blocks/*.block.json`. Every block file carries: `$block`, `$scope`,
`$styleOverlay` (the paired overlay name in shesha-design-system), `$slots`, `$bindings`,
`$validatedAgainst` (matrix rows the structure relies on), and a `subtree` (the literal markup).
Some also carry a `$rowTemplate` (a separately-published Table-type row form).

## Catalogue

| Block | Archetype | Builds | Key `$slots` | Key `$bindings` |
|---|---|---|---|---|
| `page-shell` | page | **MANDATORY outermost wrapper on every page-level form** — a borderless, heading-less `card` carrying `className: "sha-page"`. Every other component goes in its `content`; nothing else sits at root. Not for dialogs or row-template cards. | `content` | none (pure chrome) |
| `flex-split-main-rail` | record-detail | The body split: one flex `container` (row, gap 16) with a fill `main` column + a fixed 332px `rail` column. The clean fixed/`calc` idiom — never `columns`. | `main`, `rail` | none (pure structure) |
| `page-header-band` | record-detail | In-page detail title band: breadcrumb + title row (title text + status chip on the left, Edit/Save/Cancel buttonGroup on the right). NOT the global header form. | `titleText`, `statusChip`, `actionItems`, `breadcrumbContent` | title content, status `propertyName` + reflist id, actions width `calc` |
| `meta-strip` | fragment | A horizontal strip of label/value meta cells (MODULE / RELEASE / VIEW TYPE …) under a header. | `cells`, `cell.label.text`, `cell.value.text` | each cell value `propertyName`/content |
| `card-with-header-strip` | fragment | A white card (radius 12, hairline, soft shadow) with a tinted header strip (title + optional count badge) over a padded body. | `header`, `body` | header text, count badge expression |
| `rail-panel` | list | A count-badged rail card for a linked collection: title + count + inline `+` add link over a datalist bound to its own `dataContext`. | `title.text`, `count.badge.text`, `add.button.label`, `datalist` | dataContext entityType/endpoint, datalist `formId`, add `formId`, onSuccess owner |
| `rail-label-value-row` | fragment | One Details-card attribute row: a fixed 96px label cell + a `calc(100% - 106px)` value/control cell, bottom hairline. Repeat per attribute. | `labelText`, `control`, `labelCell`, `valueCell` | row label, value `propertyName`, control `type`+version |
| `status-pill` | fragment | A standalone reflist status pill (per-item colours from the reflist, pill `customStyle`). | none | status `propertyName`, reflist module + name |
| `completeness-bar` | fragment | A micro-label + line progress bar reading a 0–100 percent property (or a static percent). | `label`, `progress` | percent `propertyName` (or literal `percent`) |
| `requirement-datalist-row` | list | The wide-column requirement list: a host (`dataContext` → `datalist`) in the parent form **plus** a separately-published row-card template (`$rowTemplate`: type + status badges, body line, meta + action row). **Carries the datalist row-template collapse/scroll FIX** — `style` overflow on every container + a `minHeight` reserve on the body text (markup-only; no global CSS). Canonical live examples: `view-requirement-card`, `view-endpoint-row`, `view-role-row`. | `host.datalist`, `row.header.left`, `row.body`, `row.meta` | host entityType/endpoint, datalist `formId`, row badge/body propertyNames + reflists |
| `dashed-add-button` | fragment | The dashed `+ Add X` button at the foot of a rail list: full-width dashed-bordered wrapper + a single `link` button opening a create dialog. | `button`, `buttonLabel`, `buttonGroup` | create-form id, label, parent-FK `formArguments`, refresh-target id |

### Placeholder conventions in a subtree
- `$binding:<name>` — a value you fill from `$bindings` (entity propertyName, reflist id, label, etc.).
- `$slot:<name>` — an id you mint during stamping (kept stable so action wiring resolves).
- `$role:<token>` — a **design-system** colour/role token; resolved by the overlay, never a hex.
- `$MODULE` / `$ENTITY` / `$OWNERFK` / `$PROJECTION` — substitutions in dataContext endpoint code.

## Assembly workflow

Compose from blocks — **never** copy a 25K-line seed and edit it down.

1. **Map** each blueprint `layout-tree` node to a block **by the catalogue above** — match what the
   node *is* (a header band → `page-header-band`, a body split → `flex-split-main-rail`). Do **not**
   try to match on screen archetype: `$scope` (`page` / `region` / `fragment`) describes how big a
   block is, deliberately a different axis from the eight screen archetypes in
   [archetypes.md](archetypes.md). This field was called `$archetype` and carried values
   (`page`, `fragment`, `list`) that appear in no archetype list, so the documented join key never
   resolved for any non-`record-detail` screen.
   Body split → `flex-split-main-rail`; title band → `page-header-band`; each rail collection →
   `rail-panel` (+ `dashed-add-button`); attribute rows → `rail-label-value-row`; the wide list →
   `requirement-datalist-row` (host + row template).
2. **Insert** the block's `subtree` into the parent's named `$slot` (the `$slots` map gives the
   JSON path of the array/node to write into). Nest blocks by inserting one block's subtree into
   another's slot (e.g. `rail-panel` subtrees into `flex-split-main-rail.$slots.rail`).
3. **Re-stamp** the whole inserted subtree with `stampTree`: mint a fresh `id` per component and
   set every child's `parentId` to its new parent. Wrong/missing `parentId` renders blank. Resolve
   `$slot:` ids here and keep them stable so action `actionOwner`/`onSuccess` wiring still points at
   the right component.
4. **Fill `$bindings`**: walk the block's `$bindings` list and write each `$binding:` placeholder —
   entity `propertyName`s (validate every one against entity metadata), reflist `{module,name}`,
   labels, count/body content expressions, dataContext endpoints, dialog `formId`s, and the
   `onSuccess.actionOwner` that must equal the owning dataContext/datalist id.
5. **Validate**: run `scripts/validate-blocks.js` (skeleton JSON parses, every `$validatedAgainst`
   row is `renders`/`gotcha` in the capability matrix, no `columns`, no flex row missing
   `display:flex`). Then validate the assembled form against the component-properties index.
6. **Push** via the form-edit API (Create / UpdateMarkup / ImportJson) and push any
   `$rowTemplate` as its own Table-type form (0.46: a push is live immediately - no publish step). Expect the gate-5a.5 placement re-measure.

> There is no "stamp the overlay" step. It used to be step 5 here — 80 lines below a section
> stating the opposite — so a builder either skipped it or double-stamped. The overlays are baked
> in (see the top of this file).

## The styling boundary

**form-edit may not *author* style values; it *inserts* pre-baked block subtrees.** That is the
whole rule, and it replaces an earlier boundary that said all brand styling "comes from the paired
overlay" — true before the bake, false now, and the source of a three-way contradiction across
this file, `SKILL.md` and the designer.

- **Composing a block?** Its style is already in the subtree. Insert it and move on.
- **Need a value a block doesn't carry?** That is a change to the block's overlay in
  `shesha-design-system/assets/block-styles/`, followed by a re-bake — not a hex typed into a form.
- **Restyling a form this library did not produce** (a hand-composed or live legacy form) is
  `shesha-design-system`'s job, and its output still goes back through form-edit's single push path.

So "if you find yourself typing a hex" still holds — but the destination is the overlay plus a
re-bake, not a separate styling pass over the built form.
