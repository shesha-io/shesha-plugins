---
name: shesha-forms
description: Create and edit Shesha form configurations directly via the API. Authenticates as admin, fetches existing markup with Get/GetByName/GetJson, applies the user's requirements (adding, removing, modifying, or restructuring components — or building a brand-new form from scratch), validates against the bundled component-properties index and embedded-script rules, and pushes via Create / UpdateMarkup / ImportJson. Use when the user provides a form id (or module + name) and a set of requirements like "add a sector dropdown above the email field", "make the address tab conditional on AccountType=PBF", "wire the Save button to call /api/.../Submit", or "create a new branded login page using the auth-login pattern".
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
---

# Shesha Form Edit

Round-trip workflow: **GET form JSON → edit → PUT/POST it back**. The user supplies requirements; this skill handles auth, fetch, edit, validate, and push.

Also handles **creating new forms** — `POST /Create` for the FormConfiguration record, `PUT /UpdateMarkup` to set the body. When the user wants a brand-new form, prefer copying the JSON of an existing form with similar layout (e.g. an auth page, an entity-bound details form, a datalist host) and modifying only the parts that differ — designer-output JSON has many style fields that are tedious and error-prone to author from scratch.

Arguments received: `$ARGUMENTS`

---

## Operating principles — read first, then follow the 9 steps below

This is an **API-driven workflow.** All discovery — modules, entities, forms, reference lists, properties, sample data — happens via the Shesha backend HTTP API documented in [api.md](reference/api.md), [model-configurations.md](reference/model-configurations.md), [semantic-search.md](reference/semantic-search.md), [form-test-url.md](reference/form-test-url.md), [templates.md](reference/templates.md), and [template-placeholders.md](reference/template-placeholders.md).

**Do NOT:**

- Grep the codebase for entity / module / form / property names. The names you need come from `EntityConfig/GetMainDataList`, `Module/GetAll`, `FormConfiguration/GetAll`, `ReferenceList/Crud/GetAll`, `ModelConfigurations/{id}`.
- Read C# entity classes, DTOs, `.csproj` files, or `obj/Debug/EndpointInfo/*.json` swagger artefacts to infer metadata. They are not the source of truth and are often stale.
- `ls` / `Glob` / explore directory trees to "find what's available." The API list endpoints are the canonical inventory.
- Search the project for `launchSettings.json` or `appsettings.json` outside the **single targeted lookup** in Step 1 below.

**Do:**

- Read this skill's own `reference/*.md` files when you need a recipe.
- Read `reference/assets/component-properties.json` (Step 5) for the allowed-keys index.
- Write working files to `$env:TEMP` / `/tmp` for the duration of one invocation.
- **Ask the user** when a value can't be resolved through the workflow — never go on a filesystem adventure to fill the gap.

The 9 steps below are the workflow. Stay inside them.

---

## Step 1 — Resolve the backend URL

Use **one targeted Glob** to find the Shesha `*.Web.Host` project in the current workspace, then read its config. **Do not list directories or grep folders.**

```
Glob: src/*.Web.Host/Properties/launchSettings.json
```

Then check, in order, stopping at the first match:

1. The matched `launchSettings.json` → `profiles.Project.applicationUrl`.
2. Same project's `appsettings.json` → `Kestrel:Endpoints:Http:Url` if present.
3. Fall back to `http://localhost:21021`.

If the Glob returns zero matches, **skip filesystem entirely** and use the `localhost:21021` fallback. Don't search wider.

Strip any trailing slash. Store as `$BASE_URL`.

Quick reachability ping (PowerShell) — if it fails, stop and tell the user to start the backend:

```powershell
try { Invoke-WebRequest -Uri "$BASE_URL/swagger/index.html" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop | Out-Null; "Backend up" } catch { "Backend NOT reachable at $BASE_URL" }
```

---

## Step 2 — Authenticate as admin

Default credentials for this project: **`admin` / `123qwe`**. Don't ask the user — these are local-dev defaults; if auth fails, re-prompt.

```bash
curl -s -X POST "$BASE_URL/api/TokenAuth/Authenticate" \
  -H "Content-Type: application/json" \
  -d '{"userNameOrEmailAddress":"admin","password":"123qwe"}'
```

Extract `result.accessToken` from the response. Store as `$ACCESS_TOKEN`. (Older Shesha builds return the token at the root; check both `.result.accessToken` and `.accessToken`.)

