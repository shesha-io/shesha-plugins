# Restoring a pre-0.46 look (and styling older markup on 0.46)

Markup authored for 0.43-0.45 renders differently on 0.46 even though nothing in it changed, because **component migrations run at load time and fill in style defaults the old runtime never applied**. This file is how to see which defaults were injected, write explicit values that override them, and make sure the migration does not simply re-run and overwrite your fix.

Sources: framework release-0.46.0 (`designer-components/_common-migrations/migrateStyles.ts`, `utils/fluentMigrator/migrator.ts`, per-component `migrator` blocks) and the 0.43 -> 0.46 render delta analysis. Items marked *proven* were seen on a running 0.46 app; the rest are read from source and must be confirmed with a computed-style check (step 5).

## 1. How the machinery works

- **Migrations are client-side, in memory, on every load.** `convertFormMarkupToFlatStructure -> upgradeComponents -> upgradeComponent`. Nothing is written back to the server until someone **saves the form in the 0.46 designer** (which then persists every injected default — do not "just open and save" an old form if you want its old look).
- **Rule:** every migration step whose `version` is greater than the stored `version` runs, in ascending order; a missing `version` counts as `-1`. After each step the runner stamps `version = step.version` (`migrator.ts:68-82`).
- **Version numbers are reused across releases with different meaning.** Container is the trap: 0.43 `v6 = {shadowStyle:'none'}`; 0.46 `v6 = flex/grid -> device blocks`, `v7 = migratePrevStyles`, `v8 = hidden->visible`, `v9 = flex/grid again`. A container stored at v6 skips 0.46's v6 and runs only v7-v9. Never reason "this component is at v6 so it is current" — compare against the 0.46 `currentVersion` (table in [capability-matrix.md](capability-matrix.md) / `shesha-form-edit` components-kb).
- **Reworked components** (43 types, `allowInherit:true`) assemble their model as `getDefaultStyles()` < theme `components[type]` < `desktop` < the active device block. Anything you do not state explicitly is filled from the component default or the theme.
- Loaded forms have `ctx.isNew === false`, so every `ctx.isNew === true ? prev : ...` guard executes.

## 2. What gets injected (and the explicit values that override it)

Write these on `desktop` **and** `tablet` and `mobile` (a missing device block inherits desktop only through the same merge, and a breakpoint block overrides per key). Numbers are the values 0.46 injects; "restore" is what to write to get the pre-0.46 look.

