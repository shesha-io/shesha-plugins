# Container / card / columns / tabs

Layout components. All keep `editMode: "inherited"` or omit it (no interactive surface).

---

## container

Layout wrapper. Children go in `components: []`. Direction defaults to column.

```json
{
  "id": "...",
  "type": "container",
  "label": "Personal Info",
  "direction": "vertical",
  "components": [ /* children */ ],
  "desktop": {
    "dimensions": { "width": "100%" },
    "flexDirection": "column"
  }
}
```

Per-breakpoint settings live under `desktop` / `tablet` / `mobile` keys.

Use containers as semantic divs for grouping related rows (consents block, action row, footer row). See [layout.md](layout.md) for the full house pattern.

### Per-row / dynamic images — a container, not the `image` component

**The `image` component cannot bind its `url` to data.** Its `ownProps` carry a static `url` string and no `propertyName` or entity binding, so there is no way to make it show a different picture per row or per record. Reaching for it first and discovering this is a 15–30 minute detour.

For a datalist card thumbnail, a detail-page hero, or anything else where the image comes from data, use a plain `container` sized appropriately with a **code-mode `style`** prop:

```js
// container.style — code mode; `data` is the row/record in scope
return {
  backgroundImage: 'url(' + data.thumbnailUrl + ')',
  backgroundSize: 'cover',
  backgroundPosition: 'center',
  backgroundColor: '#f0f0f0'   // fallback while loading / when null
};
```

Build the URL with **string concatenation, not template literals** — the whole thing has to survive `JSON.stringify` into the form markup ([scripts.md](scripts.md)).

**Don't let this leak into your spacing.** The inline `style` prop wins over *all* structured style blocks, silently discarding any `desktop.background` / `border` / `shadow` you also set on that node. Use `style` **only** for the background-image itself; padding, margin and spacing on the same or sibling containers still belong in the structured `stylingBox` / `desktop.*` channels.

---

## page shell — the mandatory outer card on EVERY page-level form

**Every page-level form is wrapped in one `card`, and every other component on that page goes inside its `content.components`.** Nothing else sits at `root`. The shell is invisible chrome, configured exactly three ways:

| Property | Value | Why |
|---|---|---|
| `hideHeading` | `true` | suppresses the card's own title row — the page's real title is a `text` inside |
| `className` | `"sha-page"` | the app-level page class the portal styles against |
| border | `style: "none"` on **base and all three breakpoints** | the shell frames the page; a visible box around everything reads as a stray panel |

Plus `background #fff`, `radius 8`, no shadow, `width 100%`, `height auto` + `minHeight fit-content`, `stylingBox {"marginBottom":"5"}`.

Ready to compose: **[`assets/blocks/page-shell.block.json`](../../assets/blocks/page-shell.block.json)** — insert the page body into its `content` slot. Derived from the approved `boxfusion.test/bookings-table` revision 2.

**Two traps that revision itself contains**, so don't copy a live page blindly:

- The border was cleared on `desktop` only; `tablet`, `mobile` and the base were left `style: "solid" #d9d9d9`. Breakpoint blocks override base *per key*, so tablet and mobile still draw a 1px box. Clear it in all four places.
- `height` was a fixed `"30px"` on all breakpoints. On a wrapper holding an entire page that is wrong — use `auto` with `minHeight: "fit-content"`.

Typical body order inside the shell: title band (title + subtitle) → `dataContext` → toolbar → table/content → pager. Spacing and type come baked into the blocks — see [block-library.md](../block-library.md).

## card

Shesha's card component — a bordered, rounded, optionally-shadowed white box. **Children do NOT go in `components`** — they go in `content.components`. The card has two slots:

```json
{
  "id": "...",
  "type": "card",
  "propertyName": "myCard",
  "componentName": "myCard",
  "parentId": "...",
  "header": {
    "id": "...",
    "components": []          // usually empty for full-page forms
  },
  "content": {
    "id": "...",
    "components": [ /* the actual children */ ]
  }
}
```

**Common bug**: pushing children directly onto `card.components` and watching them silently disappear from the rendered output. Walk + push always go through `card.content.components`.

