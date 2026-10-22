# Analysis Steps

Steps 2–8 of the `clean-form-config` skill (Shesha 0.46).

The 0.46-specific checks (Step 4k) and the dead-property / syntax / render-time-script checks are also implemented, deterministically, by `scripts/scan-046.mjs` — run it first (see SKILL.md) and use this document for the interpretation, presentation and the checks the script does not cover (console.log, type checks, dropdown `values`, layout, label references, try-catch / async / `.then()`).

---

## Normalisation

Load the file provided by the user with the `Read` tool. Extract `{ components, formSettings }` from the various input shapes:

| Input shape | How to extract |
|---|---|
| `{ "Markup": "...", "Name": "..." }` (exported file) | `JSON.parse(obj.Markup)` |
| `{ "result": { "configuration": { "markup": "..." } } }` (0.46 `ConfigurationItem/GetCurrent`) | `JSON.parse(obj.result.configuration.markup)` |
| `{ "result": { "markup": "..." } }` (ABP API response) | `JSON.parse(obj.result.markup)` |
| `{ "markup": "..." }` (raw DTO) | `JSON.parse(obj.markup)` |
| `{ "components": [...], "formSettings": {} }` | use directly |

Verify you have an object with a `components` array before continuing.

---

## Step 3: Load the component properties index

The index ships as a set of group files under `assets/groups/` (relative to this skill). It is generated from the 0.46 component KB — never edit it by hand; regenerate it with `scripts/generate-index.mjs` ([generate-index.md](generate-index.md)).

**Loading procedure:**

1. Read `assets/groups/index.json` — contains `components: { [type]: groupName }`, `groupFiles: [...]` and `meta: { [type]: { version, deprecated?, hidden?, perDevice?, containers? } }` (`version` = current 0.46 component version).
2. Read `assets/groups/base.json` — always required; contains `base`, `legacyBase` (names that were valid in 0.43/0.45 and are no longer declared), `_formSettings` and `_types`.
3. For each unique component type in the form, look up `index.components[type]` to find its group file, then read `assets/groups/<groupName>.json`. Cache loaded files — don't re-read the same group file twice.

**File structure** (v4):

Each entry (`base`, `_formSettings`, or a component type like `textField`) contains a single `props` array of property descriptors:

```json
{
  "name": "alertType",
  "type": "string",
  "options": ["success", "info", "warning", "error"],
  "desc": "Determines the alert color and icon.",
  "required": false,
  "JsReturnType": "string"
}
```

Descriptor fields:
- `name` — property key.
- `type` — storage type: `string | boolean | number | object | array | script`. Omitted when unknown.
- `options` — valid string values for `type: "string"` enums.
- `desc` — human-readable description.
- `required` — whether the property must be present.
- `JsReturnType` — what a `_mode: "code"` JS expression must return. For non-script props mirrors `type`; for `type: "script"` props it is the specific return type (e.g. `"boolean"`, `"void"`, `"object"`).
- `async` — (`type: "script"` only) whether the script must be declared async.
- `context` — (`type: "script"` only) variable names available in scope.
- `keyCase` — (`type: "script"`, style-returning) return object keys must be `"camel"`.
- `valueType` — (`type: "script"`, style-returning) return object values must be `"string"`.
- `inferred` — `true` when the type was inferred from the settings editor, not curated. Type mismatches on inferred props are **always `[MANUAL REVIEW]`**, never auto-fixed.

A component entry may also carry `legacy: [names]` — props the 0.43/0.45 index knew that 0.46 no longer declares. A `type` that names an entry of `base._types` (e.g. `border-config`) is an object shape: compare as `object`.

`base.json` contains two entries:
- `base` — props valid on **every** component (including `customStyle`, `customVisibility`, all event handlers, etc.).
- `_formSettings` — props valid on the form-level `formSettings` object.

Each group file contains only the component-specific props (props not already in `base`). A property is **valid** for a component when it is in `base.base.props` or in that component's `props`.

For each component being analyzed, build:

```
groupFile   = loadedGroups[index.components[component.type]]   // undefined for unknown types
basePropMap = Object.fromEntries(base.base.props.map(p => [p.name, p]))
compPropMap = Object.fromEntries((groupFile?.[component.type]?.props ?? []).map(p => [p.name, p]))
propMap     = { ...basePropMap, ...compPropMap }   // component props override base if same name
allowedKeys = new Set(Object.keys(propMap))
```

Then for type-checking: `propMap[key].type` gives the expected type; `propMap[key].options` gives valid enum values.

For the `formSettings` object:

