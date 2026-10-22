---
name: shesha-design-system
description: Use whenever a Shesha 0.46 form or page needs to LOOK like a specific design or brand — "make it match the design", "apply our branding", "style this form", "it doesn't look good", "it looks different after the upgrade", or any request for a polished, consistent visual result rather than just working fields. Maps design tokens (colour, type, spacing, radius, shadow, status lifecycle) onto Shesha's app-level theme setting and per-component v7+ style blocks (desktop/tablet/mobile border, background, font, dimensions, shadow, stylingBoxJson) for React 19 / Ant Design 6, and restores a pre-0.46 look when load-time migrations inject defaults. Themeable, ships the requirements-studio example theme and accepts new brand token files. Pairs with shesha-form-edit (which builds structure) and is orchestrated by shesha-claude-designer. Do NOT use it to author structure/components, wire CRUD, or fix runtime errors — that is shesha-form-edit's job.
---

# Shesha Design System (0.46)

## Overview

Turn "make it look good / match the design" into **concrete Shesha style values**. This skill owns *how forms look*, never *what they contain*. It reads a brand **theme token file** and emits the exact props Shesha 0.46 components expect, in two layers that must BOTH be applied:

1. **App theme (set once):** `Shesha.ThemeSettings` — brand primary + semantic colours, layout canvas, sidebar mode, label layout, and `components.<type>` default styles. It is **narrow**: it is not an Ant Design `ConfigProvider` object, the font is forced to Inter Variable, and radius/heights/borders cannot be set there. Mechanism and limits: [references/app-theme.md](references/app-theme.md).
2. **Per-component v7+ style blocks (per form):** surfaces, cards, headers, density, chips, bands, rails — `desktop`/`tablet`/`mobile` `border`, `background`, `font`, `dimensions`, `shadow` and `stylingBoxJson`. Recipes: [references/component-recipes.md](references/component-recipes.md).

A form looks "cheap" when only one layer is done. A form looks "different after the upgrade" because 0.46 **migrations inject default style blocks** into older markup — see [references/restoring-pre-046-look.md](references/restoring-pre-046-look.md).

## When to use / not

- **Use** for visual goals: match a design, apply branding, raise polish, fix "doesn't look good", restyle a working form, or get an upgraded form back to its old look.
- **Don't use** to add fields, wire buttons/CRUD, resolve modelType, or debug runtime errors (-> `shesha-form-edit`); or to choose the layout (-> `shesha-design-comprehension`).

## Steps

1. **Pick the theme — default vs custom brand.** Theme token files live in `plugins/shesha-developer-0-46/skills/shesha-design-system/assets/themes/<brand>.tokens.json`:
   - **No brand named, or a generic Shesha app -> the shipped default `shesha`** (`shesha.tokens.json`): Cobalt `#003BB2` interactive anchor, Navy `#000E8E` sidebar/header chrome, Inter Variable, Nero `#181818` ink, white cards on Athens Grey `#F8F8F9`, radii 2/4/6/8, **borders-not-shadows**, five operational status tones, plus `$themeSettings` (the value for `Shesha.ThemeSettings`) and `$antdTheme` (reference ConfigProvider theme for custom React pages).
   - **User names a brand / hands you tokens / an app-specific `<brand>.tokens.json` exists -> that brand.** The shipped example of a custom brand is `requirements-studio` (deep green `#0d685a`, Inter, white cards on `#f0f2f5` canvas, radii 4/6/12, a six-step status lifecycle). It stores no antd keys, so nothing in it is invalid on antd 6; derive `application.primaryColor` etc. from its `roles`.
   - **A design introduces a genuinely new brand -> author it in that folder:** copy `shesha.tokens.json` -> `<brand>.tokens.json`, swap the values, **keep every key name identical** so recipes, block overlays and `roles.*` resolve unchanged.
   Load the file with Read; resolve `roles.*` (role -> token path) before authoring.
