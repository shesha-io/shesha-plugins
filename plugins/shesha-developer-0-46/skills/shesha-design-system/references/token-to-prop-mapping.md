# Token -> Shesha prop mapping (0.46)

How a brand token (from `<brand>.tokens.json`) becomes an exact Shesha value. Resolve `roles.*` first (role -> token path), then map. Two destinations: the **app theme** (`Shesha.ThemeSettings`, narrow — see [app-theme.md](app-theme.md)) and **per-component v7+ style blocks** (wide).

## App theme (`Shesha.ThemeSettings`) — only these reach the app

| Token / role | Setting field | Becomes (antd 6) |
|---|---|---|
| `brand.primary` (`appPrimary`) | `application.primaryColor` | `colorPrimary` + `colorLink` |
| `semantic.info` / `success` / `warning` / `danger` | `application.infoColor` / `successColor` / `warningColor` / `errorColor` | `colorInfo` / `colorSuccess` / `colorWarning` / `colorError` |
| `surfaces.canvas` (`pageBg`) | `layoutBackground` | layout content background (not antd `colorBgLayout`) |
| `accent.navy` / `navBg` | `sidebar` (`dark`/`light`); `sidebarBackground` is stored but unused by the core shell | |
| `ink.primary` / `ink.muted` | `text.default` / `text.secondary` | only a few components read these |
| component-type defaults | `components.<type>` (flat style model) | deep-merged under each component's `desktop` |

Not settable from the app theme on 0.46, so they go in per-component blocks (or, for custom React pages, a nested `ConfigProvider` using the brand's `$antdTheme`): `type.family` (app font is forced to Inter Variable), `radius.*`, control heights, `colorBgContainer`, borders, shadows, hover/active tints (`colorPrimaryHover/Active/Bg`).

Valid antd 6.6.4 names used by `$antdTheme` (verified in `antd/es/*/style`): global `colorPrimary`, `colorPrimaryHover`, `colorPrimaryActive`, `colorPrimaryBg`, `colorPrimaryBgHover`, `colorPrimaryBorder`, `colorPrimaryText*`, semantic `color{Success,Warning,Error,Info}{,Bg,Border}`, `colorText*`, `colorBg{Base,Container,Layout,Elevated,Spotlight}`, `colorBorder{,Secondary}`, `colorFill*`, `fontFamily`, `fontSize{,SM,LG,XL}`, `fontSizeHeading1-4`, `fontWeightStrong`, `lineHeight*`, `borderRadius{,XS,SM,LG}`, `controlHeight{,SM,LG}`, `padding*`, `margin*`, `motion*`, `boxShadow*`. Component tokens: Button `fontWeight` `primaryColor` `defaultColor` `defaultBorderColor`; Input `hoverBorderColor` `activeBorderColor` `activeShadow` `errorActiveShadow` `paddingInline`; Select `optionSelectedBg` `optionSelectedColor` `optionSelectedFontWeight` `optionActiveBg`; Table `headerBg` `headerColor` `headerSortActiveBg` `rowHoverBg` `rowSelectedBg` `rowSelectedHoverBg` `borderColor`; Card `headerBg`; Tabs `itemActiveColor` `itemHoverColor` `itemSelectedColor` `inkBarColor`; Menu `itemBg` `itemColor` `itemHoverBg` `itemHoverColor` `itemSelectedBg` `itemSelectedColor` `darkItemBg` `darkItemColor` `darkItemHoverBg` `darkItemSelectedBg`; Alert `borderRadius`. Global alias tokens may also be set inside a component block (`Button.borderRadius`). **Invalid and removed from the shipped theme:** Steps `colorFinish` and global `motionEaseIn` (neither exists in antd 6.6.4; antd silently ignores unknown keys, so they looked fine and did nothing).

## Per-component v7+ style blocks

| Token | Where it goes |
|---|---|
| `brand.primary` (section headings, brands that colour them) | text `desktop.font.color` on section-header text |
| `surfaces.surface` (white) | card container `desktop.background {type:'color', color}` |
| `surfaces.surfaceAlt` | card **header strip** `desktop.background.color` |
| `surfaces.surfaceMuted` | read-only field background |
| `lines.border` / `borderStrong` / `divider` | `desktop.border.border.all {width, style:'solid', color}` (hairline / input / row+section divider); per-side needs `border.borderType:"custom"` |
| `ink.primary` / `muted` / `soft` | text `desktop.font.color` (body / secondary / helper+placeholder) |
| `type.family` | `desktop.font.type` — **write it explicitly** (`"Inter Variable"`); component defaults say `Segoe UI` and a stored `font.type` wins over the app font |
| `type.scale.*` | `desktop.font.size` as a **number of px** (title 24, section 20 / header 16, body 14, micro 12). On `text` v7 this is the only size channel; the legacy `fontSize` Tailwind token is ignored |
| `type.weights.*` | `desktop.font.weight` (string: `"400"`/`"600"`) |
| `spacing.*` | `desktop.stylingBoxJson` — object `{ "_type":"styleBox", "paddingTop":16, ... }` (canonical on v7+; text v7 reads only this). Legacy `stylingBox` JSON **string** is converted only when `stylingBoxJson` is empty. Field gap 16, section gap 24, card pad 16/24 |
| `radius.md` (6) | controls `desktop.border.radius.all` (+ `radiusType:"all"`) |
| `radius.lg` (8-12) | cards `desktop.border.radius.all` |
| `shadow.card` | `desktop.shadow {offsetX:0, offsetY:1, blurRadius:4, spreadRadius:0, color}` on cards/panels (only if the brand defines one; Shesha default is border-forward) |
| `shadow.overlay` | `desktop.shadow` on **floating surfaces only** |
| `dimensions` | `desktop.dimensions {width, minWidth, maxWidth, height, minHeight, maxHeight}`; `minHeight:"fit-content"` stops squeeze |
| `statusLifecycle.badges.<status>` | `refListStatus` colours per item (bg/fg/border) — see the status-chip recipe |

Mirror each block across `desktop`, `tablet`, `mobile` unless the design is genuinely responsive; a breakpoint block overrides desktop per key. Stamp the component's **current** `version` (see [restoring-pre-046-look.md](restoring-pre-046-look.md) section 3) so a load-time migration does not inject defaults over your values.

**Worked micro-example — card with header strip:** container (`background.color`=surface, `border.all.color`=lines.border, `border.radius.all`=radius.lg) -> header text (`font.color`=sectionHeading role, `font.weight "600"`, `font.size` 16, `font.type "Inter Variable"`) on a child whose `background.color`=surfaceAlt with a bottom hairline -> body container `stylingBoxJson` padding 16.