If the call returns no token, surface the raw response and stop.

> **Detailed recipes (auth, fetch, push) live in [api.md](reference/api.md). Reference it inline whenever you build a curl command — don't reconstruct from memory.**

---

## Step 3 — Branch: edit existing vs create new

The user's request usually makes the path obvious — "add a field to `member-create`" is **edit**; "build a login page", "create a new … form", or naming a form that doesn't yet exist is **create**. If ambiguous, ask:

> Are we **editing an existing** form, or **creating a new** one?

### Step 3a — Edit branch

Required: form id **OR** (module + name).

> Which form are you editing? Either give me the form **id** (Guid), or **module + name** (e.g. `PBF.MembershipManagement` + `member-create`).

If only module + name are given, resolve to id via `GetByName` ([api.md §3](reference/api.md)). Store as `$FORM_ID`. Continue to Step 4.

If `GetByName` returns `null`, the user probably paraphrased the name or got the module wrong — **don't** bounce back to them immediately. Run the form-search recipe in [semantic-search.md](reference/semantic-search.md): HIGH-confidence match → use it directly; MEDIUM → present the shortlist; LOW / NO_MATCH → only then ask the user to clarify.

### Step 3b — Create branch

Required: **module name** + **form name**. Optional: `label`, `modelType`, anonymous-access flag, seed strategy.

> Which module should this form live in (e.g. `PBF.MembershipManagement`), and what should the form be called? Should it bind to an entity (`modelType`)? Should it be reachable without login?

1. **Resolve `moduleId`** — `Create` won't accept a module name. `GET /api/services/app/Module/GetAll` with bearer token, pick by `name`, capture the Guid. See [api.md §7](reference/api.md). If the user gave a fuzzy / paraphrased / typo'd module name and no exact match exists, run the module-search recipe in [semantic-search.md](reference/semantic-search.md) before asking them to be exact.
2. **Resolve `modelType` (if entity-bound)** — when the form should bind to an entity, follow [model-configurations.md](reference/model-configurations.md) to (a) resolve the entity (fuzzy name → [semantic-search.md](reference/semantic-search.md) first) and (b) fetch its full property list. Two outputs:
   - `<namespace>.<className>` — goes on the Create payload's `modelType` field **and** on `formSettings.modelType` inside the markup.
   - Property list filtered by `isFrameworkRelated: false` AND `suppress: false` — **mandatory** input to Step 6 for populating the form, regardless of seed strategy:
     - **Blank seed** — build one component per property (mapped via the `dataType → component` table in [model-configurations.md](reference/model-configurations.md)).
     - **Template / inline-markup seed** — walk every bindable input in the copied/assembled markup and rebind its `propertyName` to a real entity property. **Never leave placeholder `propertyName` values on an entity-bound form.** See the "mandatory entity binding" rule in Step 6.
3. **Pick a seed strategy.** Two flows resolve the strategy:
   - **User explicitly named a template** (e.g. "based on the details-view template") → seed = template. Resolve the name via `GetByName` (fuzzy → [semantic-search.md](reference/semantic-search.md)); capture its id as `templateId`. Respect the user's choice even if intent inference would pick differently.
   - **User described intent without naming a template** → consult [templates.md](reference/templates.md). Two templates are first-class — `Shesha/details-view` (view/edit one record) and `Shesha/table-view` (browse a collection). The decision table maps natural-language intent to template; anything that doesn't match → blank.
   
   Final seed will be one of:
   - **Template** (`templateId` on Create) — Shesha copies the template's markup. After Create, fetch the copy (Step 4) and substitute placeholder slots (Step 6, see [template-placeholders.md](reference/template-placeholders.md)).
   - **Inline markup** (`markup` on Create) — you've assembled the tree locally before submitting. Pass the stringified form JSON.
   - **Blank** (omit both) — empty record; you push the body via `UpdateMarkup` in Step 8. Use the property list from point 2 (if entity-bound) to seed sensible default fields.
4. **`POST /Create`** with `{ moduleId, name, label?, description?, modelType?, templateId?, markup? }` — see [api.md §7](reference/api.md). Capture `result.id` from the response. Store as `$FORM_ID`.
5. **Uniqueness errors** — `name` is unique within the module. If Create returns a duplicate-name error, re-prompt the user for a different name (or switch to the edit path).
6. **Anonymous-access forms** (`/no-auth/<module>/<form>` — login, register, OTP): `Create` may not honour `access` on initial create. Plan a follow-up `UpdateMarkup` with `access: 5` in Step 8 — see Notes & gotchas. Not optional.

