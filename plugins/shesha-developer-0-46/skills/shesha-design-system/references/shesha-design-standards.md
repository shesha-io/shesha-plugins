# Shesha design standards (brand-agnostic)

General conventions for how Shesha 0.46 (React 19, Ant Design 6.x, light-mode) applications should be designed and styled — distilled from the Shesha Design System reference (A. Slavchov, Senior UI/UX). These are the *standards* the comprehension layer annotates blueprints with and the styling layer enforces; they hold **regardless of brand**. A brand's concrete hex/type values live in its `*.tokens.json` — the shipped **default `shesha.tokens.json`**, or a custom brand like `requirements-studio.tokens.json` — not here.

## Foundations

- **Light mode only.** No dark mode.
- **Type — scale by surface, weight by role.** Dense data-entry (form fields, table cells, attribute rows) uses **14px**; for other surfaces pick the scale token that matches the role — 12 caption, 16 card heading, 18 hero/summary value, 20 section heading, 24 page title. Don't flatten everything to 14, and don't inflate dense data-entry past 14. **Weight by role:** body / values **400**; field labels, card & section headers **600**; micro-labels, status-chip text, table-cell emphasis **500**; **700** only where the design's title is genuinely bold. (All four live in the brand `type.weights` — use the token, don't invent a weight.) Never pure black for text — use the brand's near-black ink.
- **Surface elevation — border-forward; shadow is a brand decision.** Every white card/panel always carries a hairline 1px border (`lines.border`) on all breakpoints. Whether it *also* carries a shadow is read from the brand's `shadow.card` token, not assumed: some brands are **border-forward** and render cards essentially flat — the **Shesha default** does this (`shadow.card` is a whisper `0 1px 4px rgba(0,0,0,0.08)` or `none`; structure comes from the line, not the shadow) — while others pair the hairline with a visible `desktop.shadow {offsetX:0, offsetY:1, blurRadius:2–4, spreadRadius:0, color:…}`. Reserve the heavier `shadow.overlay` for floating surfaces only (modals, popovers, dropdown menus). Rows separate with hairlines (`lines.divider`). Never rely on a shadow *instead of* a border, and never use heavy/decorative shadows.
- **Surface proportion:** the dominant surface is the muted page canvas (~30%), with white cards on top — most of a page is *not* white. Brand-primary is the single interactive anchor (CTAs, links, active states, focus rings); deep/navy or dark-brand adds chrome depth.
- **4px spacing grid:** 4/8/12/16/20/24/32/40/48. Field gap 16px vertical; 24px between sections; card padding 16 (compact) / 24 (default).
- **Radius:** ~6px for controls (buttons/inputs/selects), ~8–12px for cards/panels, pill for status badges.

## AntD 6.x token mapping (what is settable, and where)

On Shesha 0.46 the app theme (`Shesha.ThemeSettings`) carries only `application.{primary,info,success,warning,error}Color`, `layoutBackground`, `sidebar`, label layout, and `components.<type>` defaults; `ThemeProvider` builds the antd theme from those and **forces `fontFamily` to Inter Variable** ([app-theme.md](app-theme.md)). The full token set below is therefore a *reference vocabulary* — it applies to custom React pages with a nested `ConfigProvider` and to deciding per-component values, not to the settings screen:
`colorPrimary / colorPrimaryHover / colorPrimaryActive / colorPrimaryBg`, the semantic set (`colorSuccess/Warning/Error/Info` + `Bg/Border`), neutrals (`colorText/TextSecondary/TextTertiary`, `colorBgLayout` = canvas, `colorBgContainer` = white, `colorBorder/colorBorderSecondary`), type (`fontSize=14/fontSizeLG=16/...`, `fontWeightStrong=600`, line-heights), shape (`borderRadius=6/LG=8`, `controlHeight=32/SM=24/LG=40`), and component tokens (Button/Input/Select/Table/Card/Tabs/Menu). A form looks "cheap" when only per-component blocks are set (primary still default blue) or only the app theme is set (no surface/card treatment) — apply **both** layers, and accept that radius/heights live in the blocks.

**Typography (0.46):** default family is the bundled **Inter Variable** (`interFont.generated.css`), accepted as the framework default. Component defaults still say `Segoe UI`; write `font.type` explicitly in every block you author so chrome and content agree.

## Component conventions

- **Buttons:** primary = brand fill, white 600 text, radius 6; default = white, hairline border, brand-coloured border/text on hover; danger = error fill; ghost/link = transparent, brand text. Sizes 24/32/40.
- **Inputs/Select/Date:** white bg, 1px border, radius 6, 4×12 padding, 14px; focus = brand border + 4px focus ring; error = error border + error ring; disabled = canvas bg + tertiary text. Label 14/600, required asterisk in error colour, helper 12px, validation 12px error.
- **Cards/Panels:** white bg, hairline border, radius 8–12, **plus the brand card shadow only if the brand defines one** (the Shesha default is border-forward — flat; see Surface elevation); panel header on the alt surface with a bottom hairline, 12×16 padding, 14/600; body 16 padding.
- **Data table:** header row on the alt surface, 14/600, 2px bottom border; body rows white with 1px row borders; row hover = brand-tint; selected = brand-subtle; cell 14/400, 12×16 padding.
- **Status badges/pills:** pill radius, 12px/500, 2×8 padding; colour from the **status lifecycle** in the brand tokens (bg/fg/border per status). Always pair colour with a text label — never colour alone.
- **Tabs:** inactive 14/400 secondary; active = brand text + 2px brand ink-bar.
- **Section separators / micro-labels:** uppercase 11–12/600 tertiary, letter-spacing ~0.06em.
- **Alerts/banners:** tinted bg + 4px left border in the semantic colour + matching icon.

## Voice & copy

- Labels in **sentence case** ("First name", not "First Name"). Actions verb-first ("Save changes", not "OK"). Validation specific ("Enter a valid email address"). Mark **required** with an asterisk; never mark optional. Placeholders are examples ("e.g. …"), not instructions, and never replace a label.

## Anti-patterns (never)

- Pure black `#000` text; inventing weights outside the brand `type.weights`; body >14px in **dense data entry** (larger scale tokens on reading surfaces — titles, headers, hero values — are correct, not an anti-pattern).
- **Heavy / decorative** drop shadows — large blurry shadows that don't match the brand token scale. (A card's subtle elevation shadow from the brand `shadow` token is expected and correct; only oversized/decorative shadows are banned.)
- Using a brand's accent/semantic colours decoratively — semantic colours are operational status signals only.
- Placeholder used as a label; removing focus rings (accessibility is non-negotiable).
- Colour alone to convey status (always pair with icon/text).

## How comprehension uses this

When `shesha-design-comprehension` annotates a blueprint region with a `recipe:` (e.g. `card`, `section-header`, `kib-strip`, `status-chip`), that recipe resolves through these standards + the brand's tokens into concrete v7 style blocks via [component-recipes.md](component-recipes.md) and [token-to-prop-mapping.md](token-to-prop-mapping.md).
