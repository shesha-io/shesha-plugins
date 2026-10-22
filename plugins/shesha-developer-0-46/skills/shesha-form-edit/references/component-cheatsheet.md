# Component cheat-sheet - read THIS before opening any seed

A compact `type -> current version -> minimal shape` table so you don't read 4,000-line seeds or
run a dozen probes just to discover a version. **Versions are framework-version-specific** - the
numbers below are for `@shesha-io/reactjs 0.46.x`; if the running app differs, resolve once (see
bottom) and trust that.

> Every component must carry its integer `version` (a versionless component re-runs the whole
> legacy migration chain at render and can throw `e.match` / `reading 'migrator'` / `reading 'version'`).
> `parentId` is mandatory on every node (root-level -> `"root"`). `id` must be unique, opaque and
> stable - mint with `crypto.randomUUID()`; short sequential placeholders (`btn1`) render blank.

## Versions (0.46)

**Mirrored from `assets/components-kb/_index.json`, which is the authority** (extracted from `shesha-reactjs` `release-0.46.0`).
This table is a convenience copy so you do not open a file for one integer; `scripts/check-references.mjs` fails if it drifts.
For anything not listed: `grep -A2 '"<type>"' assets/components-kb/_index.json`.

| type | version | type | version |
|---|---|---|---|
| `container` | 9 | `columns` | 6 |
| `text` | 7 | `textField` | 8 |
| `textArea` | 7 | `numberField` | 7 |
| `dateField` | 9 | `dropdown` | 15 |
| `autocomplete` | 9 | `checkbox` | 7 |
| `checkboxGroup` | 8 | `card` | 5 |
| `sectionSeparator` | 7 | `datatable` | 31 |
| `dataContext` | 5 | `datalist` | 12 |
| `datatable.pager` | 5 | `datatable.quickSearch` | 4 |
| `tableViewSelector` | 7 | `button` | 10 |
| `buttonGroup` | 16 | `alert` | 3 |
| `collapsiblePanel` | 11 | `refListStatus` | 9 |
| `progress` | 3 | `notes` | 6 |
| `tabs` | 11 | `htmlRender` | 2 |
| `subForm` | 5 | `radio` | 8 |
| `entityPicker` | 16 |  |  |

> Seeds under `assets/examples` and `assets/blocks` are stored at their older (0.45) versions. That is valid: every migration step
> above the stored version runs in memory on load, so they render on 0.46 - with the migration-injected defaults described in
> [render-hazards-046.md](render-hazards-046.md) H9/H17. Components you author fresh get the **current** version **and** the
> current shape. A too-low version silently drops the component's `desktop` style block; a too-high one skips migrations a legacy
> shape still needs.
> `dataContext` is v5 in 0.46 (the legacy `datatableContext` converts to it and is stamped 8; both load).

## Minimal shapes (omit styling - the renderer applies defaults)

Every shape is at its **0.46 current version** with the 0.46 setting names. Visibility is `visible` (boolean or code setting),
not `hidden`; per-setting permissions are `visiblePermissions` (Visible) and `editModePermissions` (Interaction Mode); legacy
`permissions` is deprecated. Details: [components/edit-mode.md](components/edit-mode.md).

