---
name: clean-form-config
description: Analyzes a Shesha 0.46 form configuration JSON and cleans it. Removes dead/obsolete component properties using a valid-property index generated from the 0.46 component KB (never touching keys a migrator still reads on components stored below the current version), strips console.log calls, validates property value types, dropdown values items, script syntax (parsed as an async function body), layout (container overflow, labelCol+wrapperCol, device style paths, subForm label span 0), label-instead-of-propertyName references, API calls missing try-catch or async/await, and .then() chaining. Adds the 0.46 render checks - unsafe member chains in render-time scripts (auto-fixed with optional chaining), htmlRender carrier hazards (sanitize), deprecated components, spacing left only in the legacy stylingBox string on per-device components, legacy scripting names, ReferenceList/GetItems URLs, editMode boolean false, antd 6 DOM selectors. Use when a form has been migrated to 0.46, components were refactored, or before pushing a form with shesha-form-edit.
---

# Clean Form Configuration (Shesha 0.46)

Identify and remove **dead properties**, **debug statements**, **type mismatches** and **0.46 render hazards** from a Shesha form configuration. Report-first, conservative: every auto-fix is idempotent, and every edited script must still parse as an async function body.

---

## Fast path: run the scanner

`scripts/scan-046.mjs` (dependency-free Node) implements the dead-property check, the syntax check and all 0.46 checks (N1-N9). Run it first, then layer the remaining steps of [analysis.md](analysis.md) on top.

```bash
node scripts/scan-046.mjs <markup.json | dir> [--json]          # report, read-only
node scripts/scan-046.mjs <markup.json> --fix --out cleaned     # apply the conservative fixes -> cleaned/<name>.cleaned.json
```

Input may be raw markup, a stringified markup, or an API envelope (`result.configuration.markup` from `ConfigurationItem/GetCurrent`, `result.markup`, `markup`). The input file is never overwritten. Exit code 0 = clean, 1 = findings, 2 = could not run. Flags: `--fix-legacy-names` (rewrite `pageContext` and `fileSaver(` only), `--dead-all` (also remove unrecognised keys on components below the current version, and dead `formSettings` keys), `--groups <dir>`.

What `--fix` changes (all `[FIXABLE]` findings, nothing else): dead props on components already at the current version (D1), optional chaining on unsafe chains in render-time scripts (N1), `sanitize: false` on `<style>` carriers (N2), `desktop.stylingBoxJson` filled from a legacy `stylingBox` string (N4). Every N1 edit is re-parsed and re-scanned; a failing edit is dropped and reported as manual.

---

## Step 1: Load the component properties index

```
assets/groups/index.json     # type -> group, plus meta{version, deprecated, hidden, perDevice}
assets/groups/base.json      # base props, legacyBase, _formSettings, _types
assets/groups/<group>.json   # per-component valid props
```

The index is **generated** from the 0.46 component KB (`../shesha-form-edit/assets/components-kb/`), so a real 0.46 prop (for example `refListStatus.itemDisplay`, `desktop`, `stylingBoxJson`) is never reported as dead. Load `base.json` and only the group files for the component types in the form (procedure: [analysis.md](analysis.md) Step 3).

> **Maintainers:** after the KB changes, run `node scripts/generate-index.mjs` (and `--check` in CI). Method and rules: [generate-index.md](generate-index.md). Never hand-edit the group files.

---

## Step 2: Load the form config

- **Option A - fetch from the API**: [api.md](api.md) (0.46: `ConfigurationItem/GetCurrent?itemType=form&module=&name=`; `FormConfiguration/GetByName` is 404).
- **Option B - local file**: use the path the caller or user gives.

Normalise to `{ components, formSettings }` as in the Normalisation section of [analysis.md](analysis.md).

---

## Step 3-8: Analyse and clean

Follow [analysis.md](analysis.md):

- **Step 3** - load the index (v4). **Step 4** - walk the tree; dead properties follow the **version rule**: a key unknown to the index is `DEAD` only on a component whose `version` is at or above the current one (`index.meta[type].version`); below it, the key is reported `[STALE - left alone]` because the 0.46 migrator may still read it.
- **Step 4b** console.log. **4c** type check (inferred types are never auto-fixed). **4d** dropdown `values` shape. **4e** layout checks ([layout-checks.md](layout-checks.md), L1-L6). **4f** label used instead of propertyName.
- **Step 4g** script syntax (parse as an async function body; heuristics only as fallback). **4h** API call without try-catch. **4i** async/await. **4j** `.then()` chaining. API patterns include `actions.callApi.*`.
- **Step 4k - Shesha 0.46 checks (N1-N9)**: unsafe chains in render-time scripts (every `_code` at any depth, including the `desktop` / `tablet` / `mobile` copies), htmlRender carrier hazards, deprecated components, per-device spacing living only in the legacy `stylingBox` string, legacy scripting names (reported, not rewritten), subForm label span 0, `ReferenceList/GetItems` URLs, `editMode` boolean `false`, pre-antd-6 DOM selectors.
- **Step 5-5k** present findings. **Step 6** single confirmation. **Step 7** apply and output. **Step 8** summary.

Auto-fix rule for scripts (4h, 4i, N1, N5): after each edit, parse the result as an async function body; if it does not parse, drop the edit and list the script as `[MANUAL REVIEW]`.

---

## Step 9: Hand the cleaned config back - do NOT push it

**Return the cleaned JSON to the caller. This skill never pushes.**

`shesha-form-edit` invokes this skill as a **mandatory blocking step immediately before its own push** (its SKILL.md Step 6). A second push path here would bypass that skill's re-fetch diff and browser smoke, and it contradicts the pipeline's "one push path - all writes go through `shesha-form-edit`" rule ([handoff-contract.md](../shesha-claude-designer/references/handoff-contract.md)).

- **Invoked as a sub-skill (the normal case):** return the cleaned JSON and the change list. The caller pushes and verifies (and must send `modelType` on `UpdateMarkup`).
- **Invoked standalone on a local file:** report the cleaned JSON and tell the user to push it with `shesha-form-edit`.

**Never call `AskUserQuestion` from this skill.** It runs inside a blocking step of a pipeline that is frequently headless, where an interactive prompt dead-ends the whole run.

---

## Notes

- **Conservative approach**: ambiguous properties go to manual review, not auto-clean.
- **Structural keys are never removed**: `id`, `type`, `parentId`, `components`.
- **Nested objects are not deep-cleaned** for dead keys: only top-level component keys are checked (scripts are scanned at any depth).
- **`IPropertySetting` wrappers** (`{ _mode, _value, _code }`) are valid for any property.
- **`_mode: 'code'` values are never type-checked** - runtime expressions; they are scanned for N1 / N5 / syntax.
- **`null` values are never type-checked.**
- Render-time scripts (code-mode settings) are scanned for unguarded chains; event handlers are not (data exists by then).
- A deprecated or unregistered component type is reported, never rewritten.
- If a form shows real 0.46 props as dead, the index is stale: regenerate it ([generate-index.md](generate-index.md)) rather than waving the report through.
