# ModelConfigurations — Entity Property Lookup

When creating or modifying a form bound to an entity (`modelType` on Create, `formSettings.modelType` inside the markup), the skill often needs to know the entity's **properties** — to suggest sensible default fields, validate property references in scripts, and avoid binding inputs to non-existent fields.

---

## The two-step lookup pattern

**Always use the two-step pattern:**

### Step 1 — Resolve entity id via EntityConfig

```bash
curl -s -G "$BASE_URL/api/services/app/EntityConfig/GetMainDataList" \
  --data-urlencode "MaxResultCount=500" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -o /tmp/entities.json
```

Filter `result.items[]` client-side: `className === "<ShortName>" && namespace === "<Namespace>"`. Capture the `id` field.

Example — `Shesha.Domain.Person`: `className: "Person"`, `namespace: "Shesha.Domain"`, `id: "8d990b2b-e788-4c33-a9e8-157f1c95a2b1"`.

If `totalCount > 500`, increase `MaxResultCount` or paginate via `SkipCount`.

> **Fuzzy match?** If the user gave the entity name fuzzily (`"the person entity"`, `"customer"`, typo'd, paraphrased), don't ask them to be exact — run the two-tier search recipe in [semantic-search.md](semantic-search.md) against the entity list before falling back to the user. The same algorithm covers modules, forms, and reference lists too.

### Step 2 — Fetch the full ModelConfigurationDto

```bash
curl -s "$BASE_URL/api/ModelConfigurations/$ENTITY_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Response shape: `{ result: { className, namespace, module, properties: [...], ... } }`.

---

## ModelPropertyDto (relevant subset)

```ts
{
  name: string,                  // PascalCase, e.g. "FirstName"
  label: string,                 // Display label, e.g. "First Name"
  dataType: string,              // see table below
  dataFormat?: string,           // qualifier — see table below
  entityType?: object,           // FK target — {id, _displayName, _className} — NOT a string!
  referenceListName?: string,    // for dataType=reference-list-item
  referenceListModule?: string,
  required: boolean,
  readOnly: boolean,
  suppress: boolean,             // intentionally hidden by config
  isFrameworkRelated: boolean,   // true for ABP audit/tenant/soft-delete fields
  source: 1 | 2,                 // 1 = Code-defined, 2 = User-defined
  properties?: ModelPropertyDto[] // nested for complex types
}
```

---

## dataType → Shesha component mapping

When generating a form from an entity's properties, use this table to pick the right component for each property:

| `dataType` (+ `dataFormat`) | Default component | Notes |
|---|---|---|
| `string` / `singleline` | `textField` |  |
| `string` / `multiline` | `textArea` |  |
| `string` / `email` | `textField` w/ email validation | Set `validate.email = true` |
| `string` / `phone-number` | `textField` | Often paired with input mask |
| `number` / `int32` / `int64` | `numberField` |  |
| `number` / `float` / `double` | `numberField` w/ decimals |  |
| `boolean` | `checkbox` or `switch` |  |
| `date` | `dateField` |  |
| `date-time` | `dateField` w/ time | `showTime: true` |
| `guid` | hidden, or `textField` read-only | `Id` should not be on user-facing forms |
| `reference-list-item` | `dropdown` with `dataSourceType: "referenceList"` | Use `referenceListName` + `referenceListModule` |
| `entity` | `entityPicker` or `autocomplete` | Use `entityType._displayName` for the bound entity |
| `array` / `many-entity` | `childTable` or `tags` | Walk recursively if nested |
| `file` | `fileUpload` |  |
| `object` (nested) | `subForm` | Recurse into `properties[]` |

---

## Gotchas

1. **`entityType` is a dict, not a string.** It comes back as `{id, _displayName, _className}`. Always read `entityType._displayName` to get the entity full name.
2. **Framework properties** (`isFrameworkRelated: true`) — `Id`, `CreationTime`, `CreatorUserId`, `LastModificationTime`, `LastModifierUserId`, `DeletionTime`, `DeleterUserId`, `IsDeleted`, `TenantId`. Filter these out when proposing fields for a user-facing form.
4. **`suppress: true`** — property is intentionally hidden by configuration. Don't bind a form to it.
5. **Stock Shesha has ~138 entities** — `MaxResultCount=500` covers a fresh install with headroom. For larger apps, paginate.
6. **`source: 1` = Code-defined, `source: 2` = User-defined** — useful when you want to surface only the entities a user added vs. framework entities.

---

## When the skill should reach for this

**Create branch (Step 3b)** — when the user specifies a `modelType`:

1. Resolve entity id via `EntityConfig/GetMainDataList` (filter by className + namespace).
2. Fetch `ModelConfigurations/{id}` for the full property list.
3. Filter out `isFrameworkRelated: true` and `suppress: true` properties.
4. Use the remaining list to propose default fields (one component per property, mapped via the table above).
5. Set `formSettings.modelType` on the form root to `<namespace>.<className>`.

**Edit branch (Step 6)** — when the user says "bind the email field to `EmailAddress1`":

1. If `formSettings.modelType` is set, fetch the property list once.
2. Verify the referenced property exists on the entity before changing `propertyName`.
3. If the user names a property that doesn't exist, surface the discrepancy and suggest the closest match.

**Reference-list dropdowns (Step 6)** — when adding a dropdown bound to a `reference-list-item` property:

1. The property's `referenceListName` + `referenceListModule` are the source for `dropdown.referenceListName` + `dropdown.referenceListModule`.
2. Set `dataSourceType: "referenceList"` and omit `values[]` — the list is loaded from the backend.

---

## Example — full Person property summary

For `Shesha.Domain.Person` (id `8d990b2b-e788-4c33-a9e8-157f1c95a2b1`), the stock-Shesha schema is 35 properties grouped roughly as:

- **Identity**: `Id` (guid), `FirstName`, `LastName`, `MiddleName`, `Initials`, `CustomShortName`, `FullName` (read-only computed), `Title` (ref-list), `DateOfBirth`, `Gender` (ref-list), `IdentityNumber`, `Photo` (file).
- **Contact**: `EmailAddress1`, `EmailAddress2`, `MobileNumber1`, `MobileNumber2`, `HomeNumber`, `PreferredContactMethod` (ref-list), `PreferredLanguages` (many-entity).
- **Relationships** (entity refs): `Address`, `WorkAddress`, `User`, `PrimaryAccount`, `PrimaryOrganisation`, `PrimarySite`.
- **Classification**: `Type` (ref-list), `TargetingFlag` (int64).
- **ABP framework** (filter out by default): `CreationTime`, `CreatorUserId`, `LastModificationTime`, `LastModifierUserId`, `DeletionTime`, `DeleterUserId`, `IsDeleted`, `TenantId`.

A sensible default Create form for Person omits the framework block and `Id`/`FullName`, includes the identity + contact blocks, and uses `entityPicker` for the relationship fields.
