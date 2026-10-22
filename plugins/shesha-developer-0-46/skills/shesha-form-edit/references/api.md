# Shesha 0.46 Form API - Recipes

All recipes assume `$BASE_URL` and `$ACCESS_TOKEN`. `$RUN_DIR/staged/` holds scratch files (never `/tmp`: git-bash `/tmp`,
`C:\tmp` and `$env:TEMP` are three different directories). Scripted helper: `scripts/form-api.mjs` implements sections 3-6 and 9
(`get`, `backup`, `push`, `verify`); the curl forms below are the contract it follows.

**What changed from 0.43/0.45:** there is **no Draft/Live lifecycle** and **no `GetByName`**. A form is one row, edited in
place; history is an automatic revision table (`Shesha.Framework/ConfigurationItems/ConfigurationItemManager.cs:350-392`).
`CreateNewVersion`, `UpdateStatus`, `CancelVersion`, `PublishAll`, `Copy`, `FormConfiguration/GetByName` and
`FormConfiguration/Autocomplete` do not exist. A saved row is live immediately - so a bad push is a live outage: back up first
(section 4). Writes to a Live environment need the repo owner's go-ahead.

---

## 1. Resolve base URL

Order: **task-supplied context block** -> `$SHESHA_BACKEND_URL` -> `src/*.Web.Host/Properties/launchSettings.json`
(`profiles.Project.applicationUrl`) -> `src/*.Web.Host/appsettings.json` (`Kestrel:Endpoints:Http:Url`) -> `http://localhost:21021`.
Strip the trailing slash. Reachability: `GET $BASE_URL/swagger/index.html` -> 200, else stop.

## 2. Authenticate

```bash
curl -s -X POST "$BASE_URL/api/TokenAuth/Authenticate" -H "Content-Type: application/json" \
  -d '{"userNameOrEmailAddress":"admin","password":"123qwe"}'
```

Token at `result.accessToken` (older builds: root `accessToken`). Credentials come from the task context; `admin`/`123qwe` is the
local-dev default only. **0.46 rate limits: login 10/min, OTP 5/min** - authenticate once per run and reuse the token (24h); do
not authenticate inside a loop or a retry. A `429` means wait a minute, not retry harder.

## 3. Resolve a form by module + name

```bash
curl -s -G "$BASE_URL/api/services/app/ConfigurationItem/GetCurrent" \
  --data-urlencode "ItemType=form" --data-urlencode "Module=Shesha" --data-urlencode "Name=header" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

(`ConfigurationItem/GetCurrent`: `Shesha.Application/ConfigurationItems/ConfigurationItemAppService.cs:30-65`; it is
`[AbpAllowAnonymous]` but then checks `CurrentUserHasAccessTo` - unauthenticated you get "You are not authorized to access the
requested configuration".) Envelope:

```json
{ "result": { "cacheMd5": "...", "configuration": {
    "id": "<guid>", "module": "Shesha", "moduleId": "<guid>", "name": "header", "label": "...",
    "markup": "{\"components\":[...],\"formSettings\":{...}}",
    "modelType": "Shesha.Domain.Person", "access": 3, "permissions": [], "suppress": false,
    "originId": "<guid>", "templateId": null, "configurationForm": null } }, "success": true }
```

* `$FORM_ID = result.configuration.id`; `markup` is a **string** (parse it once); `modelType` is the value you must send back on push.
* Add `&Md5=<cacheMd5>` to revalidate: an unchanged item answers **HTTP 304** (use it for cheap polling, not for a normal read).
* `result: null` / `success:false` -> the form does not exist under that module+name (or you lack access). Check the exact
  casing with `GetAll` (section 7); do not guess.
* Alternatives: `ConfigurationItem/Get?ItemType=form&Id=<guid>` (same envelope, by id); `ConfigurationStudio/GetItem?ItemType=form&Module=&Name=`
  (DTO without the cache layer); `FormConfiguration/Get?id=<guid>` (flat DTO).

## 4. Fetch + back up (mandatory before any write)

```bash
mkdir -p "$RUN_DIR/staged" "$RUN_DIR/backup"
curl -s -G "$BASE_URL/api/services/app/ConfigurationItem/GetCurrent" --data-urlencode "ItemType=form" \
  --data-urlencode "Module=$MODULE" --data-urlencode "Name=$NAME" -H "Authorization: Bearer $ACCESS_TOKEN" \
  -o "$RUN_DIR/backup/$MODULE.$NAME.$(date +%Y%m%d-%H%M%S).envelope.json"
