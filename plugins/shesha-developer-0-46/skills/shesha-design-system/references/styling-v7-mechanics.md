# v7 Component Styling System

Reworked Shesha components (0.46: 43 types with `allowInherit:true`, container v7+ and so on) use per-breakpoint style blocks instead of the `style` JS expression prop. This covers the full block structure, common patterns, and the move from legacy props. Block shapes are unchanged since 0.45; what changed in 0.46 is **which keys are read** (`stylingBoxJson`, `desktop.font.size`), **where each lands in the DOM** ([style-channels.md](style-channels.md)), and **that load-time migrations inject defaults** ([restoring-pre-046-look.md](restoring-pre-046-look.md)).

---

## v6 vs v7

| | v6 | v7 |
|---|---|---|
| How styled | `"style": "return { backgroundColor: '#fff', ... }"` | `"desktop": { "background": {...}, "border": {...}, ... }` |
| Breakpoints | Single style for all | Separate `desktop` / `tablet` / `mobile` keys |
| Version field | below the component's style step | at/above it (container 7+, datatable 12+, tabs 4+; current 0.46 versions in [capability-matrix.md](capability-matrix.md)) |
| Works with | `container`, some old components | `container` (v7+), newer components |

Always apply the same block to all three breakpoints unless you have viewport-specific layout differences.

---

## Full v7 style block

```json
{
  "border": {
    "hideBorder": false,
    "radiusType": "all",
    "borderType": "all",
    "border": {
      "all": { "width": 1, "color": "#e5e7eb", "style": "solid" },
      "top": {}, "bottom": {}, "left": {}, "right": {}
    },
    "radius": { "all": 12 }
  },
  "background": {
    "type": "color",
    "color": "#ffffff",
    "repeat": "no-repeat",
    "size": "auto",
    "position": "center",
    "gradient": { "direction": "to right", "colors": {} },
    "url": "",
    "storedFile": { "id": null },
    "uploadFile": null
  },
  "font": {
    "color": "#1a1a1a",
    "type": "Inter Variable",
    "align": "left",
    "size": 14,
    "weight": "400"
  },
  "dimensions": {
    "width": "100%",
    "height": "auto",
    "minHeight": "0px",
    "maxHeight": "auto",
    "minWidth": "0px",
    "maxWidth": "100%"
  },
  "shadow": {
    "offsetX": 0,
    "offsetY": 1,
    "color": "rgba(0,0,0,0.06)",
    "blurRadius": 4,
    "spreadRadius": 0
  },
  "stylingBoxJson": { "_type": "styleBox", "paddingTop": 24, "paddingBottom": 24, "paddingLeft": 32, "paddingRight": 32 },
  "enableStyleOnReadonly": false,
  "flexDirection": "column",
  "direction": "vertical",
  "justifyContent": "flex-start",
  "alignItems": "stretch",
  "flexWrap": "nowrap",
  "gap": "0",
  "overflow": true
}
```

---

## `stylingBoxJson` (padding/margin)

The canonical carrier on 0.46 is `stylingBoxJson`, an **object** (numbers or numeric strings), set per breakpoint:

```json
"stylingBoxJson": { "_type": "styleBox", "paddingTop": 24, "marginLeft": -32 }
```

Keys: `paddingTop|Bottom|Left|Right`, `marginTop|Bottom|Left|Right` only — never `textTransform`, `color` or other CSS. The effective-style merge uses `stylingBoxJson` when truthy, otherwise converts the legacy `stylingBox` **JSON string** (`"{\"paddingTop\":\"24\"}"`) — so old markup still renders, but `text` v7 reads only `desktop.stylingBoxJson`, and the migration `stylingBox -> stylingBoxJson` runs at load for components below that step. Write `stylingBoxJson`; keep a legacy string only if the same markup must open in a pre-0.46 runtime. On a container, margin lands on the outer box and **padding on the inner box** ([style-channels.md](style-channels.md)). Negative padding is invalid CSS and dropped; negative margin is valid.

## Per-side borders (`borderType: "custom"`)

To set only some sides (e.g. left accent + bottom rule):

```json
"border": {
  "hideBorder": false,
  "radiusType": "all",
  "borderType": "custom",
  "border": {
    "all": { "width": 1, "color": "#e5e7eb", "style": "none" },
    "top": {},
    "bottom": { "width": 1, "color": "#e5e7eb", "style": "solid" },
    "left": { "width": 4, "color": "#fa8c16", "style": "solid" },
    "right": {}
  },
  "radius": { "all": 0 }
}
```

- Set `borderType: "custom"` (not `"all"`) to activate per-side overrides.
- Empty `{}` on a side means "no border on that side."
- `all` acts as the fallback for sides that aren't explicitly overridden; when `borderType: "custom"`, per-side entries take precedence.

---

## Design token set (base-project-details baseline)

| Role | Value |
|---|---|
| Card surface | `#ffffff` |
| Page background | `#f3f4f6` |
| Header strip bg | `#f8fafc` |
| Section divider bg | `#f9fafb` |
| Border / divider | `#e5e7eb` |
| Light rule | `#f0f0f0` |
| Brand accent | `#fa8c16` |
| Ink (primary text) | `#111827` |
| Body text | `#1a1a1a` |
| Muted (labels) | `#6b7280` |
| Section heading | `#374151` |
| Card border radius | `12` |
| Sub-card radius | `8` |
| Card shadow | `offsetY:1, blur:4, color:rgba(0,0,0,0.06)` |
| Sub-card shadow | `offsetY:1, blur:3, color:rgba(0,0,0,0.05)` |

