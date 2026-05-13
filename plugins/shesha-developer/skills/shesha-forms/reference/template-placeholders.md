# Template Placeholders — `//*NAME*//` substitution

When a form is created with the **template seed strategy** (Step 3b.3, `templateId` on `Create`), Shesha copies the template form's markup verbatim. The Shesha stock template forms (`details-view`, `table-view`, and variants) contain **placeholder slots** marked with strings of the form `//*NAME*//` in component `propertyName` and `componentName` fields. They are sentinels — the form **is not functional** until they're replaced with concrete content.

Substitution happens in **Step 6, before** any other customization. After Step 4 fetches the copied markup, walk the tree, find every placeholder, and replace it per the catalog below — drawing content from the entity property list captured in Step 3b.2.

**The catalog is closed.** Six placeholders exist and only six. If you encounter any other `//*` marker in the wild, treat it as corruption — surface to the user and stop.

---

## Detecting placeholders

A placeholder is any string matching the regex `/^\/\/\*[A-Z]+\*\/\/$/`. They appear in two fields:

- `propertyName` — on **container** components (the slot's layout frame).
- `propertyName` and `componentName` — on **text** components (the slot is the component itself).

Walk the markup recursively, descending through every `components[]` array, card `header.components` / `content.components`, columns, and tabs.

```js
function findPlaceholders(node, results = []) {
  if (Array.isArray(node)) { node.forEach(n => findPlaceholders(n, results)); return results; }
  if (node && typeof node === 'object') {
    for (const field of ['propertyName', 'componentName']) {
      if (typeof node[field] === 'string' && /^\/\/\*[A-Z]+\*\/\/$/.test(node[field])) {
        results.push({ component: node, field, name: node[field] });
        break;
      }
    }
    for (const v of Object.values(node)) findPlaceholders(v, results);
  }
  return results;
}
```

---

## Catalog — the closed set

### `details-view` template (4 unique, 5 occurrences)

| Placeholder | Where | Replacement |
|---|---|---|
| `//*TITLE*//` | `text` component (`level: 1`, `fontSize: "text-xl"`), in both `componentName` and `propertyName`, with `content: ""` | Set `content` to a real title (e.g. `"Person Details"`). Clear `componentName` and `propertyName` (set to `""` or to a sensible slug). |
| `//*KEYINFOBAR*//` | `container` (vertical, empty `components: []`) | Replace `components[]` with a **single** `KeyInformationBar` component configured with **up to 3 columns** — pick the 3 most identifying / most user-facing properties (judgment call; for Person typically `FullName`, `EmailAddress1`, `Type`). Each column entry follows the idiom in [components.md §KeyInformationBar](components.md#keyinformationbar). Clear `propertyName`. |
| `//*DETAILSPANEL*//` | `container` (vertical, empty) | Populate `components[]` with one input per filtered entity property (Step 3b.2 — `isFrameworkRelated: false` AND `suppress: false`). Pick layout by judgment — small property counts → vertical stack; larger → wrap in a `columns` component. Use the `dataType → component` mapping in [model-configurations.md](model-configurations.md). **Set `editMode: "editable"` on every input.** Clear `propertyName`. |
| `//*CHILDTABLES*//` | `container` (vertical, empty) | For each entity property where `dataType === "array"` AND `dataFormat === "entity"`: build a `dataTableContext` bound to the property's `entityType` (flat shape — see "entityType shape" below) containing the standard `datatable.quickSearch` + `datatable` + `datatable.pager` siblings (NOT a `childTable` component — that doesn't exist). Layout: **0** matches → drop the `//*CHILDTABLES*//` container entirely; **1** match → place the `dataTableContext` directly inside; **2+** matches → wrap them in a `tabs` component, one tab per child entity, **tab label = property's `label`**. Clear `propertyName`. |

### `table-view` template (2 occurrences)

| Placeholder | Where | Replacement |
|---|---|---|
| `//*TABLEFILTER*//` | `container` (vertical, empty) | Replace `components[]` with a single `tableViewSelector` component. The first `filters[]` entry is always the "Default — show all" with no `expression`; subsequent entries are entity-appropriate quick-filters with JsonLogic `expression`s. See [components.md §tableViewSelector](components.md#tableviewselector). Clear `propertyName`. |
| `//*TABLECOLUMNS*//` | `container` (vertical, empty), nested inside the template's existing `dataTableContext` | The supporting components (`datatable.quickSearch`, `datatable.filter`, `datatable.pager`) are **already in place** as siblings — you only need to drop a single `datatable` into `components[]` with the entity's columns configured. Clear `propertyName`. |

---

## `entityType` shape — important

`entityType` appears in two different shapes in Shesha JSON, and they're not interchangeable:

| Where | Shape |
|---|---|
| FK property metadata from `ModelConfigurations/{id}` (for `dataType: "entity"` properties) | `{ id, _displayName, _className }` — read `_displayName` |
| Child-collection property metadata (for `dataType: "array"` + `dataFormat: "entity"`) AND the `entityType` field on a `dataTableContext` / `dataContext` component | `{ fullClassName, name, module }` — pass as-is |

When building a child-table for a property like `OrganisationPerson` from the parent entity's properties, the property's `entityType` field is **already** in the second shape — copy it onto the `dataTableContext` without transformation.

---

## Substitution algorithm

```
After Step 4 fetches the markup, before any other Step 6 work:

1. Walk the markup, collect all components carrying a //*NAME*// placeholder.
2. For each placeholder:
   a. Look up NAME in the catalog above (it WILL be one of the six).
   b. Apply the documented replacement:
      - text component (//*TITLE*//)            → set `content` to real value, clear componentName + propertyName.
      - container components (the other five)  → populate `components[]` with real content, clear propertyName.
   c. For //*CHILDTABLES*// with 0 matching properties, remove the container entirely.
3. Scan the markup again for any remaining "//*" strings — none should remain. If any do, it's corruption — surface to the user and stop.
4. Continue with Step 6: user-requested customization + the Mandatory Entity Binding rule (which now finds real propertyNames where placeholders used to be).
```

---

## Worked example — `details-view` cloned for Person

Pre-substitution (just after Step 4):

```jsonc
// inside the top card
{ type: "text",      componentName: "//*TITLE*//",       propertyName: "//*TITLE*//",       content: "" },
{ type: "container", propertyName: "//*KEYINFOBAR*//",   components: [] },
{ type: "container", propertyName: "//*DETAILSPANEL*//", components: [] },
{ type: "container", propertyName: "//*CHILDTABLES*//",  components: [] }
```

Post-substitution (judgment-driven, drawing from Person's filtered property list):

```jsonc
// TITLE — set content
{ type: "text", componentName: "personDetailsTitle", propertyName: "", content: "Person Details", /* preserve all other props */ }

// KEYINFOBAR — single KeyInformationBar, 3 columns; structure per components.md §KeyInformationBar
{ type: "container", propertyName: "", components: [
  { type: "KeyInformationBar", columns: [
      /* col 1: FullName        — container[text("Full Name")] + textField (editMode: readOnly, hideLabel: true, propertyName: "FullName") */,
      /* col 2: EmailAddress1   — container[text("Email")] + textField (editMode: readOnly, hideLabel: true, propertyName: "EmailAddress1") */,
      /* col 3: Type            — container[text("Type")] + dropdown (referenceList, editMode: readOnly, hideLabel: true, propertyName: "Type") */
  ] }
] }

// DETAILSPANEL — populated with editable inputs; vibe-check whether to wrap in `columns`
{ type: "container", propertyName: "", components: [
  /* if "few" props: linear vertical stack of textField/dateField/dropdown/entityPicker, one per property */
  /* if "many" props: a `columns` component with 2-3 columns, properties distributed by category */
] }

// CHILDTABLES — Person has `PreferredLanguages` (array/many-entity) but that's not "entity"; check the property list.
// If Person has 0 matching properties → REMOVE this container entirely.
// If 1 → drop a `dataTableContext` directly inside, with the standard quickSearch/datatable/pager siblings.
// If 2+ → wrap dataTableContexts in a `tabs` component, one tab per child entity, tab label = property.label.
```

---

## Gotchas

1. **Don't regenerate the container's `id` or `parentId`** when substituting. The container is *kept*; only its `components[]` is filled. New child components get fresh GUIDs.
2. **The `//*TITLE*//` marker is bivalent** — it lives in `componentName` AND `propertyName` on the same text component. Clear both.
3. **Drop empty `//*CHILDTABLES*//` slots** — when the entity has no child collections, remove the entire placeholder container rather than leaving an empty section.
4. **There's no `childTable` component.** A "child table" is *the term* for the one-to-many UI pattern; the *implementation* is `dataTableContext` + `datatable.quickSearch` + `datatable` + `datatable.pager`, identical to what `table-view` already uses.
5. **`entityType` shape differs** between FK properties (`{id, _displayName, _className}`) and array-of-entity properties (`{fullClassName, name, module}`). Use each in its correct context.
6. **After substitution, re-run the "Mandatory entity binding" check** from Step 6 — every input you just placed must have a real `propertyName` matching an entity property. `editMode: "editable"` on every interactive input, except KeyInformationBar values which are `editMode: "readOnly"` + `hideLabel: true` (they're display, not edit).
7. **Tab label for `//*CHILDTABLES*//` with 2+ matches uses the property's `label`** (e.g. `"Persons"`), not the entity class name (`"OrganisationPerson"`).

---

## When the skill uses this

**Step 6, immediately after Step 5** — if the form came from a template seed (Step 3b.3) and contains any `//*` markers. Substitution is a precondition for the rest of Step 6: until the placeholders are gone, the components have no real bindings to verify and the form is non-functional.

**Diagnostic for existing forms** — when editing a form that already exists, if Step 4's markup still has `//*` markers, the form was never fully templated. Flag it to the user before editing further.

**Canonical example markup** for the two non-obvious idioms lives at `/examples/key-info-bar.json` and `/examples/table-view-selector.json` in the skill-plugin repo. The docs here distill them; refer to the JSON when you need the full property set.
