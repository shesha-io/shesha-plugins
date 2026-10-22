---
name: shesha-form-edit
description: Create and edit Shesha 0.46 form configurations directly via the API. Authenticates once, resolves a form by module + name with ConfigurationItem/GetCurrent, backs up the markup, applies the user's requirements (adding, removing, modifying or restructuring components - or building a brand-new form from scratch), validates against the bundled 0.46 component knowledge base, the render-hazard detectors and an embedded-script syntax gate, then pushes in place via UpdateMarkup (carrying modelType forward) / ImportJson / Create and proves the write with an independent read-back. 0.46 has no Draft/Live lifecycle and no FormConfiguration/GetByName. Use when the user provides a form id (or module + name) and requirements like "add a sector dropdown above the email field", "make the address tab conditional on AccountType=Corporate", "wire the Save button to call /api/.../Submit", "fix this form that renders blank/unstyled after the 0.46 upgrade", or "create a new branded login page using the auth-login pattern". Always prefer this skill over the Shesha MCP create_form_configuration tool, which regularly fails with 'dict' object has no attribute 'lower' and JSON-RPC -32602 errors.
---

# Shesha Form Edit (0.46)

Round-trip: **resolve by name -> GET -> back up -> edit a copy -> gates -> PUT in place -> independent read-back**. Also creates new forms (`Create` then `UpdateMarkup`).

**0.46 in one paragraph.** A form is one row edited **in place** - there is no Draft/Ready/Live, no `CreateNewVersion`/`UpdateStatus`, and `FormConfiguration/GetByName` is gone (404). A 200 from `UpdateMarkup` is live immediately, so *backup first, verify after*. `UpdateMarkup` **overwrites the row's `modelType`** with whatever you send. Components are migrated in memory on every load (steps above the stored `version` run), hidden components are **not mounted**, `htmlRender` sanitises by default, antd 6 renamed the tabs/collapse DOM, and the scripting API was reworked (new names first, legacy names still resolve). The portal caches forms in IndexedDB. Each of these has a recipe or a detector below; the full catalog is [references/render-hazards-046.md](references/render-hazards-046.md).

> **For any new table / list / create / detail form, start from the canonical seeds in `assets/examples/` - see [references/examples.md](references/examples.md).** A "**table**"/grid request builds a `datatable`; a "**list**"/cards request builds a `datalist` - different components, pick from the user's wording ([data-tables.md](references/components/data-tables.md)). The seeds encode the CRUD wiring most models get wrong (Add button opens the create form in a modal, detail views toggle edit in place, child tables use `tabs` + a `permanentFilter` on `{{data.id}}`, inputs chosen by data type - [by-datatype.md](references/components/by-datatype.md)). Copy the matching example, swap entity/properties/captions/`formId`s, re-stamp `parentId`s, push. Seeds are stored at their 0.45 component versions; that is valid (they migrate on load, see [component-cheatsheet.md](references/component-cheatsheet.md)).

> **Building a form to match a design?** If the requirements arrive as a **layout blueprint** (`<screen>.blueprint.md` from `shesha-developer-0-46:shesha-design-comprehension`, usually via `shesha-claude-designer`), treat it as the structure spec: its `Archetype` picks the seed, its `layout-tree` drives the **flex-container splits** (`container` with `display:"flex"` + `flexDirection:"row"`, children sized via `desktop.dimensions.width` - **never the `columns` component**) and `parentId`s, and its `bindings` drive `propertyName`s. See [references/blueprint-consumption.md](references/blueprint-consumption.md).

Args received: `$ARGUMENTS`. Flags: `--refresh-cache` (ignore TTL, re-distill metadata/seeds), `--no-browser` (skip Step 9).

## Safety gates (read first)

- **Backup before every write**, and push only an *edited copy* of what you read. History in the revision table is not a backup ([api.md](references/api.md) section 4).
- **A push is live.** On a shared/deployed backend get the owner's go-ahead before writing; never "try" a push on Live. Never rebuild/restart/kill a backend an IDE owns - ask ([backend-restart.md](references/backend-restart.md)).
- **Never hand-build or commit a `.shaconfig`**; push through the API only. Never create backlog items. Never fabricate credentials, seed data or permission state.
- **Success is an independent read**, not a 200/toast/hash. Step 8 is not optional.

