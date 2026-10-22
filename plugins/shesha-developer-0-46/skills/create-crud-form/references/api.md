# Shesha 0.46 form API — recipes

All curl recipes assume `$BASE_URL` and `$ACCESS_TOKEN` are set. On Windows, substitute `%BASE_URL%` / `%ACCESS_TOKEN%` for cmd or `$env:BASE_URL` / `$env:ACCESS_TOKEN` for PowerShell. Authenticate **once** and reuse the token (logins are rate limited).

**0.46 differences from 0.43 / 0.45 (all proven on a running 0.46 app):**

| Was | Now |
|---|---|
| `GET FormConfiguration/GetByName` | **404.** Use `GET /api/services/app/ConfigurationItem/GetCurrent?itemType=form&module=&name=` |
| versioned lifecycle (`CreateNewVersion`, `UpdateStatus`, Draft to Ready to Live) | **gone.** One row per form, edited in place; history is an automatic revision table |
| `UpdateMarkup {id, markup}` | `UpdateMarkup {id, markup, modelType}` - **it overwrites `ModelType` with whatever you send (null if omitted)**, so always send it |
| `ReferenceList/GetItems` | **404.** Use `ConfigurationItem/GetCurrent?itemType=reference-list&module=&name=` |
| portal always shows the latest form | the portal caches forms client-side (IndexedDB `form:default-app`, `form_lookup:default-app`); clear them before judging an edit |

---

## 1. Resolve base URL

Order of precedence:

1. The task's context block (`Backend URL`).
2. `{BackendProject}.Web.Host/Properties/launchSettings.json` to `profiles.<profile>.applicationUrl`
3. `{BackendProject}.Web.Host/appsettings.json` to `Kestrel:Endpoints:Http:Url`
4. Fallback: `http://localhost:21021`

Strip the trailing slash.

---

## 2. Authenticate

```bash
curl -s -X POST "$BASE_URL/api/TokenAuth/Authenticate" \
  -H "Content-Type: application/json" \
  -d '{"userNameOrEmailAddress":"<user>","password":"<password>"}'
```

Use the credentials from the task's context block; never invent them. ABP wraps responses: the token is at `result.accessToken` (a few builds return it at the root; try `.result.accessToken // .accessToken`). If both are null the credentials are wrong or the user is locked - surface the raw response.

---

## 3. Fetch a form by module + name

