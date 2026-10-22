# Component selection by property data type

Pick the input component from the entity property's `dataType` (from `Metadata/GetProperties`). This mirrors the canonical `employee-create` example exactly.

> `editMode` per the form-type rule: the table/examples below hardcode the **detail-form** value (`"inherited"`); dialogs/action pages use `"editable"` — see [edit-mode.md](edit-mode.md).

| Property `dataType` | Component `type` | Required config |
|---|---|---|
| `string` (short) | `textField` | `propertyName`, `editMode: "inherited"` |
| `string` (long/multiline) | `textArea` | `propertyName`, `editMode: "inherited"` |
| `number` | `numberField` | `propertyName`, `editMode: "inherited"` |
| `boolean` | `checkbox` (or `switch`) | `propertyName`, `editMode: "inherited"` |
| `date` | `dateField` | `propertyName`, `editMode: "inherited"` |
| `date-time` | `dateField` | `propertyName`, `selectionType: "dateTimeMinutes"` (0.46 v9; `showTime`/`picker` are gone) |
| `reference-list-item` | `dropdown` | `dataSourceType: "referenceList"`, `referenceListId: { module, name }`, `bindingFormat: "itemValue"`, `enableMultiSelect: false` (0.46 v15; `valueFormat`/`mode` are migrated away) |
| `entity` (FK) | `autocomplete` | `dataSourceType: "entitiesList"`, `entityType: { name: "<ShortClass>", module: "<Module>" }`, `valueFormat: "entityReference"`, `mode: "single"`, `useRawValues: false` |
| `file` | `fileUpload` | `propertyName` |

## Reference-list dropdown (from `employee-create` → `employmentType`, `status`)

```json
{
  "type": "dropdown",
  "propertyName": "status",
  "label": "Status",
  "editMode": "inherited",
  "dataSourceType": "referenceList",
  "referenceListId": { "module": "A.Test", "name": "A.Test.EmployeeStatus" },
  "bindingFormat": "itemValue",
  "enableMultiSelect": false
}
```

Find the reference-list name from the property metadata: `referenceListName` + `referenceListModule` on the property. `referenceListId.name` is the **fully-qualified** list name (`<Module>.<ListName>`).

## FK autocomplete (from `employee-create` → `payGrade`)

```json
{
  "type": "autocomplete",
  "propertyName": "payGrade",
  "label": "Pay Grade",
  "editMode": "inherited",
  "dataSourceType": "entitiesList",
  "entityType": { "name": "PayGrade", "module": "A.Test" },
  "valueFormat": "entityReference",
  "mode": "single",
  "useRawValues": false
}
```

`entityType` here is an **object** `{ name: "<ShortClassName>", module }` — the short class name, NOT the full namespace. Get the FK target from the property metadata's `entityType` field.

> A bare `autocomplete`/`entityPicker` with no `entityType` renders an empty box. A `dropdown` without `dataSourceType` renders no options. Always set the data-source config.

## As a datatable inline-edit column editor

The SAME component types above are the editors for inline-editable datatable columns — but they are nested under the column's `editComponent`/`createComponent` as `{ "type": "<editorType>", "settings": { <the full component model from this table, incl `version` + `editMode:"inherited"` + `hideLabel:true`> } }`, NOT placed directly. The column's `propertyName` provides the binding, so the `settings` is widget config only (no `propertyName` needed). Map: string→`textField`, number→`numberField`, date→`dateField`, reference-list-item→`dropdown` (referenceList), entity FK→`autocomplete`. Read-only columns use `{ "type": "[not-editable]" }`. Never `[default]`, never a flat (un-`settings`-wrapped) model. Full recipe: [inline-editable-tables.md](inline-editable-tables.md).

> **When you copy a dropdown/autocomplete from a seed, you MUST override its data-source for the new field.** A copied dropdown keeps the seed's `referenceListId`/`referenceListName` (e.g. it'll still point at `EmploymentType`), and a copied autocomplete keeps the seed's `entityType`. Always replace `referenceListId`+`referenceListName` (dropdown) or `entityType` (autocomplete) with the new field's own values — verified: forgetting this makes the field show the wrong list's options.
