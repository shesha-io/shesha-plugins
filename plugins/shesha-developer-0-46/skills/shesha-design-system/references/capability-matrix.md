# Shesha style capability matrix (measured live)

Which v7 style channel actually **renders** on which component, measured against a live Shesha backend — not inferred from the props index (the index says what's *legal*; this says what *works*). Version-stamped; re-measure on a Shesha upgrade and diff. Machine-readable source: [`../assets/capability-matrix.json`](../assets/capability-matrix.json).

> **`validate-blocks` rule:** a block (`shesha-form-edit/assets/blocks`) may only reference channels marked ✅ `renders` or ⚠️ `gotcha` (with the documented working key path). A block referencing a ❌ `no-op` channel must not compose.

**Measured:** `@shesha-io/reactjs 0.45.x` · sample app · viewport 1440×900 · 2026-06-30. Method: per-cell **control twin** (channel omitted) → a no-op is `rendered == control ≠ intended`. Probe forms (`-claude` suffix, disposable): `style-lab-flex-split / surface / inputs / controls`.

**0.46 status (read this before trusting a row):** the verdict tables below are 0.45 measurements. For `@shesha-io/reactjs 0.46.0` (React 19, antd 6.6.4) the changes that matter are summarised in [§0.46 deltas](#046-deltas) from release-0.46.0 source plus facts proven on a running 0.46 app. Rows flagged `reverify046` in the JSON have **not** been re-measured. Re-measure with the style-lab forms before authoring a block that depends on one.

## ⚠️ Read first — two cross-cutting rules

1. **Component VERSION must match the live framework, or the style block silently no-ops** (and on 0.46 a version *below* a style-migration step makes the step run and inject defaults: see [restoring-pre-046-look.md](restoring-pre-046-look.md)). `numberField` at `version 3` ignored its entire `desktop` block (a total no-op); at `version 5` `dimensions.width` applied. A stale version re-runs the migration chain and drops styling with NO error. **Versions live in one place: `shesha-form-edit/assets/components-kb/_index.json`**, mirrored in [`component-cheatsheet.md`](../../shesha-form-edit/references/component-cheatsheet.md). A hand-maintained list used to sit on this line and had drifted (`dataContext` 7, actually 8) — don't reintroduce one.

<a id="flex-split"></a>
2. **The flex-split idiom — the canonical statement. Link here; don't restate it.**
   - Splits are flex `container` rows. **Never the `columns` component** (legacy; `validate-blocks.js` fails any block containing one).
   - A flex container **MUST** set `display:"flex"`, or `flexDirection` and `gap` are inert and children stack full-width — the single most common placement failure.
   - Size each child via **`desktop.dimensions.width`**. It is the only lever that reaches the child's outer `div.sha-component` wrapper. **0.46:** exact px and `%` are safe; a `calc()`/`auto`/`stretch` width is applied to the wrapper *and* the container inside it (`getFullSizeWrapperDimensions` + `getFullSizeComponentDimensions`, `stylingUtils.ts`), so `calc` can shrink a column twice. Default to main = `width:"100%"` + `minWidth:"0px"` next to a fixed-px rail; prove any `calc` with the probe's `doubleShrinkSuspect`/wrapper-vs-inner width.
   - Per-child **`customStyle:{flex:…}` is inert** for outer sizing — it lands on the inner div.
   - Canonical main+rail body: fixed rail `332px` (+ min/max `332px`), filling main `100%` + `minWidth:"0px"` (0.46) or `calc(100% - 348px)` (0.45-proven; re-verify on 0.46).

   This paragraph was duplicated near-verbatim across ~15 files, which is why it drifted. The machine-readable form is `crossCuttingRules` in [`../assets/capability-matrix.json`](../assets/capability-matrix.json).

**Measuring live (two gotchas that will fool you):**
- ~~In Live mode `text`/`refListStatus` do not carry `data-sha-c-name`~~ — **superseded on 0.46 (proven live):** every known component is wrapped in `div.sha-component` with `data-sha-c-id` / `-name` / `-type` / `-property-name` (+ `-form-name` on sub-forms). Query `[data-sha-c-name="x"]` for any component. (The 0.45 note is kept as history: a probe written for 0.45 that read a container's `innerText` still works.)
- A **dispatched DOM `MouseEvent` does NOT fire** a React/antd `onChange` (e.g. ant-select). Use a **real click** to trigger handlers, or your automated interaction silently no-ops (and you'll wrongly conclude the handler is broken).

## Containers / surfaces  (all channels land on the outer `.sha-components-container` div)
| Channel | Verdict | Working key path / note |
|---|---|---|
| `background.color` | ✅ | `desktop.background {type:'color', color}` |
| `background.gradient` | ✅ | `desktop.background {type:'gradient', gradient:{direction, colors:{0,1}}}` (renders `linear-gradient`) |
| `shadow` | ✅ | `desktop.shadow {offsetX,offsetY,blurRadius,spreadRadius,color}` — small `0 1 4 rgba(0,0,0,0.06)` AND heavy both render |
| `border.all` | ✅ | `borderType:'all'` |
| `border` per-side | ✅ | `borderType:'custom'` + only the wanted side (`left`/`bottom`); `'all'` does NOT enable per-side |
| `border.radius` | ✅ | `radius.all` (12, 9999 pill) |
| `dimensions.width` | ✅ | `%` AND `calc()` both render on outer div (the flex-split lever) |
| `dimensions.minHeight:'fit-content'` | ⚠️ gotcha | a **dimensions** channel reaching the outer div (0.46: also border/background/shadow/margin land on the outer `.sha-container-component`; padding and layout props on the inner div). The `overflow` BOOLEAN prop is a no-op — but the legacy `style` overflow is NOT (next row). |
| **`style` (legacy inline) `overflow`** | ⚠️ gotcha (deliberate) | `style:"return {overflow:'visible'}"` renders **inline on the element and reaches the inner `.sha-components-container-inner` div** — the ONLY channel that overrides the framework's hard-coded inner `overflow:auto`. **This is the datalist row-template card fix** (use `visible` on inner rows, `hidden` on the card root). Verified live 2026-06-30. Elsewhere the legacy `style` is a footgun (overrides designer props) — use it deliberately, scoped to this fix. |
| `stylingBox` padding/margin | ✅ | JSON **string** `'{"paddingTop":"20",…}'` |
| **`font` on a container** | ❌ no-op | size/weight/color/align on a *container* do NOT apply — **put font on the `text` child, not its container** |
| `customStyle:{flex}` for sizing | ❌ no-op | lands on inner div; use `dimensions.width` |
| pixel note | — | a `2px` border computes ~`1.6px`, `1px`→`0.8px` (~0.8× Shesha rem scaling) — renders, but slightly thinner |

## Inputs  (style block lands on the input's outer wrapper — at the CORRECT version)
| Component | Verdict | Working key path / note |
|---|---|---|
| `textField` (v6) | ✅ fully | bg/border/radius/`dimensions.width`/font all render on `.ant-input-affix-wrapper` |
| `dateField` (v7) | ✅ fully | on `.ant-picker` |
| `dropdown` (v11) | ✅ fully | style lands on the `.ant-select` wrapper (goes `borderless`; wrapper carries bg/border/radius/width/font) |
| `autocomplete` (v8) | ✅ fully | same `.ant-select` wrapper mechanism |
| `numberField` (**v5**) | ⚠️ partial | `dimensions.width` applies at v5 (was a total no-op at v3 — version artifact). bg/border may need the affix-wrapper; if styling is critical, wrap in a styled `container`. |
| Agent-C myth | — | "inputs can't be styled" is FALSE — 4/5 fully styleable; only numberField is finicky (version-sensitive) |

## Display / controls
| Component | Verdict | Note |
|---|---|---|
| `text` | ✅ | `fontSize` (Tailwind class) + `fontWeight` as DIRECT props; `desktop.font.{size,weight,color,align}` for exact control; `{{{triple-brace}}}` for raw content; renders inside `ant-form-item`/`ant-col-24` wrappers (`hideLabel:true` to drop the label cell) |
| `text` `customStyle` (code-mode) | ✅ | `customStyle {_mode:'code',_code:'return {letterSpacing,textTransform,lineHeight,...}'}` — for `letter-spacing`/`text-transform`/`line-height` the `font` channel can't express (proven on the live status chip + KIB micro-labels) |
| `progress` (v3) | ✅ | renders a bar; `strokeColor` applies (the completeness bar) |
| `refListStatus` (v6) | ✅ | status pill; per-item bg/fg/border from the reflist; pill radius via `customStyle` inline-flex (proven in the live form) |
| `button` / `buttonGroup` (v15) | ✅ via APP THEME | `buttonType` primary = app-theme primary fill (Cobalt `#003BB2` in the Shesha default), default = white+hairline. **Colour is app-theme-driven, not per-button** — don't override per button |
| `alert` (v2) | ❌ custom style no-op | colour is driven by `alertType` (info/success/warning/error); a `desktop` bg/border block does NOT override it. Use the right `alertType`, or wrap/replace with a styled `container` for a custom callout |
| `checkbox` (v5) | ✅ renders | (app-theme styled) |
| `sectionSeparator` (v1) | ✅ renders | |
| `card` (v3) | ✅ (proven in live form) | rail panels are `card`s carrying white bg + hairline + shadow + radius; styled via its `desktop` block. (Fresh-probe selector missed; production-confirmed.) |
| **multi-element `datalist` row-template card (overflow / collapse)** | ✅ SOLVED (markup-only) | **RESOLVED 2026-06-30 — was previously, wrongly, recorded as a hard limit needing global CSS. It is fully fixable in form config.** Root cause: the framework forces `min-height:0` on each `form-item-control-input` (an atomic class), so multi-line content paints via `overflow:visible` *out of* a collapsed wrapper → cards overlap, and the container's hard-coded inner `overflow:auto` shows **▲▼ scroll arrows** for tall text. **The fix (no global CSS, no `htmlRender`):** (1) **`style` overflow on every container** — `style:"return {overflow:'visible'}"` on inner rows, `overflow:'hidden'` on the card root. The legacy `style` JS-string renders **inline on the element and reaches the inner `.sha-components-container-inner` div** — the only channel that overrides the framework `overflow:auto` (verified: inner computed overflow becomes the value you set). (2) **Reserve `dimensions.minHeight:'24px'` on the body text** + `style:"return {whiteSpace:'normal',wordBreak:'break-word',overflow:'hidden',display:'block',maxWidth:'100%'}"` → wraps full text, no collapse/overlap. (3) `dimensions.minHeight:'fit-content'` on containers. (4) refListStatus pills `style:"return {display:'inline-flex',alignItems:'center',height:'26px',overflow:'visible',whiteSpace:'nowrap'}"` + `solidBackground:true`. (5) header is a flex row with `justifyContent:'space-between'` (badges-left container `dimensions.maxWidth:'calc(100% - 80px)'`, actions right). **Canonical live examples:** `view-requirement-card`, `view-endpoint-row`, `view-role-row` (the row templates of `view-definition-details-claude`). Recipe: [`component-recipes.md` → Datalist row-template card]; block: `requirement-datalist-row`. |
| **conditional visibility in a `datalist` row-template** | ⚠️ gotcha (`reverify046`: 0.46 migrates `hidden` to an inverted `visible`; `hidden` is still honoured when present, hidden components are not mounted) | **Use `hidden` (code-mode `{_mode:'code',_code:'return <hide?>;'}`), NOT `customVisibility`** — `customVisibility` is a **no-op** on datalist row-template components (proven on the requirement card: `customVisibility` left empty chips/badges visible; switching to `hidden` hid them). Hide-when-empty: `hidden` returns `true` when the bound value/array is empty. |
| `datatable` / `datalist` (v11/7 via `dataContext`) | ✅ (proven in live form) | header surfaceAlt, row hover tint, datalist card styling via the list's style channels |

## Data binding / filtering / counts  (measured 2026-06-30)
| Concern | Verdict | Working approach / note |
|---|---|---|
| filter a subtable/list by the **parent record** | ✅ | dataContext `permanentFilter` = `{and:[{"==":[{var:"<fk>.id"},{evaluate:[{expression:"{{data.id}}",required:false,type:"mustache"}]}]}]}`. **`required:false` DROPS the clause when empty** → show-all-if-none. Mustache for the record is `{{data.id}}`; field path is the camelCase FK + `.id` (backend-verify it — wrong path silently returns 0). |
| filter by a **GLOBAL `appContext`/`globalState` value** (cross-screen, e.g. a project switcher) | ❌ config can't | **Proven for BOTH appContext and globalState.** (1) an autocomplete's `onChangeCustom` in the global `header` form does **not fire** on selection (the global value never gets written); (2) even when present, the datatable `permanentFilter` evaluates `{{contexts.appContext.X}}`/`{{globalState.X}}` as **empty** at query time, and tables **don't refetch** on a global change. A global cross-screen filter needs **frontend-source** app wiring (app-provider seed before render + a dispatching selector + reactive refetch). Filtering by the form's OWN `data.id` works (row above) — only global/session values fail. |
| **collection count** in a header/badge | ✅ | Compute in `formSettings.onAfterDataLoad`: `var r = await http.get('…/Crud/GetAll?filter=<parentFk filter>&properties=id&maxResultCount=1000'); form.setFieldsValue({xCount:(r.data.result.items||[]).length});` then bind a text/badge to `{{data.xCount}}`. Use **`items.length`, NOT `result.totalCount`** (unreliable at small `maxResultCount`). Reading a live context value in a text for the count does NOT work (see the global-filter row). Proven on the rail count badges + "View Requirements · N". |

## TODO — not yet freshly probed (probe if a block needs them)
- Input styling in **readonly / Live mode** + the `enableStyleOnReadonly` flag (readonly inputs render empty without data — needs a bound value to measure).
- Equal **N-cell distribution** (KIB strip): `customStyle flex:'1 1 0'` is inert on the outer div, so equal cells likely need `dimensions.width:'calc((100% - <gaps>)/N)'` — the meta strip works content-width + gap regardless.
- ~~Legacy `style` / `desktop.style` override precedence~~ — **measured 2026-06-30**: the legacy `style` JS-string renders **inline on the element** and overrides designer props; crucially it **reaches the container inner div**, which is why it (and only it) fixes the datalist-card `overflow:auto` (see the row-template card row above). Footgun elsewhere; the deliberate fix here.
- `tabs` active-ink styling; `collapsiblePanel` accent header.

<a id="046-deltas"></a>
## 0.46 deltas (source-read; items marked *proven* were seen on a running 0.46 app)

| Area | 0.45 behaviour | 0.46 behaviour | Evidence |
|---|---|---|---|
| Component wrapper | `data-sha-c-name` on containers (live) | every component: `div.sha-component[data-sha-c-id,-name,-type,-property-name]` — *proven* | `knownFormComponent.tsx:98-124` |
| Container boxes | outer got dimensions (+shadow); inner got padding/layout | outer `.sha-container-component`: dimensions, border, background, shadow, margin; inner `.sha-components-container-inner`: padding, display/gap/justify/align, flex-direction/wrap, grid, `overflow:auto` | `container/styles.ts:21-55` |
| Wide widths | calc worked on the outer div | calc applied to wrapper AND container (double) — `reverify046` | `stylingUtils.ts:12-66` |
| Tabs DOM | `content-holder > content > tabpane` | `.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content`; style result as a class on `.ant-tabs-content` — *proven* | rc-tabs 1.13.0 `TabPanelList` |
| Tabs surface | pane inline style | tabs v4+ persist white bg / 1px `#f0f0f0` border / radius 8 / padding 16 on `.ant-tabs-body-holder` — *proven* | `tabs/styles.ts`, `tabs/utils.ts` |
| Text | `fontSize` Tailwind token, padding presets | v7 reads `desktop.stylingBoxJson` + `desktop.font.size`; legacy ignored — *proven* | `text/index.tsx` |
| Hidden components | mounted, CSS-hidden | **not mounted** — *proven* | `configurableFormItemLive.tsx:68` |
| htmlRender | raw HTML | DOMPurify by default; `<style>`-only output becomes the Empty placeholder — *proven* | `htmlRender/index.tsx` |
| Style migrations | sparse stored props only | defaults injected (container `minHeight 32px`, columns `marginBottom 5`, datatable zebra/header/row padding) — *proven* | `_common-migrations/migrateStyles.ts` |
| App theme | full ConfigProvider via settings (assumed) | settings reach only primary/semantic colours + layout shell; font forced to Inter Variable | `providers/theme/index.tsx` |
| Collapse DOM | `.ant-collapse-content-box` | `.ant-collapse-body` / `.ant-collapse-title` | rc-collapse 1.2.0 |