After Step 3b: **template seed** → continue to Step 4 to pull the copied markup. **Inline-markup seed** → you already have the tree; skip Step 4 and go to Step 7 (validate). **Blank seed** → skip Step 4; build the markup in Step 6 (use the property list from 3b.2 if entity-bound), validate in Step 7, push in Step 8.

---

## Step 4 — Fetch the current markup

Skip if you arrived from Step 3b with the blank or inline-markup seed — you already have (or are about to build) the tree locally.

Follow [api.md §4](reference/api.md) — `GET /api/services/Shesha/FormConfiguration/GetJson?id=$FORM_ID` with bearer token. Save the response body to `/tmp/form-current.json` (or a local temp dir on Windows: `$env:TEMP\form-current.json`).

The body is a **stringified** form JSON. Parse it: the resulting object has top-level `components` (array, nested tree) and `formSettings` (object). If you receive an envelope like `{ "result": { "markup": "..." } }`, parse `result.markup` as JSON.

---

## Step 5 — Load the component properties index

Read `reference/assets/component-properties.json` from this skill's folder. Structure:

- `_meta` — version + count, skip.
- `base.props` — keys valid on **every** component.
- `base.types` — expected types for base props (when known).
- `_formSettings.props` / `_formSettings.types` — keys/types valid on the `formSettings` object.
- Per-type entries (e.g. `textField`, `dropdown`, `container`) — `{ props: [...], types: {...} }`.

When editing or adding a component:

```
allowedKeys = new Set([...base.props, ...(index[component.type]?.props ?? [])])
typeMap     = { ...base.types, ...(index[component.type]?.types ?? {}) }
```

Use this to verify every key you write is real and every value's type matches. Skip type-checking for keys absent from `typeMap` (ambiguous types) and for `IPropertySetting` wrappers in `_mode: 'code'`.

---

## Step 6 — Apply the user's requirements

The most common edits and how to do them are in [components.md](reference/components.md). Read the section that matches the user's request (it's <600 lines, fast to scan).

**If you arrived from Step 3b with a template seed**, the copied markup almost certainly contains placeholder slots with the syntax `//*NAME*//` in `propertyName` / `componentName` fields (e.g. `//*TITLE*//`, `//*DETAILSPANEL*//`, `//*TABLECOLUMNS*//`). These are sentinels — the form **is not functional** until they're replaced. Follow [template-placeholders.md](reference/template-placeholders.md) to substitute every placeholder **first**, drawing content from the entity property list (Step 3b.2). Re-scan for `//*` after substitution and don't proceed if any remain. Only then apply user-requested customizations and the rebinding rule below.

Core principles when modifying the JSON tree:

