# Add dialogs — the modal-Add pattern

The canonical way to open a create form: the table's page-header `Add <Entity>` button uses `Show Dialog` to open the create seed in a modal, and the modal's `onSuccess` refreshes the parent table.

## The complete wiring

Add this to the table form's page-header `buttonGroup` (the one with Export + Add):

```jsonc
{
  "id": "<uuid>",
  "itemType": "item",
  "itemSubType": "button",
  "sortOrder": 1,
  "name": "addBtn",
  "label": "Add <Entity>",
  "icon": "PlusOutlined",
  "buttonType": "primary",
  "actionConfiguration": {
    "_type": "action-config",
    "actionName": "Show Dialog",
    "actionOwner": "shesha.common",
    "version": 1,
    "actionArguments": {
      "modalTitle": "Add <Entity>",
      "modalWidth": "80%",
      "formMode": "edit",
      "showCloseIcon": true,
      "footerButtons": "default",
      "formId": {
        "name": "<create-form-name>",
        "module": "<Module>"
      }
    },
    "handleSuccess": true,
    "onSuccess": {
      "_type": "action-config",
      "actionName": "Refresh table",
      "actionOwner": "<datatable-component-id>",
      "actionArguments": {}
    }
  }
}
```

Key points:

- **`modalWidth: "80%"`** — canonical width for create forms. `60%` is legacy.
- **`formMode: "edit"`** — the modal opens in edit mode; the create form's inputs (with `editMode: "editable"`) render as actual controls.
- **`footerButtons: "default"`** — the modal chrome supplies Save/Cancel. This is why the create form itself has **no in-form Save row** — adding one would double up the buttons.
- **`onSuccess: Refresh table`** — after the create submits successfully and the modal closes, the parent datatable reloads. `actionOwner` here is the CONCRETE id of the datatable component (not `shesha.common`). Re-map after regenerating UUIDs.
- **`handleFail`** — if omitted, defaults to a Close-Dialog behaviour. Add explicit `handleFail: true` + `onFail: { actionName: "Close Dialog", actionOwner: "shesha.common" }` for clarity.

## What the create form does NOT need

- **No in-form Save button**. The modal footer supplies Save/Cancel via `footerButtons: "default"`.
- **No `buttonGroup` at the bottom of the create form**. Same reason.
- **No `Back` button**. There's no "back" from a modal; the user closes it.

The create form's minimum floor is: subtitle text → `validationErrors` → N × `card` sections. That's it.

## When the create needs a parent FK preset

Contextual Adds (Add-Person-inside-Organisation-details, Add-Address-inside-Order-details) need the parent's id to reach the created record. Two things are required together:

1. **`formArguments`** on the opener button (passes the value into the dialog's form):
   ```jsonc
   "actionArguments": {
     "modalTitle": "Add Person to Organisation",
     "modalWidth": "80%",
     "formMode": "edit",
     "formId": { "name": "organisation-person-create", "module": "Forms.Optimization" },
     "formArguments": {
       "organisation": "{{data.id}}"      // passes parent Organisation id → the dialog's form.formArguments
     }
   }
   ```

2. **`formSettings.onPrepareSubmitData`** on the create form (injects the FK into the submit payload):
   ```js
   // formSettings.onPrepareSubmitData
   return { ...data, organisation: form.formArguments?.organisation };
   ```

`setFieldsValue`/`formArguments` alone do NOT reach the submit payload — only `_formFields`-declared properties (or values merged in `onPrepareSubmitData`) survive the gql submitter. This is a well-observed footgun.

## Row-scoped Adds (from a datatable's action column)

For an Add button in a row's action column that opens a child-create with the parent id preset (e.g. "Add message for this notification"):

```jsonc
{
  "columnType": "action",
  "type": "action",
  "icon": "PlusOutlined",
  "actionConfiguration": {
    "_type": "action-config",
    "actionName": "Show Dialog",
    "actionOwner": "shesha.common",
    "version": 1,
    "actionArguments": {
      "modalTitle": "Add message",
      "modalWidth": "60%",
      "formMode": "edit",
      "formId": { "name": "notification-message-create", "module": "Forms.Optimization" },
      "formArguments": {
        "partOf": "{{selectedRow.id}}"   // the parent Notification's id
      }
    },
    "handleSuccess": true,
    "onSuccess": {
      "_type": "action-config",
      "actionName": "Refresh table",
      "actionOwner": "<this-datatable-id>"
    }
  }
}
```

Note `{{selectedRow.id}}` (double-brace mustache) — the datatable's row scope makes `selectedRow` available.

## Common mistakes

- ❌ `modalWidth: "60%"` on the primary create Add button — should be `80%`. `60%` is fine for narrow row-scoped adds.
- ❌ Adding an in-form Save button on the create form — modal chrome already supplies one.
- ❌ Omitting `handleSuccess: true` + `onSuccess: Refresh table` — the modal closes but the table shows stale data.
- ❌ `actionOwner: "shesha.common"` on the Refresh — should be the concrete datatable's `id`.
- ❌ Presetting a FK via `formArguments` without also declaring it in `onPrepareSubmitData` — the submit drops the FK → `Crud/Create` fails with a required-field-missing 500.
