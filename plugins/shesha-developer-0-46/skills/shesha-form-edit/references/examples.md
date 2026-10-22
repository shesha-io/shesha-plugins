# Canonical Example Forms — copy these first

`assets/examples/` holds four **Shesha-standard reference forms** captured verbatim from a working A.Test backend. They are the single source of truth for layout, component selection, and CRUD wiring. **Before authoring any new form, open the matching example and copy its structure** — change only `modelType`, `entityType`, `propertyName`s, captions, and the `formId` references. Do not invent structure the examples don't have.

These contain template tokens `{{GEN_KEY}}` / `{{NEW_KEY}}` for some ids — replace each with a fresh `crypto.randomUUID()` (the same token must map to the same UUID within one form so parent/child links stay intact).

### When you copy a seed, swap ALL of these (easy to miss):

1. `formSettings.modelType` → the target entity as the object `{ name: "<ShortClass>", module: "<Module>" }` (favoured shape; a legacy seed may carry a full-class-name string — convert it). Resolve `name`+`module` from `EntityConfig/GetMainDataList`.
2. Every `entityType` (string on `dataContext`; object `{name,module}` on `autocomplete`) → target entity.
3. Each field's `propertyName`, `componentName`, `name`, `label` → the real entity property.
4. The datatable `items` (columns) → the columns you want, with real `propertyName`s. **For the `entity-datalist.json` + `entity-card.json` pair: edit the row-template card form's fields to the card content you want (real `propertyName`s), point the datalist's `formId` at your card form, and set `selectionMode: "multiple"` if the prompt asked to select multiple.**
5. The Add button's `actionArguments.formId` → `{ name: "<your-create-form>", module: "<module>" }`.
6. **The title text** — the component with `componentName: "//*TITLE*//"`; set its `content` to your form's title (e.g. "Pay Grade Details"). Easy to leave as "Employee Details".
7. **The `modelType` debug text** — the text component `componentName: "modelType"` literally prints the class name on the page. Delete it for a clean form, or repurpose it.
8. `uniqueStateId` / `componentName` on the `dataContext` — give each table a unique id (don't leave `TABLE_VIEW_TEMPLATE_ID`) so multiple tables on a page don't share state.
9. Re-run `stampTree` so every `parentId` is correct after edits (descend into `components`, `columns[].components`, `tabs[].components`, **and `content.components`** for collapsible panels).

> **"table" vs "list" — pick the seed from the user's noun.** A **table**/grid request → the `datatable` seeds below (`employee-table.json`). A **list**/cards request ("list of X", feed, tiles, gallery) → the `datalist` seed `entity-datalist.json`. They are different components, not synonyms — see [components/data-tables.md](components/data-tables.md#table-vs-list--pick-the-component-from-the-users-wording-decide-this-first). When the prompt names neither, ask which the user wants.

| Need | Example file | Use when |
|---|---|---|
| **Table** / index / grid page | `assets/examples/employee-table.json` | "table", "grid", "manage X", "spreadsheet of X" — tabular data with sortable columns |
| **Card list** (datalist) | `assets/examples/entity-datalist.json` **+** `assets/examples/entity-card.json` | "**list** of X", "cards", "feed", "tiles", "gallery", "directory" — repeating card view; multi-select via `selectionMode: "multiple"`. Copy **BOTH**: the list (`dataContext` → `datalist`) and its **row-template card form**, then point the datalist's `formId` at your card form. (Live-verified row-template mode — see [data-tables.md](components/data-tables.md). Do NOT use inline `items`; it renders blank on 0.45.x.) |
| Inline-editable table (edit/add/delete in-row) | `assets/examples/inline-editable-table.json` | "edit details / add / remove **directly inside the rows**", inline-CRUD grid — has `crud-operations` column + concrete `{type, settings}` editors. See [components/inline-editable-tables.md](components/inline-editable-tables.md) |
| Create / edit in modal | `assets/examples/employee-create.json` | the form the table's **Add** button opens; submit comes from the modal footer (no in-form button row) |
| Standalone create / edit **page** (own Save + Back) | `assets/examples/standalone-create.json` | a full-page create/edit form the user opens directly (not in a modal), e.g. "create a person form" or "a form with a required first-name field" — the Save + Back row is mandatory even when the prompt never mentions buttons; see note below |
| Detail page, no children | `assets/examples/employee-detail-without-child-tables.json` | a standalone record view with the **Start Edit / Save / Cancel Edit toggle** lifecycle |
| Detail page with child tables | `assets/examples/employee-detail-with-child-tables.json` | record view that also lists related child entities |

### Standalone create / edit page (own Save + Back) — copy the seed

`assets/examples/standalone-create.json` is the canonical full-page create/edit form: a
`validationErrors`, a 2-column `detailsPanel`, and one `buttonGroup` with **Save** (primary,
`Submit`/`shesha.form`) + **Back** (default, `Navigate`/`shesha.common`). It's a Person create
page — swap `modelType`, the field `propertyName`s/labels, the title `content`, and the Back
button's `actionArguments.url` to the target entity's list form. This is the seed to reach for
on any "create a form for X" / "make me a person form" request, including terse ones.

**The Save + Back row is mandatory even when the prompt says nothing about buttons.** Requests
like *"a person form with one required first-name field"* describe only the fields, but a
create form with no way out is incomplete — a user who can save must be able to leave without
saving. The exit button is implied by create/edit intent — don't wait for the user to ask for
it. (This was a real miss: a one-field form shipped with Save but no Back.)

Key points the seed already encodes — preserve them:

- `editMode: "editable"` on the inputs (a standalone create/edit page is always in edit mode —
  `inherited` renders dead inputs here; that mode is only for the toggle-lifecycle detail view).
- The `validationErrors` component (mandatory once any field is required).
- Buttons live **inside the `buttonGroup`**, never as standalone `type: "button"` components —
  tooling reads form intent largely from `buttonGroup` items, so loose buttons can get the
  form misread as read-only. Full reasoning: [form-quality.md](form-quality.md).

Beyond that floor, don't add what the request didn't ask for — no extra panels, no `modelType`
debug text. Match the component count to the field list + validationErrors + the one buttonGroup
(+ the optional title in the seed).

### Scope note — what these seeds do and don't cover

- The employee seeds demonstrate **FK child tables**: `employee-detail-with-child-tables` filters an **Entity-sourced** `dataContext` with a `permanentFilter` on the child's `<parentFk>` (shape below).
- **M:M junction subtables are NOT in this seed set** — they use the **Url-sourced** `dataContext` canon (code-object `endpoint` returning a `/api/dynamic/<module>/<Junction>/Crud/GetAll?filter=...` URL): see [components/junction-subtables.md](components/junction-subtables.md).
- **Create dialogs that preset a parent FK** need more than the create seed: pass the parent via `formArguments` on the opening button AND inject it in `formSettings.onPrepareSubmitData` — `setFieldsValue` alone never survives submit (the gql submitter serializes only `_formFields`): see [components/add-dialogs.md](components/add-dialogs.md).

## The CRUD loop (how the four fit together)

1. **Table** (`employee-table`) lists records. Its toolbar **Add** button is a `buttonGroup` item with `buttonAction: "dialogue"` → `actionName: "Show Dialog"` (owner `shesha.common`) → `actionArguments.formId: { name: "<create-form>", module: "<module>" }`, `modalWidth: "60%"`, `formMode: "edit"`. It does **not** navigate. The Add button's `onSuccess` should be `Refresh table` with `actionOwner` = the `dataContext` **component id** (full shape below).
2. **Create** (`employee-create`) renders inside that modal. `dataLoaderType: "gql"`, `dataSubmitterType: "gql"`; the dialog's OK button submits it via the form's default endpoints.
3. **Detail** opens a full record. The header `buttonGroup` carries the lifecycle: **Edit** = `Start Edit` (owner `shesha.form`), **Save** = `Submit` (owner `shesha.form`), **Cancel** = `Cancel Edit` (owner `shesha.form`), plus an optional **Audit Log** = `Show Dialog` → `entity-change-audit-log` (module `Shesha`). There is **no** manual navigate-back Save.
4. **Child tables** live in a `tabs` component; each tab is a `dataContext` + `datatable` filtered to the parent.

## Recommended improvement over the raw example: refresh the table after Add

The captured `employee-table` Add button has `handleSuccess: false`, so creating a record (verified: `POST .../api/dynamic/<Module>/<Entity>/Crud/Create` → 200) closes the modal but **does not refresh the list** — the user must reload to see their new row. For better UX, set the Add button's action to refresh the table on success:

```json
"handleSuccess": true,
"onSuccess": {
  "_type": "action-config",
  "actionName": "Refresh table",
  "actionOwner": "<dataContext component id>"
}
```

`actionOwner` must be the table's `dataContext` **component id** (the same owner the toolbar Refresh button uses). Keep `handleFail: true` + `onFail: Close Dialog`.

## Non-obvious specifics the examples encode

- **Data context type is `dataContext`** (canonical here) with `sourceType: "Entity"`, `entityType: "<full.Class.Name>"`, `dataFetchingMode: "paging"`, `defaultPageSize: 10`, `uniqueStateId`, `componentName`, `propertyName`, `sortMode: "standard"`, `allowReordering: "no"`. (`dataContext` is an accepted alias but match the example and use `dataContext`.)
- **Toolbar buttons are context-scoped**: Refresh = `actionName: "Refresh table"`, column toggle = `"Toggle Columns Selector"`, both with `actionOwner` set to the **dataContext component's id** (not `shesha.common`).
- **The captured seed uses a `columns` component** named `detailsPanel`, `hideLabel: true`, `gutterX: 10`, `gutterY: 10`, two columns each `flex: 12` (24-grid → 50/50) — **replace it with a two-cell flex row when you copy** (`columns` is legacy; see [containers.md](components/containers.md)). Fields go inside the columns' `components`.
- **Component choice is driven by the property's data type** — see [components/by-datatype.md](components/by-datatype.md).
- **Child-table filter** uses JsonLogic + mustache:
  ```json
  "permanentFilter": { "and": [ { "==": [
    { "var": "<parentFkProp>" },
    { "evaluate": [ { "expression": "{{data.id}}", "required": true, "type": "mustache" } ] }
  ] } ] }
  ```
- **`editMode: "inherited"`** on every component; the detail header's Start Edit/Cancel Edit toggles the whole form.