```bash
curl -s -G "$BASE_URL/api/services/app/ConfigurationItem/GetCurrent" \
  --data-urlencode "itemType=form" \
  --data-urlencode "module={Module}" \
  --data-urlencode "name={form-name}" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Response (ABP envelope):

```json
{
  "result": {
    "cacheMd5": "...",
    "configuration": {
      "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "module": "{Module}",
      "name": "{form-name}",
      "label": "...",
      "markup": "{...stringified form JSON...}",
      "modelType": "{Company}.{Module}.Domain.{Entity}",
      "access": 3,
      "permissions": []
    }
  },
  "success": true
}
```

Keep `configuration.id` (`$FORM_ID`) and `configuration.modelType` (you must send it back on `UpdateMarkup`). `markup` is a JSON **string** of `{ "components": [...], "formSettings": {...} }`. A missing form returns an error body, not a null `result`; read it. A 404 on an all-zero-GUID probe means "entity not found", not "route missing".

`GET /api/services/app/ConfigurationItem/Get?itemType=form&id=$FORM_ID` returns the same envelope by id. `GET /api/services/Shesha/FormConfiguration/GetJson?id=$FORM_ID` returns the raw markup as a file download (already an object).

---

## 4. Create a new form

`POST /api/services/Shesha/FormConfiguration/Create`

```ts
{
  moduleId: string,        // module Guid (required)  - GET /api/services/app/Module/GetAll
  name: string,            // unique within the module
  label?: string,
  description?: string,
  modelType?: string,      // the entity's fullClassName from EntityConfig/GetMainDataList
  templateId?: string,     // copy from another form
  markup?: string          // initial markup; can be set later with UpdateMarkup
}
```

```bash
curl -s -X POST "$BASE_URL/api/services/Shesha/FormConfiguration/Create" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"moduleId":"<module-guid>","name":"{entity}-table","label":"{Entity} table","modelType":"{Company}.{Module}.Domain.{Entity}"}'
```

Take `result.id`. For a form that is not bound to an entity (a page, a dialog with no model) leave `modelType` out.

---

## 5. Push markup - UpdateMarkup

`PUT /api/services/Shesha/FormConfiguration/UpdateMarkup`

```ts
{
  id: string,            // form Guid (required)
  markup: string,        // stringified form JSON
  modelType?: string,    // ALWAYS send the form's current modelType - omitting it clears it
  access?: number,       // RefListPermissionedAccess: 1 Disable, 2 Inherited, 3 AnyAuthenticated, 4 RequiresPermissions, 5 AllowAnonymous. Values > 2 also write the permissioned object
  permissions?: string[]
}
```

Build the body with Node so the markup string is correctly escaped (never inline nested JSON in bash):

```bash
node -e "
const fs = require('fs');
const tree = JSON.parse(fs.readFileSync('form-edited.json', 'utf8'));
fs.writeFileSync('update-markup-body.json', JSON.stringify({
  id: process.env.FORM_ID,
  markup: JSON.stringify(tree),
  modelType: process.env.MODEL_TYPE      // the value read in step 3 / used in step 4
}));
"
curl -s -X PUT "$BASE_URL/api/services/Shesha/FormConfiguration/UpdateMarkup" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d @update-markup-body.json
```

HTTP 200 with `{ "result": null, "success": true }` (the endpoint returns void) is **not** evidence of persistence - read it back (step 6).

---

## 6. Round-trip verify

Re-fetch with step 3 and compare **structure and values** with what you sent: `components` deep-equal after `JSON.parse(configuration.markup)`, `configuration.modelType` equals what you sent, and for anonymous forms `configuration.access === 5` (the `Create` endpoint may not honour `access` on initial create; call `UpdateMarkup` once more with `access: 5, permissions: []` and re-verify).

Server normalisations to ignore: re-ordered object keys, whitespace in string-encoded values, `null` collapsing to missing on optional fields. Anything else is a defect.

Then clear the portal's IndexedDB form cache (or use a fresh browser profile) before judging the render; the server cache clear endpoint does not touch it.

---

## 7. List forms in a module

```bash
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetAll" \
  --data-urlencode "MaxResultCount=200" \
  --data-urlencode 'Filter={"and":[{"==":[{"var":"module.name"},"{Module}"]}]}' \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`result.items[]` carries `{ id, name, label, module, modelType, markup, ... }` (no version columns in 0.46).

---

## 8. Common errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Missing / expired token | Re-run step 2 |
| `403 Forbidden` | User lacks the configurator permission | Log in as an admin |
| `Form is not editable` | Module is read-only | The module must be editable |
| `Markup is not valid JSON` | The string you sent isn't parseable | Re-stringify; check for truncation in `-d @file` |
| `404` on `FormConfiguration/GetByName` or `ReferenceList/GetItems` | 0.43 routes removed in 0.46 | Use `ConfigurationItem/GetCurrent` |
| form renders without its entity bindings after a push | `modelType` was omitted from `UpdateMarkup` | Re-push with `modelType` |
| `result: null` on `UpdateMarkup` but `success: true` | Normal - the endpoint returns void | Read it back |

---

## 9. Entity metadata

`GET /api/services/app/Metadata/GetProperties?container=<fullClassName>` returns the property list (PascalCase `path` - camelCase it when binding) with `dataType`, `referenceListName` / `referenceListModule`, `entityType`, `required`. `GET /api/services/app/EntityConfig/GetMainDataList?maxResultCount=500` resolves `{ name, module, fullClassName }`. See SKILL.md Step 2.

---

## 10. Browser smoke

Log in through the portal's own login page in a fresh browser context, open `<FRONTEND_URL>/dynamic/<module>/<form-name>`, wait for `.sha-form`, capture one screenshot plus console errors and any network response with status >= 400. Clear the IndexedDB form cache first (section 6). See [functional-requirements.md § smoke](functional-requirements.md#optional--browser-smoke-recipe). A captured error means the form is not done - diagnose before re-editing; never silently re-push.
