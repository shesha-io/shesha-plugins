---
name: create-crud-form
description: Build canonical Shesha 0.46 CRUD forms (table / create / details / row-template mini-card / list-of-cards) by COPYING one of six sample-* seed markups (stored at the current 0.46 component versions) and swapping only the entity-specific bits. Use when the user asks for a "table", "list view", "details view", "create form", "edit form", "list of cards", "CRUD views" (any of the common shapes) — for one entity or many. Trimmed alternative to shesha-form-edit — this skill has ONLY the six canonical seeds and the rules that keep them working; no block library, no employee-*/rs-* alternates, no design-consultation branch. Route non-canonical shapes (dashboards, wizards, master-detail splits, junction subtables, inline-editable tables) to shesha-form-edit instead. Args accept the standard headless context block (Backend URL / Username / Password / Module / Working directory).
allowed-tools:
  - Bash
  - PowerShell
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - Skill
  - Task
---

# Shesha CRUD forms

**One rule: copy one of the six `sample-*` seeds, run the swap checklist, validate, push.** Do not hand-author these structures from a prose brief. Do not remix. Do not "improve" the seed.

The six seeds live at `assets/examples/`. Every non-audit visual + structural + wiring behaviour of a canonical CRUD form is encoded there. They were captured from a live, correctly-rendering backend and then upgraded to **Shesha 0.46** by applying the 0.46 component migrators, so every component is stored at its current version (table in [canonical-seeds.md](references/canonical-seeds.md)) and the portal does not re-run migrations when it loads them.

**What changed on 0.46 that you must not undo** (details in the references):

- Component `version`s are the KB's current ones (container 9, text 7, datatable 31 ...). Lower versions re-run migrations on every load and overwrite stored values. Never copy a version from memory; look it up in `../shesha-form-edit/assets/components-kb/_index.json`.
- Plain-string mustache is rooted at `data`: `{{data.firstName}}`, not `{{firstName}}` (this flipped from 0.43 / 0.45).
- Per-device components keep style under `desktop` and spacing as the object `desktop.stylingBoxJson`, not the `stylingBox` string. Visibility is `visible`, not `hidden`.
- Render-time scripts (`{ _mode: "code" }`) optional-chain every hop after the first; `editMode` scripts return `'editable' | 'readOnly' | 'disabled' | 'inherited'`.
- Forms are fetched with `ConfigurationItem/GetCurrent` (`FormConfiguration/GetByName` is 404) and pushed in place with `UpdateMarkup {id, markup, modelType}`: no Draft/Live, and `modelType` is overwritten by whatever you send ([references/api.md](references/api.md)).
- `ReferenceList/GetItems` is gone; bind reference lists from metadata and let the dropdown load them.
- A single-choice `checkboxGroup` is a `radio` on 0.46.