```

The envelope file *is* the backup (markup + modelType + access + permissions). Then extract
`JSON.parse(envelope.result.configuration.markup)` to `$RUN_DIR/staged/<name>.current.json` and edit a **copy**.
`GET FormConfiguration/GetJson?id=` also works but returns the raw markup as a file download (parse once), carrying no
`modelType`; prefer the envelope. Server-side history: `GET ConfigurationStudio/GetItemRevisions?ItemId=<id>` and
`POST ConfigurationStudio/RestoreItemRevision {itemId, revisionId}` exist, but identical content creates no revision and a new
revision is cut only if the last is older than 15 minutes or by another user - **the revision table is not a substitute for your
own backup**.

## 5. Push - `UpdateMarkup` (default)

`PUT /api/services/Shesha/FormConfiguration/UpdateMarkup` (`FormConfigurationAppService.cs:161-190`):

```ts
{ id: string, markup: string, modelType?: string, access?: number, permissions?: string[] }
```

**The handler assigns `form.ModelType = input.ModelType`** - an omitted `modelType` blanks it, a different one replaces it
(proven on a running 0.46 app). **Always send the `modelType` you read in section 3.** `access`/`permissions` are written only
when `access > 2` (enum: 1 Disable, 2 Inherited, 3 AnyAuthenticated, 4 RequiresPermissions, 5 AllowAnonymous);
to keep a form anonymous send `access: 5, permissions: []` every time you push it.
The module must be editable (`isEditable: true`, see `Module/GetAll`) or you get an "is not editable" error. The call writes
in place: no Draft, no revision bump if the content is identical.

```bash
node -e "
const fs=require('fs');
const env=JSON.parse(fs.readFileSync(process.env.ENVELOPE,'utf8')).result.configuration;
const tree=JSON.parse(fs.readFileSync(process.env.EDITED,'utf8'));
fs.writeFileSync(process.env.BODY, JSON.stringify({ id: env.id, markup: JSON.stringify(tree), modelType: env.modelType }));
"
curl -s -X PUT "$BASE_URL/api/services/Shesha/FormConfiguration/UpdateMarkup" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" -d @"$BODY"
```

Success: HTTP 200 `{ "result": null, "success": true }` (void). **200 is not proof of persistence** - run section 8.
On `success:false` surface `error.message` + `error.details`; do not retry blindly.

## 6. Push - `ImportJson`, `Create`, `Update`

* `POST FormConfiguration/ImportJson` multipart: `ItemId=<guid>` and `file=@form.json` (field name **lowercase `file`**). Replaces
  `Markup` only; leaves `modelType` alone. Returns the updated DTO. Use when mimicking the designer's "upload JSON".
* `POST FormConfiguration/Create` (`CreateFormConfigurationRequest`: `moduleId, name, label, description, markup, modelType,
  folderId, frontEndAppId, templateId`). The module must be editable. Equivalent generic call:
  `POST ConfigurationStudio/CreateItem { discriminator: "form", moduleId, name, label, ... }`. After `Create` always push the
  markup with `UpdateMarkup` (with `modelType`) if you did not pass it, and re-send `access: 5` for anonymous forms.
* `PUT FormConfiguration/Update` (name/label/description/markup/modelType/...) exists but its duplicate-name check is buggy
  (`:245-279`); prefer `UpdateMarkup` for markup and `ConfigurationStudio/RenameItem` for renames.
* **Module id** for `Create`: `GET /api/services/app/Module/GetAll` -> `result.items[]` -> `{name, id, isEditable}` (or
  `ConfigurationStudio/GetModules`). A "There is no entity Module with id" error after a backend restart means re-fetch.
* Never hand-build or commit a `.shaconfig` (`ConfigurationStudio/ImportPackage` etc.) - push through the API only.

## 7. List and discover

```bash
# forms (paged; no versionStatus/versionNo columns any more)
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetAll" --data-urlencode "MaxResultCount=200" \
  --data-urlencode 'Filter={"and":[{"==":[{"var":"module.name"},"MyModule"]}]}' -H "Authorization: Bearer $ACCESS_TOKEN"