When walking the tree: recurse into both `header.components` and `content.components`. When updating ids: both slots' nested `id` keys must be regenerated coherently with their children's `parentId`.

The card's outer width defaults to its parent's width. To constrain it, set `desktop.dimensions.maxWidth` on the card itself, or wrap it in a fixed-max-width inner container.

---

## columns — LEGACY, do not author

> **You will see `columns` in existing forms and in the captured seeds; do not add new ones.**
> Splits are flex `container` rows sized via `desktop.dimensions.width` — the rule is canonical in
> [`capability-matrix.md`](../../../shesha-design-system/references/capability-matrix.md)
> (`crossCuttingRules`) and `validate-blocks.js` fails any block containing a `columns`. This
> section stays so you can read and migrate legacy markup.

Two-up / three-up layouts. `columns` array has child slots:

```json
{
  "id": "...",
  "type": "columns",
  "columns": [
    { "id": "...", "flex": 12, "components": [ /* left */ ] },
    { "id": "...", "flex": 12, "components": [ /* right */ ] }
  ],
  "gutterX": 8,
  "gutterY": 8
}
```

**Total `flex` must be 24** across direct columns. (`12+12`, `8+8+8`, `6+6+6+6`, `16+8`.)

For a simple inline text + link row, prefer a sub-`container` with `flexDirection: "row"` and `alignItems: "baseline"` — wraps cleaner on narrow viewports than a `columns` does.

---

## tabs

```json
{
  "id": "...",
  "type": "tabs",
  "tabs": [
    {
      "id": "...",
      "key": "personal",
      "title": "Personal",
      "components": [ /* tab content */ ]
    },
    {
      "id": "...",
      "key": "business",
      "title": "Business",
      "components": [ /* ... */ ],
      "visible": { "_mode": "code", "_code": "return data?.accountType === 'Corporate';", "_value": true }
    }
  ],
  "defaultActiveKey": "personal"
}
```

Per-tab `visible` (0.46 tabs v11; the old per-tab `hidden` is migrated to it) lets you conditionally show tabs (IPropertySetting wrapper - see [form-shape.md](form-shape.md)). Per-tab `className` lands on the antd 6 pane element `.ant-tabs-content`. Custom CSS must target the antd 6 DOM (`.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content`) or the `data-sha-c-*` anchors - [../render-hazards-046.md](../render-hazards-046.md) H7. `selectMode: "readOnly"` is migrated to per-tab `editMode: "disabled"`.

**Visual style:**

| Prop | Values | Effect |
|---|---|---|
| `tabType` | `"card"` / `"line"` | `card` = boxed tabs; `line` = underline style |
| `tabPosition` | `"top"` | set alongside `tabType: "line"` |

When switching to `line` style, also remove any leftover `size: "small"` prop.

---

## collapsiblePanel

Expandable/collapsible section card with a header strip and content slot.

```json
{
  "id": "...",
  "type": "collapsiblePanel",
  "componentName": "panelMySection",
  "propertyName": "panelMySection",
  "label": "My Section",
  "version": 8,   // stored 8 migrates to 11 on load; fresh 0.46 panels (v11): header slot is rebuilt as a `headerLayout` container - read the shape from components-kb/collapsiblePanel.json before authoring
  "collapsible": "icon",
  "accent": true,
  "borderRadius": 12,
  "isDefaultExpanded": true,
  "header": { "id": "...", "components": [] },
  "content": {
    "id": "...",
    "components": [ /* section content */ ]
  }
}
```