```jsonc
// input (string). number->numberField(v7), date->dateField(v9); same skeleton.
{ "id": "<uuid>", "type": "textField", "version": 8, "parentId": "<pid>",
  "propertyName": "name", "componentName": "name", "label": "Name", "editMode": "inherited", "textType": "text" }

// reference-list dropdown (0.46: enableMultiSelect + bindingFormat replace mode + valueFormat)
{ "id": "<uuid>", "type": "dropdown", "version": 15, "parentId": "<pid>", "propertyName": "status", "label": "Status",
  "editMode": "inherited", "dataSourceType": "referenceList",
  "referenceListId": { "module": "<mod>", "name": "<ReflistName>" }, "bindingFormat": "itemValue", "enableMultiSelect": false }

// entity FK autocomplete
{ "id": "<uuid>", "type": "autocomplete", "version": 9, "parentId": "<pid>", "propertyName": "assignedTo", "label": "Assigned To",
  "editMode": "inherited", "dataSourceType": "entitiesList", "entityType": { "name": "Person", "module": "Shesha" }, "mode": "single" }

// checkboxGroup (hardcoded) - items, NOT values; each {label,value}. (v6+: legacy single mode becomes a radio)
{ "id": "<uuid>", "type": "checkboxGroup", "version": 8, "parentId": "<pid>", "propertyName": "tags", "label": "Tags",
  "dataSourceType": "values", "mode": "multiple", "referenceListId": null, "container": {}, "validate": {},
  "items": [ { "label": "A", "value": "a" } ] }

// dataContext (wrapper for datatable/datalist - needs explicit entityType + sourceType)
{ "id": "<uuid>", "type": "dataContext", "version": 5, "parentId": "<pid>",
  "entityType": "<exact modelType>", "sourceType": "Entity", "dataFetchingMode": "paging",
  "defaultPageSize": 10, "uniqueStateId": "<name>", "componentName": "<name>", "propertyName": "<name>" }

// text (v7: style lives in desktop.*; the {{data.}} prefix is added by the migration only below v7)
{ "id": "<uuid>", "type": "text", "version": 7, "parentId": "<pid>", "componentName": "title",
  "content": "Customer details", "textType": "span",
  "desktop": { "font": { "size": 16, "weight": "600" }, "stylingBoxJson": { "_type": "styleBox", "marginBottom": "8" } } }

// htmlRender used as a CSS carrier: sanitize false, visible (never hidden), output never empty
{ "id": "<uuid>", "type": "htmlRender", "version": 2, "parentId": "<pid>", "componentName": "cssCarrier",
  "sanitize": false,
  "renderer": "return '<div></div><style>[data-sha-c-name=\"tabs1\"] .ant-tabs-nav{margin:0}</style>';" }
// (renderer is a plain script string, not a code-mode object: htmlRender/interfaces.ts)

// buttonGroup (action buttons NEVER as standalone `button` in a toolbar)
{ "id": "<uuid>", "type": "buttonGroup", "version": 16, "parentId": "<pid>", "isInline": true, "editMode": "editable",
  "items": [ { "id": "<uuid>", "itemType": "item", "itemSubType": "button", "label": "Add", "buttonType": "primary",
    "actionConfiguration": { "_type": "action-config", "actionName": "Show Dialog", "actionOwner": "shesha.common",
      "actionArguments": { "formId": { "name": "<create-form>", "module": "<mod>" }, "modalWidth": "60%" } } } ] }
```

> The shapes are minimums: **`ownProps` in `assets/components-kb/<type>.json` and a live form that already renders on this app
> win** over this sheet. Changed in 0.46 and not shown above: `dateField` v9 (`selectionType`, `bindingFormat`,
> `dateRestriction` replace `picker/showTime/showNow/showToday`); `refListStatus` v9 (`itemDisplay: name|icon|both` replaces
> `showReflistName/showIcon`); `tabs` v11 (per-tab `visible`, `editMode` replaces `selectMode`); `passwordCombo` is deprecated
> (migrates to two `textField`s - password + confirm); key/value variable lists are replaced by the Expression Editor
> ([components/scripts.md](components/scripts.md)).

## Resolve versions for THIS app in ONE probe (if not 0.46.x)

```bash
# every component type -> max version seen in the running backend's forms (GetAll returns markup inline)
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetAll" --data-urlencode MaxResultCount=1000 \
  -H "Authorization: Bearer $ACCESS_TOKEN" | node -e "
const r=JSON.parse(require('fs').readFileSync(0,'utf8')).result.items, v={};
const w=n=>{if(Array.isArray(n))n.forEach(w);else if(n&&typeof n==='object'){if(n.type&&n.id&&Number.isInteger(n.version))v[n.type]=Math.max(v[n.type]??-1,n.version);Object.values(n).forEach(w)}};
for(const f of r){try{w(JSON.parse(f.markup))}catch{}} console.log(v)"
```

Prefer this over reading large seed files. **Do not** read `employee-table.json`, `rs-detail-with-header.json`, or other
multi-thousand-line seeds wholesale - open them only with `Grep`/offset for one specific fragment.