| The user asks for… | Copy this seed | See it | Full spec |
|---|---|---|---|
| a **table** / list / index / grid page for one entity (dense rows, sortable columns) | `sample-patient-table.json` | [screenshot](assets/screenshots/sample-patient-table.png) | [canonical-seeds.md](references/canonical-seeds.md#sample-patient-tablejson--table-archetype) |
| a **list of cards** / feed / repeating row-cards (avatar + primary + right cluster) — use instead of a table when each row is 2-3 rich visual elements, not tabular data | `sample-appointment-list.json` + `sample-appointment-list-subform.json` (PAIR, always both) | [screenshot](assets/screenshots/sample-appointment-list.png) · [row template](assets/screenshots/sample-appointment-list-subform.png) | [canonical-seeds.md](references/canonical-seeds.md#sample-appointment-list-pair--list-of-cards-archetype) |
| a **create** / edit form the table's Add button opens (in a modal) | `sample-patient-create.json` | [screenshot](assets/screenshots/sample-patient-create.png) | [canonical-seeds.md](references/canonical-seeds.md#sample-patient-createjson--create-archetype) |
| a **details** / record view (with tabs + child datatables) | `sample-patient-details.json` | screenshots: [overview](assets/screenshots/sample-patient-details-overview.png) · [appointments](assets/screenshots/sample-patient-details-appointments.png) · [prescriptions](assets/screenshots/sample-patient-details-prescriptions.png) · [lab-results](assets/screenshots/sample-patient-details-lab-results.png) | [canonical-seeds.md](references/canonical-seeds.md#sample-patient-detailsjson--details-archetype) |
| a **row-template mini-card** (avatar + name-link + subtitle) embedded in a table's primary column or a details hero | `sample-patient-subform.json` | *(rendered inline in the details hero + table primary column — see the screenshots above)* | [canonical-seeds.md](references/canonical-seeds.md#sample-patient-subformjson--mini-card-archetype) |

**Table vs list-of-cards.** Table = dense, scannable, sortable columns; row height ≈40px; user is comparing rows. List-of-cards = each row is a small visual unit (avatar + primary text-block + right-side cluster like date/status/action); row height ≈100-120px; user is picking one, not comparing. If the primary column would already need a row-template mini-card, the list-of-cards archetype is likely a better fit than a table with a mini-card column.

> **Before writing any JSON, Read the target archetype's screenshot(s).** 

## The flow — five steps

> **Order of operations: domain first, forms last.** If Step 2 finds the entity missing, create it and get the backend restarted (Step 2.3) *before* copying any seed — a form built against a not-yet-registered entity won't render.

### Step 1 — Auth + resolve context

- Backend URL: from the task's context block; otherwise `http://localhost:21021`.
- Credentials: from the task's context block; otherwise the local-dev default documented in [../shesha-form-edit/references/api.md](../shesha-form-edit/references/api.md). Never invent credentials - if authentication fails, stop and ask. No tenant header. Authenticate once and reuse the token (logins are rate limited).
- `POST /api/TokenAuth/Authenticate` with `{userNameOrEmailAddress, password}` → read `result.accessToken`. Use as `Authorization: Bearer …` on every subsequent call. Send `sha-frontend-application: default-app` on any config-scoped write.
- Module id: `GET /api/services/app/Module/GetAll` → find `items[].name === "<module>"` → store `id`. Cache for the session.

### Step 2 — Resolve the entity (mandatory before touching JSON)

For every entity you're binding:

1. `GET /api/services/app/EntityConfig/GetMainDataList?maxResultCount=500` — find `items[].className === "<Entity>"`. Take `name`, `module`, and `fullClassName` verbatim.
2. `GET /api/services/app/Metadata/GetProperties?container=<fullClassName>` — the property list you'll bind fields to. `path` is PascalCase in the response — **camelCase every `propertyName` when copying into markup** (`FirstName` → `firstName`; see [references/binding-rules.md](references/binding-rules.md)).
3. `GET /api/services/app/Entities/GetAll?entityType=<fullClassName>&maxResultCount=1` — must return HTTP 200 with a `result.totalCount`. **A 400 (or the entity missing from step 2.1's `GetMainDataList`) means its dynamic CRUD isn't registered — the domain doesn't exist or hasn't been rebuilt yet.** Don't build against a missing entity. Instead:
   - **Locate the real solution root first.** The supplied **Working directory** is often a scratch/output dir with no `.sln` in it. Before delegating, resolve the actual .NET solution root: if `<workingDir>` (or `<workingDir>/backend`) has no `*.sln`, search for the backend solution (`find <workingDir> ... -iname '*.Web.Host.csproj'`, then widen the search) and use *that* directory. domain-model builds and restarts from this path — a wrong one silently builds nothing.
   - **Create it — delegate ownership.** Invoke the **`domain-model` skill directly via the `Skill` tool, inline in *this* session** — do **not** spawn a separate sub-agent / `Task` for it (a sub-agent's background backend dies when the sub-agent ends, before you can use it). It creates the entity + migration **and** performs the mandatory rebuild + **restart-twice** via its own runbook. Pass the full context block, not blobs — Backend URL · Username · Password · **Module** · **Working directory** (the *resolved solution root* from the previous bullet — load-bearing) · the **entity name + property list / requirements** the user gave (the one thing domain-model can't derive) · the **required outcome**: "entity live — `/api/dynamic/<module>/<Entity>/Crud/GetAll` returns 200 after the restart; report back the final `{name, module, fullClassName}`." **Don't run the initial domain rebuild/restart yourself** — the runbook (not you) picks that restart path: self-host Kestrel when headless, prompt the developer to Stop▸Build▸Run twice when attended/Visual Studio, shesha-agent API when ephemeral.
   - **Then verify, don't restart.** When domain-model returns, poll `GET /api/dynamic/<module>/<Entity>/Crud/GetAll?maxResultCount=1` until 200. If it still 404s, that's the known 2-boot lag, not a failure — request **one** more delegated boot per [references/backend-restart.md](references/backend-restart.md) ("budget 2–3 boots"), then re-poll. Do not build a parallel restart loop or call `dotnet build`/`dotnet run`/kill the port.
   - **Make the backend persist — headless only.** In a headless run, domain-model launched the restarted backend as a *session-bound background task* — it dies the moment this skill's session exits, leaving nothing on `:21021` for a downstream grader/harness to read (no persisted form, no screenshot). **This is the one restart create-crud-form owns:** once CRUD is verified, relaunch the built backend **detached** so it outlives the session, then confirm swagger + `Crud/GetAll` return 200 against the detached process before finishing. Exact mechanism (Start-Process / scheduled-task fallback) in [references/backend-restart.md § Persist the backend](references/backend-restart.md#persist-the-backend-after-a-headless-restart). Skip this in attended/Visual-Studio mode (the developer owns the backend) and ephemeral mode (shesha-agent owns it).
   - **Re-resolve context.** A restart can change the module id — re-run step 1's `Module/GetAll` and steps 2.1–2.2 for the now-live entity before continuing.

Once `Crud/GetAll` returns 200, store `{name, module, fullClassName}` as `MODELTYPE`. `formSettings.modelType` is authored as the **object** `{ name, module }`. Any `dataContext.entityType` uses the same object.

### Step 3 — Copy the seed + run the swap checklist

Read the seed for your archetype from `assets/examples/`. Then, verbatim, for EVERY item in the checklist at [references/canonical-seeds.md § "The swap checklist"](references/canonical-seeds.md#the-swap-checklist):

- `formSettings.modelType` → `{name, module}` from Step 2
- Every `dataContext.entityType` → `{name, module}` of the entity that dataContext queries (parent for the root dc; child for a tab's dc)
- Every field's `propertyName` / `componentName` / `name` / `label` → real camelCase property + sentence-case label
- Every `formId` reference in `actionArguments` → your family's form names (`sample-patient-create` → `<yourentity>-create`, etc.)
- Every `text.content` mustache → `{{data.propertyName}}` on 0.46, NOT a bare `{{propertyName}}` (see [references/binding-rules.md](references/binding-rules.md))
- Every column `displayComponent` for a REAL type (`refListStatus`, `entityReference`, etc.) — wrapped in `settings` with `version` + `propertyName:"editor"` (see [references/canonical-seeds.md § settings-wrapper](references/canonical-seeds.md#the-settings-wrapper-rule-for-custom-display-cells))
- Every reference-list field (dropdown / `refListStatus` / radio) → `dataSourceType: "referenceList"` + `referenceListId: {module, name}` taken **verbatim from `Metadata/GetProperties`** (`referenceListModule` / `referenceListName`). **Never call a `ReferenceList/*` API to fetch or verify items, and never loop on one** — copy framework bindings like Gender (`{module:"Shesha", name:"Shesha.Core.Gender"}`) straight from the seed (see [references/binding-rules.md § Reference-list fields](references/binding-rules.md#reference-list-fields-bind-from-metadata-never-fetch))
- Every `tab.id === tab.key` (both a fresh 30-char random string per tab; all `tab.id` unique in a `tabs.tabs[]`)
- Every child-tab `dataContext.permanentFilter` uses JsonLogic + mustache-`evaluate` (NOT `_mode:"code"` — see [references/canonical-seeds.md § permanentFilter](references/canonical-seeds.md#child-tab-filtering--permanentfilter))
- Every `buttonGroup` has `isInline: true` (visible buttons, not a "..." collapsed dropdown)
- Every `version` stays at the seed's value (= the 0.46 KB value); any component you add gets its `version` and shape from `../shesha-form-edit/assets/components-kb/<type>.json`, never from memory
- Spacing on per-device components is `desktop.stylingBoxJson` (object); no `stylingBox`-only spacing, no `hidden` (use `visible`)
- Every render-time `_code` optional-chains every hop after the first
- Every input on a **create form** has `editMode: "editable"` — inherited is only for details forms in view-mode
- Re-stamp every `id` (fresh UUIDs) and `parentId` (points at the direct parent's id) via a `stampTree` pass
- Card `content.components` field-holding containers use `desktop.display: "grid"` + `gridColumnsCount: 2` + `justifyContent: "normal"` (or 3 for medical rows) — do NOT decompose into horizontal-flex rows
- Every layout container matches the byte-exact recipe for its role — `pageShell` grey/padding-20, `whiteCard.*` white/soft-shadow, `rowCard` grid-2/soft-shadow, `cardContentGrid` grid-2-or-3, `flex-spaceBetween-row` flex-row. See [canonical-seeds.md § layout-canon](references/canonical-seeds.md#layout-canon)
- `datalist` host always references its row template by `formSelectionMode: "name"` + `formId: {name, module}` (both keys) — never inlines the row template

Full checklist + failure modes: [references/canonical-seeds.md](references/canonical-seeds.md).

### Step 4 — Validate (BLOCKING, before every push)

Run the pre-push validator against your staged markup:

```bash
node scripts/validate-form-markup.cjs <path-to-markup.json>
```

Exit code 0 → OK to push. Exit code 1 → fix the printed BLOCK-PUSH violations and re-run. **Do not push a form the validator blocks.** The rules (R1-R19) encode every "silent-drop-on-render" / "React-key-collision" / "component-crash" / "wrong-shadow" / "wrong-padding" defect observed on live builds — R1-R11 are behavioural (block or warn); R12-R16 are the styling canon (datalist wiring, grid-vs-flex distribution, soft-shadow byte-exactness, pageShell padding in `stylingBoxJson`, deprecated `columns` warn); R17-R19 are the 0.46 gates: component versions vs the KB (blocks lower), the clean-form-config scanner (script syntax and `ReferenceList/GetItems` block; unsafe render-time chains, htmlRender carrier hazards, legacy `stylingBox` spacing, dead props warn), and `refListStatus` inside a `subForm` (framework bug, blocks). Each maps to a documented rule in `references/`.

Optionally run `node ../clean-form-config/scripts/scan-046.mjs <markup.json>` for the full report (it is also what `shesha-form-edit` runs right before its own push).

### Step 5 — Push

- If the form doesn't exist yet: `POST /api/services/Shesha/FormConfiguration/Create` with `{moduleId, name, label, description, modelType}` (`modelType` = the entity's `fullClassName` from Step 2) → capture `result.id`.
- Push markup: `PUT /api/services/Shesha/FormConfiguration/UpdateMarkup` with `{id, markup: JSON.stringify(<markup>), modelType}`. **`UpdateMarkup` overwrites `ModelType` with what you send (null if omitted)** - always send it (the value you created the form with or read back). Also pass `access: 5` on anonymous pages (login, register). There is no Draft/Live step on 0.46: the form is edited in place.
- Re-fetch with `GET /api/services/app/ConfigurationItem/GetCurrent?itemType=form&module=&name=` (**`FormConfiguration/GetByName` is 404 on 0.46**) and compare markup + `configuration.modelType` with what you sent. An HTTP 200 / success toast is not evidence of persistence. After a Step 2.3 restart re-fetch too; if the form is missing or stale, re-push. See [references/api.md](references/api.md) and [references/backend-restart.md](references/backend-restart.md).
- The portal caches forms in the browser (IndexedDB `form:default-app`, `form_lookup:default-app`): clear them (or use a fresh profile) before judging the render.
- Report the form's module + name + id.

### Optional — Browser smoke

Launch a headless browser, log in, navigate to `/dynamic/<module>/<form-name>`, screenshot, capture console + page errors. Take ONE screenshot at the end (not per iteration). A one-liner using Playwright is enough — see [references/functional-requirements.md § smoke](references/functional-requirements.md#optional--browser-smoke-recipe).

## The six hard rules — these are what break forms

If nothing else, get these right on every push. Each is enforced by the validator (rule number in brackets).

1. **[R3] `displayComponent`/`editComponent`/`createComponent` with a real type MUST wrap it in `settings`** — flat `{ type: "refListStatus" }` crashes with `reading 'version'`. See [references/canonical-seeds.md § settings-wrapper](references/canonical-seeds.md#the-settings-wrapper-rule-for-custom-display-cells).
2. **[R2, R11] Plain-string mustache in `text.content`, `link.href`, action `target` is rooted: `{{data.name}}`, NOT a bare `{{name}}`** (0.46; it was the reverse on 0.43 / 0.45) — a bare one silently renders empty. `refListStatus.propertyName` is a bare property path with no braces. See [references/binding-rules.md § mustache](references/binding-rules.md#mustache-in-plain-string-bindings).
3. **[R4] Every tab has `tab.key === tab.id`, both unique** — React key collision if `tab.id` is duplicated across sibling tabs → BOTH tab bodies render on the visible tab. See [references/canonical-seeds.md § tab identity](references/canonical-seeds.md#tab-identity).
4. **[R8] Every `buttonGroup` has `isInline: true`** — otherwise buttons collapse into a "..." dropdown menu. Documented in [references/functional-requirements.md § buttonGroup](references/functional-requirements.md#buttongroup---always-isinline-true).
5. **[R9] Create-form inputs use `editMode: "editable"`** — `inherited` renders dead labels with no input boxes on a standalone create page. See [references/binding-rules.md § editMode-by-form-type](references/binding-rules.md#editmode-by-form-type).

6. **[R17] Component `version` = the 0.46 KB version** - a lower version makes the portal re-run migrations on every load (a `datatable` below v31 forces zebra rows / hover highlight over your stored values).

Everything else is style + polish. These six are correctness.

## Multi-form runs

For 2+ distinct new forms (typical CRUD triad: list + create + details), author sequentially in one context — the seeds are small enough that copying + swapping all three inline is faster than dispatching agents. Push each after its own validator pass.

For >5 near-identical forms across a fleet, escalate to `shesha-developer:shesha-form-edit`'s bulk-operations flow.

## Reference index

| Concern | File |
|---|---|
| Missing entity → create it + get the backend restarted before building (delegate to domain-model; 2-boot lag; headless Kestrel vs prompt-in-VS vs shesha-agent) | [references/backend-restart.md](references/backend-restart.md) |
| What each of the six seeds guarantees, byte-exact rules, layout canon, swap checklist | [references/canonical-seeds.md](references/canonical-seeds.md) |
| Action-configuration verbatim JSON (Show Dialog / Refresh table / Submit / Start Edit / Cancel Edit / Navigate) | [references/action-configurations.md](references/action-configurations.md) |
| Property binding, rooted mustache (`{{data.x}}`), editMode, camelCase, reference lists | [references/binding-rules.md](references/binding-rules.md) |
| 0.46 form API recipes (GetCurrent fetch, UpdateMarkup + modelType, Create, round-trip verify, errors) | [references/api.md](references/api.md) |
| Modal Add pattern + `onSuccess: Refresh table` wiring | [references/add-dialogs.md](references/add-dialogs.md) |
| What a "complete" form has (validationErrors, Save+Back, isInline, page-header, 3-layer sandwich) | [references/functional-requirements.md](references/functional-requirements.md) |
| The nineteen pre-push validator rules + how to invoke | [scripts/validate-form-markup.cjs](scripts/validate-form-markup.cjs) |
| Full 0.46 scan (dead props, render-time chains, htmlRender, deprecated types) | [../clean-form-config/scripts/scan-046.mjs](../clean-form-config/scripts/scan-046.mjs) |
| Current component versions and shapes | [../shesha-form-edit/assets/components-kb/_index.json](../shesha-form-edit/assets/components-kb/_index.json) |
