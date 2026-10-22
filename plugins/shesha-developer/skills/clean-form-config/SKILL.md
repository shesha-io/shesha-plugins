---
name: clean-form-config
description: Analyzes a Shesha form configuration JSON and removes dead/obsolete component properties, strips console.log calls from JS code strings, validates property value types, validates the shape of dropdown values items, detects scripts referencing component labels instead of propertyNames, runs layout validations (container dimension overflow, labelCol+wrapperCol span checks, device-specific style path conflicts), validates JavaScript syntax of embedded code strings, auto-fixes API calls missing try-catch by wrapping the function body in try/catch, and auto-fixes API calls in async-context properties that are missing async/await by adding the async keyword and awaiting calls. Falls back to manual review when function structure is ambiguous. Also detects API calls using .then() chaining and flags them for conversion to async/await + try-catch. Use when a form has been migrated, components have been refactored, or you want to clean up stale properties and debug statements.
---

# Clean Form Configuration

Identify and remove **dead properties**, **console.log debug statements**, and **type mismatches** from a Shesha form configuration.

---

## Step 1: Load the component properties index

Read the bundled index from the skill's own assets folder:

```
plugins/shesha-developer/skills/clean-form-config/assets/groups/index.json
```

Then load `base.json` and whichever group files are needed for the components in the form (see Step 3 of [analysis.md](analysis.md) for the full loading procedure). All files are maintained by the skill author and ship with the plugin — no generation step is needed. Proceed directly to Step 2.

> **Note for skill maintainers:** To refresh the index after a shesha-reactjs upgrade, follow [generate-index.md](generate-index.md) and replace the files in the `assets/groups/` folder.

---

## Step 2: Load the form config

Choose one of:

**Option A — Fetch from API**: Follow [api.md](api.md) to resolve the base URL, authenticate, and retrieve the form by module + name.

**Option B — Local file**: Ask the user for the file path, then use `Read` to load it.

In both cases normalise to `{ components, formSettings }` as described in the Normalisation section of [analysis.md](analysis.md) before continuing.

---

## Step 3–8: Analyse and clean

Follow [analysis.md](analysis.md) for:

- **Step 3** — Load and interpret the component properties index (v2 format).
- **Step 4** — Walk the component tree; identify dead properties and unknown types.
- **Step 4b** — Scan all string values for `console.log` calls.
- **Step 4c / 4d / 4e / 4f** — Type-check valid properties; validate dropdown `values` item shapes; run layout checks (overflow, span, device-style path); scan scripts for label used instead of propertyName.
- **Step 4g** — Validate JavaScript syntax of all embedded code strings; flag broken scripts as `[CRITICAL]`.
- **Step 4h** — Detect API calls missing try-catch; auto-fix by wrapping the function body in try/catch where the structure is unambiguous; fall back to `[MANUAL REVIEW]` for complex scripts.
- **Step 4i** — Detect API calls in async-context properties (onFinish, onSubmit, getData, etc.) missing async/await; auto-fix by adding `async` to the function signature and `await` before the call; fall back to `[MANUAL REVIEW]` for ambiguous structures. Also detects `await` used outside an `async` function (Scenario A) and auto-fixes it.
- **Step 4j** — Detect API calls using `.then()` chaining; flag as `[MANUAL REVIEW]` with a recommendation to convert to async/await + try-catch.
- **Step 5 / 5b / 5c / 5d / 5e / 5f / 5g / 5h / 5i / 5j** — Present findings (dead props, console.log, type mismatches, values shape issues, layout issues, label references, script syntax errors, missing try-catch, missing async/promise, .then() chaining).
- **Step 6** — Single confirmation prompt.
- **Step 7** — Apply all cleanups and output cleaned JSON.
- **Step 8** — Summary with size reduction.

Layout checks are defined in [layout-checks.md](layout-checks.md) — new checks can be appended there as L3, L4, etc.

---

## Step 9: Hand the cleaned config back — do NOT push it

**Return the cleaned JSON to the caller. This skill never pushes.**

`shesha-form-edit` invokes this skill as a **mandatory blocking step immediately before its own
push** (its SKILL.md Step 6). A second push path here would bypass that skill's re-fetch diff and
browser smoke, and it contradicts the pipeline's "one push path — all writes go through
`shesha-form-edit`" rule ([handoff-contract.md](../shesha-claude-designer/references/handoff-contract.md)).

- **Invoked as a sub-skill (the normal case):** return the cleaned JSON and the change list. The
  caller pushes and verifies.
- **Invoked standalone by a user on a local file:** report the cleaned JSON and tell them to push
  it with `shesha-form-edit`.

**Never call `AskUserQuestion` from this skill.** It runs inside a blocking step of a pipeline that
is frequently headless, where an interactive prompt dead-ends the whole run.

---

After a `shesha-upgrade-reconciler` fleet, run this skill on the reconciled forms to strip leftovers (dead properties, `console.log`, unwrapped API calls).

## Notes

- **Conservative approach**: ambiguous properties go to manual review, not auto-clean.
- **Structural keys are never removed**: `id`, `type`, `parentId`, `components`.
- **Nested objects are not deep-cleaned**: only top-level component keys are checked.
- **`IPropertySetting` wrappers** (`{ _mode, _value, _code }`) are valid for any property.
- **`_mode: 'code'` values are never type-checked** — runtime expressions.
- **`null` values are never type-checked** — valid for any property type.
- To regenerate the index after upgrading shesha-reactjs, delete `.claude/shesha/component-properties.json` and re-run the skill.
