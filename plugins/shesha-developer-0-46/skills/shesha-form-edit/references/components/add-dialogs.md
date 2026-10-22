# Add/create dialogs and submission mechanics

Read when wiring an "Add"/"Create" button on a details-form subtable, or authoring the dialog form it opens. Subtable structure and Add-button *placement* live in [junction-subtables.md](junction-subtables.md); this file covers the dialog form itself and how its data actually reaches the server.

---

## Two dialog patterns

|  | Junction LINK form | Child CREATE form |
|---|---|---|
| Purpose | link an EXISTING record via an M:M junction | instantiate a NEW child record |
| `formSettings.modelType` | the JOIN entity (`<Module>.Domain.<Junction>`) | the CHILD entity |
| Visible fields | ONE autocomplete picking the target entity | the child's own fields (name, reflist dropdowns, textAreas…) |
| Parent FK | from context — read-only component + submit injection (below) | read-only (NOT hidden - hidden components are not mounted in 0.46) parent-FK component + submit injection |
| Button label | `"Add <X>"` | `"Create <X>"` |

- Decide by relationship type, not habit: linking existing records → LINK form; creating new ones → CREATE form. Relationship classification (owned M:M → Add; "Used By…" reverse → NO Add button; owned child → Create) is in [junction-subtables.md](junction-subtables.md).
- **Never render a visible parent picker the user can change** — the parent is already known from the opening context; forcing a re-selection invites wrong links.
- Label rule: "Add X" when linking existing, "Create X" when instantiating. Mixed wording across similar forms confuses users about whether they are creating or linking.

---

## Passing context

The opening button passes `formArguments` inside the Show Dialog `actionArguments` — a code expression returning the parent reference:

```js
// Show Dialog → actionArguments.formArguments (code mode)
return { <parentFk>: { id: data.id, _displayName: data.name, _className: '<Module>.Domain.<Parent>' } };
```

- `formArguments: []` (empty) passes NOTHING — a common audit finding on hand-built buttons.
- The dialog reads it via `form.formArguments` in **`formSettings.onDataLoaded`** — **NOT `onBeforeDataLoad`**: form context does not exist yet there (`form` and `setFormData` are undefined; errors `Cannot read properties of undefined (reading formMode)`, `setFormData is not defined`). Use `onBeforeDataLoad` only for work that needs no form context.

```js
// formSettings.onDataLoaded — seed the display model
const a = form.formArguments;
if (a && a.<parentFk>) {
  form.setFieldsValue({ <parentFk>: a.<parentFk> });
}
```

This seeds the **display model only**. It does NOT make the value submit — see the hard rule below. Embedded-JS rules (async, try/catch, no console.log) are in [scripts.md](scripts.md).

### When `formArguments` silently doesn't arrive

The recipe above is the one that works **from a subtable's own top-level Add button**. It is not universal, and the failure is silent:

- **From inside a `datalist` row-template card, `formArguments` does not deliver code-evaluated values at all.** Authored as a `{_mode,_code}` object the dialog opens with every field empty; authored as a bare code string the dialog **doesn't open at all** — no modal in the DOM, no console error, no network call (even `"return {};"` fails, so it's the string type breaking evaluation, not the expression). Full measurements: [data-tables.md](data-tables.md) "Card click-through". Use the `datalist`'s own `onListItemClick` with a `contexts.appContext` relay instead.
- The safe general rule while this is unresolved: **treat `Show Dialog`'s `formArguments` as reliable only for static/literal values**, and relay anything dynamic through `contexts.appContext`.

### `onDataLoaded` never fires on a dialog that loads no data

A modal *feels* like a fresh page load, but it is still a form — and on `dataLoaderType: "none"` the `onDataLoaded` hook **never runs**. Nothing errors; your seeding code simply never executes. Detecting it takes a `window` flag set inside the handler.

**Use `onAfterDataLoad` for dialog seeding**, or give the dialog a real loader. This bites even people who already know the generic rule, because the modal doesn't look like a no-loader form.

---

## Submission mechanics — THE HARD RULE

The gql submitter serializes ONLY `_formFields` — the registered **visible** components.

| Mechanism | Reaches the POST body? |
|---|---|
| Visible (incl. read-only) component bound to the prop | yes |
| Component with `hidden: true` / `visible: false` | **NO** — hidden components are not mounted in 0.46 (`configurableFormItemLive.tsx:68`), so they register no field and are excluded from the payload |
| `formArguments` alone | **NO** — display model only |
| `form.setFieldsValue(...)` in onDataLoaded alone | **NO** |
| `formSettings.onPrepareSubmitData` mutation | yes — runs on the outgoing `data` |

**Rule: ANY dialog that presets a required FK contextually MUST have BOTH:**

1. a real (read-only — see [edit-mode.md](edit-mode.md)) component bound to the FK, **and**
2. `formSettings.onPrepareSubmitData` injecting it *(runtime-verified form-settings key; not in the groups index — clean-form-config may flag it; do NOT strip)*:

```js
// formSettings.onPrepareSubmitData
const a = form.formArguments;
if (a && a.<parentFk> && a.<parentFk>.id) {
  data.<parentFk> = { id: a.<parentFk>.id };
}
return data;
```

