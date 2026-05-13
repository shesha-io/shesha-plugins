# Form Test URL — `/dynamic/...` or `/no-auth/...` with auto-fetched sample id

After a form is created or edited, the user wants a URL they can paste into the running front-end to see the result. For **entity-bound** forms the URL must include a real entity id (`?id=<guid>`), otherwise the form loads empty and the user thinks nothing changed. This recipe auto-fetches one.

Mirrors the MCP's `get_form_test_url` tool — and improves on it by handling anonymous-access forms (the MCP only emits `/dynamic/`, never `/no-auth/`).

---

## Inputs available by Step 9

By the time Step 9 runs, the skill already knows:

| Field | Where it came from |
|---|---|
| `$FORM_ID` | Step 3a (GetByName) or Step 3b (Create response) |
| Form `name` | Step 3a input, or Step 3b user-supplied |
| Module `name` | Step 3a input, or Step 3b user-supplied (the same name used to resolve `moduleId`) |
| `formSettings.modelType` | Step 4 (parsed markup) or Step 3b inline-markup / blank — `null` for non-entity-bound forms |
| `formSettings.access` | Same — `5` for anonymous, anything else (typically `1`, `2`, `3`, `4`) for authenticated |

**No extra GET for form metadata is needed** — these are already in scope. The only HTTP call this recipe makes is the entity-sample fetch, and only when the form is entity-bound and the user didn't supply an id.

---

## Algorithm

```
URL_PREFIX     = formSettings.access === 5 ? "/no-auth" : "/dynamic"
BASE_PATH      = "$URL_PREFIX/$MODULE_NAME/$FORM_NAME"
ENTITY_TYPE    = formSettings.modelType                # "Shesha.Domain.Person", or null
USER_ENTITY_ID = $1                                     # optional, user-supplied

if (!ENTITY_TYPE)                       → return BASE_PATH
if (USER_ENTITY_ID)                     → return BASE_PATH + "?id=" + USER_ENTITY_ID
sample = fetchSampleEntityId(ENTITY_TYPE)
if (sample)                             → return BASE_PATH + "?id=" + sample
else                                    → return BASE_PATH    (+ a "table is empty" note)
```

The MCP swallows the empty-table case silently; the skill should **tell the user** so they understand why the URL has no id.

---

## Sample-entity-fetch — the one HTTP call

```bash
curl -s -G "$BASE_URL/api/services/app/Entities/GetAll" \
  --data-urlencode "entityType=$ENTITY_TYPE" \
  --data-urlencode "properties=id" \
  --data-urlencode "MaxResultCount=1" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Response shape:

```json
{
  "result": {
    "totalCount": 2,
    "items": [
      { "id": "b05e495a-6e47-426e-91c1-27735b962366" }
    ]
  },
  "success": true
}
```

Read `result.items[0].id`. If `totalCount === 0` (or items is empty), no entities exist and we'll return the base path without `?id=`.

**`properties=id`** is the efficient form — without it the API returns every property on the entity (potentially 30+ fields × many entities × indexes etc.), which is wasteful when we only need a guid.

`MaxResultCount=1` keeps the response tiny — we just need *any* one row.

---

## Endpoint reference

| Purpose | Path | Method | Notes |
|---|---|---|---|
| Sample entity by type | `/api/services/app/Entities/GetAll?entityType=<fullName>&properties=id&MaxResultCount=1` | GET | ✅ verified on running backend. `entityType` accepts both full namespace (`Shesha.Domain.Person`) and `typeShortAlias` (`Shesha.Core.Person`) — both return the same items. |

---

## URL shapes — full reference

| Scenario | URL |
|---|---|
| Authenticated, non-entity (login / list / dashboard) | `/dynamic/<module>/<form>` |
| Authenticated, entity-bound, sample id found | `/dynamic/<module>/<form>?id=<sample-guid>` |
| Authenticated, entity-bound, no entities yet | `/dynamic/<module>/<form>` + "⚠ no entities exist in `<modelType>` yet — URL has no id" |
| Authenticated, entity-bound, user supplied id | `/dynamic/<module>/<form>?id=<user-supplied>` |
| Anonymous (`access: 5`), non-entity (login / register / OTP) | `/no-auth/<module>/<form>` |
| Anonymous, entity-bound (rare but possible) | `/no-auth/<module>/<form>?id=<sample-guid>` |

The path returned is **relative** — the user is expected to prepend their front-end origin (`http://localhost:3000` typically). The skill doesn't track the front-end URL.

---

## Output format

Return this to the user at the end of Step 9:

```
Form $FORM_NAME updated.

Test URL (paste under your front-end origin):
  /dynamic/PBF.MembershipManagement/member-create?id=b05e495a-6e47-426e-91c1-27735b962366

(entity-bound — sample id auto-fetched from Shesha.Domain.Person)
```

Or for a non-entity form:

```
Form $FORM_NAME updated.

Test URL:
  /no-auth/PBF.MembershipManagement/auth-login

(anonymous form — reachable without login)
```

Or for an entity-bound form with empty table:

```
Form $FORM_NAME updated.

Test URL:
  /dynamic/PBF.MembershipManagement/member-details

⚠ no rows exist in Shesha.Domain.Member yet — URL has no `?id=`.
   Create a record first (via member-create) and revisit, or call /Entities/GetAll
   later to grab a real id.
```

---

## Gotchas

1. **`entityType` accepts either form.** Full namespace (`Shesha.Domain.Person`) and `typeShortAlias` (`Shesha.Core.Person`) both work. Prefer whatever's in `formSettings.modelType` — it's what the form is actually bound to.
2. **`access: 5` is the only anonymous value** in Shesha's `RefListPermissionedAccess` enum. Any other value (or absent) → authenticated. Don't try to handle other access levels here — anonymous vs authenticated is the only distinction the URL prefix cares about.
3. **Empty entity table is normal**, especially for create forms or freshly-scaffolded entities. Always degrade gracefully to the base URL with a note — never error out.
4. **Form name and module name in the URL are case-sensitive on some Shesha deployments** — preserve the case exactly as stored in the form record.
5. **The MCP always emits `/dynamic/`** — it has no notion of `/no-auth/` URLs. The skill should not copy this limitation; check `formSettings.access` first.
6. **`formSettings` may be a `_value`-wrapped IPropertySetting** in some forms — read `formSettings.access._value ?? formSettings.access` to handle both shapes.

---

## When the skill uses this

**Step 9 (Confirm + offer next step)** — every successful Create or UpdateMarkup. Output the URL via this recipe instead of the bare-prefix version.

**Standalone** — when the user asks "what's the test URL for the `member-create` form?" without doing an edit, follow this recipe after resolving the form via Step 3a (semantic-search fallback if name is fuzzy).