- **Preserve every component's `id`** — never regenerate ids on existing components, or stable references in JS scripts will break. New components get a fresh GUID.
- **Preserve `parentId`** on every component except the moved one — when re-parenting, update only the moved node's `parentId` and add it to the new parent's `components` array.
- Do not touch `formSettings` unless the user asked for a form-level change.
- Property values can be plain (`"Save"`, `42`, `true`) or `IPropertySetting` wrappers `{ "_mode": "value", "_value": ... }` / `{ "_mode": "code", "_code": "..." }`. The wrapper form lets the property be JS-evaluated. Keep wrappers when present; only convert if the user is asking for runtime behaviour.
- Embedded scripts (`onChangeCustom`, `onClickCustom`, `customVisibility`, `customEnabled`, etc.) must be valid JS. The available globals inside scripts include `data`, `formData`, `formMode`, `globalState`, `setFormData`, `application`, `http`, `message`, `moment`, and the standard browser globals. See [components.md §"Script context"](reference/components.md#script-context).
- API calls inside scripts **must** be wrapped in `try/catch` and async contexts must use `async`/`await` (no `.then()` chaining). The `clean-form-config` skill enforces this — invoke it after your edits if any scripts changed.
- **Property references against the bound entity** — when the user says "bind the email field to `EmailAddress1`" or scripts reference `formData.X`, verify the property exists on the entity at `formSettings.modelType` via [model-configurations.md](reference/model-configurations.md). If the user named the property fuzzily, fall back to [semantic-search.md](reference/semantic-search.md) against the property list before assuming a typo.
- **Mandatory entity binding for entity-bound forms** — when `formSettings.modelType` is set, every bindable input component (`textField`, `textArea`, `numberField`, `dateField`, `dropdown`, `radio`, `checkbox`, `switch`, `autocomplete`, `entityPicker`) **must** have a `propertyName` matching a real property from the entity's property list (filtered per Step 3b.2). This applies to **all components** in the markup, including those inherited from a template seed — never leave placeholder bindings (`propertyName: ""` or generic placeholders). Rebinding strategy when components arrive without valid bindings (typical for template seeds):
  1. **Label match** — exact case-insensitive match on the component's `label` against each property's `label` or `name` (e.g. component label `"First Name"` → property `FirstName`).
  2. **Semantic-search fallback** — if no exact label match, run [semantic-search.md](reference/semantic-search.md) on the property list with the component's label as the query; use HIGH-confidence hits directly, present MEDIUM as a shortlist.
  3. **Ask the user** — if still ambiguous (e.g. multiple text fields with generic labels like "Field 1"), surface the candidates from the property list and let the user assign.
  4. **Drop unmatchable** — if a template component clearly has no equivalent property (e.g. a `Submit` button, a layout-only `text`), leave it alone; the rule applies only to *bindable inputs*.
  
  For dropdowns / radio / checkboxGroup bound to a `reference-list-item` property, also copy `referenceListName` + `referenceListModule` from the property's metadata onto the component and set `dataSourceType: "referenceList"`. See the next bullet.
- **Reference-list bindings** — for `dropdown` / `radio` / `checkboxGroup` with `dataSourceType: "referenceList"`, both `referenceListName` and `referenceListModule` must match a real reference list. Fuzzy / paraphrased names → [semantic-search.md](reference/semantic-search.md) (resource type: reference list).
- **Fuzzy form / entity / module / reflist names anywhere** — any time the user names a resource and an exact lookup fails, default to [semantic-search.md](reference/semantic-search.md) before asking them to clarify. HIGH-confidence → use it; MEDIUM → present the shortlist; LOW → ask.

---

## Step 7 — Validate

Before pushing, run these sanity checks against the modified tree:

1. **Walk the tree** — every component has a unique `id` (Guid string), a `type` (string in the index OR clearly marked custom), and a valid parent chain.
2. **Dead props** — for each component, every non-underscore key must be in `allowedKeys` for that type. Drop or fix any that aren't.
3. **Type checks** — for keys present in `typeMap`, the value's runtime type must match (booleans not `"true"`, numbers not `"42"`).
4. **Dropdown values shape** — for `dropdown`/`radio`/`checkboxGroup`, when `dataSourceType === 'values'`, each item in `values` is `{ id, label, value }` — see [components.md §Dropdowns](reference/components.md#dropdowns).
5. **Scripts** — quick parse with `node --check` on each script string (write to `/tmp/check.js`, run, capture stderr). If any script fails to parse, surface the error and stop.

If anything fails, present the issues to the user before pushing. **Never push a config that fails validation without user confirmation.**

For deeper validation (layout overflow, label-vs-propertyName references, missing try/catch, missing async), invoke the bundled `clean-form-config` skill — it's purpose-built for this:

```
Skill(skill="shesha-developer:clean-form-config", args="<path to your edited form>")
```

---

## Step 8 — Push the change back

Two options. Both work; pick by user preference (default to UpdateMarkup — it's a plain JSON `PUT`, no multipart).

For the **create branch**: this is also where you push the initial body (for blank/inline seeds), and where you set `access: 5` for anonymous-access forms via a second `UpdateMarkup` call (the Create endpoint may ignore `access` on initial create).

### Option A — UpdateMarkup (default, simplest)

```bash
curl -s -X PUT "$BASE_URL/api/services/Shesha/FormConfiguration/UpdateMarkup" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/update-markup-body.json
```

Body shape: `{ "id": "$FORM_ID", "markup": "<stringified form JSON>" }`. Build it via Node to avoid escaping pain — see [api.md §5](reference/api.md).

### Option B — ImportJson (multipart upload)

`POST /api/services/Shesha/FormConfiguration/ImportJson` with `multipart/form-data`, fields `ItemId` (the form id) and `file` (the form JSON as a file). See [api.md §6](reference/api.md).

Both endpoints write `Markup` on the form configuration. UpdateMarkup is the same code path but takes JSON body; ImportJson exists for the designer's "upload .json file" flow.

A successful response is HTTP 200 with `{ "result": ... }`. On any non-200, surface the raw response and stop.

---

## Step 9 — Confirm + offer next step

Tell the user the form was updated, then build a **test URL** they can paste under their front-end origin (typically `http://localhost:3000`).

Follow [form-test-url.md](reference/form-test-url.md):
- Authenticated vs anonymous: `/dynamic/<module>/<form>` for `formSettings.access !== 5`, `/no-auth/<module>/<form>` for `access === 5`.
- Entity-bound (`formSettings.modelType` set): auto-fetch a sample entity id via `GET /api/services/app/Entities/GetAll?entityType=<modelType>&properties=id&MaxResultCount=1` and append `?id=<guid>`. If the user supplied an id explicitly, prefer that. If the entity table is empty, return the base path with a clear "no rows yet" note — don't error.

Output the URL verbatim so the user can copy it.

---

## Notes & gotchas

- **Preserve markup as a string** when round-tripping. The form's `markup` column is a string column; the API stores it verbatim. Always `JSON.stringify` your edited tree before sending.
- **No id regeneration**: if the user says "duplicate this section", deep-clone and assign **new** ids on every cloned node, but only on the clones — never touch originals.
- **`formSettings.modelType`** is the entity full name (e.g. `PBF.MembershipManagement.Domain.Domain.Member`). Keep it in sync with the actual entity if you change the form's binding.
- **`editMode: "editable"` on every interactive component** — `textField`, `textArea`, `numberField`, `dateField`, `dropdown`, `radio`, `checkbox`, `switch`, `button`, `link`, `autocomplete`, `entityPicker`. Without it, Shesha may default the component to read-only (especially on forms with `dataLoaderType: "none"` like auth pages) and the user will see a "looks fine but won't accept input/clicks" symptom. Pure visual components (`text`, `image`, `container`, `columns`, `card`) keep `editMode: "inherited"` or omit it. **This rule is non-negotiable.** See [components.md §editMode rule](reference/components.md#editmode-rule).
- **Layout pattern**: pages use **outer container → card → inner container → section sub-containers**. The outer container handles centering/full-viewport sizing; the `card` component is the white-rounded box with `header.components` and `content.components` slots; the inner container is the form-content wrapper; sub-containers act as semantic divs for grouping related rows (e.g. consents block, name row, action row). See [components.md §Layout pattern](reference/components.md#layout-pattern).
- **PowerShell + UTF-8**: `Invoke-RestMethod -Body $jsonString` encodes the body as Windows-1252 by default. If the body contains em dashes (`—`), curly quotes, accented characters, or any non-ASCII bytes, the server returns 500 with `Unable to translate bytes [E2] at index N from specified code page to Unicode`. **Always pass the body as UTF-8 bytes:**
  ```powershell
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)
  Invoke-RestMethod -Uri $url -Method Put -Headers $h -Body $bytes -TimeoutSec 60
  ```
  Or sidestep entirely by using `curl --data-binary @file` from Bash.
- **Anonymous-access forms**: set `formSettings.access = 5` on forms that need to be reachable without login (login, register, otp pages). The Create endpoint may not honour `access` on initial create — push the markup once with `Create`, then immediately call `UpdateMarkup` with `access: 5` to lock it in. Anonymous forms are served at `/no-auth/<module>/<form>`; authenticated forms at `/dynamic/<module>/<form>`.
- **Built-in auth actions**: `actionName: "Sign In", actionOwner: "shesha.common"` reads the form's `userNameOrEmailAddress` + `password` fields and calls `TokenAuth/Authenticate`. After success, `actionResponse.url` holds the Shesha-default landing URL. Compose with `onSuccess: { actionName: "Execute Script", actionArguments: { expression: "..." } }` for custom routing. OTP endpoints: `POST /api/services/app/Otp/SendPin` (`{sendTo, sendType: 1=phone | 2=email}`), `POST /Otp/VerifyPin` (`{operationId, pin}`), `POST /Otp/ResendPin` (`{operationId}`). Stash the returned `operationId` in `localStorage` between pages.
- **Don't bypass auth.** If the token expires mid-session (24h default), re-run Step 2.
- **Read [components.md](reference/components.md) before authoring components you haven't used in this session** — it has the IPropertySetting wrapper, script globals, dropdown shapes, validation patterns, and gotchas that aren't obvious from the index.
