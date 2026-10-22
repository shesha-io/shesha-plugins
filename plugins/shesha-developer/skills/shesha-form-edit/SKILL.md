---
name: shesha-form-edit
description: Create and edit Shesha form configurations directly via the API. Authenticates as admin, fetches existing markup with Get/GetByName/GetJson, applies the user's requirements (adding, removing, modifying, or restructuring components — or building a brand-new form from scratch), validates against the bundled component-properties index and embedded-script rules, and pushes via Create / UpdateMarkup / ImportJson. Use when the user provides a form id (or module + name) and a set of requirements like "add a sector dropdown above the email field", "make the address tab conditional on AccountType=PBF", "wire the Save button to call /api/.../Submit", or "create a new branded login page using the auth-login pattern". Always prefer this skill over the Shesha MCP `create_form_configuration` tool — the MCP regularly fails with `'dict' object has no attribute 'lower'` and JSON-RPC `-32602` errors, and the direct-API path is more reliable.
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

Round-trip: **GET form JSON → edit → PUT/POST it back**. Also creates new forms (`Create` then `UpdateMarkup`).

> **For any new table / list / create / detail form, start from the canonical seeds in `assets/examples/` — see [references/examples.md](references/examples.md).** A "**table**"/grid request builds a `datatable`; a "**list**"/cards request builds a `datalist` — different components, pick from the user's wording ([data-tables.md](references/components/data-tables.md)). They are real Shesha-standard forms (verified rendering against a live backend) and encode the CRUD wiring most models get wrong: the **Add button opens the create form in a modal** (`Show Dialog`), detail views toggle edit in place (`Start Edit`/`Submit`), child tables use `tabs` + a `permanentFilter` on `{{data.id}}`, and inputs are chosen by the property's data type ([by-datatype.md](references/components/by-datatype.md)). Copy the matching example, swap entity/properties/captions/`formId`s, re-stamp `parentId`s, push. Don't hand-author structure the examples already provide.

