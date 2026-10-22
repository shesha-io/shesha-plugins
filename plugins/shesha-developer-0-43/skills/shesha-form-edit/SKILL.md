---
name: shesha-form-edit
description: Create and edit Shesha 0.43 form configurations directly via the API. Authenticates as admin, fetches existing markup with Get/GetByName/GetJson, applies the user's requirements (adding, removing, modifying, or restructuring components — or building a brand-new form from scratch), validates against the bundled component-properties index and embedded-script rules, and pushes via the 0.43 versioned-ConfigurationItem lifecycle (CreateNewVersion → UpdateMarkup on a Draft → publish Draft→Ready→Live), never mutating a Live version in place. Use when the user provides a form id (or module + name) and a set of requirements like "add a sector dropdown above the email field", "make the address tab conditional on AccountType=PBF", "wire the Save button to call /api/.../Submit", or "create a new branded login page using the auth-login pattern". Always prefer this skill over the Shesha MCP `create_form_configuration` tool — the MCP regularly fails with `'dict' object has no attribute 'lower'` and JSON-RPC `-32602` errors, and the direct-API path is more reliable.
allowed-tools:
  - Bash
  - PowerShell
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - WebFetch
  - Skill
  - Task
---

# Shesha Form Edit

Round-trip on 0.43: **RESOLVE the version → GET the markup → edit → push to a DRAFT → publish Draft→Ready→Live**. A form is a **versioned ConfigurationItem**, not a mutable blob — you never `UpdateMarkup` a Live version in place; you `CreateNewVersion` (clone Live→Draft), edit the Draft, then publish it (which auto-retires the old Live). Brand-new forms `Create` → `UpdateMarkup` → publish. **The lifecycle algorithm — resolve, branch on `versionStatus`, publish, verify, cache-clear — lives in [references/version-lifecycle.md](references/version-lifecycle.md); read it once per session.** Steps 3, 7 and 8 below link there rather than re-deriving it.

> **For any new table / list / create / detail form, start from the canonical seeds in `assets/examples/` — see [references/examples.md](references/examples.md).** A "**table**"/grid request builds a `datatable`; a "**list**"/cards request builds a `datalist` — different components, pick from the user's wording ([data-tables.md](references/components/data-tables.md)). They are real Shesha-standard forms (verified rendering against a live backend) and encode the CRUD wiring most models get wrong: the **Add button opens the create form in a modal** (`Show Dialog`), detail views toggle edit in place (`Start Edit`/`Submit`), child tables use `tabs` + a `permanentFilter` on `{{data.id}}`, and inputs are chosen by the property's data type ([by-datatype.md](references/components/by-datatype.md)). Copy the matching example, swap entity/properties/captions/`formId`s, re-stamp `parentId`s, push. Don't hand-author structure the examples already provide.

