# Shesha Form API — Recipes

All curl recipes assume `$BASE_URL` and `$ACCESS_TOKEN` are set. On Windows, substitute `%BASE_URL%`/`%ACCESS_TOKEN%` for cmd or `$env:BASE_URL`/`$env:ACCESS_TOKEN` for PowerShell.

---

## 1. Resolve base URL

Order of precedence:

1. `src/PBF.MembershipManagement.Web.Host/Properties/launchSettings.json` → `profiles.Project.applicationUrl`
2. `src/PBF.MembershipManagement.Web.Host/appsettings.json` → `Kestrel:Endpoints:Http:Url`
3. Fallback: `http://localhost:21021`

Strip trailing slash.

---

## 2. Authenticate

```bash
curl -s -X POST "$BASE_URL/api/TokenAuth/Authenticate" \
  -H "Content-Type: application/json" \
  -d '{"userNameOrEmailAddress":"admin","password":"123qwe"}'
```

ABP wraps responses; expect:

```json
{
  "result": {
    "accessToken": "eyJ...",
    "encryptedAccessToken": "...",
    "expireInSeconds": 86400,
    "expireOn": "...",
    "userId": 1,
    "personId": "...",
    "resultType": 1
  },
  "targetUrl": null,
  "success": true,
  "error": null,
  "unAuthorizedRequest": false,
  "__abp": true
}
```

Some Shesha builds return the token at the **root** instead. Try both:

```bash
TOKEN=$(curl ... | jq -r '.result.accessToken // .accessToken')
```

If both are null, the credentials are wrong (or the user is locked) — surface the raw response.

---

## 3. Resolve form id by name (when user gave module + name)

```bash
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetByName" \
  --data-urlencode "module=PBF.MembershipManagement" \
  --data-urlencode "name=member-create" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Response (ABP envelope):

```json
{
  "result": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "module": { "name": "PBF.MembershipManagement", "id": "..." },
    "name": "member-create",
    "label": "Member - Create",
    "markup": "{...stringified form JSON...}",
    "modelType": "PBF.MembershipManagement.Domain.Domain.Member",
    "versionNo": 1,
    "versionStatus": 3
  },
  "success": true
}
```

Extract `result.id` → `$FORM_ID`. Note: `GetByName` already includes `markup`, so if you used this endpoint you can skip Step 4.

If `result` is null, the form doesn't exist under that module/name. Stop and tell the user.

---

## 4. Fetch form JSON by id

```bash
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetJson" \
  --data-urlencode "id=$FORM_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -o /tmp/form-current.json
```

This endpoint returns the **raw markup as a file download** (`application/json` with `Content-Disposition: attachment`). The file content **is** the form JSON (already parsed as an object — no string wrapping). Read it with `JSON.parse`.

If you need the wrapping DTO (with id, name, modelType etc.) instead, use `Get` — `GET /api/services/Shesha/FormConfiguration/Get?id=$FORM_ID` — which returns the ABP envelope.

---

## 5. Push edited markup — UpdateMarkup (preferred)

`PUT /api/services/Shesha/FormConfiguration/UpdateMarkup`

DTO (`FormUpdateMarkupInput`):

```ts
{
  id: string,           // form Guid (required)
  markup?: string,      // stringified form JSON
  access?: number,      // RefListPermissionedAccess (optional)
  permissions?: string[] // optional
}
```

Build the body via Node so the markup string is properly JSON-escaped. Don't try to construct it inline in bash — escaping nested JSON-in-JSON manually is a footgun.

```bash
node -e "
const fs = require('fs');
const tree = JSON.parse(fs.readFileSync('/tmp/form-edited.json', 'utf8'));
const body = JSON.stringify({
  id: process.env.FORM_ID,
  markup: JSON.stringify(tree)
});
fs.writeFileSync('/tmp/update-markup-body.json', body);
" 

curl -s -X PUT "$BASE_URL/api/services/Shesha/FormConfiguration/UpdateMarkup" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/update-markup-body.json
```

Successful response: HTTP 200 with `{ "result": null, "success": true, ... }`. The endpoint returns `void`.

On error, ABP returns:

```json
{
  "result": null,
  "success": false,
  "error": { "code": 0, "message": "...", "details": "..." },
  "unAuthorizedRequest": false
}
```

Surface `error.message` and `error.details` to the user and stop.

---

## 6. Push edited markup — ImportJson (multipart upload)

`POST /api/services/Shesha/FormConfiguration/ImportJson` with `multipart/form-data`. Use this when you specifically need to mimic the designer's "upload JSON" button.

DTO (`ImportFormJsonInput`):

```ts
{
  ItemId: string,    // form Guid
  file: File         // the form JSON as a file upload, field name MUST be lowercase "file"
}
```

```bash
# /tmp/form-edited.json contains the stringified-or-tree form JSON.
# If your edits are an object (parsed tree), stringify first; the API expects the file content
# to be a JSON document representing the form markup.

curl -s -X POST "$BASE_URL/api/services/Shesha/FormConfiguration/ImportJson" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "ItemId=$FORM_ID" \
  -F "file=@/tmp/form-edited.json;type=application/json"
```

Successful response: HTTP 200 with `{ "result": { ...FormConfigurationDto... }, "success": true }`. The DTO contains the updated form record.

Field name **must be `file`** (lowercase) — see `ImportFormJsonInput.File` `[BindProperty(Name = "file")]`.

---

## 7. (Optional) Create a new form

`POST /api/services/Shesha/FormConfiguration/Create`

DTO (`CreateFormConfigurationRequest`):

```ts
{
  moduleId: string,        // module Guid (required)
  name: string,            // unique within module
  label?: string,
  description?: string,
  modelType?: string,      // entity full name
  generationLogicTypeName?: string,
  templateId?: string,     // copy from another form
  markup?: string          // initial markup; can be set later via UpdateMarkup
}
```

```bash
curl -s -X POST "$BASE_URL/api/services/Shesha/FormConfiguration/Create" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "moduleId": "...module-guid...",
    "name": "member-quickview",
    "label": "Member - Quick View",
    "modelType": "PBF.MembershipManagement.Domain.Domain.Member"
  }'
```

To resolve `moduleId`, query `GET /api/services/app/Module/GetAll` with bearer token and pick the module by `name`.

---

## 8. List forms in a module (browsing)

`GET /api/services/Shesha/FormConfiguration/GetAll?Filter={...}` — ABP `GetAll` with paging. Easier:

```bash
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetAll" \
  --data-urlencode "MaxResultCount=200" \
  --data-urlencode 'Filter={"and":[{"==":[{"var":"module.name"},"PBF.MembershipManagement"]}]}' \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Returns `result.items[]` with `{ id, name, label, module: {...} }`.

---

## 9. Common errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Missing / expired token | Re-run Step 2 |
| `403 Forbidden` | User lacks `app:Configurator` permission | Login as admin (default has it) |
| `Form is not editable` | Module is read-only or imported-only | Module must have `IsEditable=true`; check `frwk.modules.is_editable` |
| `Module is null` | Form's module reference is broken | Reload the form, check `result.module` is populated |
| `Markup is not valid JSON` | The string you sent isn't parseable | Re-stringify; ensure no truncation in the curl `-d @file` form |
| Empty `result` from GetByName | Form doesn't exist under that name/module | Verify via `GetAll` |
| `result: null` on UpdateMarkup but `success: true` | Normal — endpoint returns void | No action |