# modules / item types
GET /api/services/app/ConfigurationStudio/GetModules
GET /api/services/app/ConfigurationStudio/GetAvailableItemTypes     # discriminators: form, entity, reference-list, ...
# a reference list (items inside result.configuration)
GET /api/services/app/ConfigurationItem/GetCurrent?ItemType=reference-list&Module=<mod>&Name=<list>
```

`ReferenceList/GetItems` is gone (404) - see [render-hazards-046.md H12](render-hazards-046.md#h12-referencelistgetitems-is-gone).
`GetAll` returns the full markup inline for every form - one call audits a module (see [bulk-operations.md](bulk-operations.md)).

## 8. Round-trip verify (after EVERY push)

A 200, a toast, or an equal content hash is not evidence. Do an **independent read** and compare:

```js
const after = JSON.parse((await getCurrent(module, name)).result.configuration.markup);   // fresh GET, no Md5
const cfg = (await getCurrent(module, name)).result.configuration;
assert(cfg.modelType === before.modelType);                      // UpdateMarkup overwrites it
assert(stableStringify(after) === stableStringify(sentTree));    // key order / whitespace in stylingBox may differ: diff by component id
// anonymous forms: assert(cfg.access === 5)
```

Then run `node scripts/scan-hazards.mjs <after.json> --syntax` on the read-back. Ignore only: key order, whitespace inside string
`stylingBox` values, `null` vs absent on optional fields. Anything else: surface it. Finally clear the browser cache (section 10)
before judging the render. `scripts/form-api.mjs verify` does the compare.

## 9. Pre-push gates (syntax + JSON)

1. **JSON round trip:** `JSON.parse(JSON.stringify({markup: JSON.stringify(tree)}))` must not throw. Template literals in
   `dynamicEndpoint`/script strings and literal newlines inside string values are the usual causes of "Expected ',' or ']'".
2. **Script syntax gate:** every code string (`{_mode:'code', _code}`, `formSettings.on*`, `actionArguments.expression`,
   `style`, `renderer`) must parse as an async function body:
   `new Function('return (async function(){\n' + code + '\n})')`. `node scripts/scan-hazards.mjs <file> --syntax` does this for
   all of them. A script that fails here is never pushed.
3. **Anchored, idempotent transforms:** edit through a script that asserts the anchor exists (component id or `componentName`
   resolved at run time, never a hard-coded array index) and refuses to apply if it is missing; re-running it must change
   nothing. Resolve components by `componentName`/`id`, not position.
4. Component plan + `scan-hazards` + `clean-form-config` (SKILL.md Step 6).

## 10. Clear the portal cache (before judging any change)

The admin portal caches forms in IndexedDB databases **`form:default-app`** and **`form_lookup:default-app`** (legacy: `forms`,
`form`, `form_lookup`), keyed by `cacheMd5`. The server-side md5 cache is cleared with
`POST /api/services/app/ConfigurationItem/CleanClientSideCache` (that is a write - ask first if the backend is shared).
Delete the browser databases from a static page so the app holds no open connection (recipe: [verification.md](verification.md) section 2).

## 11. Metadata

```bash
curl -s -G "$BASE_URL/api/services/app/Metadata/GetProperties" --data-urlencode "container=<fullClassName>" \
  -H "Authorization: Bearer $ACCESS_TOKEN"        # result = a DIRECT array of properties
```

`container` is the class-name **string**, never the `{name,module}` object. An unknown type answers `404` with
`error.message: "Type `x` not found"` - read the body: it means "entity not found", not "route missing". Property fields:
`path`, `dataType`, `dataFormat`, `referenceListName`/`referenceListModule` (the full dotted name, **no** `RefList` prefix),
`entityType` (short class) + `entityModule`, `listConfiguration.mappingType` (`many-to-many` -> junction subtable). Entity
registry: `GET /api/services/app/EntityConfig/GetMainDataList?maxResultCount=500` -> `name`, `module`, `fullClassName`/`className`
+ `namespace`. Cache metadata 24h under `.claude/cache/shesha-form-edit/metadata/`.

Other 0.46 metadata endpoints (verified against a running 0.46 backend):

- `GET /api/services/app/Metadata/GetNonFrameworkRelatedProperties?container=<fullClassName>` (new in 0.46; 404 on 0.43)
  returns only the entity's own business properties, framework/audit columns filtered out, as `[{ displayText, value }]`.
  Useful to list the fields worth binding on a new form.
- `GET /api/services/app/Metadata/Get` takes `entityType=<fullClassName>` or `module=<module>&name=<class>` on 0.46; the
  old `container=` parameter answers **400**. It returns the whole entity: properties, `apiEndpoints`, `methods`,
  specifications, inheritance, `isExposed`, `md5`.
- `GetProperties` carries extra fields on 0.46 (`columnName`, `containerType`, `createdInDb`, `entityFullClassName`,
  `formatting`, ...).

## 12. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| 401 | missing/expired token | authenticate once (section 2) |
| 429 | login/OTP rate limit (10/min, 5/min) | wait a minute; reuse the token |
| 404 on `FormConfiguration/GetByName` | route removed in 0.46 | `ConfigurationItem/GetCurrent` (section 3) |
| 404 on `ReferenceList/GetItems` | route removed | section 7 |
| "You are not authorized to access the requested configuration" | no token / no permission | authenticate; check form permissions |
| `modelType` empty/changed after push | `UpdateMarkup` assigns it | resend the original `modelType` (section 5) |
| "is not editable" | module `isEditable:false` | pick an editable module |
| "Markup is not valid JSON" | truncated/unescaped body | section 9.1; build the body in Node |
| 200 but the browser shows the old form | IndexedDB cache | section 10 |

## 13. Browser smoke

Tool-agnostic: use whichever browser MCP the session exposes. Open `<FRONTEND_URL>/dynamic/<module>/<form>` (authenticated) or
`/no-auth/<module>/<form>` (anonymous), clear the IndexedDB caches first (section 10), wait for `.sha-form`, collect console
errors/warnings and network `>= 400`, take at most one final screenshot. Frontend ports come from `<app>/.env*` /
`package.json`. Map every captured error through [debug.md](debug.md) and [render-hazards-046.md](render-hazards-046.md).
