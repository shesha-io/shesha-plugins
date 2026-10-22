# Canonical seeds — the source of truth

Six seeds. Copy verbatim, swap the entity bits, push. Do not hand-author these structures.

Every seed under `assets/examples/` is stored at the **current Shesha 0.46 component versions** (table below). They started as forms captured from a live, correctly-rendering 0.45 app; the 0.46 component migrators (`hidden` to `visible`, `stylingBox` string to `stylingBoxJson` object, flex/grid props copied into the `desktop` / `tablet` / `mobile` blocks, dropdown `bindingFormat` / `tagVariant`, dateField `selectionType` / `bindingFormat`, refListStatus `itemDisplay`, text `{{data.x}}` mustache ...) were then applied to them, and the result was validated against `validate-form-markup.cjs` (R1-R19), the clean-form-config 0.46 scanner and the component KB. Authoring at the current version means the portal does **not** re-run migrations when it loads the form (a stale version re-applies defaults, e.g. a `datatable` below v31 forces zebra rows and hover highlight). When something in the render doesn't match the seed, it's the build that's wrong, not the seed.

**Version table** (authoritative source: `../shesha-form-edit/assets/components-kb/_index.json`; the validator rule R17 blocks anything lower):

| Component | Seed version | Component | Seed version |
|---|---|---|---|
| `container` | 9 | `datatable` | 31 |
| `dataContext` | 5 | `datatable.quickSearch` | 4 |
| `text` | 7 | `datatable.filter` | 7 |
| `link` | 6 | `datatable.pager` | 5 |
| `button` | 10 | `datalist` | 12 |
| `buttonGroup` | 16 | `card` | 5 |
| `textField` | 8 | `tabs` | 11 |
| `textArea` | 7 | `address` | 6 |
| `numberField` | 7 | `dropdown` | 15 |
| `dateField` | 9 | `radio` | 8 |
| `checkbox` | 7 | `checkboxGroup` | 8 |
| `refListStatus` | 9 | `entityReference` | 13 |
| `validationErrors` | 1 | `htmlRender` | 2 |

Screenshots under `assets/screenshots/` were captured on 0.45 and show the intended look; the 0.46 render is the same layout (antd 6 changes tab/collapse chrome slightly). `formSettings.version` is 10.

Full screenshots of every seed live at [`assets/screenshots/`](../assets/screenshots/). Compare your render to the screenshot before claiming a form is done.

## The six seeds

### `sample-patient-table.json` — table archetype

**Screenshot:** [assets/screenshots/sample-patient-table.png](../assets/screenshots/sample-patient-table.png)

- **`dataContext` at the ROOT of the tree**, wrapping the entire page (page-header + toolbar + table + pager). Not nested inside a container. Not merged with the form loader. Everything else lives INSIDE this dataContext so `entityType`, `sourceType:"Entity"`, `dataFetchingMode:"paging"`, `defaultPageSize:10` flow through.

- **Container-nesting = three-layer visual sandwich.** The seed's `dataContext` has ONE child: a `container(pageShell)` with `background.color: "#fafafa"` (grey) and `stylingBoxJson` padding 20 all sides. Inside `pageShell` are TWO sibling `container`s, each a **white surface with `shadow` `rgba(0,0,0,0.05)` blur 8** — one wraps the page-header row, one wraps the toolbar+datatable+pager. Missing any layer produces the wrong background: no `pageShell` → the header floats bare on the canvas; only-tableSurface → the header has no card.

  ```
  dataContext(root)
  └─ container(pageShell)     bg #fafafa, padding 20              ← outer grey shell
     ├─ container(headerCard) bg #ffffff, subtle shadow, padding 15  ← white card #1
     │  └─ [page-header row: title-block + actions-block]
     └─ container(tableSurface) bg #ffffff, subtle shadow, marginTop 15, paddingBottom 15  ← white card #2
        ├─ container(toolbarRow) transparent, padding 15
        ├─ datatable
        └─ datatable.pager
  ```

- **`formSettings.dataLoaderType: "gql"`** and `dataSubmitterType: "gql"` — uniformly, even on the table.
- **`formSettings.onBeforeDataLoad`** = `"form.setFieldsValue({...form.formArguments});"` — pipes URL-query args into form state; keep it.

