# Interaction Mode (`editMode`), visibility, permissions (0.46)

In the 0.46 designer the setting formerly labelled **Edit Mode** is **Interaction Mode**; the stored key is still `editMode`. Visibility
is `visible` (the inverse of the old `hidden`), and permissions are per setting: `visiblePermissions` (Visible) and
`editModePermissions` (Interaction Mode). Legacy `permissions` is deprecated (`providers/form/models.ts:409`) and migrated to
`visiblePermissions`.

---

## editMode rule (non-negotiable) — decided PER FORM TYPE

There is no single correct value. Both blanket rules caused real production bugs: blanket `"editable"` made detail-form fields editable before the user clicked Edit; blanket `"inherited"` rendered dead inputs on action pages and dialogs tested standalone. Decide by the form's type:

| Form type | Interactive inputs (`textField`, `dropdown`, `autocomplete`, …) | Why |
|---|---|---|
| **Entity detail form** with a Start Edit / Submit / Cancel Edit lifecycle | `"inherited"` | The form-level mode governs; the lifecycle buttons toggle it. Explicit `"editable"` makes fields editable while the form is still in read mode. |
| **Create / edit dialog** (opened via Show Dialog with `formMode: "edit"`) | `"editable"` | A dialog is always an edit context; proven canon across 33 production create forms. Also keeps the dialog testable standalone. |
| **Action / anonymous pages** (`dataLoaderType: "none"`, login, OTP, search forms, custom toolbars) and inline `link`s | `"editable"` | The effective mode resolves read-only, so `"inherited"` renders fields that won't accept input and buttons that swallow clicks. |
| **Read-only attribute rail / detail summary** — controls the user *reads*, never edits inline | `"readOnly"` per control | `"inherited"` defers to form mode and renders **blank** in the default view state, so an entity/reflist field shows an empty cell until the form enters edit mode (the "rail labels with no values" defect). `"readOnly"` resolves and displays the `_displayName` immediately. |
| **Pure visual / display** (`text`, `image`, `container`, `card`, `refListStatus`) | `"inherited"` or omit | No interactive surface. |
| **Detail-header lifecycle `buttonGroup`** (Edit/Save/Cancel) | copy the canonical seed verbatim | The seeds encode the working config; don't restamp. |

Never blanket-stamp either value across a whole form. When validating an edit: walk the tree and assert each interactive component's `editMode` matches the **form-type rule above** — flag mismatches per form type, not against a single absolute.

### Interaction Mode values and what they do in 0.46

`EditMode = 'editable' | 'readOnly' | 'disabled' | 'inherited' | boolean` (`providers/form/models.ts:118`). Resolved by
`getDisabledAndReadOnly` (`components/formDesigner/formComponent/formComponentApi.ts:18-27`):

| value | result |
|---|---|
| `'editable'` or `true` | editable |
| `'readOnly'` | read-only (plain value) |
| `'disabled'` or boolean **`false`** | **disabled** (greyed control) - in 0.43/0.45 `false` meant read-only |
| `'inherited'` | resolved from the parent / form mode first |

So a code-mode `editMode` must return **strings** (`'editable' | 'readOnly' | 'disabled' | 'inherited'`), never a bare `true/false`
([render-hazards-046.md](../render-hazards-046.md) H15). The `required` rule is skipped on read-only/disabled models
(`providers/form/utils.ts:1131`), so a red "required" message on a read-only view means the model is not actually read-only (wrong
inheritance) or something calls `validateFields()`. Tabs: `selectMode: 'readOnly'` migrated to per-tab `editMode: 'disabled'`.

### Buttons: `"inherited"` renders `disabled`, with no visual cue

Worth its own warning because nothing tells you. A `button` / `buttonGroup` item left on `editMode: "inherited"` inside a read-only display context (a `datalist` row template being the common case) is rendered with the DOM attribute **`disabled`** — there is no HTML `readonly` for `<button>`, so the framework substitutes `disabled`. The button looks completely normal, clicks do nothing, and no console message appears. Schema and guardrail validation both pass clean.

Set `editMode: "editable"` explicitly on **both** the `buttonGroup` and the item, on any interactive control whose parent context you have not positively confirmed is editable. If the button is inside a datalist row template, fixing `editMode` only gets you as far as a button that is *enabled* — its action still won't fire from that scope, which is a separate problem with its own fix in [data-tables.md](data-tables.md) "Card click-through".

---

## Visibility / enabled

| Property | Meaning |
|---|---|
| `visible` | Boolean OR code-mode setting returning bool. **False removes the component - it is not mounted at all** (`configurableFormItemLive.tsx:68`); hidden helpers (CSS carriers, data holders) therefore do nothing - [render-hazards-046.md](../render-hazards-046.md) H6. Default `true`. |
| `hidden` | Legacy inverse of `visible`. Still honoured at render, and migrated to `visible` on load (a code-mode `hidden` becomes a negated `visible` script). Do not author it in new markup. |
| `customVisibility` / `customEnabled` | Deprecated JS-expression forms; use code-mode `visible` / `editMode`. |
| `editMode` | Interaction Mode, values above. **Set per the form-type rule above** (detail forms `inherited`, dialogs/action pages `editable`). |

Code-mode shape (the `_value` mirrors the last evaluated result and must be present):

```json
"visible": { "_mode": "code", "_code": "return form.formMode === 'edit' && Boolean(data?.parent);", "_value": true }
```

Always optional-chain on every hop - a throwing visibility script counts as **visible**
([render-hazards-046.md](../render-hazards-046.md) H10). Interaction rules: `'readOnly'` always wins; `'editable'` is final;
`'inherited'` resolves against the form's effective mode and is risky on forms with no data loader.

---

## Conditional containers

A `hidden` container hides itself AND its children. Don't combine with per-child `hidden` unless deliberately layered — the child rules don't override the parent's.

---

## Permissions (per setting)

```json
"visiblePermissions": ["app:Members.View"],
"editModePermissions": ["app:Members.Edit"]
```

* `visiblePermissions` - the component is not rendered unless the user holds **any** listed permission (empty/absent = no restriction).
* `editModePermissions` - without any of them the component is forced read-only/disabled (`formComponentModelPreparer.tsx:99-105`).
* Legacy `permissions` still hides the component when unmet but is deprecated; do not author it.
* To require ALL, list a single hook permission and group via roles.

Form-level permissions live on the FormConfiguration record (`access` + `permissions` on `UpdateMarkup`; `access >= 3`
writes them, see [../api.md](../api.md) section 5), not in markup.