2. **Apply the app theme (once per project).** Set the `$themeSettings` object through Configuration Studio / the settings API ([app-theme.md](references/app-theme.md)). Expect it to move colours and the canvas only. Skip when the app theme is already right.
3. **Apply per-component v7+ blocks.** For each component the design touches, copy the matching recipe from [component-recipes.md](references/component-recipes.md), fill it with resolved theme values via [token-to-prop-mapping.md](references/token-to-prop-mapping.md), mirror across desktop/tablet/mobile, and **stamp the component's current 0.46 `version`** so a load-time migration does not inject defaults over your values. Always write `font.type`, `font.size` (number), and `stylingBoxJson` (object).
4. **Restoring a pre-0.46 look.** If the complaint is "it changed after the upgrade": identify which migration injected what, write explicit values and choose the version strategy per [restoring-pre-046-look.md](references/restoring-pre-046-look.md). Never open-and-save an old form in the 0.46 designer to "refresh" it — that persists the injected defaults.
5. **Verify on the running app.** Hard-refresh (or clear the cached form), then read **computed styles** by `[data-sha-c-name="x"]` — not screenshots, not DOM position. Reload a second time: a fix that disappears means a migration step re-ran. Probe selectors that survive antd 6 are listed in `shesha-design-comprehension`.
6. **Audit (optional).** Given a screenshot + the theme, return **prop-level fixes** (component, prop path, current vs target, one-line reason), ordered by impact. Suggestions, not blockers. Rubric: [references/appearance-quality.md](references/appearance-quality.md) (the appearance companion to `shesha-form-edit`'s construction `form-quality.md` — never override a construction guardrail).

General conventions every recipe respects (light-mode; scale-by-surface type with a 14px dense default; weight-by-role 400/500/600; surface elevation = hairline **+ the brand's own card shadow, if any**; splits are flex rows sized via `dimensions.width`, never `columns`; sentence-case labels; semantic-colour-for-status-only): [references/shesha-design-standards.md](references/shesha-design-standards.md).

## Shesha-specific gotchas (0.46)

- **Padding/margin:** `stylingBoxJson` object `{ "_type":"styleBox", "paddingTop":16, ... }` is canonical; the legacy `stylingBox` JSON string is only a fallback. `text` v7 reads only `desktop.stylingBoxJson` and `desktop.font.size` (px number) — the old `fontSize` Tailwind token and padding presets are ignored.
- **Font:** the app font is Inter Variable and unsettable; component defaults still say `Segoe UI` and a stored `font.type` wins. Write `font.type` explicitly.
- **Per-side borders** need `borderType:"custom"`. A card surface is a white container with a white background. Brand primary on buttons comes from the **app theme** — don't override per-button. Code-carrying props are `{ "_mode":"code", "_code":"..." }`.
- **Containers:** outer box takes dimensions/border/background/shadow/margin; inner box takes padding/layout/overflow. `calc()` widths hit wrapper and container both — prefer `100%` + `minWidth:0` next to a fixed-px rail ([capability-matrix.md §flex-split](references/capability-matrix.md#flex-split)).
- **Hidden components are not mounted** (a hidden `htmlRender` never injects CSS); `htmlRender` sanitises `<style>` away unless `sanitize:false`; antd 6 renamed tabs/collapse DOM classes — use `data-sha-c-*` anchors.
- **Migrations overwrite:** datatable v14/15/23/25/27 force `striped`/`hoverHighlight` on every load until the stored version is >= 31.

## Mechanics & capability (this skill owns the v7+ style system)

- **Style-block shapes** (border / background / font / dimensions / shadow / stylingBoxJson, per breakpoint), the **5-channel precedence** (including the legacy `style` JS-string footgun that overrides everything), and where each channel lands in the DOM: [styling-v7-mechanics.md](references/styling-v7-mechanics.md) + [style-channels.md](references/style-channels.md).
- **Capability matrix** — which channel RENDERS per component. Measured on 0.45; 0.46 deltas are source-read or proven and flagged `reverify046` where unproven: [capability-matrix.md](references/capability-matrix.md). **Never author a style on a channel the matrix marks `no-op`.**
- **Flex-split sizing** — the one canonical statement: [capability-matrix.md §flex-split](references/capability-matrix.md#flex-split).
- **Migrations that inject defaults, and how to override them:** [restoring-pre-046-look.md](references/restoring-pre-046-look.md).

## Non-negotiables

- No custom CSS/React/HTML in forms except a deliberate, documented `htmlRender` carrier — everything else is component props on Shesha JSON.
- Tokens live in theme files, never inline hexes.
- **Style, don't restructure** — if the structure is wrong, route back to `shesha-form-edit` (layout is owned by `shesha-design-comprehension`); never move containers here.
- Mirror style blocks across breakpoints; verify against the running 0.46 app (mechanics are version-dependent; do not trust a 0.45 note marked `reverify046`).
- This skill produces styled JSON/edits; it does **not** own auth/push/save — `shesha-form-edit` does. On 0.46 there is no publish step: a saved form is live immediately, so get explicit go-ahead before pushing a restyle to a shared environment.

## Relationship to the other skills

| Concern | Skill |
|---|---|
| Ingest design, plan, orchestrate, verify | `shesha-developer-0-46:shesha-claude-designer` |
| Comprehend design -> measured layout blueprint + placement verification | `shesha-developer-0-46:shesha-design-comprehension` |
| Build structure, CRUD, validate, push | `shesha-developer-0-46:shesha-form-edit` |
| **Map tokens -> app theme + per-component v7+ style blocks; restore pre-0.46 looks** | **this skill** |