```
fsPropMap           = Object.fromEntries(base._formSettings.props.map(p => [p.name, p]))
formSettingsAllowed = new Set(Object.keys(fsPropMap))
```

Properties in `allowedKeys`/`formSettingsAllowed` with no `type` have ambiguous/union types — skip type-checking for those.

---

## Step 4: Walk the component tree and identify dead properties

The `components` array is a **nested tree** — each component may have a child `components` array. Walk it recursively.

For each component:

1. Get `component.type`.
2. Build `allowedKeys` and `typeMap` as described in Step 3.
3. For each key on the component object:
   - Skip keys starting with `_` or `shesha:`.
   - Skip the key `components`.
   - If the key is **not in `allowedKeys`** → dead property candidate. Then apply the version rule:
     - component `version` is a number **>= `index.meta[type].version`** → **DEAD** (removable).
     - component `version` is missing or **below** the current version → **do not remove**: the 0.46 migrators may still read the key (`name`, `stylingBox`, `hidden`, `fontSize`, `showIcon` ...). Report it as `[STALE — left alone]` (known `legacy` keys are labelled as such). Removal needs `--dead-all` or an explicit user instruction.
4. If `index.meta[type].deprecated` or `.hidden` → also report under Step 4k (N3). If the type is **not in the index at all** (module-provided / custom / removed type):
   - Only check against `base.props`.
   - Tag results with `[TYPE UNKNOWN — manual review]`.
   - Do **not** include these in the auto-clean list.

**Also validate `formSettings`:**

For each key in the `formSettings` object:
- Skip keys starting with `_`.
- If the key is **not in `formSettingsAllowedKeys`** → dead formSettings property.
- Report these separately under "Dead formSettings properties".

---

## Step 4b: Scan for console.log calls in string properties

Walk the **entire** parsed JSON object recursively (not just component top-level keys). For every `string` value encountered, check whether it contains `console.log`. This catches values nested in `IPropertySetting` wrappers (`{ _mode, _value, _code }`) and any other nested structure automatically.

Use this regex to find and remove console.log calls from each matching string:

```
/console\.log\s*\((?:[^)(]|\((?:[^)(]|\([^)(]*\))*\))*\)\s*;?\s*/g
```

Replace each match with `''`. After replacement, collapse excess blank lines: replace `/\n{3,}/g` with `\n\n`.

Track each removal:
- Which component it belongs to (look up the nearest ancestor component by `id`)
- Which property key the string was found in (e.g. `onChangeCustom`, or `customVisibility._code` for nested wrappers)
- How many `console.log` calls were removed from that string

---

## Step 4c: Type validation for known properties

Also type-check the `formSettings` object: for each key in `formSettings` that IS in `formSettingsAllowedKeys`, apply the same type-check logic using `formSettingsTypeMap[key]`. Report these under "formSettings type mismatches".

For each component, for each key that IS in `allowedKeys` (valid properties):

1. `propDef = propMap[key]` — if not present → skip (ambiguous type). `expectedType = propDef?.type`. If `expectedType === 'script'` → skip type-checking (value is a JS string evaluated at runtime; validate its content in Steps 4g and 4g-style).
2. `rawValue = component[key]`
3. Unwrap `IPropertySetting` wrapper if present:
   - If `rawValue` is an object with `_mode === 'code'` → skip (JS expression, runtime type unknown).
   - If `rawValue` is an object with `_mode === 'value'` → `checkValue = rawValue._value`.
   - Otherwise → `checkValue = rawValue`.
4. If `checkValue === null` or `checkValue === undefined` → skip.
5. Determine `actualType`:
   - `Array.isArray(checkValue)` → `'array'`
   - `typeof checkValue === 'object' && checkValue !== null` → `'object'`
   - Otherwise → `typeof checkValue` (string/boolean/number)
6. Compare `actualType` vs `expectedType`. If mismatch:
   - **Auto-fixable** (never when the descriptor is `inferred`):
     - boolean expected, got string `"true"` or `"false"` → auto-fixable
     - number expected, got string matching `/^\d+(\.\d+)?$/` → auto-fixable
   - **Manual review**: all other mismatches

---

## Step 4d: Validate `values` item shape for dropdown components

For every component where **`type === 'dropdown'`** and **`dataSourceType === 'values'`**:

1. Skip if `values` is absent, `null`, or not an array.
2. For each item in the array, check:
   - **Required keys present**: `id`, `label`, `value` — the `{ id, label, value }` contract that
     `shesha-form-edit` authors to ([dropdowns.md](../shesha-form-edit/references/components/dropdowns.md)).
   - **Known optional keys**: `color` (string), `icon` (string). Any other key is an **unknown key**.
   - **Type check**: `label` and `value` must be strings. `color` and `icon`, if present, must be strings.