---

## Common patterns

### White card sub-container
```json
"border": { "borderType": "all", "border": { "all": { "width":1, "color":"#e5e7eb", "style":"solid" }, ... }, "radius": { "all": 8 } },
"background": { "type": "color", "color": "#ffffff" },
"shadow": { "offsetX":0, "offsetY":1, "color":"rgba(0,0,0,0.05)", "blurRadius":3, "spreadRadius":0 },
"stylingBoxJson": { "_type": "styleBox", "paddingTop": 12, "paddingBottom": 12, "paddingLeft": 16, "paddingRight": 16 }
```

### Tinted header strip (full-bleed)
```json
"background": { "type": "color", "color": "#f8fafc" },
"border": { "borderType": "custom", "border": { "all": { "style": "none" }, "bottom": { "width":1, "color":"#e5e7eb", "style":"solid" }, ... } },
"stylingBoxJson": { "_type": "styleBox", "paddingTop": 20, "paddingBottom": 20, "paddingLeft": 32, "paddingRight": 32 }
```
Root container must have `pt=0, pl=0, pr=0` so header spans full card width.

### Left accent (branded title container)
```json
"border": { "borderType": "custom", "border": { "all": { "style": "none" }, "left": { "width":4, "color":"#fa8c16", "style":"solid" }, ... } },
"stylingBoxJson": { "_type": "styleBox", "paddingLeft": 16, "paddingTop": 4, "paddingBottom": 4 }
```

### Toolbar row
```json
"background": { "type": "color", "color": "#ffffff" },
"border": { "borderType": "custom", "border": { "top": { "width":1, "color":"#e5e7eb", "style":"solid" }, "bottom": { "width":1, "color":"#f0f0f0", "style":"solid" }, ... } },
"direction": "horizontal",
"justifyContent": "flex-end",
"alignItems": "center",
"gap": "8",
"stylingBoxJson": { "_type": "styleBox", "paddingTop": 12, "paddingBottom": 12, "paddingLeft": 32, "paddingRight": 32 }
```

---

## Text sizing and colour (text v7)

`text` v7 takes size from `desktop.font.size` (a **number of px**) and padding/margin from `desktop.stylingBoxJson`; the legacy `fontSize` Tailwind token (`text-xs`...) and padding presets are **ignored** once v7 has run, and any token that did get migrated was converted with a 14px root (text-lg 18 -> 15.75). Colour is `desktop.font.color`. Set all three breakpoints:

```json
{
  "type": "text", "version": 7,
  "desktop": { "font": { "color": "#6b7280", "type": "Inter Variable", "size": 11, "weight": "500" },
               "stylingBoxJson": { "_type": "styleBox", "marginBottom": 0 } },
  "tablet":  { "font": { "color": "#6b7280", "type": "Inter Variable", "size": 11, "weight": "500" } },
  "mobile":  { "font": { "color": "#6b7280", "type": "Inter Variable", "size": 11, "weight": "500" } }
}
```

`content` is Mustache with `{{data.x}}`-style paths on v7 (use `{{{triple}}}` for raw). `letter-spacing`, `text-transform`, `line-height` still need `customStyle {_mode:'code', _code:'return {...}'}`.

---

## Moving legacy (v6-style) props to v7+ blocks

1. Set `version` to the component's **current 0.46 version**, not a literal `7` (container 9, text 7, tabs 11, datatable 31, ...).
2. Remove the legacy `style` JS-expression prop (and null it in every breakpoint).
3. Add `desktop`, `tablet`, `mobile` blocks (same object for all three at first).
4. Move margin/padding into `stylingBoxJson`; `backgroundColor` -> `background.color`, `borderRadius` -> `border.radius.all`, `boxShadow` -> `shadow.*`; `hidden` -> `visible` (inverted); `permissions` -> `visiblePermissions`.
5. Remove `shadowStyle` if present (v6 relic).

If you do NOT bring the version up, the load-time migration runs and may inject defaults over the blocks — see [restoring-pre-046-look.md](restoring-pre-046-look.md).

---

## Recipe: make a child fill its parent's full width

A single child of a container sizes to its **content** (~700px), not the parent (e.g. a
`dataContext` inside a `sha-index-table-full` container looks narrow even though the container
is full width). The v7 renderer **ignores the legacy `direction: "vertical"`** prop. Fix by making
the container a column flexbox that stretches its children:

```jsonc
{ "type": "container", "version": 9, "flexDirection": "column", "display": "flex",
  "alignItems": "stretch" /* + width 100% via desktop.dimensions if needed */ }
```

`flexDirection: "column"` + `alignItems: "stretch"` makes the child fill the parent's width.
(Verified: this turns a 700px list into a full-width one.) Set it up front for any "full width /
stretch across the page" request — don't burn a browser DOM-climbing loop rediscovering it.

## Recipe: `text` component content escaping (`{{{triple-brace}}}`)

The `text` component renders its `content` via Mustache. `{{double-brace}}` **HTML-escapes** the
value — so a date/path like `2023/11/17` renders as `2023&#x2F;11&#x2F;17`. Use **triple-brace**
`{{{creationTime}}}` for raw/unescaped output. (Don't also apply a `date-time` `dataType` on top of
triple-brace — that double-renders the value.)
