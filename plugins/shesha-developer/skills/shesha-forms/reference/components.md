# Shesha Form Components — Authoring Reference

Practical patterns for editing form JSON. Read the section that matches the user's request. Pair this with `assets/component-properties.json` for the authoritative valid-keys list per component type.

---

## Datalist / Datatable wrapper rule (read this first too)

**`datatable` and `datalist` MUST be wrapped in a `dataTableContext` (or `dataContext`).** Never put them at root with `entityType` / `sourceType` set on the component itself — that pattern technically renders something in some Shesha versions but is wrong and brittle:

- The data-fetching, paging, sorting, and filtering all live on the **context wrapper**, not the table/list. Putting them on the inner component means they don't get re-evaluated when filters or sort change, and external components (toolbar buttons, refresh actions) can't target them by `actionOwner: "<contextId>"`.
- Built-in actions like `Refresh table`, `Export to Excel`, and quick-search wiring all expect to find a `dataTableContext` ancestor. Without it, they silently no-op.
- Sub-form-renderer datalists (`formSelectionMode: "name"` with a row-template form) inherit the row data from the context's current row. Without the context, the row template gets nothing.

**Canonical entity-bound list:**

```json
{
  "id": "...",
  "type": "dataTableContext",
  "propertyName": "tiersContext",
  "componentName": "tiersContext",
  "sourceType": "Entity",
  "entityType": "PBF.MembershipManagement.Domain.Domain.Tier",
  "defaultPageSize": 25,
  "dataFetchingMode": "paging",
  "sortMode": "standard",
  "strictSortBy": "sortOrder",
  "strictSortOrder": "asc",
  "permanentFilter": { "==": [{"var": "mode"}, {"var": "modeFilter"}] },
  "components": [
    { "id": "...", "type": "datatable.quickSearch" },
    {
      "id": "...",
      "type": "datalist",
      "formSelectionMode": "name",
      "formId": { "module": "PBF.MembershipManagement", "name": "tier-card" },
      "orientation": "wrap",
      "listItemWidth": 0.25
    },
    { "id": "...", "type": "datatable.pager" }
  ]
}
```

The `datalist` here has **no** `entityType`, **no** `sourceType`, **no** `permanentFilter`, **no** `properties` — it inherits them all from the wrapper. Same rule for `datatable`.

**URL-bound list** (custom endpoint instead of entity CRUD):

```json
{
  "type": "dataTableContext",
  "sourceType": "Url",
  "endpoint": "/api/services/app/EntityHistory/GetAuditTrail?entityId={{data.id}}&entityTypeFullName={{data.modelType}}",
  "defaultPageSize": 10,
  "components": [ /* datatable or datalist */ ]
}
```

**The only time you can skip the wrapper** is when the datalist has hardcoded `items` (not entity-bound) — e.g. an inline list of static rows for a help-style display. Even then, prefer the wrapper unless you have a specific reason.

When the user says "the datalist isn't refreshing after I change the filter", "the export button does nothing", or "the row template isn't seeing the row data" — almost always the cause is a missing wrapper. Walk up the parentId chain from the datalist; if there isn't a `dataTableContext` ancestor, that's the bug.

---

## editMode rule (read this first)

**Every interactive component must have `editMode: "editable"`.** That includes `textField`, `textArea`, `numberField`, `dateField`, `dropdown`, `radio`, `checkbox`, `switch`, `button`, `link`, `autocomplete`, `entityPicker`, file uploaders.

If you omit `editMode` (or set it to `"inherited"`) on a form whose effective mode resolves to read-only — which happens for forms with `dataLoaderType: "none"`, public/anonymous pages, or details views — the component renders but won't accept input or clicks. The symptom is "looks fine but the field is greyed out / button does nothing." The fix is always the same: set `editMode: "editable"` explicitly.

Pure visual components — `text`, `image`, `container`, `columns`, `card` — keep `editMode: "inherited"` or omit it. They have no interactive surface, so the form's effective mode doesn't matter.