- **Toolbar is composed of three primitives** — copy by TYPE, don't invent buttons:
  - `datatable.quickSearch` (v=4) — the search input
  - `datatable.filter` (v=7) — the "Filters" text-link (a dedicated component, NOT a custom button)
  - `buttonGroup` with a single item `Column Selector` — action `Toggle Columns Selector`, `actionOwner: <datatable-component-id>`

- **Page-header actions** = ONE `buttonGroup` (`isInline: true`) with two items:
  - `Export` (default) — action `Export to Excel`, `actionOwner: <datatable-component-id>`
  - `Add <Entity>` (primary) — action `Show Dialog`, `actionOwner: shesha.common`, opens the create seed at `80%` width, on success runs `Refresh table` with `actionOwner: <datatable-component-id>`. Full wiring: [add-dialogs.md](add-dialogs.md).

- **Column shape** — every column carries `itemType:"item"`, `columnType:"data"`, `isVisible:true`, `allowSorting:true`, `minWidth`/`maxWidth`/`width` in px, and the three cell-component slots:
  - `displayComponent`: `{"type":"[default]"}` for plain-text OR a wrapped real component — see [§ settings-wrapper](#the-settings-wrapper-rule-for-custom-display-cells) below.
  - `editComponent`: `{"type":"[not-editable]"}`
  - `createComponent`: `{"type":"[not-editable]"}`

### `sample-patient-create.json` — create archetype

**Screenshot:** [assets/screenshots/sample-patient-create.png](../assets/screenshots/sample-patient-create.png)

- **`formSettings.modelType`** = `{ name, module }` object. `dataLoaderType: "gql"`, `dataSubmitterType: "gql"` — uses the entity's default endpoints; do not wire a custom submitter unless the request specifically demands one.

- **Body starts with a `text` subtitle** and a **`validationErrors` (v=1, no props)** — both above the first card.

- **Sections use the dedicated `card` component (v=5)** with `header` and `content` slots. The `header` slot holds a text explanation (right-aligned in the mockup); the `content` slot holds a **container(v=9, `desktop.display: "grid"`, `gridColumnsCount: 2`,`justifyContent": "normal"`,)** with all fields as direct children — NOT decomposed into multiple horizontal-flex row containers. See [§ Card content grid](#card-content--one-grid-container).

- **Every input `editMode: "editable"`** — `inherited` renders dead labels on a standalone create page. See [binding-rules.md § editMode-by-form-type](binding-rules.md#editmode-by-form-type).

- **Section fields — the right component per data-type:**
  - Composite address → the `address` component (dedicated), NOT a `textField` named `physicalAddress`.
  - Radio-style single choice (preferredLanguage) → `radio` (v=8) `horizontal` + `dataSourceType:"values"` + `items:[{label,value}]`, NOT a `dropdown`. (The 0.45 seed used `checkboxGroup` with `mode:"single"`; 0.46 converts that to `radio` on load, so the seed is stored as `radio`.)
  - Multi-select (chronic conditions, consent) → `checkboxGroup` (v=8, multi).
  - Rich in-form explanation → `htmlRender` (v=2; `sanitize` defaults to true, which is fine for markup output; a `<style>` carrier needs `sanitize: false` and must stay visible).

- **No footer button row inside the form.** The create seed is opened in a modal (`modalWidth:"80%"`, `footerButtons:"default"`); the modal chrome supplies Save/Cancel. Adding an in-form Save row doubles up the buttons.

### `sample-patient-details.json` — details archetype

**Screenshots:** [overview](../assets/screenshots/sample-patient-details-overview.png) · [appointments](../assets/screenshots/sample-patient-details-appointments.png) · [prescriptions](../assets/screenshots/sample-patient-details-prescriptions.png) · [lab-results](../assets/screenshots/sample-patient-details-lab-results.png)

- **`formSettings.modelType`** = `{ name, module }` object. `dataLoaderType: "gql"`. `dataSubmitterType: "gql"`.

- **Root structure:**
  ```
  container(root)
  ├── hero row  (container, horizontal, gap: middle)
  │   ├── avatar + name-block
  │   │   ├── text (INITIALS — code expression, see below)
  │   │   └── column
  │   │       ├── name row (horizontal)
  │   │       │   ├── text "{{data.firstName}} {{data.lastName}}"  ← plain mustache, rooted at data (0.46)
  │   │       │   └── refListStatus(status)                  ← inline pill
  │   │       └── text (meta line — code expression using moment)
  │   └── actions column
  │       └── buttonGroup [Edit / Save / Cancel Edit]        ← lifecycle, all shesha.form
  ├── container (quick-actions bar)
  │   └── buttonGroup [Book Appointment / Prescription / Order lab test]
  └── tabs (v=11) [Overview / <child-1> / <child-2> / …]
      ├── Overview  → N × card (v=5) sections stacked vertically
      └── each child tab → dataContext(childEntity, permanentFilter) → toolbar + datatable + pager
  ```

- **Hero avatar initials — TEXT with a CODE expression** (NOT a plain "•"):
  ```jsonc
  {
    "type": "text", "version": 7,
    "content": {
      "_mode": "code",
      "_code": "const getInitials = (first, last) => ((first || '').trim()[0] || '').toUpperCase() + ((last || '').trim()[0] || '').toUpperCase(); return getInitials(data.firstName, data.lastName)"
    }
  }
  ```

- **Hero name text uses `{{data.firstName}} {{data.lastName}}`** — on 0.46 plain-string mustache resolves against the full context, so the entity is `data`; a bare `{{firstName}}` silently renders empty (0.43/0.45 was the other way round). See [binding-rules.md § mustache](binding-rules.md#mustache-in-plain-string-bindings).

- **Every input `editMode: "inherited"`** — the details form starts in view-mode; the Edit lifecycle button flips it. Do NOT set `editable`.

- **Lifecycle buttons** are ONE `buttonGroup` (`isInline: true`) with THREE items — all `actionOwner: "shesha.form"`:
  - Edit → `actionName: "Start Edit"` (`buttonType: "primary"`)
  - Save → `actionName: "Submit"` (`buttonType: "default"`)
  - Cancel Edit → `actionName: "Cancel Edit"` (`buttonType: "default"`)
  All three are always in the DOM; Shesha handles visibility via the form's editMode.

- **Tabs identity: `tab.key === tab.id`, both unique across the tabs array.** The `tabs` component (v=11) uses `key` to route rendered content. When cloning a tab body, regenerate BOTH `tab.id` AND `tab.key` to the SAME fresh 30-char alphanumeric string per tab. See [§ tab-identity](#tab-identity).

- **Child-tab filtering — `permanentFilter` on the tab's `dataContext`** (not on the datatable). Uses JsonLogic + mustache `evaluate`:
  ```jsonc
  {
    "and": [{
      "==": [
        { "var": "<parentFkProp>" },
        { "evaluate": [{ "expression": "{{data.id}}", "required": true, "type": "mustache" }] }
      ]
    }]
  }
  ```
  **Do NOT use `_mode: "code"` for the filter** — the backend expects the JsonLogic shape; `_mode: "code"` returns a JS-object that hits the Entities/GetAll endpoint with the wrong query and 400s.

- **`componentName` uniqueness in cloned tab bodies.** When you duplicate a tab body (e.g. copy the sample's Appointments-tab subtree to build Prescriptions + Lab Results tabs), rename every `componentName` in the cloned subtree with a per-tab prefix (`personsQuickSearch`, `addressesPager`, etc.). Avoids `uniqueStateId` scope collisions on toolbar Refresh/Export/Column-Selector actions.

### `sample-patient-subform.json` — mini-card archetype

The reusable row-template card: `[avatar-with-initials-text] [name-link | subtitle-text]`. Embed it as the Patient column's row-template in a datatable, or as the details-hero avatar row. The Name link's `href` is a code expression:

```jsonc
{
  "type": "link", "version": 6,
  "href": {
    "_mode": "code",
    "_code": "return `/dynamic/<Module>/<details-form-name>?id=${data.id}`"
  }
}
```

Embed in a table's primary column by setting `datatable.items[<primary col>].displayComponent = { type: "subForm", settings: { formSelectionMode: "name", formName: "sample-patient-subform" (or your equivalent) } }`.

### `sample-appointment-list` (PAIR) — list-of-cards archetype

**Screenshots:** [list host](../assets/screenshots/sample-appointment-list.png) · [row template](../assets/screenshots/sample-appointment-list-subform.png)

Two files, always both. The HOST (`sample-appointment-list.json`) is the page with page-header + toolbar + `datalist`. The ROW TEMPLATE (`sample-appointment-list-subform.json`) is the small standalone form that renders once per row inside the datalist.

- **Page structure IS the 3-layer sandwich from `sample-patient-table`** — `dataContext → pageShell(grey) → headerCard(white/shadow) + tableSurface(white/shadow)`. Same wrapper set, same paddings, same shadow. The only difference is what sits inside `tableSurface`:

  ```
  tableSurface  (white, shadow, marginTop 15, paddingBottom 15)
  ├─ toolbarRow      (transparent, padding 15) — quickSearch + filter + column-selector
  ├─ datalist        (v=12)                   — renders row-template N times
  └─ datalist.pager  (…on the same datalist component)
  ```

- **`datalist` (v=12) is the host component**, NOT `datatable`. Its `items` are NOT columns — a datalist references an external form to use as the row template:

  ```jsonc
  {
    "type": "datalist", "version": 12,
    "componentName": "appointments",
    "propertyName": "appointments",
    "formSelectionMode": "name",                       // REQUIRED — literally "name"
    "formId": { "name": "sample-appointment-list-subform", "module": "Forms.Optimization" },  // OBJECT — both keys required
    "orientation": "vertical",
    "dataFetchingMode": "paging",
    "defaultPageSize": 10,
    "showPagination": true,
    "canAddInline": "no",  "canEditInline": "no",  "canDeleteInline": "no"
  }
  ```
  **The single most common defect on this archetype: forgetting the `formId.module` key** — the row template resolves against the wrong scope and renders blank. Validator `[R12]` blocks this.

- **The row template (`sample-appointment-list-subform.json`) is a full self-contained form** with `modelType`, `dataLoaderType: "gql"`, and its own root container — the `rowCard`. NOT a headless partial; the datalist mounts it as a real Shesha form per row.

- **Row-card outer container = the `rowCard` layout recipe** — `display: "grid"`, `gridColumnsCount: 2`, `justifyContent: "normal"`, `alignItems: "center"`, `stylingBoxJson` padding 15 all sides, `marginBottom: "15"`, `shadow` = the canonical soft shadow, `radius.all: 4`. Full byte-exact block in [§ layout-canon → rowCard](#layout-canon).

  ```
  rowCard (grid, 2 cols, gap 30)
  ├─ LEFT COLUMN — nested grid, 2 cols, gap 30
  │   ├─ avatar   (75×75, radius 50, initials text or image)
  │   └─ name-block (flex column)
  │       ├─ entityReference(patient) → name link, ZERO padding, blue
  │       ├─ refListStatus(appointmentType) — pill, height 24, radius 4
  │       └─ text (reason · location) — subdued
  └─ RIGHT CLUSTER — flex row, justifyContent "right", alignItems center, gap 30
      ├─ date-status column (flex column, alignItems "end")
      │   ├─ text "{{data.startDateTime}}" (date-time — plain mustache rooted at data)
      │   └─ refListStatus(status) — pill
      └─ chevron button — Navigate to details form
  ```

- **NEVER use `justifyContent: "space-between"` on a grid container.** Grids distribute automatically via `gridColumnsCount`. Space-between on a grid produces silent visual gaps. Use `"normal"`. Space-between IS valid on `display: "flex"` — see [§ layout-canon → flex-spaceBetween-row](#layout-canon). Validator `[R13]` blocks the grid variant.

- **The two pills** (appointmentType, status) both use `refListStatus` (v=9) wrapped in the settings-wrapper (see [§ settings-wrapper](#the-settings-wrapper-rule-for-custom-display-cells)) with height 24, radius 4 — same recipe as a status column cell in a datatable.

- **The name link uses `entityReference` (v=13)**, NOT a plain `link` — `entityReference` binds directly to the FK, resolves the display value, and routes to the target details form via `formSelectionMode: "name"` + `formIdentifier: {name, module}`. See `sample-appointment-list-subform.json` for the exact block.

- **`formSettings.dataLoaderType: "gql"` on the row template** — the row template is loaded once per row by the datalist against the entity's GQL endpoint, same as any other form.

---

## The `settings`-wrapper rule for custom display cells

**The highest-frequency crash source.** A datatable column's `displayComponent` / `editComponent` / `createComponent` accepts two shapes only:

1. **Sentinels** — `{ "type": "[default]" }` or `{ "type": "[not-editable]" }`. No wrapper.

2. **Real component** (`refListStatus`, `entityReference`, `dropdown`, etc.) — MUST be wrapped:
   ```jsonc
   {
     "type": "refListStatus",
     "settings": {
       "id": "<uuid>",
       "type": "refListStatus",          // repeat the type inside
       "version": 9,                     // REQUIRED — omitting crashes with 'reading version'; 9 = current refListStatus
       "propertyName": "editor",         // literally "editor"
       "hideLabel": true,
       "visible": true,                  // 0.46: `visible`, not `hidden`
       "isDynamic": false,
       "referenceListId": { "module": "<Module>", "name": "<RefListName>" },
       "itemDisplay": "name",            // 0.46: replaces showReflistName + showIcon ('name' | 'icon' | 'both')
       "solidBackground": true,
       "desktop": { …style block (per-device component), height 24px, radius 4, hairline border… },
       "enableStyleOnReadonly": false
     }
   }
   ```

Flat `{ type: "refListStatus" }` (no settings) crashes on current datatable (v=31) with `Cannot read properties of undefined (reading 'version')`. Same rule for `entityReference`, `dropdown`, `dateField` as a display component. Only `[default]` and `[not-editable]` are settings-free.

## Card content — ONE grid container

Every `card` (v=5) in a details Overview tab or a create form section has this content pattern:

- **Simple case (all fields fit in one grid):** `card.content.components = [ one container(v=9, desktop.display:"grid", gridColumnsCount:2, direction:"vertical", gap:8,"justifyContent": "normal",) with ALL fields as direct children ]`.

- **Mixed case (grid rows + span-full siblings):** `card.content.components = [ container(grid), address-component, container(grid), htmlRender, textArea, … ]`. Each container child that HOLDS fields uses grid; standalone `address` / `htmlRender` / `textField` / `textArea` sit as span-full siblings.

- **`gridColumnsCount` can be 2 OR 3** — sample's Medical card uses 3 for `bloodType / heightCm / weightKg` on one row. Never 1; never 4+.

- **Do NOT decompose into multiple horizontal-flex row containers** (one per pair of fields). That visibly renders 2 columns but loses the seed's field-spacing behaviour.

## Tab identity

For every entry in a `tabs.tabs` array:

- `tab.id` = a fresh 30-char alphanumeric string
- `tab.key` = the SAME string as `tab.id`
- Every `tab.id` in the array is unique

```jsonc
// CORRECT
{ "id": "3Dz3RCIo49ZYnz_ZhCE063DhTG9Ou2", "key": "3Dz3RCIo49ZYnz_ZhCE063DhTG9Ou2", "name": "Tab 1", "title": "Overview", "components": [...] }

// WRONG — duplicate id across tabs → React key collision → BOTH tab bodies render
{ "id": "sNTp5jbm5TCmoVc7pAy_r9kJ5TbBKd", "key": "abc123...", "title": "Persons",   ... }
{ "id": "sNTp5jbm5TCmoVc7pAy_r9kJ5TbBKd", "key": "def456...", "title": "Addresses", ... }

// WRONG — id !== key → tab routing loses the mapping → same double-render behaviour
{ "id": "3Dz3RCIo49ZYnz_ZhCE063DhTG9Ou2", "key": "78TH9hmAO68vwbg7_RFp4JaSXuahTh", ... }
```

## Child-tab filtering — `permanentFilter`

On the child tab's `dataContext` (NOT the datatable). Shape:

```jsonc
"permanentFilter": {
  "and": [{
    "==": [
      { "var": "<parentFkProp>" },
      { "evaluate": [{ "expression": "{{data.id}}", "required": true, "type": "mustache" }] }
    ]
  }]
}
```

Where `<parentFkProp>` is the child entity's FK property that references the parent (e.g. `partOf` on `NotificationMessage`, `patient` on `Appointment`, `organisation` on `OrganisationAddress`). `{{data.id}}` resolves to the open record's id — always double-brace, never single.

**Do NOT use `_mode: "code"` for `permanentFilter`** — it's a documented mistake that produces a 400 on `Entities/GetAll`. The backend expects the JsonLogic shape above; code-mode returns a JS object the query builder can't serialise.

---

## The swap checklist

Every seed you copy from `assets/examples/sample-patient-*` gets this pass, in order. Nothing is optional.

1. **`formSettings.modelType`** → `{ name: "<YourEntity>", module: "<YourModule>" }` (the exact `name` + `module` you resolved from `EntityConfig/GetMainDataList`). Not a string, not a guess.
2. **Every `dataContext.entityType`** → same `{ name, module }` object, one per dataContext (parent for the root; children for tab-scoped filters).
3. **Every field `propertyName` / `componentName` / `name` / `label`** → real camelCase property (path from metadata, lowercased first char) + sentence-case label ("First name", not "First Name" or "FirstName").
4. **Every datatable column** — the `items[]` list → your entity's real columns (matching camelCase). Preserve the wrapped-`settings` shape on any status / entity-reference / date columns.
5. **Every `formId` reference** in action arguments → your family's form names (`sample-patient-create` → `<yourentity>-create`, `sample-patient-details` → `<yourentity>-details`).
6. **Every `actionOwner: "<datatable-id>"`** (or `"<datalist-id>"` for the list-of-cards archetype) — after regenerating IDs, remap so Export/Refresh/Column-Selector actions point at the actual `datatable` / `datalist` component's new `id`.
7. **The child-tab `permanentFilter`s** — `<parentFkProp>` → your child entity's FK property name (e.g. `patient` → `partOf` for NotificationMessage under Notification).
8. **The hero avatar/meta code expressions** — `data.firstName`/`data.lastName`/`data.patientCode`/etc. → your entity's equivalent fields. Keep the `moment().diff` age pattern where applicable.
9. **The subform's `href` code expression** — `sample-patient-details` → your details form name; `Forms.Optimization` → your module (if different).
10. **Re-run `stampTree`** so every `parentId` is fresh and points at the direct parent's `id`. Descend into `components`, `columns[].components`, `tabs[].components`, `content.components`, `header.components`.
11. **All `id`s** → fresh `crypto.randomUUID()`. Short IDs like `pr1`, `btn2` don't work — the renderer ignores non-UUID ids and the form renders blank.
12. **Tab identity**: for every entry in a `tabs.tabs` array, generate ONE fresh 30-char alphanumeric string; assign it to BOTH `tab.id` AND `tab.key`. Never leave the seed's original tab ids in place (they collide) and never set `tab.key` different from `tab.id`.
13. **componentName uniqueness across cloned tab bodies**: when you clone a tab body for multiple child collections, prefix every `componentName` in the cloned subtree with the per-tab short name.
14. **Text mustache (0.46)**: any plain-string `text.content` or `link.href` that binds an entity property is rooted: `{{data.propertyName}}` — a bare `{{propertyName}}` renders empty. `refListStatus.propertyName` is a bare property path with no braces. In code-mode (`_code`) `data` is the scope as before. Validator R2/R11 enforce this.
15. **Card content = grid container(s)**: for every `card` in the details / create form, `card.content.components` contains at least one `container(v=9, desktop.display: "grid", gridColumnsCount: 2 or 3,"justifyContent": "normal",)` holding fields as direct children.
16. **Every `buttonGroup` has `isInline: true`**. Otherwise buttons collapse into a "..." dropdown menu.
17. **Every layout container matches its canonical recipe byte-exact** — pick the role from [§ layout-canon](#layout-canon), paste the block, adjust only `id`, `parentId`, `componentName`. NEVER `justifyContent: "space-between"` on `display: "grid"`. Every white-surface `shadow` is the canonical soft shadow (`offsetY:2, blurRadius:8, spreadRadius:2, color:"rgba(0,0,0,0.05)"`). Every `pageShell` has padding-20 on all four sides.
18. **List-of-cards archetype = TWO forms.** The host uses `datalist` (v=12) with `formSelectionMode: "name"` + `formId: {name, module}` — never inlines the row template. The row template is a full standalone form whose root container is the `rowCard`. Push both; the datalist resolves the template by name at render time.
19. **Every reference-list field** (dropdown / `refListStatus` / radio) → `dataSourceType: "referenceList"` + `referenceListId: { module, name }` copied **verbatim from `Metadata/GetProperties`** (`referenceListModule` / `referenceListName`). **Never call a `ReferenceList/*` endpoint to fetch or verify items, and never loop on one** — the frontend loads them at render. Framework lists keep their seed binding as-is: Gender is `{ "module": "Shesha", "name": "Shesha.Core.Gender" }` (module `Shesha`, dotted name — **not** `{ module: "Shesha.Core", name: "Gender" }`). See [binding-rules.md § Reference-list fields](binding-rules.md#reference-list-fields-bind-from-metadata-never-fetch).
20. **Component versions**: leave every `version` at the value in the seed (the table at the top). If you add a component the seed does not contain, look its `version` up in `../shesha-form-edit/assets/components-kb/_index.json` and author the full current shape from that component's KB entry (`settingsProps.ownProps`) - never an older version, never a remembered shape. Validator R17 blocks lower versions.
21. **Per-device styling (0.46)**: for the 37 `appearanceScope: "per-device"` components, style lives under `desktop` (and optionally `tablet` / `mobile`) and spacing is the OBJECT `desktop.stylingBoxJson` (`{ "_type": "styleBox", "paddingTop": "20", ... }`), not the `stylingBox` string. Never leave spacing only in a `stylingBox` string (check N4 of clean-form-config).
22. **Render-time scripts**: any `{ _mode: "code" }` setting (visibility, style, content, editMode ...) optional-chains every hop after the first (`data.a?.b`, `data.items?.[0]?.name`) - a throwing script is swallowed and a throwing visibility shows the component. `editMode` scripts return `'editable' | 'readOnly' | 'disabled' | 'inherited'`, never a boolean.

Full failure modes per rule → the validator's exit output when it flags them.

---

## Layout canon

Every layout `container` in every seed matches ONE of the recipes below. When authoring a new form, DON'T invent a new container shape — pick the recipe that matches its role and paste the byte-exact block verbatim, then adjust only the `id`, `parentId`, `componentName`, and (where noted) padding.

| Role | Recipe | Where it appears |
|---|---|---|
| `pageShell` | grey outer wrapper, padding 20 all sides | root of every page (`table`, `create`, `details`, `list`) |
| `whiteCard.headerCard` | white, soft shadow, padding 15, radius 4 | wraps the page-header row |
| `whiteCard.tableSurface` | white, soft shadow, padding-bottom 15, marginTop 15 | wraps `toolbar + datatable + pager` (or `toolbar + datalist + pager`) |
| `whiteCard.detailsHero` | white, soft shadow, padding 20, radius 4 | wraps the details hero row |
| `rowCard` | grid-2, soft shadow, padding 15, marginBottom 15 | outer of a datalist row template |
| `cardContentGrid` | grid-2 or grid-3, `justifyContent: "normal"` | inside every card's `content.components` slot, holding fields |
| `flex-spaceBetween-row` | flex row, `justifyContent: "space-between"`, alignItems center | page-header row, toolbar row, hero-actions row |

**Canonical soft shadow** — used byte-exact on every white surface (`whiteCard.*`, `rowCard`). Validator `[R14]` blocks any deviation.

```jsonc
"shadow": { "offsetX": 0, "offsetY": 2, "blurRadius": 8, "spreadRadius": 2, "color": "rgba(0,0,0,0.05)" }
```

If a container's `desktop.background.color === "#ffffff"` and its `blurRadius > 0`, the shadow MUST match this block verbatim. Solid black (`#000000`) or single-channel colors are wrong.

### `pageShell` — grey outer wrapper

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": "<parent-id>",
  "componentName": "pageShell",
  "propertyName": "pageShell",
  "hideLabel": true, "direction": "vertical",
  "desktop": {
    "display": "block",
    "background": { "type": "color", "color": "#fafafa" },
    "stylingBoxJson": { "_type": "styleBox", "paddingLeft": "20", "paddingBottom": "20", "paddingTop": "20", "paddingRight": "20" }
  }
}
```

Every page has exactly ONE `pageShell` as the child of the root `dataContext` (table / list) or the root `container` (create / details). Validator `[R15]` blocks a `#fafafa` container without padding-20 on all four sides.

### `whiteCard.headerCard` — page-header card

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": "<pageShell-id>",
  "componentName": "headerCard",
  "propertyName": "headerCard",
  "hideLabel": true, "direction": "vertical",
  "desktop": {
    "display": "block",
    "background": { "type": "color", "color": "#ffffff" },
    "border": { "radius": { "all": 4 } },
    "shadow": { "offsetX": 0, "offsetY": 2, "blurRadius": 8, "spreadRadius": 2, "color": "rgba(0,0,0,0.05)" },
    "stylingBoxJson": { "_type": "styleBox", "paddingLeft": "15", "paddingBottom": "15", "paddingTop": "15", "paddingRight": "15" }
  }
}
```

Holds ONE `flex-spaceBetween-row` (title-block + actions-block).

### `whiteCard.tableSurface` — datatable/datalist surface

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": "<pageShell-id>",
  "componentName": "tableSurface",
  "propertyName": "tableSurface",
  "hideLabel": true, "direction": "vertical",
  "desktop": {
    "display": "block",
    "background": { "type": "color", "color": "#ffffff" },
    "border": { "radius": { "all": 4 } },
    "shadow": { "offsetX": 0, "offsetY": 2, "blurRadius": 8, "spreadRadius": 2, "color": "rgba(0,0,0,0.05)" },
    "stylingBoxJson": { "_type": "styleBox", "paddingBottom": "15", "marginTop": "15" }
  }
}
```

Contains `toolbarRow` (transparent, padding 15) + the datatable/datalist + the pager.

### `whiteCard.detailsHero` — details hero card

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": "<pageShell-id>",
  "componentName": "detailsHero",
  "propertyName": "detailsHero",
  "hideLabel": true, "direction": "vertical",
  "desktop": {
    "display": "block",
    "background": { "type": "color", "color": "#ffffff" },
    "border": { "radius": { "all": 4 } },
    "shadow": { "offsetX": 0, "offsetY": 2, "blurRadius": 8, "spreadRadius": 2, "color": "rgba(0,0,0,0.05)" },
    "stylingBoxJson": { "_type": "styleBox", "paddingLeft": "20", "paddingBottom": "20", "paddingTop": "20", "paddingRight": "20" }
  }
}
```

### `rowCard` — datalist row template outer

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": null,   // root of the row-template form
  "componentName": "rowCard",
  "propertyName": "rowCard",
  "hideLabel": true, "direction": "vertical",
  "desktop": {
    "display": "grid",
    "gridColumnsCount": 2,
    "justifyContent": "normal",             // NEVER "space-between" on grid — validator R13 blocks
    "alignItems": "center",
    "gap": "30",                            // STRING, not number, when used on grids
    "background": { "type": "color", "color": "#ffffff" },
    "border": { "radius": { "all": 4 } },
    "shadow": { "offsetX": 0, "offsetY": 2, "blurRadius": 8, "spreadRadius": 2, "color": "rgba(0,0,0,0.05)" },
    "stylingBoxJson": { "_type": "styleBox", "paddingLeft": "15", "paddingBottom": "15", "paddingTop": "15", "paddingRight": "15", "marginBottom": "15" }
  }
}
```

The two grid children are the LEFT COLUMN (avatar + name-block, itself a nested grid-2) and the RIGHT CLUSTER (`flex-spaceBetween-row` variant with `justifyContent: "right"`).

### `cardContentGrid` — card content field-holder

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": "<card-content-slot-id>",
  "componentName": "<sectionName>Grid",
  "hideLabel": true, "direction": "vertical",
  "desktop": {
    "display": "grid",
    "gridColumnsCount": 2,                  // 3 for medical rows (bloodType / heightCm / weightKg)
    "justifyContent": "normal",
    "gap": 8                                // NUMBER on cards (contrast with rowCard's string "30")
  }
}
```

Grid layout distributes fields evenly by column count — do NOT decompose into multiple horizontal-flex row containers (each holding one pair of fields). That renders 2 visual columns but loses seed spacing.

### `flex-spaceBetween-row` — page-header / toolbar / hero-actions

```jsonc
{
  "type": "container", "version": 9,
  "id": "<fresh-uuid>", "parentId": "<parent-id>",
  "componentName": "<pageHeader|toolbarRow|heroActionsRow>",
  "hideLabel": true, "direction": "horizontal",
  "desktop": {
    "display": "flex",
    "flexDirection": "row",
    "justifyContent": "space-between",      // OR "right" for the datalist-row right-cluster variant
    "alignItems": "center",
    "flexWrap": "nowrap",
    "stylingBoxJson": { "_type": "styleBox" }   // spacing varies by context — see below
  }
}
```

The three padding contexts:
- **Page-header row (inside `headerCard`)**: `stylingBoxJson: { "_type": "styleBox" }` — inherits card padding.
- **Toolbar row (inside `tableSurface`, above the table)**: `stylingBoxJson: { "_type": "styleBox", "paddingLeft": "15", "paddingBottom": "15", "paddingTop": "15", "paddingRight": "15" }`.
- **Hero-actions row (inside `detailsHero`, right of the avatar block)**: empty `stylingBoxJson` — inherits hero padding.

Two children only: the LEFT block (title-text + subtitle-text stack, or the quick-search + filter cluster) and the RIGHT block (`buttonGroup` with the row's actions).
