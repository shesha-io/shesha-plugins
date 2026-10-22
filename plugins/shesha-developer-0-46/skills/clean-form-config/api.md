# Shesha 0.46 API — authenticate and fetch a form

Used by Step 2 of the `clean-form-config` skill. **Read-only**: this skill never pushes (see SKILL.md, Step 9).

---

## 1. Resolve the base URL

1. The caller's context (`Backend URL`), or `SHESHA_BACKEND_URL`.
2. `.env` in the project root: `NEXT_PUBLIC_BASE_URL`, `REACT_APP_BASE_URL` or `BASE_URL`.
3. `appsettings.json` of the backend: `Kestrel:Endpoints:Http:Url`.
4. Otherwise fall back to Option B in SKILL.md Step 2 (a local file) and say so.

Strip any trailing slash. Store as `BASE_URL`.

---

## 2. Authenticate

**Do not ask the user for credentials** — this skill runs inside a blocking step of `shesha-form-edit`'s push path, frequently headless. Use credentials or a token supplied in the dispatch context; follow [shesha-form-edit api.md](../shesha-form-edit/references/api.md) for the canonical recipe. Authenticate **once** and reuse the token (logins are rate limited).

```bash
curl -s -X POST "{BASE_URL}/api/TokenAuth/Authenticate" \
  -H "Content-Type: application/json" \
  -d '{"userNameOrEmailAddress":"{USERNAME}","password":"{PASSWORD}"}'
```

Take `result.accessToken` as `ACCESS_TOKEN` (the response is an ABP envelope: `{ "result": { "accessToken": ... } }`). If there is no token, fall back to Option B.

---

## 3. Fetch the form by module + name (0.46)

`FormConfiguration/GetByName` does **not exist** in 0.46 (404). Use the configuration-item loader the portal itself uses:

```bash
curl -s -G "{BASE_URL}/api/services/app/ConfigurationItem/GetCurrent" \
  --data-urlencode "itemType=form" \
  --data-urlencode "module={MODULE}" \
  --data-urlencode "name={NAME}" \
  -H "Authorization: Bearer {ACCESS_TOKEN}"
```

Response: `{ "result": { "cacheMd5": "...", "configuration": { "id", "module", "name", "markup", "modelType", ... } } }`. `markup` is a JSON **string** of `{ "components": [...], "formSettings": {...} }`. Pass the whole response to the normaliser (`analysis.md` -> Normalisation handles `result.configuration.markup`) or to `scripts/scan-046.mjs`, which unwraps it.

Keep `configuration.id` and `configuration.modelType` for the caller: the push (`FormConfiguration/UpdateMarkup`) overwrites `modelType` with whatever the request carries, so the caller must send the value read here.

A 404 on an all-zero GUID probe means "entity not found", not "route missing"; read the error body.

---

## 4. Hand-back

Return the cleaned markup and the change list to the caller. Pushing is `shesha-form-edit`'s job (it re-fetches, diffs and browser-smokes). Standalone users: tell them to push with `shesha-form-edit`.
