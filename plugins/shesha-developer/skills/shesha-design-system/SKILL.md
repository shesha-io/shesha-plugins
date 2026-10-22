---
name: shesha-design-system
description: Use whenever a Shesha form or page needs to LOOK like a specific design or brand — "make it match the design", "apply our branding", "style this form", "it doesn't look good", "match Requirements Studio / the Figma / the Claude design", or any request for a polished, consistent visual result rather than just working fields. Maps design tokens (colour, type, spacing, radius, shadow, status lifecycle) onto Shesha's app-level Ant Design theme and per-component v7 style blocks. Themeable, ships the requirements-studio theme and accepts new brand token files. Pairs with shesha-form-edit (which builds structure) and is orchestrated by shesha-claude-designer. Do NOT use it to author structure/components, wire CRUD, or fix runtime errors — that is shesha-form-edit's job.
---

# Shesha Design System

## Overview

Turn an abstract "make it look good / match the design" into **concrete Shesha style values**. This skill owns *how forms look*, never *what they contain*. It reads a brand **theme token file** and emits the exact props Shesha components expect, in two layers that must BOTH be applied:

1. **App-level Ant Design theme (set once):** brand primary, base font family, base radius, semantic colours, neutrals — so the whole portal inherits them. Mechanism: [references/app-theme.md](references/app-theme.md). Don't repaint every button per form.
2. **Per-component v7 style blocks (per form):** surfaces, cards, section headers, density, status chips, header bands, rails — the structural/visual treatment the global theme can't express. Recipes: [references/component-recipes.md](references/component-recipes.md).

A form looks "cheap" when only one layer is done (AntD still default-blue, or no surface treatment). Apply both.

## When to use / not

- **Use** for visual goals: match a design, apply branding, raise polish, fix "doesn't look good", restyle a working form.
- **Don't use** to add fields, wire buttons/CRUD, resolve modelType, or debug runtime errors (→ `shesha-form-edit`); or to choose the layout (→ `shesha-design-comprehension`).
- **After a framework upgrade**, prefer a theme-level fix (Theme settings and Components defaults) before a per-form `shesha-upgrade-reconciler` fleet: one settings write needs no per-form export.

## Steps

1. **Pick the theme — default vs custom brand.** Theme token files live in one folder: `plugins/shesha-developer/skills/shesha-design-system/assets/themes/<brand>.tokens.json`. Choose which brand applies:
   - **No brand named, or a generic Shesha app → use the shipped default `shesha`** (`shesha.tokens.json`): Cobalt `#003BB2` interactive anchor, Navy `#000E8E` sidebar/header chrome, system-ui type, Nero `#181818` ink, white cards on Athens Grey `#F8F8F9` canvas, radii 2/4/6/8, **borders-not-shadows**, five operational status tones, and a ready-to-apply `$antdTheme` ConfigProvider block. This is the fallback whenever the user does not specify a brand.
   - **User names a brand / hands you brand tokens / an app-specific `<brand>.tokens.json` already exists → use that brand.** The shipped example of a custom brand is `requirements-studio` (a brand green `#0d685a`, Inter, white cards on `#f0f2f5` canvas, radii 4/6/12, RsStatus lifecycle Draft→Confirmed→InBuild→Delivered→Rejected→OnHold).
   - **A design introduces a genuinely new brand → author it in that same `assets/themes/` folder:** copy the default `shesha.tokens.json` → `<brand>.tokens.json`, swap the values (palette / type / spacing / radius / shadow / statusLifecycle / roles, and the `$antdTheme` block), but **keep every key name identical** so all recipes, block-overlays and `roles.*` resolve unchanged. Then treat the new file as the active brand.

   Load the chosen file with Read; resolve `roles.*` (role → token path) before authoring.
2. **Apply the app-level theme (once per project).** Set brand primary, font, base radius so the portal inherits them. [app-theme.md](references/app-theme.md). Skip only for a one-off tweak where the app theme is already correct; never skip when the complaint is "buttons/links are the wrong colour".
3. **Apply per-component v7 blocks.** For each component the design touches, copy the matching recipe from [component-recipes.md](references/component-recipes.md) and fill it with the theme's resolved values; map token→exact prop via [token-to-prop-mapping.md](references/token-to-prop-mapping.md). Mirror the block across desktop/tablet/mobile unless the design is genuinely responsive.
4. **Audit (optional).** Given a screenshot + the theme, return **prop-level fixes** (component, prop path, current vs target, one-line reason), ordered by impact. Suggestions, not blockers. Grading rubric: [references/appearance-quality.md](references/appearance-quality.md) (the appearance companion to `shesha-form-edit`'s construction `form-quality.md` — never override a construction guardrail).

General Shesha conventions every recipe respects (light-mode; scale-by-surface type with a 14px dense default; weight-by-role 400/500/600; surface elevation = hairline **+ subtle card shadow**; splits are flex rows sized via `dimensions.width`, never `columns`; sentence-case labels; semantic-colour-for-status-only): [references/shesha-design-standards.md](references/shesha-design-standards.md).

## Shesha-specific gotchas

- `stylingBox` is a JSON **string** (padding/margin keys only). Text components take `fontSize` (Tailwind class) + `fontWeight` as direct props. Per-side borders need `borderType: "custom"`. A card surface is a white container with a white background. Brand primary on buttons comes from the **app theme** — don't override per-button. Code-carrying props are objects `{ "_mode": "code", "_code": "…" }`.

## Mechanics & capability (this skill owns the v7 style system)

- **v7 style-block shapes** (border / background / font / dimensions / shadow / stylingBox, per `desktop`/`tablet`/`mobile`), the **5-channel precedence** (including the legacy `style` JS-string footgun that overrides everything), and where each channel lands in the DOM: [styling-v7-mechanics.md](references/styling-v7-mechanics.md) + [style-channels.md](references/style-channels.md). (These moved here from `shesha-form-edit` — appearance is this skill's job.)
- **Capability matrix** — which channel actually RENDERS per component, measured live and version-stamped: [capability-matrix.md](references/capability-matrix.md). **Never author a style on a channel the matrix marks `no-op`.**
- **Flex-split sizing** — the one canonical statement: [references/capability-matrix.md §flex-split](references/capability-matrix.md#flex-split).

## Non-negotiables

- No custom CSS/React/HTML — everything is component props on Shesha JSON.
- Tokens live in theme files, never inline hexes.
- **Style, don't restructure** — if the structure is wrong, route back to `shesha-form-edit` (and the layout is owned by `shesha-design-comprehension`); never move containers here.
- Mirror style blocks across breakpoints; verify against the running app (mechanics are version-dependent).
- This skill produces styled JSON/edits; it does **not** own auth/push/publish — `shesha-form-edit` does.

## Relationship to the other skills

| Concern | Skill |
|---|---|
| Ingest design, plan, orchestrate, verify | `shesha-developer:shesha-claude-designer` |
| Comprehend design → measured layout blueprint + placement verification | `shesha-developer:shesha-design-comprehension` |
| Build structure, CRUD, validate, push | `shesha-developer:shesha-form-edit` |
| **Map tokens → app theme + per-component v7 style blocks** | **this skill** |