**Key props:**
- `accent: true` — renders a 4px orange (`#fa8c16`) left-border strip on the panel header. Best visual signal for a branded section break on details pages.
- `collapsible: "icon"` — shows a chevron icon that collapses the panel. Set to `false` (boolean) to make always-open (cleaner on entity-details forms where users don't need to hide sections).
- `borderRadius: 12` — rounds the outer card corners; match the root card's radius token.
- `isDefaultExpanded: true` — ensures panel renders open on load (default; set `false` to start collapsed).

**Content slot**: children go in `content.components`, **not** `components`. Same slot rule as the `card` component.

**Walking the tree**: recurse into `content.components` (and `header.components` if you need to inject into the header strip).

---

## keyInformationBar

Stat-row component for 2–4 key facts across the top of a record page.

```json
{
  "id": "...",
  "type": "KeyInformationBar",
  "componentName": "keyinformationbarXXX",
  "version": 2,
  "columns": [
    {
      "id": "...",
      "components": [
        {
          "type": "container",
          "componentName": "containerLabelXXX",
          "components": [
            { "type": "text", "version": 7, "content": "Name",
              "desktop": { "font": { "color": "#6b7280", "type": "Segoe UI", "size": 11, "weight": "500" } } }
          ]
        },
        { "type": "textField", "propertyName": "name", "label": "Name",
          "desktop": { "font": { "color": "#111827", "type": "Segoe UI", "size": 15, "weight": "600" } } }
      ]
    }
  ]
}
```

**Structure**: each `column` has exactly two children — a `container` holding the **label text**, and a **value field** (`textField` or `switch`). Not the typical Shesha container pattern.

**Styling labels**: `desktop.font` `{ size: 11, weight: "500", color: "#6b7280" }` for muted gray (no legacy `fontSize` token).

**Styling values**: add `desktop.font` with `size: 15`, `weight: "600"`, `color: "#111827"` on the `textField` — makes the actual data pop.

**Card wrapper**: give the KIB component itself a `desktop` block with `border`, `background.color: "#ffffff"`, `shadow`, and `stylingBox` padding to turn it into a white stat-card (styling lives in `shesha-design-system` → `styling-v7-mechanics.md`).

---

## Section divider pattern

For a "Related Records" or section-heading strip above a tab group — style an existing `text` component with a v7 `desktop` block rather than wrapping it in a new container:

```json
{
  "type": "text",
  "version": 7,
  "content": "Related Records",
  "desktop": {
    "border": {
      "hideBorder": false,
      "borderType": "custom",
      "border": {
        "all": { "width": 1, "color": "#e5e7eb", "style": "none" },
        "top": {}, "bottom": { "width": 1, "color": "#e5e7eb", "style": "solid" },
        "left": { "width": 4, "color": "#fa8c16", "style": "solid" }, "right": {}
      },
      "radius": { "all": 0 }
    },
    "background": { "type": "color", "color": "#f9fafb" },
    "font": { "color": "#374151", "type": "Segoe UI", "size": 13, "weight": "700" },
    "stylingBoxJson": { "_type": "styleBox", "paddingTop": "10", "paddingBottom": "10", "paddingLeft": "16", "paddingRight": "16", "marginTop": "28", "marginBottom": "0" }
  }
}
```

Copy `desktop` to `tablet` and `mobile` as well. (0.46 text v7 reads `desktop.font.size` and `desktop.stylingBoxJson` - the legacy `fontSize` token / `stylingBox` string are ignored or mis-converted, [../render-hazards-046.md](../render-hazards-046.md) H8.) This creates a branded section-header strip that reads immediately as a visual separator — orange left accent + subtle gray band + bottom rule.

---

## Full-bleed header pattern (details pages)

Standard approach for a tinted header zone that spans the full card width:

**Correct approach (v2+):** Set the root container padding to `0` (top/sides) and let the header container own its own padding. No negative margins needed.

```
root container:  pt=0, pb=24, pl=0, pr=0
header container: pt=20, pb=20, pl=32, pr=32  ← owns its zone
content container: pt=16, pb=0, pl=32, pr=32   ← owns content zone
```

**Anti-pattern (avoid):** Negative-margin hack (root has padding, header uses `marginTop:-24, marginLeft:-32, marginRight:-32`). This works but is fragile — if the root padding changes, all offsets must be recalculated manually.

For the header left accent on the **title container** inside the header (title + status badge), use a custom v7 border block with `borderType: "custom"` and `left: { width: 4, color: "#fa8c16", style: "solid" }` — this creates the branded left-border signal without touching the full header background.