When validating an edit, walk the tree and assert: every node whose `type` is in the interactive list above has `editMode === "editable"`. Treat a missing or non-editable mode as a bug, not a styling choice.

---

## Layout pattern: container → card → inner container → sections

This is the project's house pattern for full-page forms (auth pages, registration, single-record edit screens). Mirror it whenever you build a new page-style form so the new form looks consistent with what's already there. The reference implementation is `auth-login` in module `PBF.MembershipManagement` — copy its JSON when starting a new page.

```
[root]
└── container "outer"            ← page-level wrapper. centers the card.
    ├── direction: vertical
    ├── display: grid
    ├── justifyContent: center
    ├── alignItems: center
    ├── dimensions.height: 100svh
    └── stylingBox padding: 15px
        │
        └── card                  ← Shesha card component (the white box with shadow)
            ├── header.components: []          ← usually empty
            └── content.components:
                ├── image                       ← logo at top of card
                │   ├── dataSource: "url"
                │   └── url: "/images/pbf-logo.png"
                │
                └── container "innerContent"   ← form content wrapper
                    ├── text "heading"          ← page title
                    ├── text "subtitle"
                    │
                    ├── columns "rowOfFields"   ← side-by-side inputs (firstName + lastName)
                    │   ├── col.components: [textField]
                    │   └── col.components: [textField]
                    │
                    ├── textField "field1"      ← editMode: "editable"
                    ├── textField "field2"      ← editMode: "editable"
                    │
                    ├── container "groupBlock"  ← a semantic div
                    │   ├── checkbox "consent1" ← editable
                    │   └── checkbox "consent2" ← editable
                    │
                    ├── button "submit"         ← editable, primary action
                    │
                    ├── container "footerRow"   ← inline text + link row
                    │   ├── text "Already have an account?"
                    │   └── link "Sign in"      ← editable
                    │
                    └── text "footer"           ← copyright line
```

Key conventions:

1. **`card` is a real component** with `header: { id, components: [] }` and `content: { id, components: [...] }` slots. Children of the card go in `content.components`, **never** directly on the card. The header slot is usually empty for full-page forms; only use it if you need a card title bar.
2. **The inner `container`** inside `content.components` exists so you can scope padding, background, and spacing for the form-content area separately from the card chrome itself. Without it, padding fights with the card's built-in padding.
3. **Sub-containers as semantic divs** — wrap related rows in their own `container` (e.g. consents block, action row, "already have an account?" row). Each sub-container can carry its own `desktop.flexDirection`, `justifyContent`, and `alignItems` to lay its children out horizontally where needed.
4. **`columns`** is for true grid rows (firstName + lastName, two-button rows, label + value). Total `flex` must be 24 across direct columns. For a simple inline text + link row, prefer a sub-`container` with `flexDirection: "row"` and `alignItems: "baseline"` — it wraps cleaner on narrow viewports.
5. **`link` for inline anchors** — for "Sign in" / "Forgot password" / "Create one" links inline with text, use the `link` component (see [§link](#link)), not a button styled as a link. Buttons in a flex row don't align well with surrounding text.
6. **Don't try to recreate page chrome from scratch** — copy `auth-login`'s JSON, deep-copy it, regenerate ids on the cloned subtree (preserving `parentId` references via an id-remap pass), and replace just the inner content. The designer-tweaked styles for the outer container, card, image, and inner container are tedious to author by hand.

When building a new auth-style page (login, OTP, password reset, branded confirmation):

```python
# Pseudo-code for the structural transform
template = json.loads(GET_FORM_MARKUP("auth-login"))
fresh_ids(template)                        # new GUIDs, parentId references coherent
inner = template.components[0]             # outer container
       .components[0]                      # card
       .content.components[1]              # inner container
inner.components = [build_my_fields(parent_id=inner.id)]
PUT(/UpdateMarkup, { id: my_form_id, markup: json.dumps(template), access: 5 })
```

---

## Form JSON shape

Top level (after `JSON.parse(markup)`):

```json
{
  "components": [
    { "id": "...", "type": "...", "propertyName": "...", "...": "..." },
    { "id": "...", "type": "container", "components": [ ... ] }
  ],
  "formSettings": {
    "modelType": "PBF.MembershipManagement.Domain.Domain.Member",
    "layout": "horizontal",
    "labelCol": { "span": 8 },
    "wrapperCol": { "span": 16 },
    "colon": true,
    "size": "middle",
    "...": "..."
  }
}
```

`components` is a **nested tree** — containers, tabs, columns and similar layout components have their own `components: []` array of children. Walk recursively.

---

## Component skeleton

Every component has these structural keys:

```json
{
  "id": "uuid-v4-string",
  "type": "textField",
  "propertyName": "firstName",
  "label": "First Name",
  "parentId": "uuid-of-parent-or-'root'"
}
```

- `id` — unique GUID. Stable; never regenerate on existing components.
- `type` — must match a key in `component-properties.json` (or be a known custom type).
- `propertyName` — for **input** components, the entity property to bind (camelCase). Required for any component that reads/writes form data.
- `parentId` — `'root'` for top-level, otherwise the parent container's `id`.
- `label` — display label. Hidden if `hideLabel: true`.

---

## IPropertySetting wrapper

Many string/number/boolean properties accept either a **plain value** or a **wrapped JS expression**:

```json
"hidden": false                                    // plain
"hidden": { "_mode": "value", "_value": false }    // wrapped, equivalent
"hidden": { "_mode": "code", "_code": "data.accountType !== 'PBF'" }   // runtime JS
```

When `_mode === 'code'`, `_code` is evaluated at runtime against the script context (see below). Use this for dynamic visibility, dynamic enabled, dynamic default values, dynamic labels, etc.

When you write a wrapped value, **always include `_mode`** — bare `{ _value: ... }` won't be recognized.

---

## Script context

Inside any embedded JS string (`onChangeCustom`, `onClickCustom`, `customVisibility`, `customEnabled`, `customSubmit`, `getOptions`, etc.), these globals are available:

| Global | What it is |
|---|---|
| `data` / `formData` | The current form values object (entity instance keyed by `propertyName`) |
| `formMode` | `'designer'` \| `'edit'` \| `'readonly'` |
| `globalState` | App-wide reactive state |
| `setFormData` | `(values, mergeOrReplace) => void` — programmatic form mutation |
| `application` | App context (`{ id, name, ... }`) |
| `http` | Axios-like client. Use `http.get/post/put/delete` |
| `message` | AntD message (e.g. `message.success('Saved')`) |
| `moment` | Moment.js |
| `pageContext` | Current page's data context |
| `selectedRow` | (in datatables) the currently selected row |
| `event` | (event handlers) the underlying DOM/AntD event |
| `value` | (onChange-style handlers) the new value |

**Do not use `console.log`** — `clean-form-config` strips them and the user is on a hardened build.

---

## Async + try/catch (mandatory for API calls)

API calls must be wrapped in try/catch and properly awaited:

```js
// GOOD
try {
  const response = await http.get('/api/services/PBF.MembershipManagement/Member/GetTier', {
    params: { id: data.id }
  });
  setFormData({ values: { tier: response.data.result }, mergeValues: true });
} catch (err) {
  message.error(err?.response?.data?.error?.message ?? 'Failed to load tier');
}
```

The function holding this code must be `async`. If it's an event handler property like `onChangeCustom`, the function is generated for you — you can use `await` directly inside the script body without an explicit `async` keyword (Shesha wraps it).

**Banned patterns:**
- `.then(...).catch(...)` chains — convert to `async`/`await` + `try/catch`.
- Bare `await` outside an async wrapper — Shesha wraps event scripts but not arbitrary helpers; check the property's context.
- Unhandled promise (`http.get(...)` without `await` and without `.catch`).

---

## Common components

### textField

```json
{
  "id": "...",
  "type": "textField",
  "propertyName": "firstName",
  "label": "First Name",
  "validate": { "required": true, "maxLength": 100 },
  "placeholder": "Jane",
  "size": "middle",
  "parentId": "..."
}
```

Variants: `textArea` (multiline), `passwordCombo` (password + confirm).

### numberField

```json
{
  "id": "...",
  "type": "numberField",
  "propertyName": "capacity",
  "label": "Capacity",
  "min": 0,
  "max": 10000,
  "step": 1,
  "precision": 0
}
```

### dateField / timePicker / calendar

```json
{
  "id": "...",
  "type": "dateField",
  "propertyName": "startsAt",
  "label": "Starts At",
  "showTime": true,
  "format": "YYYY-MM-DD HH:mm",
  "validate": { "required": true }
}
```

### checkbox / switch / threeStateSwitch

```json
{ "id": "...", "type": "checkbox", "propertyName": "popiaConsent", "label": "POPIA consent" }
```

`threeStateSwitch` adds an "indeterminate" state — value is `true | false | null`.

### dropdown

Two data sources: `'values'` (hardcoded list) or `'referenceList'` (Shesha reference list).

```json
{
  "id": "...",
  "type": "dropdown",
  "propertyName": "accountType",
  "label": "Account Type",
  "dataSourceType": "referenceList",
  "referenceListId": {
    "module": "PBF.MembershipManagement",
    "name": "AccountType"
  },
  "mode": "single"
}
```

For hardcoded values (every item must have all three keys):

```json
{
  "id": "...",
  "type": "dropdown",
  "propertyName": "preference",
  "dataSourceType": "values",
  "values": [
    { "id": "1", "label": "Email", "value": "email" },
    { "id": "2", "label": "SMS", "value": "sms" }
  ]
}
```

`mode` is `single` | `multiple` | `tags`.

### autocomplete

Async lookup. Bind to entity, set `entityType`, optional `displayPropertyName`:

```json
{
  "id": "...",
  "type": "autocomplete",
  "propertyName": "subscription",
  "label": "Subscription",
  "entityType": "PBF.MembershipManagement.Domain.Domain.Subscription",
  "displayPropertyName": "_displayName",
  "filter": "..."
}
```

For URL-based autocomplete: set `dataSourceType: 'url'` and provide `dataSourceUrl`.

### entityPicker

Modal-based entity picker with full search. Heavier than `autocomplete` but supports filtering by columns:

```json
{
  "id": "...",
  "type": "entityPicker",
  "propertyName": "tier",
  "entityType": "PBF.MembershipManagement.Domain.Domain.Tier",
  "displayEntityKey": "name",
  "modalTitle": "Select Tier",
  "items": [ /* table columns config */ ]
}
```

### radio / checkboxGroup

Same `dataSourceType` rules as `dropdown`.

### refListStatus

Display-only badge for a reference-list-typed property:

```json
{
  "id": "...",
  "type": "refListStatus",
  "propertyName": "status",
  "module": "PBF.MembershipManagement",
  "referenceListName": "ApplicationStatus",
  "showIcon": true
}
```

### container

Layout. Children go in `components` array. Direction defaults to column.

```json
{
  "id": "...",
  "type": "container",
  "label": "Personal Info",
  "direction": "vertical",
  "components": [ /* children */ ],
  "desktop": {
    "dimensions": { "width": "100%" },
    "flexDirection": "column"
  }
}
```

Per-breakpoint settings live under `desktop` / `tablet` / `mobile` keys.

Use containers as semantic divs for grouping. See [§Layout pattern](#layout-pattern-container--card--inner-container--sections) for the full house pattern.

### card

Shesha's card component — a bordered, rounded, optionally-shadowed white box. **Children do NOT go in `components`** — they go in `content.components`. The card has two slots:

```json
{
  "id": "...",
  "type": "card",
  "propertyName": "myCard",
  "componentName": "myCard",
  "parentId": "...",
  "header": {
    "id": "...",
    "components": []          // usually empty for full-page forms
  },
  "content": {
    "id": "...",
    "components": [ /* the actual children */ ]
  }
}
```

When walking the tree, recurse into both `header.components` and `content.components`. When updating ids, both slots' nested `id` keys must be regenerated coherently with their children's `parentId`.

The card's outer width defaults to its parent's width. To constrain it, set `desktop.dimensions.maxWidth` on the card itself, or wrap it in a fixed-max-width inner container.

### link

Inline anchor link — use this for "Sign in", "Forgot password", "Create one" style links inside a text row. **Not** a button styled as link; the visual rendering and the action wiring are different.

```json
{
  "id": "...",
  "type": "link",
  "propertyName": "signInLink",
  "componentName": "signInLink",
  "label": "link1",
  "hideLabel": true,
  "content": "Sign in",
  "target": "_self",
  "editMode": "editable",
  "actionConfiguration": {
    "_type": "action-config",
    "actionName": "Navigate",
    "actionOwner": "shesha.common",
    "handleSuccess": false,
    "handleFail": false,
    "actionArguments": {
      "navigationType": "url",
      "url": "/no-auth/PBF.MembershipManagement/auth-login"
    }
  }
}
```

Notes:
- The visible text comes from `content`, **not** `label`. `label` is the designer-side caption (kept hidden via `hideLabel: true`).
- `target` is `"_self"` (default) or `"_blank"`.
- `editMode: "editable"` is required, otherwise the click is swallowed.
- Compose with a parent sub-`container` (`flexDirection: "row"`, `alignItems: "baseline"`) when placing inline alongside `text` — e.g. "Already have an account? Sign in" reads as `[text "Already have an account?"] [link "Sign in"]` inside a horizontal flex container.

### columns

Two-up / three-up layouts. `columns` array has child slots:

```json
{
  "id": "...",
  "type": "columns",
  "columns": [
    { "id": "...", "flex": 12, "components": [ /* left */ ] },
    { "id": "...", "flex": 12, "components": [ /* right */ ] }
  ],
  "gutterX": 8,
  "gutterY": 8
}
```

Total flex must be 24 across direct columns.

### tabs

```json
{
  "id": "...",
  "type": "tabs",
  "tabs": [
    {
      "id": "...",
      "key": "personal",
      "title": "Personal",
      "components": [ /* tab content */ ]
    },
    {
      "id": "...",
      "key": "business",
      "title": "Business",
      "components": [ /* ... */ ],
      "hidden": { "_mode": "code", "_code": "data.accountType !== 'PBF'" }
    }
  ],
  "defaultActiveKey": "personal"
}
```

Per-tab `hidden` lets you conditionally show tabs.

### button / buttons (toolbar)

Single button:

```json
{
  "id": "...",
  "type": "button",
  "label": "Approve",
  "buttonType": "primary",
  "icon": "CheckOutlined",
  "actionConfiguration": {
    "actionOwner": "Shesha.Common",
    "actionName": "ExecuteScript",
    "actionArguments": {
      "expression": "try { await http.post('/api/services/PBF.MembershipManagement/Application/Approve', { id: data.id }); message.success('Approved'); } catch (err) { message.error(err?.response?.data?.error?.message ?? 'Failed'); }"
    }
  }
}
```

`actionConfiguration` is the standard configurable-action shape. Common `actionName` values:
- `ExecuteScript` — run JS (above example)
- `NavigateAction` / `Navigate` — go to URL
- `ShowDialog` / `ShowModal` — open modal
- `Submit` (in form) — submit the parent form
- `ExecuteEndpoint` — call a configured endpoint with mapped args

The `buttons` (plural) component is a toolbar — `items` array of `{ id, type: 'button' | 'separator' | 'group', ... }`.

### subForm

Embed another form configuration:

```json
{
  "id": "...",
  "type": "subForm",
  "propertyName": "address",
  "formId": { "module": "Shesha", "name": "address-edit" },
  "modelType": "Shesha.Domain.Address",
  "queryParamsExpression": "{ id: data.address?.id }"
}
```

### fileUpload / attachmentsEditor / imagePicker

```json
{
  "id": "...",
  "type": "fileUpload",
  "propertyName": "coverImage",
  "label": "Cover Image",
  "ownerType": "PBF.MembershipManagement.Domain.Domain.Event",
  "ownerName": "CoverImage"
}
```

`ownerType` + `ownerName` link uploads to a `StoredFile` property on the entity (the framework wires the FK).

### datatable / datatableContext / datalist

**Both `datatable` and `datalist` must live inside a `dataTableContext` (or `dataContext`) wrapper.** See [§Datalist / Datatable wrapper rule](#datalist--datatable-wrapper-rule-read-this-first-too) for the full pattern, why it's required, and the entity-vs-URL variants.

Quick reference for the inner components:

- **`datatable`** — column-based grid view. Columns go in `items: []`. Sorting/filter/paging are inherited from the wrapper.
- **`datatable.quickSearch`** — search box that targets the wrapper's data.
- **`datatable.pager`** — pagination controls.
- **`datatable.toolbar`** — toolbar slot (Add / Refresh / Export buttons; their `actionOwner` typically references the wrapper's id).
- **`datalist`** — card / list view. Either `items: []` (inline) or `formSelectionMode: "name"` + `formId: { module, name }` (sub-form row template) for the row layout. Cards lay out via `orientation` (`vertical` / `horizontal` / `wrap`) and `listItemWidth` (fraction of container width).

Skeleton:

```json
{
  "id": "...",
  "type": "dataTableContext",
  "propertyName": "membersContext",
  "componentName": "membersContext",
  "sourceType": "Entity",
  "entityType": "PBF.MembershipManagement.Domain.Domain.Member",
  "components": [
    { "id": "...", "type": "datatable.quickSearch" },
    { "id": "...", "type": "datatable", "items": [ /* column defs */ ] },
    { "id": "...", "type": "datatable.pager" }
  ]
}
```

`entityType` accepts either the dotted full name (`"Shesha.Domain.Person"`) or an object `{ "name": "Person", "module": "Shesha" }`. Both work — the object form is what Shesha emits in newer templates (see `tableViewSelector` below).

### KeyInformationBar

Highlight up to 3 important fields in a horizontal hero strip at the top of a details form. Used to fill the `//*KEYINFOBAR*//` placeholder in `details-view`. Canonical example at [`/examples/key-info-bar.json`](../../../../examples/key-info-bar.json).

Idiom: a single `KeyInformationBar` whose `columns: []` is an array of column configs. Each column has its own `components: []` containing **two siblings**:

1. A `container` (`direction: "vertical"`) holding a single `text` component with `content` = the property's display label.
2. The actual value component (`textField` / `dateField` / `numberField` / `dropdown` / `entityPicker` / etc.) bound to the property, with **`editMode: "readOnly"`** and **`hideLabel: true`** (the form-level label is suppressed since the text above already shows it).

```json
{
  "type": "KeyInformationBar",
  "componentName": "personKeyInfo",
  "columns": [
    {
      "id": "...",
      "width": 200,
      "textAlign": "center",
      "flexDirection": "column",
      "padding": "0px",
      "components": [
        { "id": "...", "type": "container", "direction": "vertical",
          "components": [
            { "id": "...", "type": "text", "content": "Full Name", "level": 1, "textType": "span" }
          ]
        },
        { "id": "...", "type": "textField", "propertyName": "FullName",
          "editMode": "readOnly", "hideLabel": true }
      ]
    }
    /* repeat for column 2 and 3 — max 3 columns */
  ]
}
```

Notes:
- Component type is **`KeyInformationBar`** (PascalCase).
- Each column is **standalone** — the label text and the value component are siblings inside the column's `components[]`, NOT nested inside the label's container.
- Value components are *display-only* — `editMode: "readOnly"` and `hideLabel: true` are non-negotiable for the hero-strip pattern.
- Width is typically 200px per column.
- For reference-list-item properties, use a `dropdown` with `dataSourceType: "referenceList"` (still `editMode: "readOnly"` + `hideLabel: true`). The dropdown will render the resolved label, not the raw enum value.

### tableViewSelector

Quick-filter dropdown sitting above a `datatable`. Used to fill the `//*TABLEFILTER*//` placeholder in `table-view`. Canonical example at [`/examples/table-view-selector.json`](../../../../examples/table-view-selector.json).

Lives inside a `dataContext` (or `dataTableContext`) that's bound to the table's entity:

```json
{
  "type": "tableViewSelector",
  "componentName": "personViewSelector",
  "title": "View",
  "persistSelectedFilters": true,
  "filters": [
    {
      "id": "default-all-records",
      "name": "Default",
      "tooltip": "Shows all records without any filtering",
      "sortOrder": 0
    },
    {
      "id": "<random-id>",
      "name": "Females Only",
      "sortOrder": 1,
      "expression": {
        "and": [
          { "==": [ { "var": "gender" }, 2 ] }
        ]
      }
    },
    {
      "id": "<random-id>",
      "name": "Same Address",
      "sortOrder": 2,
      "expression": {
        "and": [
          { "==": [
            { "var": "address" },
            { "evaluate": [ { "expression": "{{data.address}}", "required": true, "type": "mustache" } ] }
          ] }
        ]
      }
    }
  ]
}
```

`filters[]` shape:
- `id` — opaque, random-looking string. Each filter needs its own.
- `name` — the user-visible filter label.
- `tooltip` — optional hover text.
- `sortOrder` — integer, controls dropdown order.
- `expression` — JsonLogic expression. **Omit on the "Default" / show-all entry** (sortOrder 0) — the absence of `expression` is what makes it the no-op filter.

Inside `expression`:
- `{"var": "<propertyName>"}` references a property of the entity row.
- `{"evaluate": [{"expression": "{{data.X}}", "type": "mustache"}]}` resolves to a value from the surrounding form's `data` at runtime (useful for "same as the current record's address" filters).
- Reference-list-item comparisons use the integer value (e.g. `{"==": [{"var": "gender"}, 2]}` matches the `2` member of the Gender ref list).

---

## Validation patterns

`validate` is a sub-object on input components:

```json
"validate": {
  "required": true,
  "minLength": 3,
  "maxLength": 100,
  "min": 0,
  "max": 1000,
  "regExp": "^[A-Z]{2}\\d{4}$",
  "validator": "value && value.startsWith('PBF')"
}
```

`validator` is a JS expression — same script context, must return truthy for valid. Invalid → AntD shows the message in `validate.message`.

For complex business rules across fields, use **FluentValidation** on the .NET side (see the `shesha-fluent-validators` skill) rather than per-component validators. UI validators can't enforce server-side invariants reliably.

---

## Visibility / enabled

Four properties control whether a component renders, accepts input, and is enabled:

| Property | Meaning |
|---|---|
| `hidden` | Boolean OR `IPropertySetting` with `_mode: 'code'` returning bool. When true, the component is removed from the DOM. |
| `customVisibility` | Pure JS expression returning bool (legacy form of `hidden`). Prefer `hidden` with the code-mode wrapper for new code. |
| `editMode` | `'editable'` \| `'readOnly'` \| `'inherited'`. **For interactive components, must be `'editable'`** — see [§editMode rule](#editmode-rule-read-this-first). |
| `customEnabled` | JS expression returning bool. When false, the component renders but is disabled (greyed out, doesn't accept input). |

Use `hidden` (with code-mode wrapper) over `customVisibility` for new code — same effect, better DX.

```json
"hidden": {
  "_mode": "code",
  "_code": "formMode === 'create' && !data.parent"
}
```

`editMode` and `customEnabled` interact: `editMode === 'readOnly'` always wins; `editMode === 'editable'` lets `customEnabled` decide; `editMode === 'inherited'` resolves against the form's effective mode and is risky on forms with no data loader (see the editMode rule above).

---

## Permissions

```json
"permissions": ["app:Members.View", "app:Members.Edit"]
```

The component is hidden if the user lacks **all** listed permissions. To require ALL, list them; to require ANY, use a single hook permission and group via roles.

Form-level permissions live on the FormConfiguration record itself (set via the designer or the API), not in markup.

---

## Common gotchas

1. **`propertyName` is camelCase**, but the underlying entity property is PascalCase (`firstName` ↔ `FirstName`). The framework maps automatically; don't double-case.
2. **`modelType` mismatch**: if the form points at the wrong entity, reference-list dropdowns and entity pickers silently fail to bind. Match `formSettings.modelType` to the actual entity.
3. **Children of unknown parent**: every child's `parentId` must reference a `id` that exists in the tree. After moving components, sweep the tree to verify.
4. **Stale `id` references in scripts**: scripts that reference component ids (rare but possible — usually only for `useFormItem`-style lookups) break when ids are regenerated. Prefer `data.<propertyName>` access.
5. **Reference list dropdowns**: `referenceListId` is **not** a Guid — it's `{ module, name }`. The framework resolves at runtime.
6. **Empty markup**: an empty form is `{ "components": [], "formSettings": { "modelType": "..." } }`. Don't push `null` or `""`.
7. **Multiline JS in JSON**: escape newlines as `\n`. Prefer building the tree in Node and `JSON.stringify`-ing — never hand-edit deeply nested escaped strings.
8. **Conditional containers**: a `hidden` container hides itself AND its children. Don't combine with per-child `hidden` unless deliberately layered.
9. **`formSettings.layout`**: `"horizontal"` is the default; `"vertical"` puts labels above inputs. Setting `layout: "inline"` on a form-wide setting rarely produces what users expect — use a `container` with horizontal direction instead.
10. **Save behavior**: most member/details forms have an implicit submit button via `formSettings.onSubmit` — explicit `button` with `actionName: "Submit"` is for custom toolbars.
11. **Anonymous-access forms (`access: 5`)**: the `Create` endpoint may not honour `access` on the initial POST. Push a baseline form, then immediately call `UpdateMarkup` with `access: 5, permissions: []` to lock it in. Verify by re-fetching with `GetByName` and checking `result.access === 5`. Anonymous forms are served at `/no-auth/<module>/<form>` (vs `/dynamic/<module>/<form>` for authenticated).
12. **PowerShell `Invoke-RestMethod` + non-ASCII body**: the cmdlet encodes `-Body $jsonString` as Windows-1252 by default. Em dashes (`—`), curly quotes, and other non-ASCII chars trigger a server 500 with `Unable to translate bytes [E2] at index N from specified code page to Unicode`. Always pass the body as UTF-8 bytes:
    ```powershell
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)
    Invoke-RestMethod -Uri $url -Method Put -Headers $h -Body $bytes -TimeoutSec 60
    ```
    Or use `curl --data-binary @file` from Bash.
13. **Card children**: a `card` component holds children in `content.components`, NOT `components`. A common bug is to push children directly onto `card.components` and watch them silently disappear from the rendered output. Walk + push always go through `card.content.components`.
14. **Tree id-remap when cloning forms**: when copying a form's JSON as a starting point for a new form, regenerating ids requires two passes — first pass: assign new ids and build an old→new map; second pass: rewrite every `parentId`, every `containerId`, and any other id references using the map. A single-pass approach drops parent-child relationships. See the structural-transform pseudo-code in [§Layout pattern](#layout-pattern-container--card--inner-container--sections).
15. **Datalist / datatable without a wrapper**: putting `entityType` / `sourceType` / `permanentFilter` directly on a `datalist` or `datatable` instead of on a parent `dataTableContext` will sometimes render data but breaks refresh, quick-search wiring, toolbar actions, and row-template data binding. Always wrap. See [§Datalist / Datatable wrapper rule](#datalist--datatable-wrapper-rule-read-this-first-too).

---

## When in doubt

- The authoritative valid-keys-per-type list is `assets/component-properties.json`. If you're about to write a key that isn't there, you're probably wrong.
- The `clean-form-config` skill (in the shesha-developer plugin) catches dead props, type mismatches, layout overflows, broken scripts, missing try/catch, and missing async — invoke it after edits as a safety net.
- For component types not covered here (kanban, charts, queryBuilder, themeEditor, mainMenuEditor, processMonitor, kpi-style cards), inspect an existing form that uses them — the designer's output is canonical.