3. Classify each issue:
   - Missing `id`, `label` or `value` → **[MANUAL REVIEW]**
   - Missing `color` → **not an issue.** `color` is optional; do not report it and **do not inject
     `"color": ""`**. This skill runs as a blocking step immediately before `shesha-form-edit`
     pushes, so injecting a key mutates markup the caller deliberately authored — the two skills
     were disagreeing about the same contract, and the caller's is the one that renders.
   - Wrong type for `label`, `value`, `color`, or `icon` → **[MANUAL REVIEW]**
   - Unknown extra key on an item → **[MANUAL REVIEW]**
4. Report issues grouped by component under "Step 5d". Track auto-fixable vs manual.

---

## Step 4e: Run layout checks

Read [layout-checks.md](layout-checks.md) and run all checks (L1, L2, …) against the full component tree and `formSettings`. Collect results into two lists: **auto-fixable layout issues** and **manual-review layout issues**. Report under Steps 5e and 5f.

---

## Step 4f: Scan scripts for label used instead of propertyName

Build a lookup of every component that has **both** a non-empty `label` (string) **and** a non-empty `propertyName` (string) where `label !== propertyName`.

Walk all JS code strings in the form config (same strings scanned in Step 4b). For each label in the lookup, search the string for the label appearing in data-access patterns:

```
// bracket notation (works for labels with spaces)
(?:data|formData|initialValues|values|form)\s*(?:\?\.)?\s*\[\s*['"]LABEL['"]\s*\]

// dot notation (only relevant when label has no spaces)
(?:data|formData|initialValues|values|form)\s*(?:\?\.)?\s*\.LABEL\b
```

For each match, record:
- The component id and property key where the script lives
- The label string found
- The correct `propertyName` to use instead

These are **never auto-fixable** — script replacements could change logic. Report under Step 5f.

---

## Step 4g: Validate JavaScript syntax of code strings

**Scope:** Collect all JS code strings from the component tree:
- `IPropertySetting` objects where `_mode === 'code'` — use the `_code` string.
- Standalone string values that contain JS indicators: `function`, `=>`, `return `, `if(`, `var `, `let `, `const `.

For each code string, check for these syntax problems:

| Heuristic | How to detect |
|---|---|
| Unmatched braces/parens/brackets | Count opens vs closes for `{`, `[`, `(` — flag if the totals differ |
| Unclosed string literal | Count unescaped `'`, `"`, `` ` `` occurrences — flag if any count is odd |
| Template literal `${` without closing `}` | Count `${` vs `}` inside template literals — flag mismatch |
| `function` missing closing `)` or `{` | Check that each `function(` or `function name(` has a matching `)` followed by `{` |

**Preferred method (Node available):** parse every script as the body of an async function — `new (Object.getPrototypeOf(async function(){}).constructor)(code)` — which is how the 0.46 runtime wraps it (`new Function("context", "with(context){...}")` over the script body). Any `SyntaxError` is `[CRITICAL]`. `scripts/scan-046.mjs` reports these as `S1`. The heuristics below are the fallback when Node is not available.

These are heuristics — reason about the script content to identify the most likely issue. When a script is too long to analyze fully, check the first and last 300 characters for obvious unclosed constructs.

Severity: **`[CRITICAL]`** — invalid scripts throw runtime errors and break form functionality.
**Never auto-fixable** — repair requires developer intent.

Output format per finding:
```
[CRITICAL] Script syntax error
  Component: <id> (<type>)
  Property:  <key>
  Issue:     <description, e.g. "unmatched braces: 3 opens, 2 closes">
  Excerpt:   <first 120 chars of script>
```

**Additional check for style-returning scripts (`customStyle`, `style`, `wrapperStyle`):**

For any script property where `propMap[key]?.keyCase === 'camel'`, attempt to extract the returned object literal from the script string (look for `return {` or an arrow-function implicit `({`). For each key found in the object literal:

- Flag any key in kebab-case (contains `-`) as `[WARNING — use camelCase key]`
- Flag any value that is a bare number without units (e.g. `fontSize: 14` instead of `fontSize: '14px'`) as `[WARNING — value should be a quoted string]`

Severity: **`[WARNING]`** — the component will likely not style correctly at runtime.
**Never auto-fixable** — the correct unit/value requires developer intent.

Output format:
```
[WARNING] customStyle object rule violation
  Component: <id> (<type>)
  Property:  <key>
  Issue:     kebab-case key "font-size" — use camelCase "fontSize"
             bare number value for "opacity: 1" — use quoted string "opacity: '1'"
```

---

## Step 4h: Detect API calls missing try-catch

Walk all JS code strings (same set as Step 4g).

**API call patterns to match (regex):**
- `axios\s*\.\s*(get|post|put|delete|patch|request)\s*\(`
- `fetch\s*\(`
- `\b(getHttp|postHttp|putHttp|deleteHttp|patchHttp)\s*\(` (Shesha HTTP helpers)
- `http\s*\.\s*(get|post|put|delete|patch)\s*\(`
- `actions\s*\.\s*callApi\s*\.\s*(get|post|put|delete|patch|request)\s*\(` (0.46 name for `http`)

For each script containing a match, check whether the call site is inside a try-catch block:
- Heuristic: scan backwards from the match position for a `try\s*{` that has not yet been closed by a matching `}`.
- If no enclosing try-catch is found → attempt auto-fix.

**Auto-fix algorithm:**
1. Locate the outermost function body (between the opening `{` after the function signature and its matching closing `}`).
2. If the script contains exactly **one** top-level function and no existing partial try-catch wrapping the same call, replace the function body with:
   ```
   try {
     <original body>
   } catch (error) {
     console.error('API call failed:', error);
   }
   ```
3. If the script has **multiple top-level functions**, nested function declarations that own the API call, or a partially existing try-catch at the same level → fall back to `[MANUAL REVIEW]`.

Severity: **`[AUTO-FIXABLE]`** for simple single-function scripts; **`[MANUAL REVIEW]`** for complex ones.

Output format per finding:
```
[AUTO-FIXABLE — try-catch added]
  Component: <id> (<type>)
  Property:  <key>
  API call:  <matched text excerpt>

[MANUAL REVIEW — add try-catch]
  Component: <id> (<type>)
  Property:  <key>
  API call:  <matched text excerpt>
  Reason:    <why auto-fix was skipped, e.g. "multiple top-level functions">
```

---

## Step 4i: Detect API calls missing async/promise handling

Walk all JS code strings (same set as Step 4g). Use the API call patterns from Step 4h.

**Async-context property keys** — these Shesha lifecycle hooks must return a Promise or be declared async:

```
onFinish, onSubmit, getData, postData, customValidators,
onValuesChange, onInitialized, onComplete
```

Detect the following two scenarios and attempt auto-fix:

**Scenario A — `await` used outside an `async` function:**
- Script contains `await ` (with trailing space or opening paren) **and**
- The containing function is NOT declared `async`: none of `async function`, `async (`, `async\s+\w+\s*(` match.
- This is broken JavaScript — `await` in a non-async context is a syntax/runtime error.

**Auto-fix for Scenario A:** Add `async` before the function keyword or arrow:
- `function name(` → `async function name(`
- `(params) =>` → `async (params) =>`
- Named arrow assigned to `const name = (params) =>` → `const name = async (params) =>`
- Fall back to `[MANUAL REVIEW]` if there are multiple function declarations and it is ambiguous which one owns the `await`.

**Scenario B — API call in an async-context property without async handling:**
- The property key matches the async-context list above **and**
- The script contains an API call pattern **and**
- The function is NOT async (no `async function` / `async (`) **and**
- The call is NOT chained with `.then\s*(` **and**
- The script does NOT contain `return new Promise\s*(`.
- Result: the hook executes the call but does not await the response — the operation silently runs in the background and any return value is lost.

**Auto-fix for Scenario B:**
1. Add `async` to the function signature (same rules as Scenario A fix).
2. Prepend `await ` before each matched API call expression that is not already preceded by `await`.
3. Fall back to `[MANUAL REVIEW]` if the function structure is ambiguous (e.g., multiple top-level functions, generator functions).

Output format per finding:
```
[AUTO-FIXABLE] Missing async/promise handling
  Component: <id> (<type>)
  Property:  <key>  (async context — must return a Promise)
  Scenario:  A — await used in non-async function  →  added async to function signature
             B — API call result not awaited        →  added async + await to call site(s)
  API call:  <matched text excerpt>

[MANUAL REVIEW] Missing async/promise handling
  Component: <id> (<type>)
  Property:  <key>  (async context — must return a Promise)
  Scenario:  A or B
  API call:  <matched text excerpt>
  Reason:    <why auto-fix was skipped>
  Fix:       declare the function async and await the call
```

---

## Step 4j: Detect API calls using .then() chaining

Walk all JS code strings (same set as Step 4g). Use the API call patterns from Step 4h.

For each script where an API call pattern is followed by `.then\s*\(`, flag it as a style issue — `.then()` chaining works but is inconsistent with the async/await style used throughout Shesha.

Only flag cases where the `.then(` directly follows an API call pattern or is chained within the same expression. Do not flag `.then(` on non-API call chains.

Severity: **`[MANUAL REVIEW]`** — converting `.then()` callbacks to async/await requires restructuring the callback body, so this is never auto-fixed.

> **Note:** Step 4i still skips Scenario B detection for scripts that use `.then()` (they are handling the async result), but Step 4j will flag those same scripts here for style conversion.

Output format per finding:
```
[MANUAL REVIEW — replace .then() with async/await + try-catch]
  Component: <id> (<type>)
  Property:  <key>
  API call:  <matched text excerpt including .then(>
  Fix:       declare the function async, await the call,
             and wrap in try { ... } catch (error) { ... }
```

---

## Step 4k: Shesha 0.46 checks

Implemented by `scripts/scan-046.mjs` (finding ids in brackets). Run the script; interpret and present its output. **Every auto-fix is idempotent and re-parsed**: an edited script that no longer parses as an async function body is discarded and reported as manual.

| Id | Check | Detection | Auto-fix |
|---|---|---|---|
| N1 | **Unsafe member chain in a render-time script.** Scripts in code-mode settings run on every render, including before `data` is populated; a throw is swallowed and a throwing visibility means the component is shown. | Every `_code` at any depth — including the `desktop` / `tablet` / `mobile` copies that the style migration makes — and the plain-string `customVisibility`, `customEnabled`, `style`, `wrapperStyle`, `renderer`. Roots: `data`, `form.data`, `page.state`, `contexts`, `initialValues`, `parentFormValues`, `query`, `selectedRow`. A hop after the first property read (`selectedRow`: any hop) that uses `.` / `[` instead of `?.` / `?.[`. Strings, comments and shadowed names are ignored; assignment targets are never touched. | Insert `?` at each unguarded hop (`data.a.b` becomes `data.a?.b`, `data.items[0].name` becomes `data.items?.[0]?.name`). Rejected unless the result parses and re-scans clean. |
| N2 | **htmlRender carrier hazards** | `<style>` with `sanitize` not `false` (DOMPurify drops a leading `<style>`); style-only output (empty placeholder); `contentType: 'html'` with no `html`; empty renderer; `hidden` / `visible: false` carrier (hidden components are not mounted in 0.46). | `sanitize: false` only. Hidden / style-only / contentType cases are manual. |
| N3 | **Deprecated, hidden or unregistered component type** | `index.meta[type].deprecated` / `.hidden`; type absent from the index. Replacement hints: `datatableContext` to `dataContext`, `list` to `datalist`, `title` / `paragraph` to `text`, `passwordCombo` to two `textField`. | none (report) |
| N4 | **Spacing only in the legacy `stylingBox` string on a per-device component** (`index.meta[type].perDevice`): 0.46 reads the object `desktop.stylingBoxJson`; the migration copies only device-block strings, never the root one. Also a `stylingBoxJson` that is a string. | Root `stylingBox` with keys and no `desktop.stylingBoxJson` keys; `desktop/tablet/mobile.stylingBox` without the matching `stylingBoxJson`. | Write `{ "_type": "styleBox", ...parsed }` into the matching `stylingBoxJson` (the string is left in place). |
| N5 | **Legacy scripting names** (`pageContext`, `http.*`, `message.*`, `modal.*`, `moment`, `fileSaver`, `globalState`, `selectedRow`, `formData`, `setFormData`, `formMode`, `application.user`, `application.navigator`, `evaluateString`). They still resolve through `with(context)`, so this is a report, not a defect. Prefer `page.state`, `actions.callApi`, `actions.showMessage`, `actions.showDialog`, `actions.showConfirmation`, `utils.*`, `form.data`. | Token match outside strings / comments. | Only with `--fix-legacy-names`, and only the two trivially safe ones: `pageContext` to `page.state`, `fileSaver(` to `utils.saveAs(`, skipped if the script declares a binding with that name. The rest are manual (a local `message` variable in a catch block makes blind rewrites unsafe). |
| N6 | **subForm label span 0** | `type: subForm` and (`hideLabel === true` or `labelCol` falsy): hosted-field labels are hidden (`span = hideLabel ? 0 : labelCol ?? 0`; `labelCol` / `wrapperCol` on a subForm are numbers). | none. Workaround: `labelCol: 8`, `wrapperCol: 16`, `hideLabel: false` — only if the hosted form should show labels. |
| N7 | **`ReferenceList/GetItems` URL** (404 on 0.46) | any string, including inside scripts. | none. Use `GET /api/services/app/ConfigurationItem/GetCurrent?ItemType=reference-list&Module=<m>&Name=<n>` (items under `result.configuration`) or a dropdown with a reference-list data source. |
| N8 | **`editMode` returning boolean `false`** (DISABLED in 0.46, read-only in 0.43) | `editMode: false` or an `editMode` script with `return true/false`. | none. Return `'editable' / 'readOnly' / 'disabled' / 'inherited'`. |
| N9 | **Pre-antd-6 DOM selectors** (`.ant-tabs-content-holder`, `.ant-tabs-tabpane`, `.ant-collapse-content-box`) | any string. | none. Use `.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content`, `.ant-collapse-body`, or `[data-sha-c-name="..."]`. |

Render-time versus event-time: N1 applies to `_code` settings and the render keys listed above only. Event handlers (`onClickCustom`, `onFinish` ...) run after data exists and are scanned for N5 / N7 / syntax only.

---

## Step 5: Present the dead property findings

If no dead properties are found in either components or `formSettings`, skip this section.

Otherwise show `formSettings` dead properties first (if any):

```
Dead formSettings properties (if any):
  - onBeforeData:  "console.log(data)"  [DEAD — not in IFormSettings]
  - postUrl:       "https://..."        [LEGACY — replaced by dataSubmittersSettings]
```

Then component dead properties:

```
Found N dead properties across M components:

Component                    | Type         | Dead Properties
-----------------------------|--------------|-----------------------------
"First Name" (id: abc…)      | textField    | fontColor, borderRadius
"Submit" (id: def…)          | button       | backgroundColor

Details:
  • "First Name" (textField)
      - fontColor:     "#333333"
      - borderRadius:  4

  • "Submit" (button)
      - backgroundColor:  "#0070f3"
```

For each dead property value, truncate strings longer than 60 characters with `…`.

---

## Step 5b: Present console.log findings

If no console.log calls were found, skip this section.

Otherwise show:

```
console.log cleanup:
  • "My Component" (textField) → onChangeCustom: removed 2 console.log call(s)
  • "Submit" (button) → customVisibility._code: removed 1 console.log call(s)

Total: 3 console.log calls removed from 2 components
```

---

## Step 5c: Present type mismatch findings

If no type mismatches were found, skip this section.

Otherwise show:

```
Type mismatches:
  • "First Name" (textField) → spellCheck: expected boolean, got string ("true") [AUTO-FIXABLE]
  • "Age" (numberField) → max: expected number, got string ("100") [AUTO-FIXABLE]
  • "Container" (container) → alignItems: expected string, got object [MANUAL REVIEW]

Total: N mismatches (X auto-fixable, Y need manual review)
```

---

## Step 5d: Present values shape findings

If no issues were found, skip this section.

Otherwise show:

```
values shape issues:
  • "Category" (dropdown) — item[1]: missing color [AUTO-FIXABLE]
  • "Status" (dropdown) — item[0]: label is not a string [MANUAL REVIEW]
  • "Status" (dropdown) — item[2]: unknown key "extraProp" [MANUAL REVIEW]

Total: N issues (X auto-fixable, Y manual review)
```

---

## Step 5e: Present layout findings

If no layout issues were found, skip this section.

Otherwise show auto-fixable issues first, then manual-review issues:

```
Layout issues:
  [L2 — span] formSettings: wrapperCol.span=null → set to 16 [AUTO-FIXABLE]
  [L1 — overflow] "Container1" (container) — desktop: width 200% [MANUAL REVIEW]
  [L2 — span] "First Name" (textField): 10+10=20 ≠ 24 [MANUAL REVIEW]

Total: N issues (X auto-fixable, Y manual review)
```

---

## Step 5f: Present script label reference findings

If no matches were found, skip this section.

Otherwise show:

```
Script label references (N found):
  • "Submit" (button) [customAction]: uses data['First Name'] — should be data['firstName'] [MANUAL REVIEW]
  • "Panel" (container) [onLoad]: uses data['Status'] — should be data['status'] [MANUAL REVIEW]
```

---

## Step 5g: Present script syntax error findings

If no syntax errors were found, skip this section.

Otherwise show:

```
Script syntax errors (N found — CRITICAL):
  • "Submit" (button) [customAction]
      Issue:   unmatched braces: 3 opens, 2 closes
      Excerpt: function onSubmit(data) { if (data.id) { return axios.post('/api/...
  • "Panel" (container) [onLoad]
      Issue:   unclosed string literal (odd number of " characters)
      Excerpt: const label = "First Name;
```

---

## Step 5h: Present missing try-catch findings

If no API calls without try-catch were found, skip this section.

Show auto-fixable items first, then manual-review items:

```
API calls missing try-catch (N found):
  Auto-fixable (try-catch will be added):
  • "Submit" (button) [onFinish]
      API call:  axios.post('/api/services/...')
  • "Load Data" (customComponent) [getData]
      API call:  getHttp('/api/...')

  Manual review required (not changed):
  • "Complex" (customComponent) [onLoad]
      API call:  axios.get('/api/...')
      Reason:    multiple top-level functions — cannot determine wrapping scope
```

---

## Step 5i: Present missing async/promise findings

If no async/promise issues were found, skip this section.

Show auto-fixable items first, then manual-review items:

```
API calls missing async/promise handling (N found):
  Auto-fixable (will be updated):
  • "Submit" (button) [onFinish]  (async context — must return a Promise)
      Scenario: B — API call not awaited or chained
      API call:  axios.post('/api/services/...')
      Fix:       add async to function signature + await before call
  • "Validator" (textField) [customValidators]  (async context — must return a Promise)
      Scenario: A — await used in non-async function
      API call:  fetch('/api/...')
      Fix:       add async to function signature

  Manual review required (not changed):
  • "Complex" (button) [onFinish]  (async context — must return a Promise)
      Scenario: B — API call not awaited or chained
      API call:  axios.post('/api/...')
      Reason:    ambiguous — multiple top-level functions
      Fix:       declare the function async and await the call
```

---

## Step 5j: Present .then() chaining findings

If no `.then()` chaining on API calls was found, skip this section.

Otherwise show:

```
API calls using .then() chaining (N found — manual review recommended):
  • "Submit" (button) [onFinish]
      API call:  axios.post('/api/services/...').then(result => {
      Fix:       declare function async, await the call, wrap in try { ... } catch (error) { ... }
  • "Load Data" (customComponent) [getData]
      API call:  getHttp('/api/...').then(data => {
      Fix:       declare function async, await the call, wrap in try { ... } catch (error) { ... }
```

---

## Step 5k: Present Shesha 0.46 findings

If `scan-046.mjs` reported nothing for N1–N9, skip this section. Otherwise group by id, one line per finding, fixable first:

```
Shesha 0.46 checks:
  [N1 FIXABLE] "Status" (dropdown) desktop.font.color._code — unguarded chain "page.state.mode.x"
  [N2 FIXABLE] "styles" (htmlRender) — <style> with sanitize not false
  [N4 FIXABLE] "Name" (textField) — spacing only in legacy stylingBox string
  [N6] "Applicant" (subForm) — effective label span 0, hosted labels hidden [MANUAL REVIEW]
  [N3] "legacy list" (list) — deprecated, use datalist [MANUAL REVIEW]
  [N5] "Save" (button) onClickCustom — legacy name "http" (still resolves) [INFO]

Total: N findings (X auto-fixable, Y manual review, Z info)
```

---

## Step 6: Confirm removal

Ask the user a **single** confirm prompt covering all findings:

> Apply N cleanups:
>   - X dead properties removed
>   - Y console.log calls removed
>   - Z type fixes (W items need manual review — listed above)
>   - V values shape fixes (U items need manual review — listed above)
>   - X layout fixes (Y items need manual review — listed above)
>   - N script label references (manual review only — listed above)
>   - S script syntax error(s) — CRITICAL, manual fix required
>   - T API call(s) missing try-catch auto-fixed (M need manual review — listed above)
>   - U API call(s) missing async handling auto-fixed (P need manual review — listed above)
>   - V API call(s) using .then() — manual review recommended (listed above)
>   - F Shesha 0.46 fixes (optional chaining, htmlRender sanitize, stylingBoxJson); M manual-review items (listed above)
>
> Proceed? (yes / no / skip-type-fixes)

Adjust to omit whichever counts are zero. If there is nothing to clean, tell the user and stop.

- **no** → stop, output nothing.
- **yes** → apply everything (dead props + console.log + all auto-fixable type/values/API fixes).
- **skip-type-fixes** → apply dead props and console.log only (skips type, values, and API auto-fixes).

---

## Step 7: Output the cleaned form

1. Deep-clone the markup object.
2. Walk the component tree. For each component flagged in Step 4, delete the dead property keys.
3. Delete dead keys from `formSettings`.
4. Apply console.log cleanup: for every string value that contained `console.log`, replace with the regex-stripped, blank-lines-collapsed version.
5. Apply auto-fixable type fixes (components and `formSettings`):
   - `"true"` → `true`, `"false"` → `false` for boolean properties.
   - `"123"` → `parseFloat("123")` for number properties.
   - If the value was wrapped (`_mode: 'value'`), fix `_value` rather than the outer key.
   - Do **not** modify `[MANUAL REVIEW]` items.
6. Values shape: **nothing is auto-fixable here.** A missing `color` is legal and must be left
   alone; everything else in `values` is `[MANUAL REVIEW]`. Do not mutate items.
7. Apply auto-fixable layout fixes (L2 span fixes only):
   - For each `[AUTO-FIXABLE]` L2 issue: set the absent/null span to `24 − knownSpan` on the same object (`formSettings`, `component.labelCol`, or `component.wrapperCol`).
   - Do **not** modify `[MANUAL REVIEW]` layout items.
8. Do **not** auto-fix script label references from Step 4f — these are manual review only.
9. Apply auto-fixable try-catch fixes (Step 4h `[AUTO-FIXABLE]` items):
   - For each flagged script, locate the outermost function body and wrap its content in `try { ... } catch (error) { console.error('API call failed:', error); }`.
   - Update the property string value in the cloned component/formSettings object.
   - Do **not** modify `[MANUAL REVIEW]` try-catch items.
10. Apply auto-fixable async/await fixes (Step 4i `[AUTO-FIXABLE]` items):
    - **Scenario A**: In the script string, find the function declaration or arrow that owns the `await` and insert `async` before the `function` keyword or before the parameter list of an arrow function.
    - **Scenario B**: Apply the Scenario A async-add first, then prepend `await ` before each matched API call expression that is not already preceded by `await `.
    - Update the property string value in the cloned component/formSettings object.
    - Do **not** modify `[MANUAL REVIEW]` async items.
11. Do **not** auto-fix `.then()` chaining findings from Step 4j — these are manual review only.
    Apply the Step 4k `[FIXABLE]` items (N1, N2, N4; N5 only with `--fix-legacy-names`), or use the `scan-046.mjs --fix` output as the starting point and layer the other steps on top. Re-parse every edited script (async function body); drop the edit if it fails.
12. Do **not** modify component structure or any valid non-flagged properties.
13. Output the cleaned `{ components, formSettings }` object as a formatted JSON code block.

---

## Step 8: Summary

```
Cleaned form — N changes applied:

Dead properties removed:
  • "First Name" (textField): fontColor, borderRadius
  • "Submit" (button): backgroundColor

console.log calls removed:
  • "My Component" (textField) → onChangeCustom: 2 call(s)
  • "Submit" (button) → customVisibility._code: 1 call(s)

Type fixes applied:
  • "First Name" (textField) → spellCheck: "true" → true
  • "Age" (numberField) → max: "100" → 100

Values shape fixes applied:
  • "Category" (dropdown) → item[1]: added color ""

Values items needing manual review (not changed):
  • "Status" (dropdown) → item[0]: label is not a string

Items needing manual review (not changed):
  • "Container" (container) → alignItems: expected string, got object

Layout fixes applied:
  • [L2] formSettings: wrapperCol.span set to 16

Layout issues needing manual review (not changed):
  • [L1] "Container1" (container) — desktop: width 200% (wrap enabled)
  • [L2] "First Name" (textField): labelCol=10 + wrapperCol=10 = 20

Script label references needing manual review (not changed):
  • "Submit" (button) [customAction]: uses data['First Name'] — should be data['firstName']

Script syntax errors — CRITICAL, fix required:
  • "Submit" (button) [customAction]: unmatched braces: 3 opens, 2 closes
  • "Panel" (container) [onLoad]: unclosed string literal

Try-catch fixes applied:
  • "Submit" (button) [onFinish]: wrapped function body in try/catch
  • "Load Data" (customComponent) [getData]: wrapped function body in try/catch

Try-catch needing manual review (not changed):
  • "Complex" (customComponent) [onLoad]: multiple top-level functions

Async/await fixes applied:
  • "Submit" (button) [onFinish]: added async + await before axios.post(...)
  • "Validator" (textField) [customValidators]: added async to function signature

Async/await needing manual review (not changed):
  • "Complex" (button) [onFinish]: ambiguous — multiple top-level functions

API calls using .then() — manual review recommended (not changed):
  • "Submit" (button) [onFinish]: axios.post(...).then(result => {
  • "Load Data" (customComponent) [getData]: getHttp(...).then(data => {

Original size:  XX,XXX chars
Cleaned size:   YY,YYY chars
Reduction:      ZZZ chars (P%)
```

Omit whichever sections have no entries.
