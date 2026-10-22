# Style channels and override precedence

Why a stamped style prop doesn't render, where each channel lands in the DOM, and the ordered debug procedure. Block shapes (border/background/dimensions/font/shadow) are in [styling-v7-mechanics.md](styling-v7-mechanics.md). Layout idioms / structure (`containers.md`, `layout.md`, `detail-page-pattern.md`) live in the `shesha-form-edit` skill — this skill (`shesha-design-system`) owns appearance only. Capability verdicts (which channel actually renders per component) are in [capability-matrix.md](capability-matrix.md).

---

## The five style channels

A single component's rendered style is the merge of FIVE sources. Lowest → highest:

| # | Channel | Shape | Wins over |
|---|---|---|---|
| 1 | Designer props | top-level keys: `alignItems`, `display`, `flexDirection`, `justifyContent`, `gap`, `background`, `border`, `font`, `shadow`, `dimensions` | — (base) |
| 2 | `stylingBoxJson` (0.46; legacy `stylingBox` JSON string converted only if this is empty) | object `{ "_type":"styleBox", "paddingTop":10, "marginBottom":0 }` | merges with 1 |
| 3 | Breakpoint objects `desktop`/`tablet`/`mobile` | same keys as 1+2, nested per breakpoint | overrides base **PER-KEY** at render time |
| 4 | Legacy `style` prop | a JS-expression **STRING**: `"return { padding: '10px' }"` — rendered as an **INLINE** style attribute | wins over everything |
| 5 | Framework CSS via `className` | `sha-page`, `sha-page-heading`, `.sha-page-content:not(.no-padding){padding:12px}`, `sha-index-table-control`, `index-table-controls-right` | applies regardless of markup; some rules `!important` |

Notes:
- Channel 3 is per-key: base `border.radius=0` is dead if all three breakpoints carry `radius=8`. Base `borderType:"custom"` is dead if `desktop.border.borderType` is `"all"`.
- Channel 4 is the v6 leftover. `style` can also exist *inside* breakpoints (`desktop.style`) — check both.
- Channel 5 cuts both ways: `.sha-page-content` *adds* 12px padding (escape hatch = append ` no-padding` to `className` on base AND `desktop/tablet/mobile.className`); `sha-index-table-control` *provides* the `padding: <Gd> 12px !important` toolbar inset that aligns quick-search to the datatable — don't remove it. Source: `@shesha-io/reactjs` 0.46 (`components/formDesigner/formComponent/formComponentModelPreparer.tsx`, `designer-components/container/styles.ts`).

---

## Channel→div mapping (0.46)

Every live component sits in `div.sha-component[data-sha-c-id,-name,-type,-property-name]` (the **wrapper**; it gets `dimensions` (via `getWrapperStyle`) and **margin**). A container then renders **two more divs** inside it:

| Div | Class | Receives |
|---|---|---|
| wrapper | `sha-component` (+ `data-sha-c-*`) | wrapper `dimensions` (percent kept, exact px -> `fit-content`, calc/auto/stretch kept) and margin |
| container outer | `sha-components-container sha-container-component` | the component's `dimensions` (percent -> `stretch`), `border`, `background`, `shadow`, margin, `alignSelf/justifySelf` |
| container inner | `sha-components-container-inner` | **padding**, `display`, `gap`, `justify*`/`align*`, `flex-direction`/`wrap`, grid template, **`overflow:auto` (always)**, and the legacy `style` string (inline) |

(0.45 recorded the outer div as taking "ONLY dimensions (+shadow)"; on 0.46 border/background/shadow/margin are on the outer box via the generated class. Superseded.) Consequences:

- A `style`-channel `flexShrink:0` still renders on the inner div and cannot stop the parent squeezing the outer one. `dimensions` is the lever for the flex item: for a squeezed container use `"dimensions": { "minHeight": "fit-content", "height": "auto", "maxHeight": "auto" }` on base + every breakpoint.
- **calc/auto/stretch widths are applied to the wrapper and to the container inside it** (non-exact values are not "fit-contented"), so a `calc(100% - 348px)` column can be narrowed twice. Percent and exact px do not have this problem. Verify with the probe (`doubleShrinkSuspect`).
- Padding on a container is **inside** its border/background; margin is outside.
- Reworked inputs (`allowInherit`) put their `desktop` block on the antd control wrapper (`.ant-input-affix-wrapper`, `.ant-picker`, `.ant-select`); label cell and form-item chrome come from `sha-form-item` styles (`min-height:0 !important` on `.ant-form-item-control-input`).

---

## Hard-coded framework behavior

- Container css-in-js is hard-coded `outer { overflow: hidden }`, `inner { ...getOverflowStyle(true,false) }` → every container's **inner div is ALWAYS `overflow:auto`** (`container/styles.ts`). The markup `overflow` prop is a **no-op in view mode** — stamping `overflow:false` does nothing.
- A scrollbar therefore means *content exceeds the box*, which in a stretched flex row means **flex-shrink squeeze**: `flex-shrink` defaults to 1 and `overflow:hidden` removes the min-content floor, so e.g. a title row collapses to 28px around 43px of content (non-`allowInherit` components get **5px top/bottom margins** unless `stylingBoxJson` says otherwise; `allowInherit` components take margins only from `stylingBoxJson` plus injected defaults such as columns `marginBottom 5` — content is often taller than it looks).
- Fix via the `dimensions` channel (above), never via `overflow`.

---

## enableStyleOnReadonly

