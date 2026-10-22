# Shesha Claude Designer — design → Shesha pipeline

Four skills that turn a **design** (a runnable prototype, a screenshot set, a Figma-style kit, or an HTML/JSX mock) into **on-brand, correctly-built Shesha forms** — and prove the result matches the design *by measurement*, not by eyeballing. The pipeline is **brand-generic**: theming is a token file you edit, not code you change.

```
design source ──▶ 1 ingest+tier ──▶ 2 comprehend (measured blueprint)
                                              │
                                              ▼
                                    3 plan {archetype, blocks[], recipes[]}
                                              │
                        ┌─────────────────────┴─────────────────────┐
                        ▼                                            ▼
            4a STRUCTURE (shesha-form-edit)            4b APPEARANCE (shesha-design-system)
            compose blocks, wire CRUD, push            resolve token overlays onto the built form
                        └─────────────────────┬─────────────────────┘
                                              ▼
                          5 verify: structural · PLACEMENT diff · visual
                                              │  (mismatch → route back)
                                              ▼
                                        on-brand screen
```

---

## The four skills and their responsibilities

The whole point of the rework is a **clean responsibility split** — each skill owns one thing and is forbidden from the others' jobs. That is what keeps the build correct *and* cheap (you never read appearance docs to build structure, or read a 25K-line seed to add a field).

| Skill | Owns | Must NOT |
|---|---|---|
| **`shesha-claude-designer`** (conductor — start here) | Ingest the design, detect fidelity tier, sequence the screens, plan each as `{archetype, blocks[], recipes[]}`, orchestrate the other three, gate on verification | Author form JSON · pick colours · push to the backend |
| **`shesha-design-comprehension`** | Turn each screen into a **measured layout blueprint** (grid columns/spans, nesting, tab assignment, bindings, a placement `assertions` block); re-measure the built form and **diff** it against the blueprint (the placement gate) | Author JSON · push |
| **`shesha-form-edit`** | **Structure only**: build native components, wire CRUD, validate, and the **single push path**; **compose the block library** (small correct fragments) instead of mutating giant seeds | Apply v7 appearance blocks · author the `columns` component · read styling docs during a structural build |
| **`shesha-design-system`** | **All appearance**: the app-level Ant theme, the **brand token file**, per-component v7 style recipes, block **style-overlays**, and the empirical **capability matrix** | Author structure · wire CRUD · push |

---

## How they tie together (the flow)

1. **Ingest** (`shesha-claude-designer`) — read the design source; extract the token set + screen list. *Run* a compiled prototype and probe it; never parse a minified bundle.
2. **Comprehend** (`shesha-design-comprehension`) — each screen → `blueprints/<screen>.blueprint.md`, a measured layout map with a placement `assertions` block. This is what stops container placement from drifting.
3. **Plan** (`shesha-claude-designer`) — establish the theme **once**, then map each blueprint region to a **block** (`shesha-form-edit/assets/blocks`) + its paired **style overlay/recipe** (`shesha-design-system`). The per-screen plan is `{archetype, blocks[], recipes[]}`.
4. **Build** — for each screen: **(a)** `shesha-form-edit` composes the blocks into native structure, wires CRUD, validates, pushes; **(b)** `shesha-design-system` resolves the token overlays and returns styled JSON — which `shesha-form-edit` pushes through its single push path.
5. **Verify** — four gates in order: **structural** (native components, fully flexed, fields bound) → **placement diff** (`shesha-design-comprehension` re-measures the live form against the blueprint assertions) → **design critique** (`design-critic`; `generic` is not done) → **visual** (screenshot vs theme). Mismatches route back to the owning skill.

The contract that wires the conductor to the sub-skills is [`references/handoff-contract.md`](references/handoff-contract.md).

---

## The design system is generic, editable, and reusable

Nothing about a brand is hard-coded into the recipes, blocks, or skills. **Brand lives entirely in one token file.**

### 1. The brand token file — the single source of brand truth
`shesha-design-system/assets/themes/<brand>.tokens.json`. **The shipped default is `shesha.tokens.json`** — the framework's own Cobalt/Navy/Athens-Grey brand, used automatically whenever no app-specific brand is named. `requirements-studio.tokens.json` ships alongside it as an **example custom brand** (a brand green). All brand files live in this one folder; a new brand is a new file dropped here (copy the default, swap values). Each holds, as data:

- `palette` — `brand`, `accent`, `surfaces`, `lines`, `ink`, `semantic` colour groups
- `type` — font `family`, a `scale` (micro → title), `weights`, `lineHeights`
- `spacing` (4px scale), `radius` (xs → pill), `shadow` (card/overlay/rowHover), `chrome` metrics
- `statusLifecycle` — the status reflist + a per-status `badges` map (bg/fg/border) so status colour is data, not code
- `roles` — a **semantic indirection map**: e.g. `"bodyText": "palette.ink.primary"`, `"cardBg": "palette.surfaces.surface"`, `"cardRadius": "radius.lg"`
- `$antdTheme` *(default brand)* — the pre-resolved Ant Design 6.x `ConfigProvider` `{token, components}` object, applied verbatim at the app level (the "set once" theme layer)

### 2. Recipes & overlays reference **`$role:` tokens, never hexes**
A block style-overlay says `"color": "$role:bodyText"`, not `"#1f1f1f"`. At stamp time the overlay's `$role:` tokens are resolved through the token file's `roles` map (via [`references/token-to-prop-mapping.md`](../shesha-design-system/references/token-to-prop-mapping.md)). So **the same blocks/overlays render any brand** — you only swap the token file.

