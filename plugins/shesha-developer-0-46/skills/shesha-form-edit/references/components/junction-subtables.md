# Junction (M:M) subtables: structure, columns, drill-down, delete/unlink

**Scope:** this EXTENDS [child-tables.md](child-tables.md). That file covers the simple FK-child pattern (`sourceType: "Entity"` + `permanentFilter` on the child's FK). This file covers tabs bound to an M:M **junction entity** via a Url-sourced `dataContext` — link/unlink rows, dot-notation columns, drill-down through the junction to the far entity. Wrapper rules and inner components: [data-tables.md](data-tables.md). Add/link dialogs: [add-dialogs.md](add-dialogs.md).

---

## When this applies

An entity property is an M:M collection when its metadata shows:

- `dataType: "array"` + `listConfiguration.mappingType: "many-to-many"`.
- The junction is **uniquely identified by `listConfiguration.dbMapping.manyToManyTableName`** — bidirectional: both sides of the relationship report the **same table**.
- Resolve table → junction-entity `className` via `GET /api/services/app/EntityConfig/GetMainDataList` (returns `className` ↔ `tableName` pairs).

Junction-row model: **link = create a junction row, remove = delete the junction row, navigate = open `selectedRow.<accessor>.id`'s detail form.** The subtable binds to the *junction* entity, never to the far entity directly.

---

## Relationship-treatment decision table

| Relationship | Treatment |
|---|---|
| Owned / forward M:M | Add/link subtable — Add button opens a link-existing dialog ([add-dialogs.md](add-dialogs.md)) + delete/unlink column |
| Reverse usage (tab titles like "Used By…") | View-only subtable + drill-down. **NO Add button, no delete** |
| Owned 1:M child (child holds the FK; parent is definitional) | Subtable with an internal **Create** dialog (new child, FK preset) — see [child-tables.md](child-tables.md) for the binding |
| Single owning FK | A field on the Details tab (autocomplete), **not** a subtable |

Editable-vs-view-only signal on an existing form: a subtable is editable ⟺ its tab contains an Add button (`actionConfiguration.actionName === "Show Dialog"`). View-only tabs get neither Add nor delete.

---

## Canonical structure

The tab's **ONLY direct child is the `dataContext`**; toolbar / add-button wrapper / datatable are three siblings INSIDE it:

```
tab
└─ dataContext            sourceType:"Url", entityType:{name:"<Junction>", module:"<module>"},
   │                      endpoint = CODE OBJECT returning a Crud/GetAll?filter= URL
   ├─ container           toolbar (horizontal space-between row — see next section)
   │  ├─ container        quickSearch + pager (left)
   │  └─ container        add-button wrapper holding a buttonGroup (right)
   └─ datatable           columns under items[], NOT "columns"
```

```json
{
  "type": "dataContext",
  "componentName": "<junction>Context",
  "sourceType": "Url",
  "entityType": { "name": "<Junction>", "module": "<module>" },
  "endpoint": {
    "_mode": "code",
    "_code": "return '/api/dynamic/<module>/<Junction>/Crud/GetAll?filter=' + encodeURIComponent(JSON.stringify({ and: [{ '==': [{ var: '<parentFk>.id' }, data.id] }] }));"
  },
  "components": [ /* toolbar container, then datatable */ ]
}
```

- The endpoint **must be a code object** (`{_mode:"code", _code:"return ..."}`). A plain-string JS endpoint is STRIPPED on form save and silently disappears. Related trap: `permanentFilter` with `_mode:"code"` at the filter ROOT is invalid and ignored — dynamic filters must be a proper IPropertySetting wrapper on the prop, or valid JsonLogic with `evaluate` nodes ([form-shape.md](form-shape.md)).
- `<parentFk>` is the junction's FK property pointing at the entity *whose detail form this is*; the filter is `<parentFk>.id == data.id`.
- `entityType` on subtables is the object `{name, module}`; on standalone table pages it's the full class string.
- Add button = buttonGroup item: `label: "Add <Singular>"`, `buttonType: "link"`, `icon: "PlusOutlined"`, wired to `Show Dialog` ([add-dialogs.md](add-dialogs.md)). Unwired placeholder: `actionName: "Execute Script"`, owner `shesha.common`, expression `"// not yet implemented"` — never an empty `actionName: ""` (clicking logs "Action name is mandatory").

---

## Toolbar layout + framework classes

Single **horizontal `justifyContent: "space-between"`** row (`alignItems: "center"`, `flexWrap: "nowrap"`, width 100%) with exactly two children:

1. Inner container with `datatable.quickSearch` + `datatable.pager` at `flex-start` (left).
2. Add-button wrapper at `flex-end` (right, `parentId` = the toolbar container's id).

**Framework classNames are mandatory** — on `desktop` + `tablet` + `mobile` `className`:

- Toolbar container: `sha-index-table-control`
- Inner qs/pager container: `index-table-controls-right`

The CSS `.sha-components-container.sha-index-table-control` applies `padding: <Gd> 12px !important` (+ white bg, bottom border, min-height, justify-content:space-between). Without the classes the quick-search box overhangs the datatable's left edge by ~8px — the 12px side padding is what seats it just inside the table line.

When restructuring an existing form: locate the toolbar/add-wrapper **by subtree content** (which child container holds quickSearch/pager vs the buttonGroup), not by `componentName` — names vary wildly between forms.

---

## Columns

Columns live in the datatable's `items: []` array (runtime-verified; `datatable` has no props entry in the groups index — clean-form-config may flag column item keys; do NOT strip).

- **Junction-bound columns use FK dot-notation `propertyName`s**: `<fkProp>.<targetProp>` — first segment the junction's FK property, second the target entity's property.
- `anchored: "left"` pins columns on horizontal scroll — conventionally the action column(s) and the name column.
- **Reflist badge column** — a plain data column shows the raw NUMBER. Use:

```json
{
  "columnType": "data",
  "propertyName": "<fkProp>.<reflistProp>",
  "displayComponent": { "type": "refListStatus", "settings": { "referenceListId": { "module": "<module>", "name": "<RefListName>" } } }
}
```

  Resolve the reflist from the bound entity's metadata `referenceListName` (direct, non-dotted columns only on main-entity-bound tables) — never guess from the property name; names diverge. `refListStatus`/`refListDropDown` cells require the `displayComponent` configured per the working pattern or the form crashes.

**Column KILL-SWITCHES** (each silently blocks the ENTIRE fetch — table chrome renders, zero rows, no error):

1. An `items` entry with an **empty/missing `propertyName`** — `prepareColumns()` returns `[]` immediately, columns never register, fetch is permanently blocked.
2. A **nested path not registered in entity metadata** (e.g. `<fkProp>.name` when the FK property isn't in metadata) — qualifying columns = `[]` → columns never register → fetch blocked. Verify every (nested) path exists in metadata before referencing it.

---

## Row drill-down action column

The leftmost item: `columnType: "action"`, `icon: "EyeOutlined"`, `minWidth`/`maxWidth` 35, `anchored: "left"`.

```json
"actionConfiguration": {
  "actionName": "Navigate",
  "actionOwner": "shesha.common",
  "actionArguments": {
    "navigationType": "form",
    "formId": { "name": "<child-detail-form>", "module": "<module>" },
    "queryParameters": [{ "key": "id", "value": "{{selectedRow.<X>.id}}" }]
  },
  "onSuccess": { "actionName": "Refresh", "actionOwner": "shesha.form" }
}
```

**Targeting rule** — the target is the *displayed* child:

| Table binding | formId | queryParameters value |
|---|---|---|
| Junction-bound tab | detail form of the **COLUMN accessor**'s entity | `{{selectedRow.<columnAccessor>.id}}` |
| Main-entity-bound tab | that entity's detail form | `{{selectedRow.id}}` |

---

## Clone-and-swap (mirroring a tab to the junction's other side)

To add the missing M:M tab on the other entity: clone any existing tab using the **same junction** and swap the two accessors. The accessor lives in **THREE places**:

1. the `dataContext.endpoint` filter (`<parentFk>.id == data.id`),
2. the datatable column `propertyName`s,
3. the action column's `formId` + `queryParameters`.

Swap **ALL THREE** or drill-down silently navigates to the WRONG entity (a real audit found 10 tabs with exactly this bug). Then:

- Reset column `caption`s per property (captions don't swap with propertyNames).
- Skip accessors that don't resolve 1:1 to an entity name (self-referential/aliased FKs — verify the FK's target entity, don't capitalize blindly).
- Verify the new `Crud/GetAll` returns 200 with the correct `filter` + `properties` ([verification.md](../verification.md)).

---

## Delete / unlink

On junction rows delete = **unlink**; on owned children delete = destroys the entity. Same recipe both ways. Insert the column right after the Eye/view action column, before the first data column:

```json
{
  "columnType": "action",
  "icon": "DeleteOutlined",
  "minWidth": 35, "maxWidth": 35, "anchored": "left",
  "actionConfiguration": {
    "actionName": "Execute Script",
    "actionOwner": "shesha.common",
    "actionArguments": { "expression": "try { await actions.callApi.delete('/api/dynamic/<module>/<Entity>/Crud/Delete?id=' + selectedRow.id); actions.showMessage.success('Removed'); } catch (e) { actions.showMessage.error('Remove failed'); }" },
    "onSuccess": { "actionName": "Refresh table", "actionOwner": "<enclosing dataContext id>" }
  }
}
```

- `<Entity>` = the enclosing `dataContext.entityType` (the junction on M:M tabs).
- Resolve the Refresh owner by **walking the datatable's parent chain to the first `dataContext`/`dataContext`** — NOT `datatable.parentId`, which is a container on table pages.
- **NEVER** `actionName: "Delete row"` with `actionOwner: "table"` — throws *"Action 'Delete row' in the owner 'table' not found"*.
- `canDeleteInline: "yes"` alone shows **nothing** on a read-only display table.
- **Verify soft-deletes via `Crud/GetAll` `totalCount === 0`** filtered on the row id — never via `Crud/Get?id=` (Get skips the soft-delete filter and happily returns deleted rows).
- **Frontend block-delete guards** (count children → `actions.showMessage.error('Cannot delete…')` → skip the delete call) belong **in the button script**: dynamic CRUD lands on `/api/dynamic/...` which custom app services cannot intercept per-entity server-side ([full-stack-prereqs.md](../full-stack-prereqs.md)). Backend cascade cleanup, if any, runs in `*ed` event handlers — never `*ing`.

---

### Worked example (project-specific)

The self-referential `ModuleDefinitionUsedModule` junction (module `Shesha.RequirementsStudio`, accessors `moduleDefinition` / `usedModule`):

- **"Used Modules" tab on `module-definition-details`** (forward/owned side): `dataContext` `entityType: {name: "ModuleDefinitionUsedModule", module: "Shesha.RequirementsStudio"}`, endpoint `_code` returns `'/api/dynamic/Shesha.RequirementsStudio/ModuleDefinitionUsedModule/Crud/GetAll?filter=' + ...` filtering `moduleDefinition.id == data.id`. Columns: `usedModule.name`, `usedModule.status` (badge via `RsStatus` — the RS `status` reflist is always `RsStatus`). Eye column → `formId: {name: "module-definition-details", module: "Shesha.RequirementsStudio"}` + `{{selectedRow.usedModule.id}}` (`usedModule` resolves to ModuleDefinition — a known accessor≠entity exception). Add button → `Show Dialog` on `module-definition-used-module-add`, which needs the gotcha-#7 `onPrepareSubmitData` parent-FK injection ([add-dialogs.md](add-dialogs.md)). Delete column unlinks via `http.delete('/api/dynamic/Shesha.RequirementsStudio/ModuleDefinitionUsedModule/Crud/Delete?id=' + selectedRow.id)`.
- **Mirrored "Used By Modules" tab** (reverse side, clone-and-swap): endpoint filters `usedModule.id == data.id`, columns `moduleDefinition.name`/`moduleDefinition.status`, eye → `{{selectedRow.moduleDefinition.id}}` (same detail form — self-referential). Title starts with "Used By" → view-only: **no Add, no delete**.