## Non-interactive (headless) runs

When invoked non-interactively (`claude -p`, harness, CI) or when the task supplies a context block (Backend URL / Username / Password / Module / Working directory): **never call `AskUserQuestion`.** Use the supplied context verbatim - it **overrides** Step 1 discovery, Step 2 defaults and the target module. Defaults: design ask -> skip, author from seeds; missing form identity -> resolve from the task wording against the module's form list (`GetAll`), else create `{entity-kebab}-{type}` in the context module; push failure -> re-fetch & re-apply once, then stop and report; Step 9.5 -> skip. **Always end with a summary naming every form created or modified (module + name + id)** and the read-back result.

## Step R - Scale the effort to the request (always first)

- **Small edit** (one component/property/script/action on an existing form) -> inline, Steps 1-8 only, no design pass; browser check only if visual/behavioural.
- **One whole form** (table/list/create/details/dialog/subform) -> inline, Steps 0-10, seed-first.
- **Backend prerequisites may be missing** (entity/property/reflist/API/menu item) -> gate on Step 4.5 / the `fullstack-prereq-checker` agent and fix via the owning sibling skill BEFORE writing form JSON.
- **Multiple linked pages / a whole app** -> plan first, build in waves, fan out per [orchestration.md](references/orchestration.md); state the rough cost up front.
- **Route OUT non-form work** (reference list, role, notification, job, API) to the sibling skill.
- **This skill does not author style values.** Structure + CRUD wiring is the job; appearance (palette, type scale, spacing, surfaces, theme) belongs to `shesha-developer-0-46:shesha-design-system`. Composing a pre-styled block is supported ([block-library.md](references/block-library.md)); inventing hexes/fonts freehand is not. For "make it look like X / style it / brand it", build the structure then hand off to the design-system skill. Structural splits stay here: flex `container` rows, never `columns`.

## Step 1 - Resolve backend URL

Order: **task context (wins)** -> `SHESHA_BACKEND_URL` -> `src/*.Web.Host/Properties/launchSettings.json` (`profiles.Project.applicationUrl`) -> `src/*.Web.Host/appsettings.json` (`Kestrel:Endpoints:Http:Url`) -> `http://localhost:21021`. Strip the trailing slash -> `$BASE_URL`. `GET $BASE_URL/swagger/index.html` must answer; if not, stop and tell the user to start the backend (do not start it yourself).

## Step 2 - Authenticate once

