# Consuming a layout blueprint (from shesha-design-comprehension)

When this skill is invoked by `shesha-claude-designer` (or directly with a design to match), the requirements arrive as a **layout blueprint** — a `<screen>.blueprint.md` produced by `shesha-developer-0-46:shesha-design-comprehension`. The blueprint is a *measured placement contract*; build to it exactly, then expect a placement re-measure (gate 5a.5) against its `assertions`.

## How to read it

A blueprint has, per screen: a header (entity modelType, form identity, **Archetype**, fidelity/confidence/viewport) and per-region `layout-tree`, `bindings`, and `assertions` fenced blocks. Map them onto a build:

| Blueprint part | Drives |
|---|---|
| `Archetype:` (one of the 8) | which seed to copy from `assets/examples/` (record-detail → `rs-detail-with-header.json`; list/table → `rs-table.json`; create dialog → `rs-create-dialog.json`; link-add → `rs-link-add-dialog.json`) |
| `layout-tree` `row=[…]` / `flex=[…]` | a flex **`container` row** (`display:"flex"` + `flexDirection:"row"` + `gap`) — **never the `columns` component**; size each child via `desktop.dimensions.width` (fill = `"calc(100% - <others>px)"`, fixed rail = `"332px"`). `native=[…px]` flags a fixed-width child |
| `layout-tree` nesting (indentation) | the container nesting + every component's `parentId` |
| `layout-tree` `kind` (card/tabs/datatable/datalist/field/buttonGroup/chip) | the component `type` to use — **exactly**, see below |
| `bindings` table | each input's `propertyName` + component `type` (validate every propertyName against the entity metadata, Step 4.5) |
| region `recipe:` annotations | passed through to `shesha-design-system` for styling (not your concern — build structure only) |
| `assertions` block | what gate 5a.5 will re-measure: column membership, row grouping, nesting depth, tab assignment |

## A `kind` is a contract, not a suggestion — substituting one is a defect

**If the blueprint says `card`, build a `card`.** Never substitute a `container` because it is
easier to emit. This is not hypothetical: a real run produced a detail screen with **56 containers
and zero cards** from a blueprint that named `card` three times, cited
`card-with-header-strip` by name, and wrote assertions about those cards (*"the Passenger card AND
the Payment card are BOTH in the LEFT column"*). The build script's helper had ten component types
and `card` was not one of them, so every card silently became a container and the page shipped
flat.

Two things follow:

1. **Before writing a build script, give it an emitter for every `kind` the blueprint uses.** For
   `card` that means handling `content.components` / `header.components` rather than `components` —
   the asymmetry that makes card the one component a generic helper skips
   ([detail-page-pattern.md](components/detail-page-pattern.md)).
2. **A substituted `kind` is a failure to report, not a degradation to accept.** If you genuinely
   cannot build the specified component, say so as a blocker with the node named. Shipping a
   different component than the spec asked for, silently, is the same class of defect as an agent
   reporting done for a file it never wrote.

Gate 5a.5 re-measures the blueprint's `assertions` against the built form and would catch this —
assertions that name cards fail against a page of containers. On the run above that gate never ran
(`manifest.json` recorded `gate5a5: null`), so nothing caught it. Do not rely on the gate in place
of building to spec; rely on it to prove you did.

## Building to the placement (the part that drifts)

- **Restructure the seed to match the `layout-tree`** — don't keep the seed's body just because it's there. If the blueprint says an 18/6 body with a right rail of panels, the seed's "full-width attributes + bottom tabs" body must be rebuilt into that split (attributes into the rail, the main list into the wide column).
- **Every split child needs an explicit `desktop.dimensions.width`, AND the row needs `display:"flex"`.** A flex row missing `display:"flex"` renders `display:block` → children stack full-width (the single most common placement failure: related panels end up under the main column instead of in the rail). `customStyle:{flex}` does NOT size the child — it is inert on the outer div; use `dimensions.width`.
- **Fixed-width rail:** for a `native=[…,332px]` rail, set the rail child `desktop.dimensions.width:"332px"` (`minWidth`/`maxWidth` `"332px"`) and the main child `width:"calc(100% - 348px)"` (332 rail + 16 gap). Collapse to stacked full-width on tablet/mobile.
- **Re-stamp `parentId` on every moved component** so the new nesting is real (wrong/missing parentIds render blank).

## After build — expect the placement diff

`shesha-design-comprehension` re-probes the built, published, table→details-navigated form and diffs measured placement against the blueprint `assertions`. Mismatches come back as concrete, routed fixes in this skill's vocabulary (move node into the right flex `container` row; give the child its `desktop.dimensions.width`; add `display:"flex"` to a row that's stacking; wrap rows 2-cell; assign to the right tab). Apply, re-push, repeat until all assertions pass. Don't consider the form done at "it renders" — done is "placement assertions pass".