### 3. The capability matrix is empirical and version-stamped
[`shesha-design-system/assets/capability-matrix.json`](../shesha-design-system/assets/capability-matrix.json) (+ a readable `.md`) records which v7 style channel actually **renders** on which component, measured against a live backend. It is the source of truth for "what works" and gets **re-measured on a Shesha upgrade** (diff = upgrade-impact report). `validate-blocks.js` gates every block against it.

> **To theme a brand-new app you write zero code:** copy the token file, edit the values, point the designer at it. The recipes, blocks, overlays, and capability matrix are all reused as-is.

---

## How to edit the pipeline

| You want to… | Edit | Notes |
|---|---|---|
| **Re-theme an existing app** (colour/type/spacing/radius/shadow) | the brand **token file** only | never edit recipes or blocks for a colour change |
| **Pick default vs custom brand** | nothing — `shesha` (`assets/themes/shesha.tokens.json`) is the automatic default; name a brand or hand over tokens to select a custom one | see `shesha-design-system/SKILL.md` Step 1 for the selection rule |
| **Add a new brand** | copy the default `assets/themes/shesha.tokens.json` → `assets/themes/<brand>.tokens.json`, edit values (keep key names), set it active | blocks/overlays/recipes are reused unchanged |
| **Add a new component block** | a skeleton in `shesha-form-edit/assets/blocks/<name>.block.json` **+** a paired overlay in `shesha-design-system/assets/block-styles/<name>.style.json` | list the matrix rows it relies on in the block's `$validatedAgainst`, then run `validate-blocks.js` |
| **Add / change an appearance recipe** | `shesha-design-system/references/component-recipes.md` | keep it `$role:`-token-based, no hexes |
| **Record a new empirical finding / re-measure after a Shesha upgrade** | `assets/capability-matrix.json` (+ `references/capability-matrix.md`) | re-run `validate-blocks.js`; a block referencing a `no-op` channel must fail |
| **Relax or tighten a design rule** | recipes in `references/shesha-design-standards.md`; **functional guardrails stay in** `shesha-form-edit/references/form-quality.md` | guardrails and relaxable recipes are deliberately kept in separate blocks |
| **Change blueprint/placement vocabulary** | `shesha-design-comprehension/references/blueprint-ir.md` + `verification-loop.md` | must move in lockstep with the flex-split idiom |

---

## Reference map — what references what

```
shesha-claude-designer/
  SKILL.md ............... conductor; invokes the 3 sub-skills below
  references/
    design-ingestion.md . fidelity tiers, token extraction, "run don't parse"
    handoff-contract.md . the {archetype, blocks[], recipes[]} contract between skills
  README.md ............. (this file)

shesha-design-comprehension/
  SKILL.md
  scripts/layout-probe.js ........ measures DOM x-clusters + computed styles (live)
  references/blueprint-ir.md ..... the measured blueprint format (flex-split, never columns)
  references/verification-loop.md  the placement-diff gate (re-measure vs assertions)

shesha-form-edit/                  ── STRUCTURE ──
  SKILL.md ....................... build/CRUD/validate/single-push; load-on-demand refs
  references/block-library.md .... index of the blocks ▼
  assets/blocks/*.block.json ..... structure skeletons; each names its $styleOverlay + $validatedAgainst
  references/blueprint-consumption.md  blueprint → components/propertyNames (flex, not columns)
  scripts/validate-blocks.js ..... gates blocks against ▼ the capability matrix

shesha-design-system/              ── APPEARANCE ──
  SKILL.md
  assets/themes/*.tokens.json .... the BRAND token file — default `shesha`, example custom `requirements-studio` (palette/type/spacing/radius/shadow/status/roles/$antdTheme)
  assets/block-styles/*.style.json  per-block style overlays (use $role: tokens, paired to a block)
  assets/capability-matrix.json .. empirical "what renders" truth (+ references/capability-matrix.md)
  references/component-recipes.md  per-archetype v7 style recipes
  references/token-to-prop-mapping.md  resolves $role: tokens → component props
  references/shesha-design-standards.md  appearance rules (relaxable recipes)
  references/styling-v7-mechanics.md + style-channels.md  the v7 style channel mechanics
```

**The two pairings that hold it together:**
- **block ↔ overlay**: `block.$styleOverlay` names the overlay in `shesha-design-system/assets/block-styles`.
- **block ↔ matrix**: `block.$validatedAgainst` names rows in `assets/capability-matrix.json`; `validate-blocks.js` fails the block if any referenced channel is a `no-op`.

---

## Firm rules (invariants the whole pipeline obeys)

- **Splits follow the flex-split idiom** — [capability-matrix.md §flex-split](../shesha-design-system/references/capability-matrix.md#flex-split).
- **Structure (form-edit) and appearance (design-system) never mix.** A hex in a block subtree is a bug — it belongs in the overlay/token file.
- **Comprehend before building; verify placement by measurement.** No screen is "done" until its placement assertions pass.
- **One push path** (form-edit). Theme is set **once**, via Configuration Studio / the token file — not per-form, and not by editing frontend source.
- **Status is never colour-alone**; destructive actions are never primary; `validationErrors` is present when required inputs exist.
- **Datalist row-template cards** need the markup-only collapse/scroll fix (the `style`-overflow + reserved-`minHeight` recipe) — see the capability matrix entry "datalist-row-template card" and `component-recipes.md → Datalist row-template card`.

---

## When to use which skill directly

- A **design exists** and you want it realised in Shesha across one or more screens → start at **`shesha-claude-designer`**.
- **Several screens described only in prose**, with design intent ("a 3-page booking system, make it look properly designed") → also start at **`shesha-claude-designer`**. It runs the same pipeline, deriving each blueprint from the screen's archetype and the default `shesha` brand (Tier D) instead of measuring a source.
- A **single form with no design intent** ("add a sector dropdown") → go straight to **`shesha-form-edit`**.
- **Style an already-working form** → go straight to **`shesha-design-system`**.
