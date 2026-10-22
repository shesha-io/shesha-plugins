# Applying the app-level theme (set once per project)

The first of the two styling layers. Set the brand colours and layout shell at the **application theme** so the whole portal inherits them — then per-component blocks handle everything the theme cannot express.

## What the 0.46 theme setting actually is

`Shesha.ThemeSettings` (client-specific, `IFrontendSettings.Theme`; editor form `theme-settings`) deserialises to `IConfigurableTheme` (`providers/theme/contexts.ts`, `Shesha.Framework/Configuration/ThemeSettings.cs`). It is **not** an Ant Design `ConfigProvider` theme object:

| Field | Reaches | Notes |
|---|---|---|
| `application.primaryColor` | antd `colorPrimary` **and** `colorLink` | buttons, links, active tab ink-bar, focus ring, checked states |
| `application.infoColor` / `successColor` / `errorColor` / `warningColor` | `colorInfo` / `colorSuccess` / `colorError` / `colorWarning` | each applied only when non-blank |
| `layoutBackground` | main/horizontal layout content background | the page canvas |
| `sidebar` (`dark`/`light`) | side menu theme | |
| `sidebarBackground` | declared, **not consumed** by the 0.46 core shell (no reader in `shesha-reactjs/src`) | verify live before relying on it |
| `text.default` / `text.secondary` | read by a few components (colour picker); not a global text colour | |
| `labelSpan` / `componentSpan` / `labelAlign` / `layout` / `colon` | form-item label layout defaults | |
| `components.<type>` | **per-component-type default style model**, deep-merged under each component's own `desktop` block | the one lever that restyles a whole component type at once |

`ThemeProvider` (`providers/theme/index.tsx`) then builds the antd theme itself: `cssVar.prefix 'ant'`, `token.fontFamily = 'Inter Variable'` (forced, plus a `body{font-family}` baseline), `Menu.itemHeight`, `Tabs.zIndexPopup 2000`, and the colours above. **Every other antd token in a brand's `$antdTheme` block (radius, control heights, `colorBgLayout`, `colorBorder`, component tokens, ...) cannot be delivered through the theme setting.** The same goes for the font: it is not a setting.

Consequences:

- The brand's `$antdTheme` object is a **reference**, valid token names verified against antd 6.6.4, for (a) custom React pages that wrap content in their own nested `ConfigProvider`, (b) an app that owns its provider, or (c) a deliberate frontend-source change. Do not paste it into `Shesha.ThemeSettings`.
- The designer's claim that "custom pages inherit radius/font from `ConfigProvider`" is only true for the colours above and the forced Inter font; radius and the rest stay antd 6 defaults unless the page sets them.
- Radius, heights and borders on Shesha components come from the per-component blocks (or `components.<type>`), not the app theme.

## The value to set

Use the brand file's `$themeSettings` block (see `shesha.tokens.json`) as an OBJECT:

```json
{
  "application": { "primaryColor": "#003BB2", "infoColor": "#003BB2", "successColor": "#007E00", "warningColor": "#FF6600", "errorColor": "#D61111" },
  "sidebar": "dark",
  "layoutBackground": "#F8F8F9",
  "text": { "default": "#181818", "secondary": "#333333" },
  "labelSpan": 6, "componentSpan": 18,
  "components": {}
}
```

Derive it for any brand from its `roles`: `appPrimary -> application.primaryColor`, `pageBg -> layoutBackground`, semantic palette -> the four colours, `navBg -> sidebarBackground`. A brand file with no `$themeSettings` (e.g. `requirements-studio`) needs this derivation, nothing else; its token names are brand-neutral and contain no antd keys.

Set it through **Configuration Studio -> Settings -> Default UI -> Frontend -> Theme settings** (or the Theme/Components settings screens, whose "components" pages write `components.<type>`), or the settings API with header `sha-frontend-application: default-app` and the value as an object (not a JSON string). Never edit `ConfigProvider`, the app provider, or layout source to theme.

## `components.<type>`: set a look once for a whole type

`components.<type>` is a flat style model (`border`, `background`, `font`, `dimensions`, `shadow`, `stylingBoxJson`), merged as: component `getDefaultStyles()` < `components[type]` < the component's `desktop` < the active device block (`formComponentModelPreparer.tsx:51-77`). Use it for type-wide defaults (every `textField` radius 6 and height 32; every `datatable` header fill) instead of stamping the same block on hundreds of nodes. Rules:

- Only reworked components (`allowInherit:true`, 43 types) read it. Others ignore it.
- A component that carries its own explicit `desktop` value wins, per key. A migration that injects a default into `desktop` also wins over the theme — see [restoring-pre-046-look.md](restoring-pre-046-look.md).
- Keep it sparse. A theme-level block that fights block-library visuals is a regression you cannot see in the markup.
- Verify per type on the running app; this lever is source-read, not yet measured on 0.46.

## Set expectations first: the app theme moves little on a configured form

Every component an authored form ships carries explicit `desktop`/`tablet`/`mobile` values, so the theme is the *lowest*-precedence input on the page ([style-channels.md](style-channels.md)). What it reaches: primary-button fill, link colour, active tab ink-bar, focus ring, page canvas, semantic colours. What it does not: type scale, spacing rhythm, surface treatment (card background, hairline, radius, shadow), table chrome, status chips, page shell. **Set the theme once for chrome, then stop**; fidelity comes from the pre-styled blocks in `shesha-form-edit/assets/blocks/` (values baked from [`../assets/block-styles/`](../assets/block-styles/) + the brand tokens).

## When to apply vs skip

- **Apply** when establishing a brand, or when the complaint is "buttons/links/active states are the wrong colour".
- **Skip** for a one-off single-form tweak where the theme is already correct.

## Verify

In the running app: a primary button, a link, an active tab ink-bar and a focus ring are the brand primary; the page background is `layoutBackground`; text is Inter. Reload hard (or clear the IndexedDB form/settings cache from `/favicon.ico`) after changing settings. Check by computed style on `[data-sha-c-type="button"]` etc., not by eye.