| Component (0.46 version) | Injected on load | Restore by writing |
|---|---|---|
| `container` (9) | `dimensions.minHeight "32px"`, `width auto`, `border {1px #d9d9d9, style none}`, `direction horizontal`, `flexDirection row`, `justifyContent left`, `flexWrap nowrap`, `display block`; `enableStyleOnReadonly:false` | `dimensions.minHeight "0px"` (or the old value); `display`/`flexDirection`/`gap` explicitly; `enableStyleOnReadonly:true` if the styling must show read-only |
| `columns` (6) | `stylingBoxJson.marginBottom 5`, `width/maxWidth 100%`; Row margin forced to 0 so the block is inset `gutterX/2` per side (*proven by source*) | prefer replacing with a flex-row `container`; if kept, offset with `stylingBoxJson` `marginLeft/marginRight = -(gutterX/2)` and set `marginBottom` explicitly; verify by measurement |
| `text` (7) | v5: `fontSize` token -> px using a **14px root** (text-sm 12.25, text-base 14, text-lg 15.75, text-xl 17.5; `text-2xl`/`text-6xl` fall to 14 because of a stray `;`); v6 `level`; v7 reads `desktop.stylingBoxJson` + `desktop.font.size` and **ignores legacy `fontSize` and padding presets** (*proven*) | `desktop.font.size` as a number equal to the old rendered px (token rem x 16: text-sm 14, text-base 16, text-lg 18, text-xl 20, text-2xl 24); padding/margin in `desktop.stylingBoxJson`; line-height via `customStyle` (it is dropped by migration) |
| `text` content | v7 prefixes `{{` with `data.` (`{{x}}` -> `{{data.x}}`; `{{data.x}}` -> `{{data.data.x}}`) | author the already-migrated form (`{{data.x}}`) and stamp version 7, or leave content unprefixed and let v7 run once — never both |
| `tabs` (11) | v4: white `background`, 1px `#f0f0f0` border, radius 8, padding 16, font Segoe UI 14/500, card bg `rgba(0,0,0,.02)` (*proven*); v11: `hidden -> visible`, `selectMode readOnly -> editMode disabled` | `background {type:'color',color:'transparent'}`, `border` with `borderType:'all'` and width 0 / style none, `border.radius.all 0`, `stylingBoxJson` padding 0, explicit `font`; per-tab `className` for custom CSS (pane inline `style` is gone) |
| `datatable` (31) | v13 `useMultiselect -> selectionMode` (false -> `single`); v14/15/23 `striped = true`; v16/17 `rowHeight 40px`, `rowPadding 8px 12px`, `rowBorder 1px solid #f0f0f0`, `headerFontSize 14px`, `headerFontWeight 600`; v20/25/27 `hoverHighlight = true`; v22 `headerBackgroundColor #fafafa`, `headerFontWeight 500`, `rowAlternateBackgroundColor #f5f5f5`; v28 row height `40px -> auto`; v29 `actionIconSize 14px` (*proven*: zebra/header/row padding) | `striped:false`, `hoverHighlight:false`, `headerBackgroundColor`, `headerFontWeight`, `rowPadding`, `rowHeight`, `selectionMode` — **and stamp `version` 31**, because v14/15/23/25/27 overwrite a stored value on every load |
| `textField`/`textArea`/`numberField`/`dateField`/`dropdown`/`autocomplete`/`button`/`buttonGroup`/`refListStatus`/`checkbox`/`radio` | `migratePrevStyles`: input `height 32` (`size small/large` -> 24/40), `border 1px #d9d9d9`, radius 8 (textField), font 14/400, `enableStyleOnReadonly:false` | explicit `desktop.dimensions.height`, `border`, `font`, `shadow`; `enableStyleOnReadonly:true` |
| `alert` (3) | +8px padding | `stylingBoxJson` padding to the old value |
| `card` (5) | `width auto; height fit-content` (v4) | explicit `dimensions` |
| `subForm` (5) / `iconPicker` | `hideLabel:true` | `hideLabel:false` if labels were shown |
| `collapsiblePanel` (11) | v10 rebuilds the header into a `headerLayout` container; new antd 6 classes | restyle the `headerLayout` container; update custom CSS to `.ant-collapse-body` / `.ant-collapse-title` |
| `refListStatus` (9) | v9: colour-only badge (neither name nor icon) becomes `itemDisplay:'both'` | `itemDisplay` explicitly (`'name'`) |
| `datatableContext` | becomes `dataContext` (version reset to 8, component's own step 5 skipped) | nothing to restore; do not author the legacy type |

**Fonts.** The app font is Inter Variable and is not settable from `Shesha.ThemeSettings` (see [app-theme.md](app-theme.md)). Component defaults still hard-code `font.type "Segoe UI"` (text, textField, tabs), so a migrated component renders Segoe UI while chrome is Inter unless you write `font.type` explicitly. For the 0.46 look write `"Inter Variable"`; to keep a pre-0.46 Segoe look write `"Segoe UI"` on every block — a stored `font.type` always wins.

## 3. Pick a version strategy per component (this is the part that re-breaks fixes)

You write explicit values; the loader may still run steps over them. Two strategies:

1. **Lift to current (default).** Author the post-migration 0.46 shape — `visible` instead of `hidden`, `stylingBoxJson` object instead of a `stylingBox` string, `visiblePermissions`, structured `desktop`/`tablet`/`mobile` blocks, content in `{{data.x}}` form — and stamp the component's **current** 0.46 `version`. No step runs, so nothing is injected or overwritten, and your explicit values are what renders. Required for `datatable` (its steps overwrite stored values).
2. **Stay low, make it idempotent.** Leave the old `version` and let the shape-conversion steps run once (`hidden -> visible`, `stylingBox -> stylingBoxJson`), while your explicit `desktop` values are present. Only safe for steps that merge rather than overwrite; confirm with step 5. Never mix: a stamped-high component carrying legacy `hidden`/`stylingBox` keeps them un-migrated, and `hidden` on its own still hides (the renderer tests `hidden || visible===false`).

Guard rails: never lower a version to "re-run" a step on purpose; never copy a `version` from a different component or from 0.45 docs; after any stamp, re-read the component's computed styles — do not trust the JSON.

## 4. Other pipeline changes that look like style regressions

- **Hidden components are not mounted** (`configurableFormItemLive.tsx:68`, *proven*): a hidden `htmlRender` CSS carrier never injects; hidden inputs used as data holders register no field. Mount carriers (`hidden:false`/`visible:true`) and keep data in form data via `onAfterDataLoad` or a data context instead of hidden inputs.
- **`htmlRender` sanitises by default** (*proven*): a `<style>` at the start of the output is dropped and an empty result shows the Empty placeholder. Set `sanitize:false` (honoured at `htmlRender/index.tsx:39`), start the renderer with a real element if you keep sanitising, and never set `contentType:'html'` without an `html` value.
- **antd 6 DOM:** rewrite any custom CSS inside an htmlRender — `.ant-tabs-content-holder > .ant-tabs-content > .ant-tabs-tabpane` becomes `.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content`; `.ant-collapse-content-box` becomes `.ant-collapse-body`. Prefer `[data-sha-c-name="x"]` anchors (no hashed classes, no antd version coupling). Chevron-style tabs: give each tab a `className` and select `.ant-tabs:has(> .ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content.<class>)`.
- **`editMode` returning a boolean** `false` now means *disabled* (greyed), not read-only: return `'readOnly'` / `'editable'` / `'inherited'`.
- **Page shell:** `.has-heading` / `.fixed-heading` no longer exist; the header is fixed with `--sha-header-height`. Custom heading CSS keyed on those classes does nothing.

## 5. Verify the restoration

1. Clear the cached form (hard-refresh; or clear the `form` / `form_lookup` IndexedDB stores from `/favicon.ico`) and reload.
2. For each fixed component, read **computed style** by `[data-sha-c-name="x"]` (not a screenshot): `min-height`, `padding`, `font-size`, `border`, `background-color`, `font-family`. Compare to the target.
3. For a datatable: count zebra rows (`.ant-table-row` background alternation), check hover, header background, row padding.
4. Reload once more: a fix that survives only until the second load means a step re-ran and overwrote it (version strategy, section 3).
5. Run the placement probe from `shesha-design-comprehension`: injected `minHeight 32px` and `marginBottom 5` show up as small height/inset deltas, not structure faults.
