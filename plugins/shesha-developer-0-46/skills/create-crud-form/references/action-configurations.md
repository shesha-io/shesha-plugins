# Action configurations

Every action wiring in the four seeds — byte-exact. Copy from here for a canonical CRUD form. Legacy field `buttonAction: "dialogue"` is redundant on current builds; drop it.

## Show Dialog — the modal Add / Add row-actions

Opens a form (typically the create seed) in a modal. Used by the table's `Add <Entity>` button, and by row-level "Book …" / "Order …" quick-actions.

```jsonc
{
  "_type": "action-config",
  "actionName": "Show Dialog",
  "actionOwner": "shesha.common",
  "version": 1,
  "actionArguments": {
    "modalTitle": "Add <Entity>",
    "modalWidth": "80%",            // 80% for create forms; 60% is legacy
    "formMode": "edit",
    "showCloseIcon": true,
    "footerButtons": "default",     // modal chrome supplies Save/Cancel — no in-form Save row
    "formId": {
      "name": "<create-form-name>",
      "module": "<Module>"
    }
  },
  "handleSuccess": true,
  "onSuccess": {
    "_type": "action-config",
    "actionName": "Refresh table",
    "actionOwner": "<datatable-component-id>",   // the concrete id of the target datatable component
    "actionArguments": {}
  }
}
```

`actionOwner: "<datatable-component-id>"` is the **concrete `id` of the `datatable` component** in the tree — after regenerating UUIDs, remap this. Not a symbolic name.

For contextual Adds that need to preset a parent FK on the created record (e.g. Add-Person-inside-Organisation-details), pass `formArguments` in the dialog AND have `formSettings.onPrepareSubmitData` on the create form inject the FK. `formArguments`/`setFieldsValue` alone don't reach the submit payload.

## Refresh table

Reloads a specific datatable. Fired by the toolbar Refresh button, and by the modal Add's `onSuccess`.

```jsonc
{
  "_type": "action-config",
  "actionName": "Refresh table",
  "actionOwner": "<datatable-component-id>",
  "actionArguments": {}
}
```

## Export to Excel

Fired by the page-header's Export button.

```jsonc
{
  "_type": "action-config",
  "actionName": "Export to Excel",
  "actionOwner": "<datatable-component-id>",
  "actionArguments": {}
}
```

## Toggle Columns Selector

Opens the built-in column-picker drawer. Wired to the toolbar's `Column Selector` button.

```jsonc
{
  "_type": "action-config",
  "actionName": "Toggle Columns Selector",
  "actionOwner": "<datatable-component-id>",
  "actionArguments": {}
}
```

## Detail-view lifecycle — Start Edit / Submit / Cancel Edit

All three live in a single `buttonGroup` in the details header. `actionOwner` is `shesha.form` (the form itself, not a specific component).

```jsonc
// Edit button (primary)
{
  "_type": "action-config",
  "actionName": "Start Edit",
  "actionOwner": "shesha.form",
  "actionArguments": {}
}

// Save button
{
  "_type": "action-config",
  "actionName": "Submit",
  "actionOwner": "shesha.form",
  "actionArguments": {}
}

// Cancel Edit button
{
  "_type": "action-config",
  "actionName": "Cancel Edit",
  "actionOwner": "shesha.form",
  "actionArguments": {}
}
```

All three buttons are always in the DOM; Shesha handles visibility via the form's edit state. Do NOT add conditional-render logic — the framework handles it.

## Row → detail navigation

The last column of the datatable is an action column that navigates to the details form with the row's id.

```jsonc
// datatable column (in .items[])
{
  "id": "<uuid>",
  "columnType": "action",
  "type": "action",
  "itemType": "item",
  "caption": "",
  "isVisible": true,
  "sortOrder": 999,
  "minWidth": 45, "maxWidth": 60, "width": 50,
  "icon": "EyeOutlined",
  "anchored": "right",
  "actionConfiguration": {
    "_type": "action-config",
    "actionName": "Navigate",
    "actionOwner": "shesha.common",
    "version": 2,
    "actionArguments": {
      "navigationType": "form",
      "formId": {
        "name": "<details-form-name>",
        "module": "<Module>"
      },
      "queryParameters": [
        { "key": "id", "value": "{{selectedRow.id}}" }
      ]
    }
  }
}
```

