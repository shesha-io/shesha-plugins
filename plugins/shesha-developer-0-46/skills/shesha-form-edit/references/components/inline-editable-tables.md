# Inline-editable datatables (edit / add / delete directly in rows)

Use this when the request is to change row details, add records, or delete records **inside the
grid** (not via a modal Add dialog or a separate detail page). It is a distinct contract from the
standard display table — the template generator produces display-only tables (`canEditInline:"no"`,
every column `editComponent:"[not-editable]"`, a modal "Add" button), so you must layer inline
editing on yourself.

> Seed: copy [`../../assets/examples/inline-editable-table.json`](../../assets/examples/inline-editable-table.json) — a verified working inline-CRUD table — and swap `entityType`/`modelType`/columns/editors.

---

## 1. Datatable flags

On the `datatable` component (inside its `dataContext` wrapper — see [data-tables.md](data-tables.md)):

```jsonc
"canEditInline": "yes",
"canAddInline": "yes",
"canDeleteInline": "yes",
"crud": false,                 // the separate toolbar-CRUD mode; inline editing does NOT need it true
"inlineEditMode": "one-by-one",
"inlineSaveMode": "manual",
"newRowCapturePosition": "top",
"newRowInsertPosition": "top"
```

`"yes"/"no"` are **strings**, not booleans.

**No toolbar "New" button.** With `canAddInline:"yes"` + `newRowCapturePosition:"top"`, add is the
in-row capture row (a "+" Add control at the top). A separate toolbar New button is redundant **and**
there is no valid toolbar inline-add action — wiring one to `Add list items` throws
`Validation failed: Action 'Add list items' ... not found`. Keep the toolbar to quick-search + pager.
(The harness's "exactly one primary button" check does not apply to a pure inline-CRUD table; the
in-row controls are the affordances.)

## 2. The `crud-operations` column (required for per-row controls)

Without it, rows render but show no Edit/Delete/Save buttons. Add it as the first column:

```json
{ "id": "<uuid>", "columnType": "crud-operations", "caption": "", "isVisible": true, "sortOrder": -1, "itemType": "item" }
```

With `canAddInline:"yes"` an **add-capture row** appears at the top (with Add/Reset buttons and an
editor in every column); with `canEditInline:"yes"` each row gets an Edit button (→ Save/Cancel);
with `canDeleteInline:"yes"` each row gets a Delete button.

## 3. Per-column editors — the shape that actually works

Each `data` column has three slots. **`displayComponent` may be `[default]`. `editComponent` and
`createComponent` may NOT.**

| Slot | Allowed values |
|---|---|
| `displayComponent` | `{ "type": "[default]" }` (default display) — fine |
| `editComponent` / `createComponent` | `{ "type": "[not-editable]" }` (read-only cell) **OR** `{ "type": "<editorType>", "settings": { …full model… } }` |

**Two shapes crash the whole table — never produce them:**
- `{ "type": "[default]" }` on edit/create → `Cannot read properties of undefined (reading 'migrator')`.
- a **flat** model (props at the top level, no `settings` wrapper) → `Cannot read properties of undefined (reading 'version')`.

The cell renderer reads `customComponent.type` (must be a registered component) and
`customComponent.settings` (a FULL component model — its own `type` + `version` + styling). The
column's `propertyName` provides the binding, so `settings` is widget config only (no `propertyName`).

Editor type per property `dataType` (see [by-datatype.md](by-datatype.md)): string→`textField`,
number→`numberField`, date→`dateField`, reference-list-item→`dropdown` (referenceList), entity FK→`autocomplete`.

### Example column (string → textField editor)

```json
{
  "id": "<uuid>", "columnType": "data", "propertyName": "name", "caption": "Item Name",
  "isVisible": true, "itemType": "item", "minWidth": 150, "maxWidth": 250, "allowSorting": true,
  "displayComponent": { "type": "[default]" },
  "editComponent":   { "type": "textField", "settings": { "type": "textField", "version": 8, "editMode": "inherited", "hideLabel": true, "label": "", "textType": "text", "validate": {} } },
  "createComponent": { "type": "textField", "settings": { "type": "textField", "version": 8, "editMode": "inherited", "hideLabel": true, "label": "", "textType": "text", "validate": {} } }
}
```

### Reference-list dropdown editor (category / status)

```json
"editComponent": { "type": "dropdown", "settings": {
  "type": "dropdown", "version": 15, "editMode": "inherited", "hideLabel": true, "label": "",
  "dataSourceType": "referenceList",
  "referenceListId": { "module": "<module>", "name": "<ReflistName>" },
  "bindingFormat": "itemValue", "enableMultiSelect": false, "validate": {}
} }
```

### Entity FK autocomplete editor (assignedTo → Person)

```json
"editComponent": { "type": "autocomplete", "settings": {
  "type": "autocomplete", "version": 9, "editMode": "inherited", "hideLabel": true, "label": "",
  "dataSourceType": "entitiesList",
  "entityType": { "name": "Person", "module": "Shesha" },
  "mode": "single", "useRawValues": false, "validate": {}
} }
```

`numberField` (`version` 3) and `dateField` (`version` 7) follow the same pattern. **Use the
component versions of the running app** (grep a form dump) — versions are framework-version-specific.

> **Practical sourcing:** rather than hand-writing each `settings`, clone a full component model of
> each type from the running app's own forms (a form dump), strip `id`/`parentId`/`propertyName`/
> `componentName`/`name`/`defaultValue`, and set `editMode:"inherited"` + `hideLabel:true`. That
> guarantees version-consistency with the app and avoids migration crashes.

## 4. Known cosmetic limitation

In `@shesha-io/reactjs` 0.45.x (not re-verified on 0.46), a **reference-list dropdown used as an inline-grid editor shows
`unknown` for the row's existing value** in edit mode (the display cell still resolves the label
correctly, and the dropdown's options load and save fine). This is not a config bug — toggling
`valueFormat`/`useRawValues` does not change it. Leave it; the editor is fully functional.

## 5. Save / data binding

The grid's create/update/delete go through the entity's dynamic CRUD endpoints (the
`dataContext` `entityType` must be the exact registered class). Reference-list and FK columns
require the reflist to have items / the FK target to have records, or the dropdowns/pickers are empty.