`enableStyleOnReadonly: false` **silently disables padding/background** when the form renders read-only — styling looks fine in the designer, vanishes live. On 0.46 the style migration (`migratePrevStyles`) **stamps `enableStyleOnReadonly:false` on every block it builds**, so migrated components lose their styling read-only by default. Set `true` explicitly on any component whose styling must persist.

---

## Stamping rule

- Every style fix goes on **base AND every breakpoint object that exists** (`desktop`, `tablet`, `mobile`). Breakpoint-only values are invisible in a base-level audit and resurface at render.
- Any style audit/normalization must sweep **all five channels**, not just designer props — a `stylingBox`/`dimensions` audit can show a band as clean (`stylingBox: "{}"`) while `style` carries the offending padding.
- When transplanting styles from a template form, clone whole style objects and overwrite ONLY style keys (`direction`/`flex*`/`display`/`justify*`/`align*`/`gap`/`dimensions`/`border`/`background`/`font`/`shadow`/`stylingBox`/`desktop`/`tablet`/`mobile`/`className`/`style`); preserve `id`/`parentId`/`componentName`/`propertyName`/`version` and data bindings.
- Never build dividers as standalone components — an empty border-only container collapses to **0×0** (percentage height needs a stretching parent; border on a zero-size box paints nothing) and a `sectionSeparator` divider needs a hard-coded `lineHeight` (e.g. a stray `lineHeight: "150px"` drags the whole row taller — and a sibling `dimensions.height: "32px"` red-herring can hide it). Correct pattern: row `alignItems: "stretch"`, columns `alignSelf: "stretch"`, `gap: 0`, `flexWrap: "nowrap"`, height caps → `"auto"`, and columns 2+ carry `border.borderType: "custom"` + `border.border.left = { "width": "1px", "style": "solid", "color": "#d9d9d9" }` on base and every breakpoint. Dividers are then flush by construction (computed: `border-left 1px solid rgb(217,217,217)`, column height == band height).
- Negative padding in `stylingBox` (`"paddingTop": "-30"`) is invalid CSS — silently dropped, not an offset hack.

---

## The legacy style string

Symptoms:
- A stamped designer prop (e.g. `alignItems: "stretch"` on base + all breakpoints) **doesn't render** — DOM shows `flex-start`/`flex-end`.
- **Mystery padding** that no `stylingBox` explains.

Recipe:
1. Grep the component **AND every ancestor** for a truthy `style` or `desktop.style` (any breakpoint) FIRST — before touching any other channel.
2. When migrating a v6 component to v7 props, **null `style` on base + all breakpoints** and re-express the needed keys as designer props / breakpoint blocks.
3. When normalizing a form to a template, **diff the `style` strings too**, not just designer props — identical-looking designer JSON can render differently because of one `style` string.
4. Style strings that are **identical across all forms including the template** (e.g. a banner's `flex: '1 1 auto'`) can stay — only divergent ones cause divergent rendering.

---

## Debug checklist — when a prop doesn't render

Run in order; stop at the first hit:

1. **Legacy `style` string** — truthy `style`/`desktop.style` on the component or any ancestor? (inline wins over everything)
2. **Breakpoint override** — does `desktop`/`tablet`/`mobile` carry a different value for the same key? (per-key override of base)
3. **Framework class** — is a `className` like `sha-page-content` / `sha-index-table-control` injecting/blocking the style? (check computed styles; some rules `!important`)
4. **Channel→div mapping** — is the prop landing on the inner div when the constraint is on the outer flex item? (sizing fixes must go through `dimensions`)
5. **enableStyleOnReadonly** — read-only mode with `enableStyleOnReadonly: false` (the migration default)?
5b. **Injected migration default** — is the stored `version` below a style-migration step, so a default (container `minHeight 32px`, columns `marginBottom 5`, tabs v4 surface, datatable zebra/header) is being filled in? See [restoring-pre-046-look.md](restoring-pre-046-look.md).
6. Verify with `getBoundingClientRect`/`getComputedStyle` in-browser on `[data-sha-c-name="x"]`, **not screenshots** — scaled screenshots fake 10–15px offsets that are really 0.
7. Before re-testing, hard-refresh; if the old markup still renders, clear the FE form cache (**IndexedDB** `form`/`form_lookup`; the per-item cache is keyed by `cacheMd5`, which changes when markup changes). `indexedDB.deleteDatabase` from inside the app silently blocks — clear from a static page (e.g. `/favicon.ico`). See [verification.md](../../shesha-form-edit/references/verification.md).

---

### Worked example (project-specific)

Gotcha #18, 2026-06-10 audit of a sample app (0.45). The view-definition-details / base-project-details header band (`container60`) showed dead space above the KIB and a title indent that no other form had. `alignItems: "stretch"` was stamped on base + desktop + tablet + mobile; the JSON looked right; the DOM rendered `flex-start` plus unexplained padding. The stylingBox audit showed the band clean (`stylingBox: "{}"`).

Cause: channel 4. `container60` carried a legacy `style` string — `"return { padding: '10px 0px 10px 25px', alignItems: 'flex-start' }"` — rendered inline, overriding everything; and the `container52` KIB wrapper carried `style` with `flex: '0 0 auto'`, `alignItems: 'flex-end'`, `alignSelf: 'flex-start'`, blocking the vertical stretch. The template form (module-definition-details) had `style: null` on the analogous containers — which is exactly why only those two forms misbehaved.

Fix: null `style` on base + desktop + tablet + mobile of `container60` (designer props already carried bg/border/width), delete the `container52` wrapper and re-parent the KIB container directly into `container60` for structural parity. Banner `style` strings identical across all 17 forms (`flex: '1 1 auto'…`) were left alone.