> **Building a form to match a design?** If the requirements arrive as a **layout blueprint** (`<screen>.blueprint.md` from `shesha-developer:shesha-design-comprehension`, usually via the `shesha-claude-designer` orchestrator), treat that blueprint as the structure spec: its `Archetype` picks the seed, its `layout-tree` `flex=[…]`/nesting drive the **flex-container splits** (a `container` with `display:"flex"` + `flexDirection:"row"`, children sized via `desktop.dimensions.width` — **never the `columns` component**) + `parentId`s, and its `bindings` drive `propertyName`s. Build to it exactly — then expect a placement re-measure (the orchestrator's gate 5a.5) against the blueprint's `assertions`. See [references/blueprint-consumption.md](references/blueprint-consumption.md).

Args received: `$ARGUMENTS`. Flags: `--refresh-cache` (ignore TTL, re-distill metadata/seeds), `--no-browser` (skip Step 9 browser smoke).

## Non-interactive (headless) runs — read this first

When invoked non-interactively (`claude -p`, a test harness, CI) or when the task supplies a context block (Backend URL / Username / Password / Module / Working directory): **never call `AskUserQuestion` — it dead-ends the run.** Use the supplied context verbatim — it **overrides** Step 1 URL discovery, Step 2 default credentials, and the target module. Defaults for every ask-gate: Step 0 design ask → skip, author from seeds; Step 3 missing form identity → resolve from the task wording against the module's form list (`GetAll`), else create a new form named `{entity-kebab}-{type}` in the context module; push-failure menu → re-fetch & re-apply once, then stop and report; Step 9.5 → skip. **Always end with a summary naming every form created or modified (module + name + id)** — downstream evaluation identifies your work from that output.

## Step R — Scale the effort to the request (always first)

Match your process weight to the task, and **default down** when unsure:

- **A small edit** (one component / property / script / action on an existing form) → stay inline, do Steps 1–8 only, skip the design pass, and only do a browser check (Step 9) if the change is visual/behavioral. Keep it cheap — don't run the full pipeline for a one-line tweak.
- **One whole form** (table / list / create / details / dialog / subform) → inline, full Steps 0–10, seed-first from `assets/examples/`. ("table"/grid → `datatable`; "list"/cards → `datalist`.)
- **Backend prerequisites may be missing** (entity / property / reflist / API / menu item) → gate on Step 4.5 (or the `fullstack-prereq-checker` agent) and fix gaps via the owning sibling skill BEFORE writing form JSON.
- **Multiple linked pages, or a whole app from a brief** → don't build it all in one context: plan first, then build in waves (create → details → table, then cross-link), fanning out per [orchestration.md](references/orchestration.md). State the rough cost up front. See [orchestration.md](references/orchestration.md).

Also **route OUT non-form work** — a pure backend ask (reference list, role, notification, background job, API) goes straight to the sibling skill, not wrapped in form workflow.

**This skill does not AUTHOR style values — but the blocks it composes arrive pre-styled.** Structure + CRUD wiring is the job; *deciding* appearance (palette, type scale, spacing rhythm, surfaces, the brand theme) belongs to `shesha-developer:shesha-design-system`. Composing a block whose overlay is already baked in is not authoring — it is the supported path, and it is why forms come out on-brand without a second pass ([block-library.md](references/block-library.md)). What is banned is inventing hexes, fonts or spacing freehand in a form; that belongs in the block's overlay plus a re-bake. A structural build/edit never reads styling docs and never authors v7 appearance blocks. When the request is "make it look like X / match the design / style it / it looks bad / apply our brand", build/confirm the structure, then hand off: `Skill(shesha-developer:shesha-design-system)`. The ONE layout concern that stays here is **structural splits**, which are flex `container` rows (`display:"flex"` + `flexDirection:"row"`, children sized via `desktop.dimensions.width`) — **never the `columns` component** (firm project rule).

## Step 1 — Resolve backend URL

Order: **task-supplied context block (always wins)** → **`SHESHA_BACKEND_URL` environment variable** (sandboxed/ephemeral environments where the backend runs in a separate process or pod, not at `localhost`) → `src/*.Web.Host/Properties/launchSettings.json` (`profiles.Project.applicationUrl`) → `src/*.Web.Host/appsettings.json` (`Kestrel:Endpoints:Http:Url`) → fallback `http://localhost:21021`. Strip trailing slash. Store as `$BASE_URL`. Ping `$BASE_URL/swagger/index.html` to confirm reachability; if it fails, stop and tell the user to start the backend.

## Step 2 — Authenticate as admin

Task-supplied credentials win; local-dev defaults otherwise: **`admin` / `123qwe`** — don't ask. POST `$BASE_URL/api/TokenAuth/Authenticate` with `{ userNameOrEmailAddress, password }`; extract `result.accessToken` (or `accessToken` on older builds). See [references/api.md §2](references/api.md). If no token, surface raw response and stop.

**Module ID lookup** (needed for `Create`): `GET $BASE_URL/api/services/app/Module/GetAll` (note: `app` namespace — `Shesha/Module/GetAll` returns 404). Find the entry where `name === "<module>"` and take its `id`. Cache it for the session. If a subsequent `Create` call returns `"There is no entity Module with id = …"`, the backend was restarted and the ID changed — re-fetch via this endpoint.

## Step 3 — Identify the form

Required: form id **OR** (module + name). Ask the user only what's missing:

> Which form? Either give me the **id** (Guid), or **module + name** (e.g. `PBF.MembershipManagement` + `member-create`).

If module + name only, resolve via `GetByName` ([api.md §3](references/api.md)). Store as `$FORM_ID`.

## Step 4 — Fetch the current markup

`GET /api/services/Shesha/FormConfiguration/GetJson?id=$FORM_ID` ([api.md §4](references/api.md)). Save to `$RUN_DIR/staged/<form>.current.json`. The response body is a stringified form JSON; parse it. Resulting object has top-level `components` (nested tree) and `formSettings`.

## Step 4.5 — Entity introspection (mandatory for entity-bound forms)

Skip if `formSettings.dataLoaderType === "none"`. Otherwise fetch the entity's metadata and validate every `propertyName` in the edit.

**Get the exact entity type first (critical — wrong type causes 500 errors at runtime):**

`formSettings.modelType` must identify the **exact registered entity for THIS backend** — resolve it dynamically every time; never assume or copy a namespace from this doc. The same logical entity is registered under different namespaces across Shesha/BoxStack versions: framework entities like `Person` are `Shesha.Domain.Person` on current versions but `Shesha.Core.Person` on older ones, and a backend may even carry both. **The only authority is the live `EntityConfig` for the running backend** — its record gives you the `name`, `module`, and `fullClassName` you need below. Getting this wrong causes 500/404 errors in the browser when the loader or `dataContext` queries the entity — any mismatch with the registered entity is a runtime failure.

**Favour the object shape for `formSettings.modelType`:** `{ "name": "<ShortClass>", "module": "<Module>" }` (e.g. `{ "name": "Person", "module": "Shesha" }`) — the shape current Shesha builds emit. A full-class-name **string** still renders on legacy forms, but write new/edited forms with the object. **Independently, you always also need the resolved `fullClassName` string** — the metadata fetch below passes it as `?container=`, and component-level `entityType`s use either the short class+module or the full class string per their own rules (unchanged).

Resolve it (in priority order) — and use the result verbatim:
1. **From entity config (authoritative)**: `GET $BASE_URL/api/services/app/EntityConfig/GetMainDataList?maxResultCount=200` — find the entity by `name`, then take its **`name` + `module`** for the `modelType` object **and** its **`fullClassName`** (fall back to `className`) for the metadata `container` param. These are authoritative — use them verbatim.
2. **Cross-check against an existing form**: `GET $BASE_URL/api/services/Shesha/FormConfiguration/GetAll?maxResultCount=50` — a form bound to the same entity shows the in-use `modelType`. If existing forms disagree with each other (legacy `Shesha.Core.*` vs current `Shesha.Domain.*`), the EntityConfig `fullClassName` wins.

**Entity existence check**: before building any form, verify the entity exists: `GET $BASE_URL/api/services/app/Metadata/GetProperties?container=<exactModelType>`. If the response returns an empty array or error, the entity does not exist — stop and invoke `Skill(skill="shesha-developer:domain-model")`. Never build forms for entities that don't exist; they silently fail at runtime.

**If you (or `domain-model`) create or change an entity/property/reflist, the backend MUST be rebuilt and restarted before the entity is usable — follow [references/backend-restart.md](references/backend-restart.md).** Do this BEFORE building the form, and in this order: domain change → rebuild + restart (+ the 2-boot lag for new entities) → poll the entity's `…/api/dynamic/<module>/<Entity>/Crud/GetAll` until 200 → only then author/push the form. Never relaunch IIS Express outside Visual Studio (it 500s); headless runs take over :21021 with `dotnet`, attended runs hand the restart back to VS. This restart sequence is the biggest cost/failure sink when improvised — use the runbook.

1. Take the resolved `fullClassName` (the class-name string from the resolution above; `formSettings.modelType` itself is the `{ name, module }` object).
2. Fetch `GET $BASE_URL/api/services/app/Metadata/GetProperties?container=<fullClassName>` — `container` is the class-name **string**, never the object. Returns `result` as a direct array of properties (not wrapped). Cache to `.claude/cache/shesha-form-edit/metadata/<entity>.raw.json`.
3. **Validate `propertyName` against the property list** for every input component you're adding/editing. Surface mismatches before push.

Metadata semantics (`referenceListName` is the full dotted name used **without** any `RefList` prefix; `entityType` is the SHORT class name with `entityModule` separate; FK property names can differ from class names): [api.md §10](references/api.md). Array properties with `listConfiguration.mappingType: "many-to-many"` mean **junction subtables** — read [junction-subtables.md](references/components/junction-subtables.md) before touching those tabs.

TTL 24h; `--refresh-cache` forces re-fetch. If the metadata fetch returns nothing or surfaces a malformed entity, optionally invoke `Skill(skill="shesha-developer:test-entity-crud-api", args="--no-fix")` and fix entity bugs before continuing — a form bound to a broken entity will look fine in markup but fail at runtime.

**For a NEW entity-bound form, or any entity/junction not already verified this session: dispatch the `shesha-developer:fullstack-prereq-checker` agent** (Task tool; pass backend URL, token-file path, and the entity list) and block until its verdict is `ready` — its failures name the fixing skill per gap. Inline checks remain fine for small edits to an already-rendering form. Catalog of backend-rooted symptoms: [full-stack-prereqs.md](references/full-stack-prereqs.md).

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
| **Visual styling / appearance** (surfaces, shadows, layering, v7 style blocks, theme) | **do NOT read during a structural build — call `Skill(shesha-developer:shesha-design-system)`** |
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

**Touching more than ~3 forms?** Read [references/bulk-operations.md](references/bulk-operations.md) first — pilot-first is mandatory. Mutations go through **one `shesha-developer:fleet-transformer` agent** (never per-form authoring agents); audits fan out **one `shesha-developer:form-auditor` per form**. Dispatch templates + cost table: [references/orchestration.md](references/orchestration.md).

**Authoring 2+ genuinely distinct new forms?** Dispatch one `shesha-developer:form-author` agent per form in parallel (each gets the seed, metadata, requirements, and an output path); you audit and push centrally afterwards. A single new form stays in-context.

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

2. **Confirm each type exists** in the component index at `../clean-form-config/assets/groups/index.json` (bundled in this skill's assets folder). If a type is missing, you have the wrong name. The index is the authoritative source for the exact `type` string used in form JSON (e.g. `dataContext` for the table/list data wrapper; `datatable` not `dataTable`).

3. **Load the group file** for each component type (the index maps type → group file). Read the group file to get the full list of valid property names, their expected types, and descriptions. Only use properties listed there — anything else will be stripped by `clean-form-config` at Step 6.

3b. **When a prop's exact shape is disputed or non-obvious, check the source-derived KB** at `assets/components-kb/` — 121 components extracted from `shesha-reactjs` `releases/0.45` (provenance in `_meta.json`). Per component it gives `ownProps` (the props that genuinely exist on that component), `resolvedProps`, the current `version` integer, and the `initModel` defaults.

   **Read it lazily — never wholesale.** `_index.json` is 28 KB on its own and the folder is ~700 KB; grep for the type, then open only that one file:
   ```bash
   grep -A6 '"refListStatus"' assets/components-kb/_index.json   # → its file + version
   ```
   `_index.json` is also the authoritative source for each component's current `version` integer — prefer it over the hand-maintained 0.45.x list in Non-negotiables, which will drift.

   This is the tie-break for "which shape is real". Two parallel authoring agents once produced two different, mutually incompatible shapes for the same `refListStatus` prop, each reasoning from a doc example; the KB's `ownProps` (`referenceListId`, `showIcon`, `solidBackground`, `showReflistName` — no flat `module`/`referenceListName` keys at all) settles it immediately. Ranking when sources disagree: **a live form that already renders** > the KB > `../clean-form-config/assets/groups/` > a doc example. `_gaps.json` lists the components whose settings could not be extracted — if your type is in there, the KB has no opinion and you must fall back.

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

Walk tree (unique ids, valid types, valid parent chain); dead-prop check: look up each component's group in `../clean-form-config/assets/groups/index.json`, then validate its props against that group file; runtime-type checks (booleans not `"true"`, numbers not `"42"`); dropdown `values` shape (`{ id, label, value }`); `node --check` each script string. Then run the **[form-quality checklist](references/form-quality.md)** — validationErrors present, human-readable labels, dropdown sources complete, primary action visible, consistent layout.

**Migration-safety checks (mandatory — each of these silently passed review yet crashed the live form):**
- **Every component has an integer `version`.** A versionless component re-runs the whole legacy migration chain at render and can throw `e.match` / `reading 'migrator'` / `reading 'version'`. Flag any component object missing `version` (except pure layout slots).
- **No `defaultValue` that is a non-string** (array/number/object). `defaultValue` is resolved as a mustache template via `.match()`; a literal array → `e.match is not a function`. Flag and remove (or convert to a data binding).
- **Datatable `editComponent`/`createComponent` is `[not-editable]` or `{type, settings:{…}}`** — never `[default]` (→ `reading 'migrator'`), never a flat model missing the `settings` wrapper (→ `reading 'version'`). Flag either.
- **`checkboxGroup` hardcoded options live in `items` (not `values`)** with `version: 5`.

Then **invoke `clean-form-config` ONCE, right before the final push** (mandatory, blocking) — covers layout overflow, label-vs-propertyName refs, missing try/catch, missing async, broken script syntax:

```
Skill(skill="shesha-developer:clean-form-config", args="<path to your edited form>")
```

**Run it once on the finished markup — not after every intermediate edit** (re-running it per change is a large, repeated cost for no extra signal). **A dead-prop report is a real finding — investigate it, don't wave it through.** This line used to carry a "known false positives, don't re-investigate" list (`entityType`, `sourceType`, `dataFetchingMode`, `defaultPageSize`, `flexDirection`, the datatable inline props). Every one of them **is** enumerated in the index; the exemption was defending a defect that had already been fixed, while training readers to ignore the checker. Genuinely-missing props do exist — `alert.description` was absent from the index and being stripped from live forms — so the correct response to a dead-prop report is to check `assets/components-kb/<type>.json`'s `ownProps` and fix the index, not to add a new exemption.

If validation surfaces a REAL issue, fix it before pushing. **Never push a config that fails validation without user confirmation.**

**Before any bulk push (>3 forms changed): fan out `shesha-developer:form-auditor` agents — one per form** — with the verdict contract from [orchestration.md](references/orchestration.md); aggregate and never push a form with a `fail` verdict.

## Step 7 — Push

Default: **UpdateMarkup** — `PUT $BASE_URL/api/services/Shesha/FormConfiguration/UpdateMarkup`, body `{ "id": "$FORM_ID", "markup": "<stringified form JSON>" }`. Build the body in Node to avoid escaping pain. See [api.md §5](references/api.md).

**Scratch-script hygiene (avoids a recurring time-sink):** write build/push scripts and staged JSON into **`$RUN_DIR/staged/`** (the run directory — `.claude/shesha/runs/<slug>/`, created in `shesha-claude-designer` SKILL.md Step 0; when this skill runs standalone, create one the same way), NOT `/tmp` — git-bash `/tmp` maps to `%TEMP%` (e.g. `C:\Users\…\AppData\Local\Temp`), which is a *different* path than Windows `C:\tmp` and from PowerShell `$env:TEMP`, so a file written by `bash` is frequently "not found" by `node`/PowerShell. The same trap catches **native Windows Python**, which cannot open a git-bash `/c/...` path at all and reports a plain `FileNotFoundError` that looks exactly like a missing file — pass absolute Windows paths with forward slashes, or `cd` into the directory and use bare filenames. Pass values into Node via **env vars** (`VAR=x node script.js`), not positional argv that the shell may not forward. Prefer **one combined fetch→mutate→push script** over many small probe commands (each round-trip is cost).

Alternative: **ImportJson** — multipart upload (`ItemId` + `file`). See [api.md §6](references/api.md). Both write `Markup` on the form configuration.

Success: HTTP 200 with `{ "result": ... }`.

### On push failure (any non-200)

1. Surface the raw response and a short diagnosis.
2. Ask the user via `AskUserQuestion`: **retry as-is** / **re-fetch and re-apply** / **abort**.
3. Act on the choice. **Never silently retry. Never just stop.**

## Step 8 — Verify

Re-fetch via `GetByName`/`GetJson`; diff against what you sent. Surface any normalization the server applied. For anonymous forms (`access: 5`), confirm `result.access === 5` — the `Create` endpoint may not honor `access` on initial create; call `UpdateMarkup` once more if it didn't stick.

## Step 8.5 — Diagnose common runtime errors

After verifying, watch for these patterns in the browser console or from Playwright:

| Error | Cause | Fix |
|---|---|---|
| `HTTP 400` on dataContext data load | Entity doesn't have GQL query API enabled in backend | Invoke `shesha-developer:domain-model` to enable GQL on entity, or use `sourceType: "Url"` with an explicit REST endpoint |
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

Load the form in a browser, screenshot it, and capture console + network errors that JSON validation can't catch (editMode regressions, runtime script failures, broken layout). Recipe in [api.md §12](references/api.md).

**Use whichever browser MCP this session exposes** — `mcp__playwright__*`, `mcp__Claude_Browser__*` or `mcp__claude-in-chrome__*`. The steps are the same in all three: navigate → clear the IndexedDB form cache from `/favicon.ico` → reload → screenshot → read console + network. There is no playwright *skill*; this step used to invoke one by that name, which resolves to nothing and made the whole gate unrunnable. If no browser tool is available, skip and report "built but NOT visually verified" — never "done".

Frontend URL: `adminportal/` (auth forms) or `publicportal/` (anonymous) — read the dev port from `<app>/.env*` or `<app>/package.json`. If neither front-end is running, skip the smoke step and warn the user.

Test `*-details` forms via the **table row's view link**, never a pasted `?id=` URL — direct loads render but subtable Add/Create submits 500 (missing page context). If the browser disagrees with a verified API re-fetch, clear the **IndexedDB form cache from `/favicon.ico`** before debugging further.

**Verification cost discipline (this is where runs blow up — keep it tight):**
- Assert with the **a11y snapshot** + `getBoundingClientRect`/`getComputedStyle`, **not screenshots**. Reading a full-page screenshot is ~60 KB of tokens each — take **at most ONE screenshot, at the very end** for a final visual confirmation, never one per iteration.
- **Batch all DOM measurements into a single `evaluate` call** rather than climbing the tree across many calls.
- Before reaching for the browser, check whether the layout question is already answered by a recipe — e.g. full-width = `display:"flex"` + `flexDirection:"column"` + `alignItems:"stretch"`; a flex container needs an explicit `display:"flex"` or `flexDirection` is inert; date renders `&#x2F;` = use `{{{triple-brace}}}`. (v7 styling mechanics now live in `shesha-design-system/references/styling-v7-mechanics.md`.) Don't rediscover documented gotchas with a long browser loop.

Full recipes: [references/verification.md](references/verification.md).

**On any captured error or 4xx/5xx**: consult [references/debug.md](references/debug.md) before guessing — it maps common symptoms to causes. Quote the captured error verbatim; reference the matching row number.

## Step 10 — Confirm

Tell the user: form `$FORM_ID` updated. Authenticated forms render at `/dynamic/<module>/<form>`; anonymous at `/no-auth/<module>/<form>`.

## Cache (`.claude/cache/shesha-form-edit/`)

Project-scoped learning state. **Skill reads `.summary.md` by default; opens raw `.raw.json` only when summary is insufficient.** Layout: `metadata/`, `seeds/`, `docs/`, `_archive/` — see `.claude/cache/shesha-form-edit/README.md`. Populate via `node .claude/skills/shesha-form-edit/scripts/summarize.js <input.json> [--out <out.summary.md>]`. TTLs: metadata 24h; seeds invalidate on `versionNo` change. `--refresh-cache` ignores TTL.

## Non-negotiables

Rules that have no other home, or that are cheap to state and expensive to miss. **Everything else
lives in exactly one reference file** — the table below is the index, not a summary. This section
used to restate ~24 rules that already existed verbatim elsewhere; the copies drifted (four
independent component-version lists, three `editMode` rules, four `modelType` rules), which is the
whole reason for the split.

### Renderer-fatal — get these wrong and the form renders blank or throws

- **`parentId` on every component** — the direct parent's `id`; root-level components get `"root"`. Stamp with `stampTree` (Step 5). Missing or all-`root` parentIds crash the renderer with no useful error.
- **`id` unique, opaque and stable** — mint with `crypto.randomUUID()`. The failure is **short sequential placeholders** (`btn1`, `pr2`), not "non-UUID": nanoid and truncated-hex ids render fine ([verification.md §0](references/verification.md)).
- **Every component carries its integer `version`.** A versionless component is treated as `-1`, re-runs the entire legacy migration chain and can throw (`e.match is not a function`, `reading 'migrator'`). Worse, a **too-low version silently drops the component's whole `desktop` style block** — `numberField` at v3 ignored its styling; at v5 the same block applied. Numbers: [component-cheatsheet.md](references/component-cheatsheet.md), mirrored from `assets/components-kb/_index.json`. Never hand-maintain another list.
- **`defaultValue` is a mustache-template STRING**, never a literal array/number/object — [inputs.md](references/components/inputs.md).
- **Code-mode props are objects** — a `dataContext` `endpoint` (or any code-carrying prop) stored as a plain string is silently stripped on save; use `{ "_mode": "code", "_code": "…" }`.
- **Mustache always `{{double braces}}`** — `{data.id}` is silently ignored at runtime and yields an empty value with no error.
- **`dataContext` is the data wrapper for every `datatable`/`datalist`** — the universal wrapper, and it fires the entity query. It needs explicit `entityType` + `sourceType`; it does **not** inherit them from `formSettings.modelType`, and a bare one 500s on page load. Shape: [component-cheatsheet.md](references/component-cheatsheet.md); rules: [data-tables.md](references/components/data-tables.md).

### Structural

- **One page-shell card wraps every page-level form**, everything else inside its `content.components` — `hideHeading: true`, `className: "sha-page"`, no border on base and all three breakpoints. Compose [`assets/blocks/page-shell.block.json`](assets/blocks/page-shell.block.json). Dialogs and row templates are not pages. Spec: [containers.md](references/components/containers.md).
- **Splits are flex `container` rows, never `columns`** — [capability-matrix.md §flex-split](../shesha-design-system/references/capability-matrix.md#flex-split).
- **Preserve ids** on existing components; fresh ids only on clones and new nodes.
- **`access: 5`** on anonymous forms (login, register, OTP) — verify by re-fetch after push.
- **`actionArguments.target`** for plain Navigate: `{ actionName: "Navigate", actionOwner: "shesha.common", actionArguments: { target: "/dynamic/…" } }`.

### Fidelity

- **The app theme only reaches chrome.** A breakpoint block overrides theme defaults per key, so tuning the AntD theme and expecting a page to transform is the most reliably wasted hour here. Compose pre-styled blocks ([block-library.md](references/block-library.md)); a value a block lacks belongs in its overlay plus a re-bake, never typed into a form. Why: [app-theme.md](../shesha-design-system/references/app-theme.md).

### Everything else — one owner each, read on demand

| Rule | Owner |
|---|---|
| "list" → `datalist`, "table"/"grid" → `datatable`; row-template card runtime rules | [data-tables.md](references/components/data-tables.md) |
| camelCase every `propertyName`, incl. datatable columns | [form-quality.md](references/form-quality.md) |
| `editMode` per form type, incl. the read-only rail case | [edit-mode.md](references/components/edit-mode.md) |
| `modelType` = resolved `{ name, module }`; default gql endpoints | [form-shape.md](references/components/form-shape.md) |
| CRUD wiring — Add dialog, detail lifecycle, standalone Save+Back, toolbar, row→detail | [examples.md](references/examples.md) |
| Contextually-preset FKs need a real component **and** `onPrepareSubmitData` | [add-dialogs.md](references/components/add-dialogs.md) |
| Row delete/unlink = Execute Script + `http.delete` + `Refresh table` | [junction-subtables.md](references/components/junction-subtables.md) |
| Inline-editing column editors (`[not-editable]` / full `settings`, never `[default]`) | [inline-editable-tables.md](references/components/inline-editable-tables.md) |
| `checkboxGroup` uses `items`, not `values` | [dropdowns.md](references/components/dropdowns.md) |
| `validationErrors` always present; human-readable labels; buttonGroup + Submit/exit pair; minimal component count | [form-quality.md](references/form-quality.md) |
| JSON-safe script strings; `try/catch` + `async/await`, no `.then()` | [scripts.md](references/components/scripts.md) + Step 5.5 |
| No `globalState` — use `contexts.appContext` / `pageContext` | [shared-state.md](references/components/shared-state.md) |
| Backend rebuild + restart after a domain change (budget 2–3 boots) | [backend-restart.md](references/backend-restart.md) |
| PowerShell UTF-8 bytes + BOM-free staged files | [api.md](references/api.md) |

## Required skill & agent invocations

| Trigger | Invoke | Strength |
|---|---|---|
| Entity/property/reflist missing or broken (Step 4.5 gate) | `shesha-developer:domain-model` | MUST before any form push |
| After a domain change (entity/property/reflist/migration created) | [backend-restart.md](references/backend-restart.md) runbook (rebuild + restart + 2-boot + poll CRUD) | MUST before building the form |
| New entity-bound form / unverified entity this session | `shesha-developer:fullstack-prereq-checker` agent | MUST (block until `ready`) |
| Form needs a custom (non-dynamic) endpoint for a Url-source or submit | `shesha-developer:shesha-app-layer` | MUST before wiring the endpoint |
| Every push (Step 6) | `shesha-developer:clean-form-config` | MUST (respect its documented false positives) |
| >3 forms changed (Step 6) | `shesha-developer:form-auditor` fan-out | MUST before pushing |
| Any bulk mutation | `shesha-developer:fleet-transformer` agent (exactly one) | MUST |
| 2+ distinct new forms | `shesha-developer:form-author` per form | SHOULD (parallel) |
| After ANY `form-author` dispatch, before trusting its verdict | `node scripts/verify-artifact.mjs <outputPath> --backend <url> --token $RUN_DIR/access-token` | MUST — the file on disk is the evidence, not the agent's report ([orchestration.md](references/orchestration.md)) |
| Form renders and placement is settled, before reporting done | `shesha-developer:design-critic` agent | SHOULD — apply its ranked fixes or report the verdict verbatim; never overrule it silently |
| Any runtime error / failed smoke (Step 8.5/9) | Reproduce before theorising: capture the error verbatim, match it in [debug.md](references/debug.md), change one thing at a time | MUST before proposing fixes |
| Before claiming done (Step 10) | Evidence first — re-fetch diff + smoke output ([verification.md](references/verification.md)) | MUST |
| Multi-form plan execution | [orchestration.md](references/orchestration.md) fan-out playbook | SHOULD |
| Requirement mentions notifications / app settings | `shesha-developer:shesha-notifications` / `shesha-settings` | SHOULD |
| New endpoints exposed post-rollout | `shesha-developer-0-43:harden-permissions` | ASK the user |

(Skills via the Skill tool; agents via the Task tool. In headless runs, ASK-strength items are skipped, MUST items still run.)

**Every skill named above ships in this marketplace.** Four rows used to cite `superpowers:*` —
two of them **MUST** — and one cited harden-permissions under a shesha-utils namespace; neither plugin exists, so
those were hard blockers no agent could satisfy. `harden-permissions` lives in
`shesha-developer-0-43`. If you add a row for an external skill, declare the dependency in
`.claude-plugin/plugin.json` first, and never mark it MUST.

## Upgrade reconciliation

When many forms break the same way after a framework upgrade, or a branch authored for the old version has to land on forms that were already reconciled, do not hand-edit each form: use `shesha-upgrade-reconciler` (rule packs, pilot-first fleets, backups, a verification bar and a ledger-based report).

## Doc fallback

When you hit an unfamiliar API / component / action, fetch docs first via `WebFetch` instead of guessing — `https://shesha-grads.vercel.app/docs/` for practical how-to ("how do I X"), `https://docs.shesha.io/` for canonical contracts ("what is the contract for X"). Quote field names and gotchas verbatim; cache distillates in `.claude/cache/shesha-form-edit/docs/<topic>.summary.md`. If the token expires (24h default), re-run Step 2.