`navigationType: "form"` + `formId: { name, module }` + `queryParameters: [{ key: "id", value: "{{selectedRow.id}}" }]` is the canonical shape. **Do NOT** use `target: "/dynamic/<mod>/<form>?id={{selectedRow.id}}"` as a raw URL — that's the legacy shape and it fails silently on some builds.

## Plain Navigate (Back / Home / arbitrary URL)

For a Back button, or any inter-page navigation not driven by a selected row:

```jsonc
{
  "_type": "action-config",
  "actionName": "Navigate",
  "actionOwner": "shesha.common",
  "version": 2,
  "actionArguments": {
    "navigationType": "form",
    "formId": { "name": "<target-form-name>", "module": "<Module>" }
  }
}
```

Or for a raw URL (only if there's no target form):
```jsonc
"actionArguments": { "target": "/dynamic/<mod>/<form-name>" }
```

## Execute Script (rare — for anonymous form submit, custom fetches)

The login form uses this to POST to `/api/TokenAuth/Authenticate` and stash the token:

```jsonc
{
  "_type": "action-config",
  "actionName": "Execute Script",
  "actionOwner": "shesha.common",
  "actionArguments": {
    "expression": "try { const r = await http.post('/api/TokenAuth/Authenticate', { userNameOrEmailAddress: data.userNameOrEmailAddress, password: data.password }); if (r.data?.result?.accessToken) { localStorage.setItem('accessToken', r.data.result.accessToken); window.location.href = '/dynamic/<Module>/<home-form>'; } else { message.error('Login failed'); } } catch (e) { message.error('Login failed: ' + (e.message || e)); }"
  }
}
```

Scripts run against these globals: `data` (form values), `http` (axios-like), `message` (Ant message), `moment`, `application` (with `application.user` for current user), `contexts.appContext` / `pageContext` (shared state). Use `try/catch` + `await` — no `.then()` chains, no `console.log`.

## Show Confirmation Dialog (delete rows, destructive ops)

```jsonc
{
  "_type": "action-config",
  "actionName": "Show Confirmation Dialog",
  "actionOwner": "shesha.common",
  "actionArguments": {
    "title": "Delete <Entity>",
    "content": "Are you sure you want to delete this record?",
    "okText": "Yes",
    "cancelText": "No",
    "danger": true
  },
  "handleSuccess": true,
  "onSuccess": {
    "_type": "action-config",
    "actionName": "Execute Script",
    "actionOwner": "shesha.common",
    "actionArguments": {
      "expression": "try { await http.delete('/api/dynamic/<Module>/<Entity>/Crud/Delete?id=' + selectedRow.id); message.success('Deleted'); } catch (e) { message.error('Delete failed'); }"
    },
    "handleSuccess": true,
    "onSuccess": {
      "_type": "action-config",
      "actionName": "Refresh table",
      "actionOwner": "<datatable-component-id>"
    }
  }
}
```

## Anti-patterns

- ❌ Legacy `buttonAction: "dialogue"` on a buttonGroup item — drop it; use `actionConfiguration.actionName: "Show Dialog"` directly
- ❌ Row-nav via `actionArguments.target` raw URL — use `navigationType: "form"` + `queryParameters` instead
- ❌ `actionOwner: "table"` for `Delete row` — no such built-in action; use `Execute Script` + `http.delete`
- ❌ Save button wired to anything other than `Submit`/`shesha.form` — the submit pipeline never fires, and downstream tooling misreads the form as read-only
- ❌ Loose top-level `button` components in a form's action row — every action button lives inside a `buttonGroup`