Symptom of omission: the dialog renders fine, but submit hits `/api/dynamic/<Module>/<Entity>/Crud/Create` and returns **500** because the required parent FK is missing from `_formFields`. **This bug shipped on 16 production forms before being found** — setFieldsValue alone never survives submit.

---

## Create-form layout canon

Per `sectionSeparator` section, top to bottom:

1. A `validationErrors` component at the top of the content container.
2. ALL short fields in **fully-paired two-cell flex rows**: a `container` with `display:"flex"`,
   `flexDirection:"row"`, `gap:"12"`, holding two child `container`s each sized
   `desktop.dimensions.width: "calc(50% - 6px)"`. Dissolve unpaired rows and re-pair
   consecutively; only the FINAL row of a section may be half-filled.
   **This used to say "fully-paired 12/12 `columns` rows".** The `columns` component is banned
   project-wide and `validate-blocks.js` fails any block containing one — but this file was a
   *canon* instructing you to author them, which is how they kept appearing. Flex rows are the
   idiom ([containers.md](containers.md) "page shell" and the flex-split rule).
3. Full-width multi pickers: `autocomplete` with `mode: 'multiple'`, `valueFormat: 'simple'`, `dataSourceType: 'entitiesList'`.
4. `textArea`s at the section BOTTOM. Long-text props (description / requirement / logic / validationRules / …) are `textArea`, NOT `textField`.

Rules:

- `formSettings.labelCol` 8 / `wrapperCol` 16.
- Every input `editMode: 'editable'` — see [edit-mode.md](edit-mode.md).
- Reflist dropdowns: `dataSourceType: 'referenceList'` + `referenceListId: {module, name}` where `name` is the FULL dotted `referenceListName` from entity metadata — the reflist name often ≠ the property name (see [dropdowns.md](dropdowns.md)).
- Owned-M:M picker judgment: include only the pickers the user actually asked for — a 16-picker dialog was rejected as unusable and reverted.
- Transform assertions (the #1 risk is silent field loss): non-final rows have both cells filled; no paired row after a `textArea` within a section; field-set identical before/after.

---

## Add-button wiring

The Add button is a `buttonGroup` item in the subtable toolbar (placement/toolbar layout: [junction-subtables.md](junction-subtables.md)):

- `label: "Add <Singular>"`, `buttonType: "link"`, `icon: "PlusOutlined"`, `buttonAction: "dialogue"` *(runtime-verified; not in the groups index — clean-form-config may flag it; do NOT strip)*
- `actionConfiguration`: `actionName: "Show Dialog"`, `actionOwner: "shesha.common"`
- `actionArguments`: `formId: { name: "<add-form-name>", module: "<module>" }`, `modalWidth: "60%"`, `formMode: "edit"`, `formArguments` (code, see above)
- `onSuccess` → `Refresh table` with **actionOwner = the enclosing `dataContext` component's id** (the table refreshes through its data context, NOT `shesha.common`)

Placeholder buttons ("place the button, don't implement yet"): **never leave `actionName: ""`** — clicking logs **"Action name is mandatory"**. The clean no-op:

```json
"actionConfiguration": {
  "actionName": "Execute Script",
  "actionOwner": "shesha.common",
  "actionArguments": { "expression": "// not yet implemented" }
}
```

Verify the autocomplete `entityType` against live metadata before shipping — entity config names can diverge from FK property names (see [../full-stack-prereqs.md](../full-stack-prereqs.md)). End-to-end checks: [../verification.md](../verification.md).

---

### Worked example (project-specific)

Junction link-add dialog for `ModuleDefinitionUsedModule` — the "Used Modules" tab on `module-definition-details` opens `module-definition-used-module-add`.

- `formSettings.modelType` = `Shesha.RequirementsStudio.Domain.ModuleDefinitionUsedModule` (the JOIN entity).
- Junction accessors: `module` (parent), `usedModule` (target → `ModuleDefinition`).
- Visible field: ONE `autocomplete` bound to `usedModule`, `dataSourceType: 'entitiesList'`, `entityType: "Shesha.RequirementsStudio.Domain.ModuleDefinition"`.
- Read-only `autocomplete` bound to `module` (satisfies hard-rule part (a)).
- Opening Add button (on the Used Modules subtable): Show Dialog with `formArguments` code returning
  `{ module: { id: data.id, _displayName: data.name, _className: 'Shesha.RequirementsStudio.Domain.ModuleDefinition' } }`;
  `onSuccess` → Refresh table, actionOwner = the Used Modules `dataContext` id.
- Metadata caveat from this project: RS `Release` is registered as `ReleaseDefinition` — always resolve `entityType` via `EntityConfig/GetMainDataList`, not the FK property name.

`formSettings.onPrepareSubmitData` (exact, satisfies hard-rule part (b)):

```js
const a = form.formArguments;
if (a && a.module && a.module.id) {
  data.module = { id: a.module.id };
}
return data;
```

Fleet precedent (2026-06-10): the same injection (`data.baseProject = { id: a.baseProject.id }`) was stamped on all 16 `base-project-detail-*-create` forms, fixing the shipped 500s; verified end-to-end — `bpd-api-create` Crud/Create returned 200 with `baseProject` in the payload.
