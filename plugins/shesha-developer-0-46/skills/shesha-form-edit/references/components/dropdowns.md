# dropdown / radio / checkboxGroup / refListStatus

All interactive variants use `editMode: "inherited"` (except `refListStatus`, which is display-only).

---

## dropdown

Two data sources: `'values'` (hardcoded) or `'referenceList'` (Shesha reference list).

### Reference list source

**Always read `referenceListId.module` and `referenceListId.name` from the property metadata — never guess.** The property object returned by `Metadata/GetProperties` has two fields you need:

- `property.referenceListModule` → `referenceListId.module`
- `property.referenceListName` → `referenceListId.name` (this is the fully-qualified list name, e.g. `"MyApp.Membership.AccountType"`)

A wrong module/name pair produces a **silent empty dropdown** with no runtime error — there is no way to detect this without opening the form in a browser. Never infer or guess these values.

```json
{
  "id": "...",
  "type": "dropdown",
  "propertyName": "accountType",
  "label": "Account Type",
  "dataSourceType": "referenceList",
  "referenceListId": {
    "module": "MyApp.Membership",
    "name": "MyApp.Membership.AccountType"
  },
  "version": 15,
  "bindingFormat": "itemValue",
  "enableMultiSelect": false,
  "editMode": "inherited"
}
```

**`referenceListId` is NOT a Guid** — it's `{ module, name }`. The framework resolves at runtime.

### Hardcoded values source

Every item must have all three keys (`id`, `label`, `value`):

```json
{
  "id": "...",
  "type": "dropdown",
  "propertyName": "preference",
  "dataSourceType": "values",
  "values": [
    { "id": "1", "label": "Email", "value": "email" },
    { "id": "2", "label": "SMS", "value": "sms" }
  ],
  "editMode": "inherited"
}
```

Validation: when `dataSourceType === "values"`, each item in `values` is `{ id, label, value }`. Missing any of the three is a bug — `clean-form-config` flags this.

0.46 (dropdown v15): multi-select is the boolean `enableMultiSelect` (the old `mode: single|multiple|tags` is migrated to it), and the stored-value shape is `bindingFormat: "itemValue" | "itemLabel"` (the old `valueFormat: "simple"` is migrated to `itemValue`; a legacy `custom` format is left without a `bindingFormat`). Display is `displayStyle: "text" | "tags"` with `tagVariant: "solid" | "outlined" | "filled"`. `autocomplete` still uses `mode`/`valueFormat`.

---

## radio

Same `dataSourceType` rules as `dropdown` (above). `radio` is single-select.

---

## checkboxGroup (multi-select)

**`checkboxGroup` does NOT match `dropdown`'s shape — do not conflate them.** Verified against a working form:

- Hardcoded options live in **`items`** (NOT `values`), and each item is **`{ label, value }`** (no `id` needed — the renderer auto-assigns one).
- Carries **`version: 8`** (0.46; legacy single mode migrates to a `radio`), plus `dataSourceType: "values"`, `referenceListId: null`, `container: {}`, `validate: {}`.
- For a reference-list source, use `dataSourceType: "referenceList"` + `referenceListId: { module, name }` (same as dropdown), with `items`/`values` null.

```json
{
  "id": "...",
  "type": "checkboxGroup",
  "propertyName": "operatingSystems",
  "label": "Operating Systems",
  "version": 8,
  "dataSourceType": "values",
  "mode": "multiple",
  "direction": "vertical",
  "editMode": "readOnly",
  "referenceListId": null,
  "container": {},
  "validate": {},
  "items": [
    { "label": "Windows", "value": "windows" },
    { "label": "Linux", "value": "linux" }
  ]
}
```

**Do NOT give a checkboxGroup (or any multi-select) a literal-array `defaultValue`** — see the `defaultValue` rule below. To pre-select values on a display form, bind through form data / a data loader rather than `defaultValue`.

---

## `defaultValue` is a mustache template string — never a literal non-string

The framework resolves `defaultValue` at render via `defaultValue.match(/{{key.accessor}}/)`. A plain string is returned as-is (when it isn't a `{{…}}` expression); a mustache string is resolved against form data. But a literal **array** (e.g. a multi-select default `["a","b"]`), **number**, or **object** has no `.match` → **`e.match is not a function`** and the component fails to render (`'checkboxGroup' has configuration issue(s) — e.match is not a function`). Only ever set `defaultValue` to a string. For multi-value defaults, omit it and bind via data.

---

## refListStatus

Display-only badge for a reference-list-typed property (0.46 v9). Shape per the component's `ownProps`
(`referenceListId`, `itemDisplay`, `solidBackground`) - **there are no flat `module` / `referenceListName` keys**:

```json
{
  "id": "...",
  "type": "refListStatus",
  "version": 9,
  "propertyName": "status",
  "referenceListId": { "module": "MyApp.Membership", "name": "ApplicationStatus" },
  "itemDisplay": "both",
  "solidBackground": true
}
```

`itemDisplay` is `"name" | "icon" | "both"` (or a code-mode setting returning `{showName, showIcon}`); it replaces the old
`showReflistName`/`showIcon` pair - a legacy "neither" (colour-only badge) now migrates to `"both"`. The tag renders in every interaction mode.
**Never place a `refListStatus` inside a `subForm`** - it throws `Component with id ... is not found`
([../render-hazards-046.md](../render-hazards-046.md) H13).

No `editMode` needed (display-only).