> **Building a form to match a design?** If the requirements arrive as a **layout blueprint** (`<screen>.blueprint.md` from `shesha-developer-0-43:shesha-design-comprehension`, usually via the `shesha-claude-designer` orchestrator), treat that blueprint as the structure spec: its `Archetype` picks the seed, its `layout-tree` `flex=[…]`/nesting drive the **flex-container splits** (a `container` with `display:"flex"` + `flexDirection:"row"`, children sized via `desktop.dimensions.width` — **never the `columns` component**) + `parentId`s, and its `bindings` drive `propertyName`s. Build to it exactly — then expect a placement re-measure (the orchestrator's gate 5a.5) against the blueprint's `assertions`. See [references/blueprint-consumption.md](references/blueprint-consumption.md).

Args received: `$ARGUMENTS`. Flags: `--refresh-cache` (ignore TTL, re-distill metadata/seeds), `--no-browser` (skip Step 9 browser smoke), `--no-design` (skip Step 0 / 9.5 design passes).

## Non-interactive (headless) runs — read this first

When invoked non-interactively (`claude -p`, a test harness, CI) or when the task supplies a context block (Backend URL / Username / Password / Module / Working directory): **never call `AskUserQuestion` — it dead-ends the run.** Use the supplied context verbatim — it **overrides** Step 1 URL discovery, Step 2 default credentials, and the target module. Defaults for every ask-gate: Step 0 design ask → skip, author from seeds; Step 3 missing form identity → resolve from the task wording against the module's form list (`GetAll`), else create a new form named `{entity-kebab}-{type}` in the context module; push-failure menu → re-fetch & re-apply once, then stop and report; Step 9.5 → skip. **Always end with a summary naming every form created or modified (module + name + id)** — downstream evaluation identifies your work from that output.

## Step R — Scale the effort to the request (always first)

Match your process weight to the task, and **default down** when unsure:

- **A small edit** (one component / property / script / action on an existing form) → stay inline, do Steps 1–8 only, skip the design pass, and only do a browser check (Step 9) if the change is visual/behavioral. Keep it cheap — don't run the full pipeline for a one-line tweak.
- **One whole form** (table / list / create / details / dialog / subform) → inline, full Steps 0–10, seed-first from `assets/examples/`. ("table"/grid → `datatable`; "list"/cards → `datalist`.)
- **Backend prerequisites may be missing** (entity / property / reflist / API / menu item) → gate on Step 4.5 (or the `fullstack-prereq-checker` agent) and fix gaps via the owning sibling skill BEFORE writing form JSON.
- **Multiple linked pages, or a whole app from a brief** → don't build it all in one context: plan first, then build in waves (create → details → table, then cross-link), orchestrating with `superpowers:dispatching-parallel-agents`. State the rough cost up front. See [orchestration.md](references/orchestration.md).

Also **route OUT non-form work** — a pure backend ask (reference list, role, notification, background job, API) goes straight to the sibling skill, not wrapped in form workflow.

**Styling is not this skill's job.** This skill builds correct **structure + CRUD wiring**; *appearance* (surfaces, backgrounds, shadows, layering, radii, v7 style blocks, theme) belongs to `shesha-developer-0-43:shesha-design-system`. A structural build/edit never reads styling docs and never authors v7 appearance blocks. When the request is "make it look like X / match the design / style it / it looks bad / apply our brand", build/confirm the structure, then hand off: `Skill(shesha-developer-0-43:shesha-design-system)`. The ONE layout concern that stays here is **structural splits**, which are flex `container` rows (`display:"flex"` + `flexDirection:"row"`, children sized via `desktop.dimensions.width`) — **never the `columns` component** (firm project rule).

## Step 0 — Design consultation (ask first)

For brand-new forms or major restructures, **ask the user via `AskUserQuestion`** whether to invoke the `frontend-design` skill for a design plan (typography, palette, spatial system, section list):

> Want a design consultation from the `frontend-design` skill for this form? It returns aesthetic direction (~30s extra) before authoring.
> - **Yes — get a design plan** (recommended for new pages / major restructures)
> - **No — author from seeds only** (good for adding fields, small tweaks, internal forms)

On Yes: invoke `Skill(skill="frontend-design", ...)` per [references/design.md](references/design.md); cache the plan at `.claude/cache/shesha-form-edit/design-plans/<form-name>.md` for Step 9.5.

**Don't ask** (skip silently) for: trivial edits (add a field, fix a script, change a propertyName), bug fixes, row-template / sub-form / utility forms, or when `--no-design` is in `$ARGUMENTS`. If `frontend-design` isn't installed, warn the user once and continue without it.

## Step 1 — Resolve backend URL

Order: **task-supplied context block (always wins)** → **`SHESHA_BACKEND_URL` environment variable** (sandboxed/ephemeral environments where the backend runs in a separate process or pod, not at `localhost`) → `src/*.Web.Host/Properties/launchSettings.json` (`profiles.Project.applicationUrl`) → `src/*.Web.Host/appsettings.json` (`Kestrel:Endpoints:Http:Url`) → fallback `http://localhost:21021`. Strip trailing slash. Store as `$BASE_URL`. Ping `$BASE_URL/swagger/index.html` to confirm reachability; if it fails, stop and tell the user to start the backend.

## Step 2 — Authenticate as admin

Task-supplied credentials win; local-dev defaults otherwise: **`admin` / `123qwe`** — don't ask. POST `$BASE_URL/api/TokenAuth/Authenticate` with `{ userNameOrEmailAddress, password }`; extract `result.accessToken` (or `accessToken` on older builds). See [references/api.md §2](references/api.md). If no token, surface raw response and stop.

**Module ID lookup** (needed for `Create`): `GET $BASE_URL/api/services/app/Module/GetAll` (note: `app` namespace — `Shesha/Module/GetAll` returns 404). Find the entry where `name === "<module>"` and take its `id`. Cache it for the session. If a subsequent `Create` call returns `"There is no entity Module with id = …"`, the backend was restarted and the ID changed — re-fetch via this endpoint.

## Step 3 — Identify the form + RESOLVE its lifecycle (0.43)

Required: form id **OR** (module + name). Ask the user only what's missing:

> Which form? Either give me the **id** (Guid), or **module + name** (e.g. `PBF.MembershipManagement` + `member-create`).

Then **RESOLVE the lifecycle context before touching anything** — a 0.43 form has many versions and `GetByName` hides an in-flight Draft. Run the in-flight lookup (`GetAll` with `isLast==true`) to get the latest version's `id` + `versionNo` + `versionStatus` + `origin`, and **BRANCH on `versionStatus`**: Live(3) → you'll `CreateNewVersion` in Step 7; Draft(1)/Ready(2) → reuse that version's id; Retired(5)/Cancelled(4) → resolve to the latest non-terminal version first. Full algorithm + curl/Node helpers: [references/version-lifecycle.md](references/version-lifecycle.md). Store the resolved edit-target id as `$FORM_ID` (this is the id you will *read*; the id you *write* is decided in Step 7).

## Step 4 — Fetch the current markup

`GET /api/services/Shesha/FormConfiguration/GetJson?id=$FORM_ID` ([api.md §4](references/api.md)) — fetch the markup of the version you resolved in Step 3 (for a Live form, this is the Live markup you're about to clone). Save to `$env:TEMP\form-current.json`. The response body is a stringified form JSON; parse it. Resulting object has top-level `components` (nested tree) and `formSettings`.

## Step 4.5 — Entity introspection (mandatory for entity-bound forms)

Skip if `formSettings.dataLoaderType === "none"`. Otherwise fetch the entity's metadata and validate every `propertyName` in the edit.

**Get the exact entity type first (critical — wrong type causes 500 errors at runtime):**

`formSettings.modelType` must identify the **exact registered entity for THIS backend** — resolve it dynamically every time; never assume or copy a namespace from this doc. The same logical entity is registered under different namespaces across Shesha/BoxStack versions: framework entities like `Person` are `Shesha.Domain.Person` on current versions but `Shesha.Core.Person` on older ones, and a backend may even carry both. **The only authority is the live `EntityConfig` for the running backend** — its record gives you the `name`, `module`, and `fullClassName` you need below. Getting this wrong causes 500/404 errors in the browser when the loader or `dataContext` queries the entity — any mismatch with the registered entity is a runtime failure.

**Favour the object shape for `formSettings.modelType`:** `{ "name": "<ShortClass>", "module": "<Module>" }` (e.g. `{ "name": "Person", "module": "Shesha" }`) — the shape current Shesha builds emit. A full-class-name **string** still renders on legacy forms, but write new/edited forms with the object. **Independently, you always also need the resolved `fullClassName` string** — the metadata fetch below passes it as `?container=`, and component-level `entityType`s use either the short class+module or the full class string per their own rules (unchanged).

Resolve it (in priority order) — and use the result verbatim:
1. **From entity config (authoritative)**: `GET $BASE_URL/api/services/app/EntityConfig/GetMainDataList?maxResultCount=200` — find the entity by `name`, then take its **`name` + `module`** for the `modelType` object **and** its **`fullClassName`** (fall back to `className`) for the metadata `container` param. These are authoritative — use them verbatim.
2. **Cross-check against an existing form**: `GET $BASE_URL/api/services/Shesha/FormConfiguration/GetAll?maxResultCount=50` — a form bound to the same entity shows the in-use `modelType`. If existing forms disagree with each other (legacy `Shesha.Core.*` vs current `Shesha.Domain.*`), the EntityConfig `fullClassName` wins.

**Entity existence check**: before building any form, verify the entity exists: `GET $BASE_URL/api/services/app/Metadata/GetProperties?container=<exactModelType>`. If the response returns an empty array or error, the entity does not exist — stop and invoke `Skill(skill="shesha-developer-0-43:domain-model")`. Never build forms for entities that don't exist; they silently fail at runtime.

**If you (or `domain-model`) create or change an entity/property/reflist, the backend MUST be rebuilt and restarted before the entity is usable — follow [references/backend-restart.md](references/backend-restart.md).** Do this BEFORE building the form, and in this order: domain change → rebuild + restart (+ the 2-boot lag for new entities) → poll the entity's `…/api/dynamic/<module>/<Entity>/Crud/GetAll` until 200 → only then author/push the form. Never relaunch IIS Express outside Visual Studio (it 500s); headless runs take over :21021 with `dotnet`, attended runs hand the restart back to VS. This restart sequence is the biggest cost/failure sink when improvised — use the runbook.

1. Take the resolved `fullClassName` (the class-name string from the resolution above; `formSettings.modelType` itself is the `{ name, module }` object).
2. Fetch `GET $BASE_URL/api/services/app/Metadata/GetProperties?container=<fullClassName>` — `container` is the class-name **string**, never the object. Returns `result` as a direct array of properties (not wrapped). Cache to `.claude/cache/shesha-form-edit/metadata/<entity>.raw.json`.
3. **Validate `propertyName` against the property list** for every input component you're adding/editing. Surface mismatches before push.

Metadata semantics (`referenceListName` is the full dotted name used **without** any `RefList` prefix; `entityType` is the SHORT class name with `entityModule` separate; FK property names can differ from class names): [api.md §10](references/api.md). Array properties with `listConfiguration.mappingType: "many-to-many"` mean **junction subtables** — read [junction-subtables.md](references/components/junction-subtables.md) before touching those tabs.

TTL 24h; `--refresh-cache` forces re-fetch. If the metadata fetch returns nothing or surfaces a malformed entity, optionally invoke `Skill(skill="shesha-developer-0-43:test-entity-crud-api", args="--no-fix")` and fix entity bugs before continuing — a form bound to a broken entity will look fine in markup but fail at runtime.

**For a NEW entity-bound form, or any entity/junction not already verified this session: dispatch the `shesha-developer-0-43:fullstack-prereq-checker` agent** (Task tool; pass backend URL, token-file path, and the entity list) and block until its verdict is `ready` — its failures name the fixing skill per gap. Inline checks remain fine for small edits to an already-rendering form. Catalog of backend-rooted symptoms: [full-stack-prereqs.md](references/full-stack-prereqs.md).

## Step 5 — Apply the user's requirements

Read **only** the topic files relevant to the edit. Most edits need 1–3 files:

| Topic | File |
|---|---|
| Form structure, skeleton, IPropertySetting wrapper | [references/components/form-shape.md](references/components/form-shape.md) |
| Inputs, validation, file uploads | [references/components/inputs.md](references/components/inputs.md) |
| Dropdowns / radio / checkboxGroup / refListStatus | [references/components/dropdowns.md](references/components/dropdowns.md) |
| Autocomplete, entityPicker | [references/components/selectors.md](references/components/selectors.md) |
| Containers, card, **flex-row splits**, tabs (structure only — appearance → `shesha-design-system`) | [references/components/containers.md](references/components/containers.md) |
| Buttons, links, subForm, action wiring | [references/components/actions.md](references/components/actions.md) |
| Datatable (table/grid) vs datalist (card list), dataContext — incl. the **table-vs-list** decision | [references/components/data-tables.md](references/components/data-tables.md) |
| Component selection by property data type | [references/components/by-datatype.md](references/components/by-datatype.md) |
| Child tables on a detail view (tabs + permanentFilter) | [references/components/child-tables.md](references/components/child-tables.md) |
| **Block library — compose small vetted blocks (do this BEFORE copying a seed)** | [references/block-library.md](references/block-library.md) |
| Canonical example seeds (fallback when the block library lacks a shape) | [references/examples.md](references/examples.md) |
| Embedded scripts, current user, async/try-catch | [references/components/scripts.md](references/components/scripts.md) |
| Shared state (appContext, pageContext) | [references/components/shared-state.md](references/components/shared-state.md) |
| editMode, visibility, permissions | [references/components/edit-mode.md](references/components/edit-mode.md) |
| **Visual styling / appearance** (surfaces, shadows, layering, v7 style blocks, theme) | **do NOT read during a structural build — call `Skill(shesha-developer-0-43:shesha-design-system)`** |
| Layout pattern (full-page forms, auth) | [references/components/layout.md](references/components/layout.md) |
| Detail page **structure/nav** anatomy (sections, label grid, table→row nav) — *appearance of it (header band, KIB styling) → `shesha-design-system`* | [references/components/detail-page-pattern.md](references/components/detail-page-pattern.md) |
| M:M junction subtables — link, drill-down, delete/unlink | [references/components/junction-subtables.md](references/components/junction-subtables.md) |
| Add/create dialogs, formArguments, onPrepareSubmitData | [references/components/add-dialogs.md](references/components/add-dialogs.md) |
| Inline-editable datatables (editComponent shape, crud-operations column) | [references/components/inline-editable-tables.md](references/components/inline-editable-tables.md) |
| Form quality contract (always-on construction rules) | [references/form-quality.md](references/form-quality.md) |
| Adding forms to the app navigation/menu | [references/navigation-menu.md](references/navigation-menu.md) |
| Edits across many forms (pilot-first transforms) | [references/bulk-operations.md](references/bulk-operations.md) |
| Multi-agent fleet dispatch, verdict schemas, cost table | [references/orchestration.md](references/orchestration.md) |
| Browser testing, IndexedDB cache, layout measurement | [references/verification.md](references/verification.md) |
| Symptoms whose fix is backend (reflists, junction DTOs, GQL) | [references/full-stack-prereqs.md](references/full-stack-prereqs.md) |
| Rebuild + restart the backend after a domain change (entity/migration) | [references/backend-restart.md](references/backend-restart.md) |

**Touching more than ~3 forms?** Read [references/bulk-operations.md](references/bulk-operations.md) first — pilot-first is mandatory. Mutations go through **one `shesha-developer-0-43:fleet-transformer` agent** (never per-form authoring agents); audits fan out **one `shesha-developer-0-43:form-auditor` per form**. Dispatch templates + cost table: [references/orchestration.md](references/orchestration.md).

**Authoring 2+ genuinely distinct new forms?** Dispatch one `shesha-developer-0-43:form-author` agent per form in parallel (each gets the seed, metadata, requirements, and an output path); you audit and push centrally afterwards. A single new form stays in-context.

**Read [references/component-cheatsheet.md](references/component-cheatsheet.md) FIRST** — it has the current per-component `version` + minimal shape, so you don't burn round-trips probing for versions or read multi-thousand-line seeds. **Never read a large seed wholesale** (`employee-table.json`, `rs-detail-with-header.json`, etc. are thousands of lines — that's tens of thousands of wasted tokens); open them only with `Grep`/offset for one specific fragment. Prefer the small lean seeds (`inline-editable-table.json`, `standalone-create.json`, `rs-create-dialog.json`).

**Seed discovery for new forms** (in this order):
0. **`assets/blocks/` — the BLOCK LIBRARY (compose, don't copy-a-seed).** Build the form by composing small, individually-validated blocks (`flex-split-main-rail`, `page-header-band`, `meta-strip`, `card-with-header-strip`, `rail-panel`, `rail-label-value-row`, `status-pill`, `completeness-bar`, `requirement-datalist-row`, `dashed-add-button`) — assembly workflow in [references/block-library.md](references/block-library.md). Each block is a structure skeleton paired with a `shesha-design-system` style overlay and validated against the capability matrix (`scripts/validate-blocks.js`). This is cheaper (compose ~600 lines, not a 25K-line seed) and correct-by-construction — **prefer it.** Styling is applied by `shesha-design-system` from the paired overlay, not here.
1. **`assets/examples/` — CANONICAL Shesha-standard seeds (fallback when the block library lacks a shape).** See [references/examples.md](references/examples.md) for the index and the CRUD-loop wiring (modal Add button, Start Edit/Submit detail header, child-table tabs). Copy the matching example and change only `modelType`/`entityType`/`propertyName`/captions/`formId`s. **Prefer the small/lean seeds; never read the multi-thousand-line ones in full.** These forms render correctly and follow standards.
2. `assets/patterns/` — other vendor seeds (index: [references/patterns.md](references/patterns.md)).
3. `.claude/cache/shesha-form-edit/seeds/` — project-specific forms cached from prior edits.
4. **MCP `search_forms`** — query `mcp__shesha__search_forms` for forms in this backend matching the layout type. Use the closest match as a seed; cache it under `seeds/` for next time.
5. Author from scratch only if no seed fits — guided by the design plan from Step 0.

**Picking the input component for each field** — driven by the property's `dataType` (string→textField, number→numberField, date→dateField, reference-list-item→dropdown, entity FK→autocomplete, …). Full table + config in [references/components/by-datatype.md](references/components/by-datatype.md).

**Proactive doc fetch**: when the user's requirements mention non-trivial mechanisms (wizard, OTP, navigator, complex appContext composition, custom action chaining), `WebFetch` the relevant `shesha-grads.vercel.app` / `docs.shesha.io` page **before** writing scripts. Distill into `.claude/cache/shesha-form-edit/docs/<topic>.summary.md` (~30 lines) so subsequent edits don't re-fetch.

**Component plan + index check (mandatory, blocking — do this before writing any component JSON)**:

For every new or edited form, before writing a single component object:

1. **List every component `type` you plan to use.** (e.g. for a table form: `container`, `text`, `button`, `dataContext`, `datatable`; for a list form: `container`, `dataContext`, `datalist`, `datatable.pager`)

2. **Confirm each type exists** in the component index at `assets/groups/index.json` (bundled in this skill's assets folder). If a type is missing, you have the wrong name. The index is the authoritative source for the exact `type` string used in form JSON (e.g. `dataContext` for the table/list data wrapper; `datatable` not `dataTable`).

3. **Load the group file** for each component type (the index maps type → group file). Read the group file to get the full list of valid property names, their expected types, and descriptions. Only use properties listed there — anything else will be stripped by `clean-form-config` at Step 6.

4. **Scan the group for alternatives.** While in the group file, check whether a better-fit component exists (e.g. `refListStatus` instead of `dropdown` for read-only status display). **For side-by-side / split layout use a flex `container` row — NEVER the `columns` component** (firm project rule): `display:"flex"` + `flexDirection:"row"` + `gap`, with each child sized via `desktop.dimensions.width` (a fixed-width rail = `width:"332px"`; a filling main column = `width:"calc(100% - <rail+gap>px)"`). Per-child `customStyle:{flex:…}` does NOT size the outer div — proven inert; use `dimensions.width`.

5. **Update the plan** with corrected type names, valid properties, and any swapped alternatives — then write the JSON.

Tree-editing principles: preserve every existing component's `id` and `parentId` (fresh GUIDs only on clones / new nodes); when re-parenting, update only the moved node and add it to the new parent's `components`; don't touch `formSettings` unless asked.

**`parentId` is mandatory on every component** — the Shesha renderer uses it to build the component tree and crashes entirely when it is absent. Set `parentId` to the direct parent component's `id`. Components at the root level of a form get `parentId: "root"`. Components inside a `columns` slot get `parentId` equal to the `columns` component's `id` (not the slot's own `id`). Use a recursive stamping pass before push:

```js
function stampTree(nodes, parentId) {
  return nodes.map(node => {
    if (!node?.type) return { ...node, components: stampTree(node.components||[], parentId) }; // col slot
    const n = { ...node, parentId };
    if (n.components) n.components = stampTree(n.components, node.id);
    if (n.columns)    n.columns    = stampTree(n.columns,    node.id);
    if (n.tabs)       n.tabs       = n.tabs.map(t => ({ ...t, components: stampTree(t.components||[], node.id) }));
    if (n.content?.components) n.content = { ...n.content, components: stampTree(n.content.components, node.id) }; // card / collapsiblePanel slot
    if (n.header?.components)  n.header  = { ...n.header,  components: stampTree(n.header.components,  node.id) };
    return n;
  });
}
// Usage: markup.components = stampTree(markup.components, 'root');
```

## Step 5.5 — Pre-push JSON safety check (mandatory)

Before calling UpdateMarkup, run this Node snippet to catch JSON-in-JSON errors that will cause `"Expected ',' or ']' after array element in JSON"` in the browser:

```js
const markup = { /* your form object */ };
try {
  const str = JSON.stringify(markup);
  JSON.parse(str);        // must not throw
  JSON.parse(JSON.stringify({ markup: str })); // round-trip test
  console.log('JSON OK, length:', str.length);
} catch (e) {
  console.error('BROKEN JSON:', e.message);
  process.exit(1);
}
```

Common causes of failure: template literals (`` `${x}` ``) inside `dynamicEndpoint` or script fields — replace with string concatenation; literal newline characters in string values — replace with `\n`.

## Step 6 — Validate

Walk tree (unique ids, valid types, valid parent chain); dead-prop check: look up each component's group in `assets/groups/index.json`, then validate its props against that group file; runtime-type checks (booleans not `"true"`, numbers not `"42"`); dropdown `values` shape (`{ id, label, value }`); `node --check` each script string. Then run the **[form-quality checklist](references/form-quality.md)** — validationErrors present, human-readable labels, dropdown sources complete, primary action visible, consistent layout.

**Migration-safety checks (mandatory — each of these silently passed review yet crashed the live form):**
- **Every component has an integer `version`.** A versionless component re-runs the whole legacy migration chain at render and can throw `e.match` / `reading 'migrator'` / `reading 'version'`. Flag any component object missing `version` (except pure layout slots).
- **No `defaultValue` that is a non-string** (array/number/object). `defaultValue` is resolved as a mustache template via `.match()`; a literal array → `e.match is not a function`. Flag and remove (or convert to a data binding).
- **Datatable `editComponent`/`createComponent` is `[not-editable]` or `{type, settings:{…}}`** — never `[default]` (→ `reading 'migrator'`), never a flat model missing the `settings` wrapper (→ `reading 'version'`). Flag either.
- **`checkboxGroup` hardcoded options live in `items` (not `values`)** with `version: 5`.

Then **invoke `clean-form-config` ONCE, right before the final push** (mandatory, blocking) — covers layout overflow, label-vs-propertyName refs, missing try/catch, missing async, broken script syntax:

```
Skill(skill="shesha-developer-0-43:clean-form-config", args="<path to your edited form>")
```

**Run it once on the finished markup — not after every intermediate edit** (re-running it per change is a large, repeated cost for no extra signal). **Known false positives — don't re-investigate or strip these:** the `dataContext` data props (`entityType`, `sourceType`, `dataFetchingMode`, `defaultPageSize`, …), container `direction`/`flexDirection`, `text.padding`, and the datatable inline props (`canEditInline`/`canAddInline`/`canDeleteInline`/`inlineEditMode`/`inlineSaveMode`) are valid and render in live forms; the bundled index just doesn't enumerate them.

If validation surfaces a REAL issue, fix it before pushing. **Never push a config that fails validation without user confirmation.**

**Before any bulk push (>3 forms changed): fan out `shesha-developer-0-43:form-auditor` agents — one per form** — with the verdict contract from [orchestration.md](references/orchestration.md); aggregate and never push a form with a `fail` verdict.

## Step 7 — Push through the 0.43 version lifecycle

**Never `UpdateMarkup` a Live version.** On 0.43 the push is a lifecycle, not a single PUT. Follow the branch you resolved in Step 3 (full algorithm, curl + Node helpers, invariants: [references/version-lifecycle.md](references/version-lifecycle.md)):

1. **Get the write-target Draft id (`$NEW_ID`).**
   - **Live(3)** → `CreateNewVersion { id: $FORM_ID }` (POST — a real id is mandatory, an empty body 404s) → capture `result.id` as `$NEW_ID`. Do this **at most once per edit session.**
   - **Draft(1)/Ready(2) in flight** → **reuse** that version's id as `$NEW_ID`; do NOT `CreateNewVersion`.
   - **Brand-new form** → `Create` ([api.md §7](references/api.md)) → its Draft id is `$NEW_ID`.
2. **Write markup to `$NEW_ID`** — `PUT UpdateMarkup`, body `{ "id": "$NEW_ID", "markup": "<stringified form JSON>" }`. Build the body in Node to avoid escaping pain. See [api.md §5](references/api.md). (Alternative: **ImportJson** multipart `ItemId=$NEW_ID` + `file` — [api.md §6](references/api.md).) **`$NEW_ID`, never `$FORM_ID`.**
3. **Publish** — `PUT UpdateStatus` with a mandatory stringified `filter` on the id, in two hops: `status:2` (Draft→Ready) then `status:3` (Ready→Live). Publishing to Live auto-retires the prior Live. See [api.md §5.1](references/api.md) / [version-lifecycle.md](references/version-lifecycle.md).
4. **Any verify/fix loop (Step 8/9) edits and re-publishes THIS SAME `$NEW_ID`** — never `CreateNewVersion` again (that spawns orphaned Drafts).

**Scratch-script hygiene (avoids a recurring time-sink):** write build/push scripts and staged JSON into the **supplied working directory**, NOT `/tmp` — git-bash `/tmp` maps to `%TEMP%` (e.g. `C:\Users\…\AppData\Local\Temp`), which is a *different* path than Windows `C:\tmp` and from PowerShell `$env:TEMP`, so a file written by `bash` is frequently "not found" by `node`/PowerShell. Pass values into Node via **env vars** (`VAR=x node script.js`), not positional argv that the shell may not forward. Prefer **one combined resolve→branch→createDraft→mutate→publish script** over many small probe commands (each round-trip is cost).

Success per call: HTTP 200 (`UpdateMarkup`/`UpdateStatus` return `{ "result": null, "success": true }` — void endpoints; the 200 is acceptance, NOT proof — verify in Step 8).

### On push/publish failure (any non-200) — lifecycle-aware recovery

1. Surface the raw response and a short diagnosis.
2. **Locate the failure in the lifecycle** — a good `UpdateMarkup` followed by a failed `UpdateStatus` leaves a real, correctly-edited Draft that is **unpublished**; do NOT `CreateNewVersion` again.
3. Ask the user via `AskUserQuestion`: **retry the failed step on the same `$NEW_ID`** / **re-fetch and re-apply markup to `$NEW_ID`** / **abort and cancel the Draft** (`UpdateStatus status:4` — `CancelVersion` only works on a Ready version on 0.43). **Never silently retry. Never leave a dangling Draft.** Recovery matrix: [version-lifecycle.md §Failure recovery](references/version-lifecycle.md).

## Step 8 — Verify (version-aware)

Confirm the **lifecycle landed**, not just that markup round-trips ([version-lifecycle.md §Version-aware verification](references/version-lifecycle.md)):

1. **Latest is Live with the incremented `versionNo`** — `GetByName` (no `version` param) returns `versionStatus === 3` and `versionNo === <previous + 1>`.
2. **The previous Live is now Retired** — `Get?id=<old Live id>` returns `versionStatus === 5`.
3. **Diff against the PUBLISHED version's markup, not the old `$FORM_ID`** — re-fetching the pre-edit id may return the now-retired version and mislead you. Diff the markup you sent against the new Live version; surface any server normalization ([api.md §11](references/api.md)).
4. **Clear the frontend cache** (mandatory after publish) — see Step 8.5 / [verification.md](references/verification.md).

For anonymous forms (`access: 5`), confirm `result.access === 5` on the published version — the `Create` endpoint may not honor `access` on initial create; if it didn't stick, re-`UpdateMarkup` the Draft (before publishing) or clone→fix→publish again.

## Step 8.5 — Diagnose common runtime errors

After verifying, watch for these patterns in the browser console or from Playwright:

| Error | Cause | Fix |
|---|---|---|
| `HTTP 400` on dataContext data load | Entity doesn't have GQL query API enabled in backend | Invoke `shesha-developer-0-43:domain-model` to enable GQL on entity, or use `sourceType: "Url"` with an explicit REST endpoint |
| `HTTP 404` on metadata fetch (`"Failed to fetch metadata of type …"`) | Wrong entity class name in `formSettings.modelType` | Re-verify entity type via `EntityConfig/GetMainDataList` or `FormConfiguration/GetAll` on existing forms |
| `HTTP 500` on dataContext | `entityType` or `sourceType` missing on the `dataContext` component | Add `entityType`, `sourceType: "Entity"`, `dataFetchingMode`, `defaultPageSize`, `uniqueStateId` |
| `JSON parse error` in browser console | Malformed script string in form markup — template literals or literal newlines | Run Step 5.5 JSON safety check; replace template literals with concatenation |
| Form shows blank/empty without error | Short IDs (`pr1`, `btn2`) or all-`root` parentIds | Re-run `stampTree`; ensure `crypto.randomUUID()` IDs |
| Detail form shows blank when navigated to without `?id=` | Normal — `gql` loader has no ID to fetch | This is expected; test detail forms with `?id=<real-guid>` |
| Create/edit fields show as read-only labels (no input boxes) standalone | `editMode: "inherited"` + form not in edit context | Expected — they become inputs inside the Add modal (`formMode: "edit"`) or after Start Edit. Don't "fix" by forcing `editable`. |
| Dropdown opens but shows "No matches" / no options | The backend **reference list has no items**, or wrong `referenceListId` | Verify the reflist name via property metadata; confirm items exist in the backend reflist editor. Config itself (see by-datatype.md) is likely correct. |
| Autocomplete (FK) shows "No matches" | Target entity has no records, or wrong `entityType:{name,module}` | Confirm the FK target short class name + module; ensure records exist. |
| Junction/child `Crud/Create` 500 on dialog submit | Contextually-preset FK never reached the payload (`_formFields` rule) | Real component + `formSettings.onPrepareSubmitData` — see [add-dialogs.md](references/components/add-dialogs.md) |
| Push returned 200 but the browser shows old markup | Frontend IndexedDB form cache | Clear from a static page (`/favicon.ico`) — see [verification.md](references/verification.md) |

Full catalog (~40 rows, grouped): [references/debug.md](references/debug.md).

## Step 9 — Browser smoke (default; `--no-browser` opts out)

Invoke the playwright skill to load the form, screenshot, and capture console + network errors that JSON validation can't catch (editMode regressions, runtime script failures, broken layout). Recipe in [api.md §12](references/api.md):

```
Skill(skill="playwright", args="<directive from api.md §12, with FRONTEND_URL + form path filled in>")
```

Frontend URL: `adminportal/` (auth forms) or `publicportal/` (anonymous) — read the dev port from `<app>/.env*` or `<app>/package.json`. If neither front-end is running, skip the smoke step and warn the user.

Test `*-details` forms via the **table row's view link**, never a pasted `?id=` URL — direct loads render but subtable Add/Create submits 500 (missing page context). If the browser disagrees with a verified API re-fetch, clear the **IndexedDB form cache from `/favicon.ico`** before debugging further.

**Verification cost discipline (this is where runs blow up — keep it tight):**
- Assert with the **a11y snapshot** + `getBoundingClientRect`/`getComputedStyle`, **not screenshots**. Reading a full-page screenshot is ~60 KB of tokens each — take **at most ONE screenshot, at the very end** for a final visual confirmation, never one per iteration.
- **Batch all DOM measurements into a single `evaluate` call** rather than climbing the tree across many calls.
- Before reaching for the browser, check whether the layout question is already answered by a recipe — e.g. full-width = `display:"flex"` + `flexDirection:"column"` + `alignItems:"stretch"`; a flex container needs an explicit `display:"flex"` or `flexDirection` is inert; date renders `&#x2F;` = use `{{{triple-brace}}}`. (v7 styling mechanics now live in `shesha-design-system/references/styling-v7-mechanics.md`.) Don't rediscover documented gotchas with a long browser loop.

Full recipes: [references/verification.md](references/verification.md).

**On any captured error or 4xx/5xx**: consult [references/debug.md](references/debug.md) before guessing — it maps common symptoms to causes. Quote the captured error verbatim; reference the matching row number.

## Step 9.5 — Aesthetic review (ask first; skip if `--no-design` or no Step 0 plan)

If a design plan exists for this form, **ask the user via `AskUserQuestion`** whether to run a post-render aesthetic critique:

> Run an aesthetic review on the rendered form via `frontend-design`? It compares the screenshot against the design plan and returns up to 5 prop-level tweaks.
> - **Yes — review and suggest tweaks**
> - **No — confirm and finish**

On Yes: pass screenshot + plan + original requirements to `frontend-design`. Surface findings as **suggestions, not blockers** — accept/reject per item; on accept, loop back to Step 5 → 8 → 9. Recipe: [references/design.md](references/design.md).

## Step 10 — Confirm

Tell the user: form `<module>/<name>` published as **Live v`<new versionNo>`** (prior Live retired). Authenticated forms render at `/dynamic/<module>/<form>`; anonymous at `/no-auth/<module>/<form>`. If a Draft was intentionally left unpublished, say so and give its id + status.

## Cache (`.claude/cache/shesha-form-edit/`)

Project-scoped learning state. **Skill reads `.summary.md` by default; opens raw `.raw.json` only when summary is insufficient.** Layout: `metadata/`, `seeds/`, `docs/`, `_archive/` — see `.claude/cache/shesha-form-edit/README.md`. Populate via `node .claude/skills/shesha-form-edit/scripts/summarize.js <input.json> [--out <out.summary.md>]`. TTLs: metadata 24h; seeds invalidate on `versionNo` change. `--refresh-cache` ignores TTL.

## Non-negotiables

- **A 0.43 form is a versioned ConfigurationItem — NEVER `UpdateMarkup`/`ImportJson` a Live version.** Editing Live = `CreateNewVersion` (clone Live→Draft) → write the **Draft** → publish Draft→Ready→Live (`UpdateStatus`, mandatory `filter`) → clear the cache. `CreateNewVersion` **once** per session; the verify/fix loop re-pushes the **same Draft**; abandon a Draft with `UpdateStatus status:4` (not `CancelVersion`, which needs Ready on this build). Every session ends with its Draft **Live or Cancelled**, never dangling. Full algorithm: [references/version-lifecycle.md](references/version-lifecycle.md).
- **"list" → `datalist`, "table"/"grid" → `datatable` — build the component the user's wording names.** A "list of X" (or "cards", "feed", "tiles", "gallery") is a `datalist` (card view) — never a datatable, and **never** stacked static `container` cards. A "table"/"grid"/"spreadsheet" is a `datatable` (column grid). Honor the explicit noun even when the other would also render the data; for multi-select-from-a-list use `selectionMode: "multiple"` on the `datalist` (not a switch to a datatable). When the prompt names neither and the shape is genuinely ambiguous, **ask** before building. Decision table + both seeds: [data-tables.md](references/components/data-tables.md).
- **Every `propertyName` is camelCase — including datatable column `propertyName`s.** Entity GQL field keys are camelCase, but `Metadata/GetProperties` returns the `path` in PascalCase. A PascalCase column still fetches data + shows the right row count, but renders **blank cells** (the cell accessor reads the literal key). Lower-case the first letter (`ActionedBy`→`actionedBy`). **Datalist row-template cards** also have their own runtime rules (name-mode bound text, `dimensions: fit-content`, single-line `ellipsis` for long text, status chip on its own row, padding/overflow via the legacy `style` prop, card `height:"auto"`) — see [data-tables.md](references/components/data-tables.md).
- **On 0.43 the data wrapper is `datatableContext` (v7), NOT `dataContext` (v8).** `dataContext` v8 is a 0.45+ component — a 0.43 backend's forms wrap `datatable`/`datalist` in a **`datatableContext`** (verified: it is the type carried by live 0.43 forms, e.g. a typical 0.43 application build). Author the wrapper as `{"type":"datatableContext","version":7, …}`. Everything below about explicit `entityType`+`sourceType`+fetching props applies unchanged — only the `type`/`version` differ. Where a bundled seed or reference says `dataContext`, substitute `datatableContext` v7 for 0.43 (and always grep the running app to confirm). It's the universal wrapper — renders display tables, multiselect tables, datalists, AND inline-editable tables, and reliably fires the entity data query.
- **The data wrapper requires explicit `entityType` + `sourceType`** — it does NOT inherit from `formSettings.modelType`. A bare wrapper without these props causes HTTP 500 on page load. Mandatory props: `entityType` (string — the resolved `fullClassName` of the same entity `formSettings.modelType` binds; `entityType` keeps the string form even though `modelType` is the `{ name, module }` object), `sourceType: "Entity"`, `dataFetchingMode: "paging"`, `defaultPageSize: 10`, `uniqueStateId: "<componentName>"`, `componentName: "<name>"`, `propertyName: "<name>"`. Template (**0.43 → `datatableContext` v7**):
  ```json
  {
    "type": "datatableContext",
    "version": 7,
    "entityType": "<resolved fullClassName string — same entity formSettings.modelType binds (modelType is the {name,module} object; this stays a string)>",
    "sourceType": "Entity",
    "dataFetchingMode": "paging",
    "defaultPageSize": 10,
    "uniqueStateId": "myTable",
    "componentName": "myTable",
    "propertyName": "myTable",
    "sortMode": "standard",
    "allowReordering": "no"
  }
  ```
- **`parentId` on every component** — set to the direct parent's `id`; root-level components get `"root"`. Use `stampTree` (see Step 5). Missing `parentId` or all-`root` parentIds crashes the Shesha renderer with no useful error.
- **`id` must be a real UUID** — use `crypto.randomUUID()` or `uuid.v4()`. Short placeholder IDs like `btn1`, `pr2` are NOT valid; the renderer ignores components with non-UUID ids, causing forms to render blank.
- **Every authored component carries its component-type's current `version`** (an integer). At render Shesha runs each component's settings-migration chain as `upgrade({ ...settings, version: settings.version ?? -1 })`. A component with **no `version`** is treated as `-1`, so the ENTIRE legacy migration chain re-runs on already-current data and a step can throw (`e.match is not a function`, `Cannot read properties of undefined (reading 'migrator')` / `(reading 'version')`). Copy components from a canonical seed that carries `version`, or stamp the current version. Versions are framework-version-specific — confirm against the running app's existing forms (grep a form dump). **For Shesha 0.43 (captured from 40 live forms on a running 0.43 backend) the current values are:** `checkbox` **4**, `checkboxGroup` **5**, `textField` **5**, `numberField` **4**, `dateField` **5**, `dropdown` **7**, `radio` **6**, `autocomplete` **6**, `refListStatus` **4**, `datalist` **8**, `datatable` **11**, `datatableContext` **7**, `datatableTotalRow` **1**, `text` **2**, `textArea` **4**, `tableViewSelector` **2**, `button` **7**, `buttonGroup` **15**, `alert` **2**, `container` **7**, `columns` **2**, `tabs` **5**, `sectionSeparator` **3**, `collapsiblePanel` **8**, `subForm` **3**, `childTable` **3**, `entityReference` **6**, `entityPicker` **9**, `validationErrors` **0**, `fileUpload` **5**, `attachmentsEditor` **7**, `image` **5**, `link` **4**, `statusTag` **2**, `richTextEditor` **3**, `htmlRender` **1**, `notes` **4**, `KeyInformationBar` **2**. (`card`/`progress` weren't present in the sample — grep the running app before authoring them.) **These are LOWER than the 0.45.x values — do not copy 0.45 versions onto a 0.43 form.** **A stale/too-low version doesn't only risk a migration throw — it can SILENTLY DROP the component's entire `desktop` style block** (style-lab verified: a `numberField` at v3 ignored its style block entirely; at v5 the same block applied). So copying versions from the running app is a *styling* prerequisite, not just a render one.
- **`defaultValue` is a mustache-TEMPLATE STRING, never a literal non-string.** At render the value resolver does `defaultValue.match(/{{key.accessor}}/)` to detect templates. A literal **array** (e.g. a multi-select default `["a","b"]`), **number**, or **object** has no `.match` → **`e.match is not a function`**, and the component (often the whole form) fails to render. Allowed: a plain string (returned as-is when not a `{{…}}` expression) or a mustache string. For a multi-select default (checkboxGroup / multi-`dropdown`), do NOT set a literal-array `defaultValue` — bind the value through form data / the data loader, or omit it.
- **Datatable inline-editing column editors (verified shape):** an inline-editable `data` column's `editComponent`/`createComponent` MUST be either `{ "type": "[not-editable]" }` (read-only cell) OR `{ "type": "<editorType>", "settings": { <FULL component model: its own `type` + `version` + `editMode:"inherited"` + `hideLabel:true` + styling> } }`. **NEVER `{ "type": "[default]" }`** (only `displayComponent` resolves `[default]`; edit/create cells pass it straight to the component wrapper → `F6()["[default]"]` is `undefined` → `reading 'migrator'`), and **NEVER a FLAT model without the `settings` wrapper** (the cell wrapper reads `customComponent.settings`; flat → `undefined` → `reading 'version'`). Per-row Edit/Delete/Save controls require a `{ "columnType": "crud-operations", "sortOrder": -1, "itemType": "item" }` column, plus `canEditInline`/`canAddInline`/`canDeleteInline: "yes"` on the datatable. Full recipe + seed: [inline-editable-tables.md](references/components/inline-editable-tables.md).
- **`checkboxGroup` hardcoded options use `items` (NOT `values`), each `{ label, value }`** — plus `version: 5`, `dataSourceType: "values"`, `referenceListId: null`, `container: {}`, `validate: {}`. (`dropdown`/`radio` use `values` with `{id,label,value}`; `checkboxGroup` is different — do not conflate.) See [dropdowns.md](references/components/dropdowns.md).
- **CRUD wiring follows the canonical examples (`references/examples.md`), not ad-hoc navigation:**
  - **Table "Add" button** = a `buttonGroup` item with `buttonAction: "dialogue"`, `actionConfiguration.actionName: "Show Dialog"` (owner `shesha.common`), `actionArguments.formId: { name: "<create-form>", module: "<module>" }`, `modalWidth: "60%"`, `formMode: "edit"`. It opens the create form in a **modal** — verified to render the create form's fields inline. Do NOT make Add a Navigate.
  - **Detail-view lifecycle buttons** = a header `buttonGroup`: Edit → `Start Edit`, Save → `Submit`, Cancel → `Cancel Edit` (all owner `shesha.form`); optional Audit Log → `Show Dialog` → `{ name: "entity-change-audit-log", module: "Shesha" }`. The form toggles edit state in place; there is no manual navigate-back Save.
  - **Standalone create/edit page Save + Back** = one `buttonGroup`: Save → `Submit`/`shesha.form` (primary), Back → `Navigate`/`shesha.common` (default). Copy `assets/examples/standalone-create.json` whole. **The Back button is mandatory even when the prompt mentions no buttons** (e.g. "a form with one required field") — a create form with no way out is incomplete.
  - **Toolbar Refresh / column-toggle** buttons use `actionName: "Refresh table"` / `"Toggle Columns Selector"` with `actionOwner` set to the **dataContext component's id**.
  - **Row → detail navigation** (only when a separate detail page is wanted): action column item with `columnType: "action"`, `action: "navigate"`, `targetUrl: "/dynamic/<module>/<form>?id={{selectedRow.id}}"`, `icon: "EditOutlined"`.
- **`actionArguments.target`** for plain Navigate actions: `{ actionName: "Navigate", actionOwner: "shesha.common", actionArguments: { target: "/dynamic/..." } }`.
- **Preserve ids** on existing components — fresh GUIDs only on clones / new nodes.
- **`editMode` is per form type — never blanket-stamp either value.** Detail forms with Start Edit/Submit lifecycle: `"inherited"` (explicit `"editable"` makes fields editable before Edit is clicked). Create/edit dialogs and action/anonymous pages: `"editable"` (`"inherited"` renders dead inputs there). Visual components: omit. Full decision table: [edit-mode.md](references/components/edit-mode.md).
- **Contextually-preset required FKs on create dialogs need BOTH a real component AND `formSettings.onPrepareSubmitData`** — `formArguments`/`setFieldsValue` alone never reach the submit payload (only `_formFields` serialize). Omission = `Crud/Create` 500. See [add-dialogs.md](references/components/add-dialogs.md).
- **Row delete/unlink = Execute Script + `await http.delete(...)` + onSuccess `Refresh table` with actionOwner = the dataContext component id.** `actionName: "Delete row"` with owner `"table"` does not exist and throws. See [junction-subtables.md](references/components/junction-subtables.md).
- **Code-mode props are objects** — a dataContext `endpoint` (or any code-carrying prop) stored as a plain JS string is silently stripped on save; use `{ "_mode": "code", "_code": "..." }`.
- **JSON-safe script strings** — ALL script values embedded in form JSON must be serialisable without breaking the outer `JSON.stringify`. Rules: (a) no template literals — use string concatenation instead of `` `${x}` ``; (b) no unescaped newlines — use `\n`; (c) no smart/curly quotes — use straight quotes; (d) validate every script-containing component with `node -e "JSON.stringify(comp)"` before push. A broken script string produces `"Expected ',' or '}' after property value"` parse errors in the browser.
- **No `globalState`** for cross-form state. Default to `contexts.appContext` (app-wide) or `pageContext` (inter-page). `localStorage` / `sessionStorage` are OK only when state must survive a hard refresh AND the data is not sensitive (no auth tokens / PII) — see [shared-state.md](references/components/shared-state.md).
- **API calls in scripts**: `try/catch` + `async/await` (no `.then()` chains) — see [scripts.md](references/components/scripts.md).
- **Mustache expressions always use `{{double braces}}`** — e.g. `{{data.id}}`, `{{selectedRow.id}}`. Never write `{data.id}` (single brace). Single-brace expressions are silently ignored at runtime, producing empty values with no error.
- **A domain change requires a backend rebuild + restart before the entity is usable** — follow [references/backend-restart.md](references/backend-restart.md). Order: domain change → restart → poll the entity's `…/Crud/GetAll` until 200 → then build the form. **Never relaunch IIS Express outside Visual Studio** (`hostingModel=InProcess` + `%LAUNCHER_PATH%` → 500.0 ANCM); headless = take over :21021 with `dotnet` (Kestrel), attended = hand the restart to VS. A **new** entity needs **two boots** (its dynamic CRUD controller registers a boot late). After any restart, re-verify your forms resolve by name (`GetByName`) and re-push if a live revision was orphaned.
- **`access: 5`** on anonymous forms (login, register, OTP). Verify post-push via re-fetch.
- **PowerShell + non-ASCII body**: pass UTF-8 bytes (em dashes / curly quotes trigger server 500 — `Unable to translate bytes [E2] ... from specified code page to Unicode`). Use `[System.Text.Encoding]::UTF8.GetBytes($jsonBody)` or `curl --data-binary @file`. And write staged JSON files **without a BOM** (`New-Object System.Text.UTF8Encoding $false`) — `Out-File -Encoding utf8` emits a BOM that breaks Node's `JSON.parse`. Recipe in [api.md](references/api.md).
- **Human-readable labels on every field** — labels are user-facing AND how browser-based tests locate fields; a raw `propertyName` as a label fails both. Full contract: [form-quality.md](references/form-quality.md).
- **`modelType` is the object `{ name, module }`, resolved, never assumed** — write `formSettings.modelType` as `{ "name": "<ShortClass>", "module": "<Module>" }` (e.g. `{ "name": "Person", "module": "Shesha" }`), the shape current Shesha builds emit. A bare full-class-name string still renders on legacy forms but is not the shape to author. Resolve `name`+`module` (and the `fullClassName` string the metadata fetch + `dataContext.entityType` need) from `EntityConfig/GetMainDataList` for the running backend (Step 4.5). Never hardcode a namespace from memory or from this doc's examples; `Shesha.Core.*` vs `Shesha.Domain.*` is version-dependent and a mismatch 500s at runtime.
- **Favour the default endpoints when binding a form to a type.** An entity-bound form (`formSettings.modelType` set) uses `dataLoaderType: "gql"` + `dataSubmitterType: "gql"` — the entity's standard dynamic CRUD/GraphQL endpoints, resolved from `modelType` with no URL supplied. Use `"none"` only for non-loading forms (card templates, anonymous/action pages). A **custom form-level loader/submitter endpoint is opt-in only** — wire one solely when the user explicitly asks for a specific endpoint (or in a documented forced case), and build/verify it via `shesha-developer-0-43:shesha-app-layer` first. Never reach for a custom endpoint by default. Detail + decision table: [form-shape.md](references/components/form-shape.md).
- **A `validationErrors` component is ALWAYS in the tree** (conventionally just above the action row) **whenever the form has any required input**. Omitting it makes a failed submit render nothing — the user sees a dead form. Type string is exactly `validationErrors`; it takes no props. This applies to simple forms too — it is not an "advanced" extra.
- **Form action buttons live in a `buttonGroup`, never as standalone `button` components — and the Save button MUST carry `actionConfiguration: { actionName: "Submit", actionOwner: "shesha.form" }`.** Save/Submit, Back/Cancel, Edit, Delete, Refresh, Add — every action goes in a single `buttonGroup` (`items[]` of `{ itemType: "item", itemSubType: "button", buttonType, buttonAction, actionConfiguration }`), not as loose top-level `button` nodes. This is the **single highest-leverage rule** — a standalone `button` (type `"button"`) or a Submit wired to anything other than `Submit`/`shesha.form` causes three problems at once: (1) the scattered button reads as ungrouped/inconsistent layout; (2) tooling that infers a form's *intent* from its `buttonGroup` item actions can misread an editable form as read-only when there's no proper `Submit`/`shesha.form` action to detect; and (3) the submit wiring never fires. The standalone `button` type in [actions.md](references/components/actions.md) is reserved for rare inline-in-content cases (e.g. a button beside a paragraph), never the form's action row. A **Back** button is a `buttonGroup` item with `actionName: "Navigate"` (owner `shesha.common`). Canonical structure: copy a `buttonGroup` from a seed in `assets/examples/`.
- **Minimal component count — add only what the request needs, but the Submit + exit pair is part of the floor, not an extra.** Every editable form is exactly: the requested input fields + a `validationErrors` + one `buttonGroup` holding **both Submit and an exit (Back/Close/Cancel) button** + the minimum structure to satisfy layout (one `columns`/`sectionSeparator` when >5 inputs). A terse prompt that names only fields ("a form with one required first-name field") still gets the Submit **and** the exit button — they are part of a working form, never "unnecessary extras", and a Submit with no exit is an incomplete form. What to avoid is padding the user didn't ask for: extra containers, decorative panels, headers, or duplicate wrappers, and (for tables) unrequested toolbar chrome. Seeds are a starting point: after copying, strip every node the current request doesn't use — but never the `validationErrors` or the Submit/exit pair.

## Required skill & agent invocations

| Trigger | Invoke | Strength |
|---|---|---|
| Entity/property/reflist missing or broken (Step 4.5 gate) | `shesha-developer-0-43:domain-model` | MUST before any form push |
| After a domain change (entity/property/reflist/migration created) | [backend-restart.md](references/backend-restart.md) runbook (rebuild + restart + 2-boot + poll CRUD) | MUST before building the form |
| New entity-bound form / unverified entity this session | `shesha-developer-0-43:fullstack-prereq-checker` agent | MUST (block until `ready`) |
| Form needs a custom (non-dynamic) endpoint for a Url-source or submit | `shesha-developer-0-43:shesha-app-layer` | MUST before wiring the endpoint |
| Every push (Step 6) | `shesha-developer-0-43:clean-form-config` | MUST (respect its documented false positives) |
| >3 forms changed (Step 6) | `shesha-developer-0-43:form-auditor` fan-out | MUST before pushing |
| Any bulk mutation | `shesha-developer-0-43:fleet-transformer` agent (exactly one) | MUST |
| 2+ distinct new forms | `shesha-developer-0-43:form-author` per form | SHOULD (parallel) |
| Any runtime error / failed smoke (Step 8.5/9) | `superpowers:systematic-debugging` | MUST before proposing fixes |
| Before claiming done (Step 10) | `superpowers:verification-before-completion` | MUST — evidence (re-fetch diff + smoke output) first |
| Multi-form plan execution | `superpowers:subagent-driven-development` / `dispatching-parallel-agents` | SHOULD |
| >10 forms or a restructure | `superpowers:writing-plans` first | SHOULD |
| Requirement mentions notifications / app settings | `shesha-developer-0-43:shesha-notifications` / `shesha-settings` | SHOULD |
| New endpoints exposed post-rollout | `shesha-utils:harden-permissions` | ASK the user |

(Skills via the Skill tool; agents via the Task tool. In headless runs, ASK-strength items are skipped, MUST items still run.)

## Doc fallback

When you hit an unfamiliar API / component / action, fetch docs first via `WebFetch` instead of guessing — `https://shesha-grads.vercel.app/docs/` for practical how-to ("how do I X"), `https://docs.shesha.io/` for canonical contracts ("what is the contract for X"). Quote field names and gotchas verbatim; cache distillates in `.claude/cache/shesha-form-edit/docs/<topic>.summary.md`. If the token expires (24h default), re-run Step 2.
