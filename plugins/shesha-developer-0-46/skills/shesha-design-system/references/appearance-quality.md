# Appearance quality (the look)

The appearance companion to `shesha-form-edit`'s `form-quality.md`. **Clear split:** `form-quality.md` owns *construction* (bindings, CRUD wiring, `validationErrors`, the guardrails) — those are kept verbatim there and **appearance never overrides a construction guardrail**. This file owns *appearance*: when a form must look like a design or brand, grade it against the positive recipes below. Concrete v7 shapes are in [component-recipes.md](component-recipes.md); which channels actually render is in [capability-matrix.md](capability-matrix.md).

## Surface & elevation
- Page root = `surfaces.canvas`; cards = white + hairline (`lines.border`) + `radius.lg` **plus the brand card shadow only if the brand defines one** (the Shesha default is border-forward — cards render flat; a brand with a visible `shadow.card` e.g. `0 1 4 rgba(0,0,0,0.06)` pairs it with the hairline); header strips = `surfaces.surfaceAlt` + bottom hairline. Structure comes from the line — never a shadow instead of a border, and never a heavy/decorative shadow.
- Reserve `shadow.overlay` for floating surfaces only (modals, popovers, dropdown menus).
- Build depth by **layering token surfaces** (canvas → surface → surfaceAlt → tint), not by stacking heavier shadows.

## Type & weight
- **Scale by surface:** 14 dense data-entry · 16 card header · 18 hero/summary value · 20 section heading · 24 page title. Don't flatten everything to 14; don't inflate dense entry past 14.
- **Weight by role:** 400 body/values · 500 micro-labels + table-cell emphasis · 600 field labels + card/section headers · 700 only a genuinely-bold title. Use the brand `type.weights`; don't invent a weight.

## Splits, rhythm & shape
- **Splits follow the flex-split idiom** — [capability-matrix.md §flex-split](capability-matrix.md#flex-split).
- 4px spacing grid (4/8/12/16/20/24/32/40/48); field gap 16; section gap 24; card padding 16 (compact) / 24 (default).
- Radius by role: `radius.pill` status badges · `radius.md` (6) controls · `radius.lg` (8 in the Shesha default; up to 12 in other brands) cards · `radius.sm` (4) chips/legacy inputs.

## Status & semantic colour
- Status = a `refListStatus` chip coloured from `statusLifecycle.badges` (bg/fg/border) — **never colour alone**, always with the label.
- Semantic colours are operational status signals only — never decorative.

## Audit output
Given a screenshot + the theme, return **prop-level fixes** (component · prop path · current vs target · one-line reason), ordered by impact — suggestions, not blockers. Route any *structural* finding back to `shesha-form-edit`; never restructure here.

## NOT governed here (→ `form-quality.md` guardrails — never relaxed)
`validationErrors` present · Submit + paired exit · `propertyName` camelCase (incl. datatable columns) · `modelType` `{name,module}` object · dropdown `dataSourceType` · dates → `dateField` · `editMode` per form type · unique ids · no clipping (`dimensions.minHeight:'fit-content'`) · destructive never primary · no loose `button` nodes. If an appearance goal seems to require breaking one of these, stop — the structure is wrong; route to `shesha-form-edit`.