Task-supplied credentials win; local-dev default `admin` / `123qwe` (don't ask). `POST $BASE_URL/api/TokenAuth/Authenticate`, token at `result.accessToken`. **0.46 rate-limits login (10/min) and OTP (5/min): authenticate once, reuse the token, never in a loop or retry** ([api.md](references/api.md) section 2). If no token, surface the raw response and stop. Module id for `Create`: `GET /api/services/app/Module/GetAll` -> `result.items[].id`.

## Step 3 - Identify the form

Required: form id **or** module + name. Ask only what is missing. Resolve by name with
`GET /api/services/app/ConfigurationItem/GetCurrent?ItemType=form&Module=<module>&Name=<name>` -> `result.configuration` (`id`, `markup` string, `modelType`, `access`, `permissions`) and `result.cacheMd5` ([api.md](references/api.md) section 3). **Not `FormConfiguration/GetByName` (404 on 0.46).** `$FORM_ID = configuration.id`.

## Step 4 - Fetch and back up the current markup

Save the whole GetCurrent envelope to `$RUN_DIR/backup/<module>.<name>.<timestamp>.envelope.json` (the backup), parse `configuration.markup` once into `$RUN_DIR/staged/<form>.current.json`, and edit a **copy** (`node scripts/form-api.mjs get --module M --name N` does both). Record the `modelType` and `access` you read - you must send them back. Result has top-level `components` (nested tree) and `formSettings`. Run `node scripts/scan-hazards.mjs <current.json>` now: it shows which render hazards the form already carries, so you do not blame your edit for them.

## Step 4.5 - Entity introspection (mandatory for entity-bound forms)

Skip if `formSettings.dataLoaderType === "none"`. Otherwise resolve the **exact registered entity for THIS backend** (a wrong type causes runtime 500/404; never copy a namespace from this doc - `Person` is `Shesha.Domain.Person` on current builds and `Shesha.Core.Person` on older ones):

1. `GET /api/services/app/EntityConfig/GetMainDataList?maxResultCount=500` -> take `name` + `module` (for the `formSettings.modelType` **object** `{ "name", "module" }`, the shape to author) and `fullClassName`/`className`+`namespace` (the **string** used as the metadata `container`). Cross-check against an existing form bound to the same entity; EntityConfig wins.
2. `GET /api/services/app/Metadata/GetProperties?container=<fullClassName>` -> `result` is a direct array. An error ``Type `x` not found`` (HTTP 404) means the **entity** does not exist (read the body - it is not a missing route): stop and invoke `Skill(skill="shesha-developer:domain-model")` (shipped in the `shesha-developer` plugin, not in this one). Cache to `.claude/cache/shesha-form-edit/metadata/`.
3. **Validate every `propertyName`** you add/edit against the property list. Metadata semantics (`referenceListName` is the full dotted name without any `RefList` prefix; `entityType` is the short class with `entityModule` separate): [api.md section 11](references/api.md). `many-to-many` array properties mean **junction subtables** - read [junction-subtables.md](references/components/junction-subtables.md).

The form-configuration **row** also has a string `modelType` (the one `UpdateMarkup` overwrites) - distinct from `formSettings.modelType` inside the markup ([form-shape.md](references/components/form-shape.md)).

If you or `domain-model` change an entity/property/reflist, the backend must be rebuilt and restarted first - follow [backend-restart.md](references/backend-restart.md) (poll the entity's `Crud/GetAll` until 200 before authoring). For a NEW entity-bound form dispatch the `shesha-developer-0-46:fullstack-prereq-checker` agent and block until `ready`; catalog of backend-rooted symptoms: [full-stack-prereqs.md](references/full-stack-prereqs.md).

## Step 5 - Apply the user's requirements

Read **only** the topic files the edit needs (usually 1-3):

| Topic | File |
|---|---|
| **0.46 render hazards - read before writing markup** | [references/render-hazards-046.md](references/render-hazards-046.md) |
| Per-component `version` + minimal shape (read FIRST) | [references/component-cheatsheet.md](references/component-cheatsheet.md) |
| Form structure, skeleton, IPropertySetting wrapper | [components/form-shape.md](references/components/form-shape.md) |
| Inputs, validation, file uploads | [components/inputs.md](references/components/inputs.md) |
| Dropdown / radio / checkboxGroup / refListStatus | [components/dropdowns.md](references/components/dropdowns.md) |
| Autocomplete, entityPicker | [components/selectors.md](references/components/selectors.md) |
| Containers, card, flex-row splits, tabs (structure only) | [components/containers.md](references/components/containers.md) |
| Buttons, links, subForm, action wiring | [components/actions.md](references/components/actions.md) |
| Datatable vs datalist, dataContext, the table-vs-list decision | [components/data-tables.md](references/components/data-tables.md) |
| Component by property data type | [components/by-datatype.md](references/components/by-datatype.md) |
| Child tables on a detail view | [components/child-tables.md](references/components/child-tables.md) |
| **Block library - compose before copying a seed** | [block-library.md](references/block-library.md) |
| Canonical example seeds | [examples.md](references/examples.md) |
| Embedded scripts, scripting API (new names), current user, async/try-catch, Expression Editor | [components/scripts.md](references/components/scripts.md) |
| Shared state (`contexts.appContext`, `page.state`) | [components/shared-state.md](references/components/shared-state.md) |
| Interaction Mode, `visible`, per-setting permissions | [components/edit-mode.md](references/components/edit-mode.md) |
| **Visual styling / appearance** | **do NOT read during a structural build - call `Skill(shesha-developer-0-46:shesha-design-system)`** |
| Layout pattern (full-page forms, auth) | [components/layout.md](references/components/layout.md) |
| Detail page structure/nav anatomy | [components/detail-page-pattern.md](references/components/detail-page-pattern.md) |
| M:M junction subtables | [components/junction-subtables.md](references/components/junction-subtables.md) |
| Add/create dialogs, formArguments, onPrepareSubmitData | [components/add-dialogs.md](references/components/add-dialogs.md) |
| Inline-editable datatables | [components/inline-editable-tables.md](references/components/inline-editable-tables.md) |
| Form quality contract (always-on rules) | [form-quality.md](references/form-quality.md) |
| Navigation/menu | [navigation-menu.md](references/navigation-menu.md) |
| Edits across many forms (pilot-first) | [bulk-operations.md](references/bulk-operations.md) |
| Fleet dispatch, verdict schemas, cost table | [orchestration.md](references/orchestration.md) |
| Browser testing, IndexedDB cache, measurement | [verification.md](references/verification.md) |
| Backend-rooted symptoms / restart runbook | [full-stack-prereqs.md](references/full-stack-prereqs.md), [backend-restart.md](references/backend-restart.md) |

**More than ~3 forms?** Read [bulk-operations.md](references/bulk-operations.md): pilot-first, **one** `shesha-developer-0-46:fleet-transformer` agent for mutations, one `form-auditor` per form for audits. **2+ distinct new forms?** One `form-author` agent per form in parallel; you audit and push centrally. A single new form stays in-context. **Never read a large seed wholesale** (`employee-table.json`, `rs-detail-with-header.json` are thousands of lines) - `Grep`/offset one fragment; prefer the lean seeds (`inline-editable-table.json`, `standalone-create.json`, `rs-create-dialog.json`).

**Seed discovery for new forms**, in order: (0) `assets/blocks/` block library - compose, don't copy ([block-library.md](references/block-library.md)); (1) `assets/examples/` canonical seeds ([examples.md](references/examples.md)); (2) `assets/patterns/` ([patterns.md](references/patterns.md)); (3) `.claude/cache/shesha-form-edit/seeds/`; (4) MCP `search_forms` for a closest match; (5) author from scratch only if nothing fits.

**Input component by data type**: string->textField, number->numberField, date->dateField (`selectionType`), reference-list-item->dropdown, entity FK->autocomplete ([by-datatype.md](references/components/by-datatype.md)).

**Proactive doc fetch** for non-trivial mechanisms (wizard, OTP, navigator, appContext composition, action chaining): `WebFetch` `docs.shesha.io` (contracts) or `shesha-grads.vercel.app` (how-to) before writing scripts; distil to `.claude/cache/shesha-form-edit/docs/<topic>.summary.md`.

### Component plan + KB check (mandatory, blocking - before writing any component JSON)

1. List every component `type` you plan to use.
2. Confirm each type exists in `../clean-form-config/assets/groups/index.json` (authoritative `type` strings: `dataContext`, `datatable`, `datatable.pager` ...).
3. Read that type's group file for valid property names; anything else is stripped by `clean-form-config`.
4. **Source-derived KB `assets/components-kb/`** (extracted from `shesha-reactjs` `release-0.46.0`; provenance in `_meta.json`): per component `ownProps`, `resolvedProps`, the current `version` integer, `initModel` defaults. Read lazily - `grep -A6 '"refListStatus"' assets/components-kb/_index.json`, then open one file; never the folder. `_gaps.json` lists components whose settings could not be extracted. Tie-break when sources disagree: **a live form that already renders on this app > the KB > `../clean-form-config/assets/groups/` > a doc example.** `_index.json` is the authority for `version` ([component-kb.md](references/component-kb.md) explains the layout).
5. Scan the group for a better-fit component (e.g. `refListStatus` instead of `dropdown` for read-only status). **Splits are flex `container` rows, never `columns`** (`display:"flex"` + `flexDirection:"row"` + `gap`, children sized via `desktop.dimensions.width`; per-child `customStyle:{flex}` is inert).
6. Update the plan with corrected types/properties/alternatives, then write the JSON.

### The 0.46 component rules

- **Version + shape together.** Fresh components carry the **current** `version` from the KB *and* the 0.46 settings names; stored lower versions are upgraded in memory on load (that is how seeds work). A too-low version on a new component silently drops its `desktop` style block; a versionless one re-runs the whole legacy chain and can throw.
- **Reworked settings layout.** Most components use `desktop`/`tablet`/`mobile` style blocks (border/background/font/dimensions/shadow, `stylingBoxJson` object) and the Common / Events / Appearance / Validations tabs; legacy flat keys (`fontSize` tokens, `stylingBox` string, `padding: 'padding-base'`) are ignored or mis-converted ([H8](references/render-hazards-046.md)). Do not author appearance values here.
- **Interaction Mode** (`editMode`, renamed from "Edit Mode"): `'editable' | 'readOnly' | 'disabled' | 'inherited'`; boolean `false` now means *disabled*, code-mode settings must return strings ([edit-mode.md](references/components/edit-mode.md)).
- **Visibility** is `visible` (boolean or code-mode), not `hidden`; a hidden component is not mounted ([H6](references/render-hazards-046.md)).
- **Per-setting permissions**: `visiblePermissions` (Visible) and `editModePermissions` (Interaction Mode); legacy `permissions` is deprecated.
- **Property Name** no longer accepts JavaScript - a plain identifier/path. **Key/value variable lists are replaced by the Expression Editor**: take the property's current shape from the KB `ownProps` or a live form, never invent it ([scripts.md](references/components/scripts.md)).
- **Password Combo is deprecated** (migrates to two `textField`s). `checkboxGroup` v6+ single mode becomes `radio`; `datatableContext` becomes `dataContext`.
- **Scripting API**: write `user`, `form`, `data`, `actions.callApi`, `actions.showMessage`, `actions.showDialog`, `utils.moment`, `page.state`, `storage`, `query`; the legacy names (`http`, `message`, `moment`, `pageContext`, `formData`, `application.user`, ...) still resolve at runtime but are untyped - convert only when already editing the script ([scripts.md](references/components/scripts.md)).
- **Render-time scripts** (any `_code`: `visible`, `editMode`, `style`, `desktop.*.color`, `content`) run before data loads: optional-chain **every** hop, never on assignment targets, `.slice()` arrays you keep ([H10, H11](references/render-hazards-046.md)).

### Tree-editing principles

Preserve every existing component's `id` and `parentId` (fresh GUIDs only on clones/new nodes); when re-parenting update only the moved node and add it to the new parent's `components`; don't touch `formSettings` unless asked. **`parentId` is mandatory on every component** (direct parent's `id`; root-level `"root"`; for a `columns` slot the `columns` component's id). Express edits as **anchored, idempotent transforms** that resolve by `componentName`/`id` at run time and refuse to apply if the anchor is missing. Stamp before push:

```js
function stampTree(nodes, parentId) {
  return nodes.map(node => {
    if (!node?.type) return { ...node, components: stampTree(node.components||[], parentId) }; // col slot
    const n = { ...node, parentId };
    if (n.components) n.components = stampTree(n.components, node.id);
    if (n.columns)    n.columns    = stampTree(n.columns,    node.id);
    if (n.tabs)       n.tabs       = n.tabs.map(t => ({ ...t, components: stampTree(t.components||[], node.id) }));
    if (n.content?.components) n.content = { ...n.content, components: stampTree(n.content.components, node.id) };
    if (n.header?.components)  n.header  = { ...n.header,  components: stampTree(n.header.components,  node.id) };
    return n;
  });
}
// markup.components = stampTree(markup.components, 'root');
```

## Step 5.5 - Pre-push safety gates (mandatory)

1. **JSON round trip**: `JSON.parse(JSON.stringify({ markup: JSON.stringify(tree) }))` must not throw (template literals in `dynamicEndpoint`/scripts and literal newlines inside strings are the usual causes of "Expected ',' or ']'"). Use string concatenation, `\n` escapes.
2. **Script syntax gate**: every edited script string must parse as an async function body. `node scripts/scan-hazards.mjs <edited.json> --syntax` checks all `_code`, `renderer`, `style`, `expression` and `on*` strings. A failing script is never pushed.
3. **Hazard scan**: `node scripts/scan-hazards.mjs <edited.json>` - no *new* findings relative to Step 4.

## Step 6 - Validate

Walk the tree (unique ids, valid types, valid parent chain); dead-prop check against the group file; runtime-type checks (booleans not `"true"`, numbers not `"42"`); dropdown `values` shape `{ id, label, value }`. Then the **[form-quality checklist](references/form-quality.md)** (validationErrors present, human labels, dropdown sources complete, primary action visible, consistent layout).

**Migration-safety checks (each silently passed review yet crashed a live form):** every component has an integer `version`; no non-string `defaultValue` (array/number/object -> `e.match is not a function`); datatable `editComponent`/`createComponent` is `[not-editable]` or `{type, settings:{...}}` - never `[default]`, never a flat model; `checkboxGroup` hardcoded options live in `items`.

Then **invoke `clean-form-config` ONCE, right before the final push** (mandatory, blocking): `Skill(skill="shesha-developer-0-46:clean-form-config", args="<path to edited form>")`. Run it once on the finished markup, not per edit. **A dead-prop report is a real finding** - check the KB `ownProps` and fix the index rather than waving it through. Never push a config that fails validation without user confirmation. **Before any bulk push (>3 forms)** fan out one `shesha-developer-0-46:form-auditor` per form ([orchestration.md](references/orchestration.md)); never push a `fail` verdict.

## Step 7 - Push

Default: `PUT $BASE_URL/api/services/Shesha/FormConfiguration/UpdateMarkup` with body `{ "id": "$FORM_ID", "markup": "<stringified form JSON>", "modelType": "<the modelType you read in Step 3/4>" }` - **always carry `modelType` forward** (omitting it blanks it; a different value replaces it). For an anonymous form also send `access: 5, permissions: []`. Build the body in Node ([api.md](references/api.md) section 5). `node scripts/form-api.mjs push --module M --name N --edited <file>` runs the gates and prints a dry-run plan; add `--apply` to back up, write and verify. Alternatives: `ImportJson` (multipart `ItemId` + lowercase `file`), `Create` ([api.md](references/api.md) section 6).

Scratch hygiene: write staged JSON and scripts under `$RUN_DIR/staged/` (not `/tmp` - git-bash `/tmp`, `C:\tmp` and `$env:TEMP` differ; native Windows Python can't open `/c/...` paths); pass values via env vars; one combined fetch->mutate->push script beats many probes.

**On any non-200**: surface the raw response with a short diagnosis, ask via `AskUserQuestion` (retry as-is / re-fetch and re-apply / abort), act on it. Never silently retry; never just stop.

## Step 8 - Verify (independent read-back)

Re-read with `ConfigurationItem/GetCurrent` (no `Md5`), then assert: `modelType` unchanged, `access` as intended (anonymous: `5`), and the markup equals what you sent (compare by component id; ignore key order, `stylingBox` whitespace, `null` vs absent). Run `scan-hazards --syntax` on the read-back. A 200, a toast or a matching hash is **not** evidence ([api.md](references/api.md) section 8). Before judging any visual result, **clear the portal's IndexedDB caches** (`form:default-app`, `form_lookup:default-app`, legacy `forms`) from `/favicon.ico` ([verification.md](references/verification.md) section 2). A save that reached the DB is not a working feature: verify the read path (render) separately in Step 9.

### Step 8.5 - Diagnose common runtime errors

| Error | Cause | Fix |
|---|---|---|
| 404 on `FormConfiguration/GetByName` or `ReferenceList/GetItems` | removed in 0.46 | `ConfigurationItem/GetCurrent` ([api.md](references/api.md)) |
| `modelType` blank/changed after push | `UpdateMarkup` assigns it | resend the original; verify on read-back |
| `HTTP 400` on dataContext load | entity has no GQL query API | `domain-model` skill, or `sourceType: "Url"` with a REST endpoint |
| `HTTP 404` on metadata fetch | wrong entity class in `formSettings.modelType` | re-verify via `EntityConfig/GetMainDataList` |
| `HTTP 500` on dataContext | `entityType`/`sourceType` missing | add `entityType`, `sourceType: "Entity"`, `dataFetchingMode`, `defaultPageSize`, `uniqueStateId` |
| `JSON parse error` in console | malformed script string | Step 5.5 gates |
| Form blank, no error | short ids / all-`root` parentIds | re-run `stampTree`, `crypto.randomUUID()` ids |
| "Please, provide some content for this HTML render"; CSS carrier dead | sanitiser / empty output / hidden carrier | [H3-H6](references/render-hazards-046.md) |
| Custom tabs/collapse CSS matches nothing | antd 6 DOM rename | [H7](references/render-hazards-046.md) |
| Hidden thing is visible; `Cannot read properties of undefined` | render-time script throws before data | [H10](references/render-hazards-046.md) |
| `Component with id ... is not found` | `refListStatus` inside `subForm` (framework bug) | [H13](references/render-hazards-046.md) |
| Sub-form fields have no labels | `labelCol: 0` | [H14](references/render-hazards-046.md) |
| Read-only view shows greyed controls | `editMode: false` = disabled | [H15](references/render-hazards-046.md) |
| Detail form blank without `?id=` | normal - `gql` loader has no id | test with `?id=<real-guid>` |
| Fields are read-only labels standalone | `editMode: "inherited"` outside edit context | expected; inputs appear in the Add modal / after Start Edit |
| Dropdown "No matches" | reflist has no items or wrong `referenceListId` | check the reflist; config is likely right |
| Junction/child `Crud/Create` 500 | contextual FK missing from payload (`_formFields`) | real component + `onPrepareSubmitData` ([add-dialogs.md](references/components/add-dialogs.md)) |
| 200 but the browser shows old markup | IndexedDB cache | clear from `/favicon.ico` |
| HTTP 429 on login | rate limit 10/min | reuse the token |

Full catalog (~45 rows): [debug.md](references/debug.md).

## Step 9 - Browser smoke (default; `--no-browser` opts out)

Load the form, capture console + network errors JSON validation cannot catch. Use whichever browser MCP the session exposes (`mcp__playwright__*`, `mcp__Claude_Browser__*`, `mcp__claude-in-chrome__*`): navigate -> clear the IndexedDB form caches from `/favicon.ico` -> reload -> read console + network -> at most one final screenshot. If no browser tool exists report "built but NOT visually verified", never "done". Frontend URL: `adminportal/` (auth) or `publicportal/` (anonymous), port from `<app>/.env*`/`package.json`; skip if neither runs. Test `*-details` via the table row's view link, not a pasted `?id=` URL (direct loads render but subtable Add/Create submits 500). **Cost discipline:** assert with the a11y snapshot + one batched `getBoundingClientRect`/`getComputedStyle` evaluate, not screenshots; check documented recipes before a browser loop. On any error consult [debug.md](references/debug.md) and quote it verbatim. Recipes: [verification.md](references/verification.md), [api.md section 13](references/api.md).

**The real completion signal for user-facing work is the owner exercising it in their own browser.** Do not declare done, commit or open a PR before that.

## Step 10 - Confirm

Report: form `$FORM_ID` (module + name) updated; read-back result (modelType, access, component diff); hazards found/fixed; what was NOT verified. Authenticated forms render at `/dynamic/<module>/<form>`, anonymous at `/no-auth/<module>/<form>`.

## Cache (`.claude/cache/shesha-form-edit/`)

Project-scoped: `metadata/`, `seeds/`, `docs/`, `_archive/`. Read `.summary.md` by default, open `.raw.json` only when insufficient. Populate via `node scripts/summarize.js <input.json> [--out <out.summary.md>]`. TTLs: metadata 24h; seeds invalidate on revision change. `--refresh-cache` ignores TTL.

## Non-negotiables

Renderer-fatal (get these wrong and the form renders blank or throws):

- **`parentId` on every component** (`"root"` at top level); `id` unique, opaque, stable - `crypto.randomUUID()` (short sequential placeholders like `btn1` fail; nanoid and truncated hex are fine - [verification.md](references/verification.md) section 0).
- **Every component carries its integer `version`** - current KB version for fresh components ([component-cheatsheet.md](references/component-cheatsheet.md)); never hand-maintain another list.
- **`defaultValue` is a mustache-template STRING**, never a literal array/number/object.
- **Code-mode props are objects** - `{ "_mode": "code", "_code": "...", "_value": ... }`; a code-carrying prop stored as a plain string is silently stripped (exceptions are properties declared as plain script strings, e.g. `htmlRender.renderer`).
- **Mustache always `{{double braces}}`**; `{data.id}` is ignored silently.
- **`dataContext` wraps every `datatable`/`datalist`** and needs explicit `entityType` + `sourceType` (a bare one 500s).

Structural:

- **One page-shell card wraps every page-level form** (`assets/blocks/page-shell.block.json`; spec in [containers.md](references/components/containers.md)); dialogs and row templates are not pages.
- **Splits are flex `container` rows, never `columns`.** **Preserve ids.** **`access: 5`** on anonymous forms (verify on read-back). Plain Navigate: `actionArguments.target`.
- **Fidelity**: the app theme only reaches chrome; compose pre-styled blocks, never type values a block lacks ([block-library.md](references/block-library.md)).

| Rule | Owner |
|---|---|
| list -> `datalist`, table/grid -> `datatable`; row-template runtime rules | [data-tables.md](references/components/data-tables.md) |
| camelCase every `propertyName`, incl. datatable columns | [form-quality.md](references/form-quality.md) |
| Interaction Mode per form type; read-only rail case | [edit-mode.md](references/components/edit-mode.md) |
| `formSettings.modelType` = resolved `{ name, module }`; default gql endpoints | [form-shape.md](references/components/form-shape.md) |
| CRUD wiring (Add dialog, detail lifecycle, standalone Save+Back, row->detail) | [examples.md](references/examples.md) |
| Contextually-preset FKs: real (not hidden) component **and** `onPrepareSubmitData` | [add-dialogs.md](references/components/add-dialogs.md) |
| Row delete/unlink = Execute Script + `actions.callApi.delete` + Refresh table | [junction-subtables.md](references/components/junction-subtables.md) |
| Inline-edit column editors (`[not-editable]` / full `settings`) | [inline-editable-tables.md](references/components/inline-editable-tables.md) |
| JSON-safe scripts; `try/catch` + `async/await`, no `.then()`; no `console.log` | [scripts.md](references/components/scripts.md) |
| No `globalState` - use `contexts.appContext` / `page.state` | [shared-state.md](references/components/shared-state.md) |
| Backend rebuild/restart after a domain change (owner's call) | [backend-restart.md](references/backend-restart.md) |
| PowerShell UTF-8 bytes + BOM-free staged files | [api.md](references/api.md) |

## Required skill & agent invocations

| Trigger | Invoke | Strength |
|---|---|---|
| Entity/property/reflist missing or broken (Step 4.5) | `shesha-developer:domain-model` (shesha-developer plugin) | MUST before any form push |
| After a domain change | [backend-restart.md](references/backend-restart.md) runbook (owner decides the restart) | MUST before building the form |
| New entity-bound form / unverified entity | `shesha-developer-0-46:fullstack-prereq-checker` agent | MUST (block until `ready`) |
| Custom endpoint for a Url-source/submit | `shesha-developer:shesha-app-layer` (shesha-developer plugin) | MUST before wiring |
| Every push (Step 6) | `shesha-developer-0-46:clean-form-config` | MUST |
| >3 forms changed | `shesha-developer-0-46:form-auditor` fan-out | MUST before pushing |
| Any bulk mutation | `shesha-developer-0-46:fleet-transformer` agent (exactly one) | MUST |
| A hazard found on many forms after an upgrade | `shesha-developer:shesha-upgrade-reconciler` (packaged, tested rules with pilot, fleet and report) instead of hand-editing each form | SHOULD |
| 2+ distinct new forms | `shesha-developer-0-46:form-author` per form | SHOULD |
| After ANY `form-author` dispatch | `node scripts/verify-artifact.mjs <outputPath> --backend <url> --token $RUN_DIR/access-token` | MUST - the file on disk is the evidence |
| Form renders and placement is settled | `shesha-developer-0-46:design-critic` agent | SHOULD |
| Any runtime error / failed smoke | capture verbatim, match in [debug.md](references/debug.md) / [render-hazards-046.md](references/render-hazards-046.md), change one thing at a time | MUST before proposing fixes |
| Before claiming done | evidence first - read-back diff + smoke ([verification.md](references/verification.md)) | MUST |
| Requirement mentions notifications / app settings | `shesha-developer:shesha-notifications` / `shesha-settings` | SHOULD |
| New endpoints exposed post-rollout | `harden-permissions` skill (shesha-developer-0-43 / shesha-utils) | ASK the user |

(Skills via the Skill tool; agents via the Task tool. In headless runs ASK-strength items are skipped, MUST items still run. Skills not shipped in this plugin live in the named sibling plugin; if absent, say so rather than improvising.)

## Doc fallback

For an unfamiliar API/component/action fetch docs first (`WebFetch`): `https://shesha-grads.vercel.app/docs/` (how-to) or `https://docs.shesha.io/` (contracts). Quote field names and gotchas verbatim; cache distillates under `.claude/cache/shesha-form-edit/docs/`. If the token expires (24h) re-run Step 2 - once.
