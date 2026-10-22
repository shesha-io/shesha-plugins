# Form Shape, Skeleton, and IPropertySetting Wrapper

The structural foundation. Read this first when authoring or validating any form JSON.

---

## Top-level form JSON

After `JSON.parse(markup)`:

```json
{
  "components": [
    { "id": "...", "type": "...", "propertyName": "...", "...": "..." },
    { "id": "...", "type": "container", "components": [ ... ] }
  ],
  "formSettings": {
    "modelType": { "name": "Member", "module": "MyApp.Membership" },
    "dataLoaderType": "gql",
    "dataSubmitterType": "gql",
    "layout": "horizontal",
    "labelCol": { "span": 8 },
    "wrapperCol": { "span": 16 },
    "colon": true,
    "size": "middle",
    "access": 3,
    "permissions": []
  }
}
```

- Top-level `components` **MUST be an array**, not a plain object — the designer calls `e.components.forEach(...)`, so an object crashes it with `e.components.forEach is not a function`. When generating with a single root container, wrap it: `"components": [rootContainer]`.
- `components` is a **nested tree** — containers, tabs, columns, cards have their own `components: []` (or in card's case, `content.components`). Walk recursively.
- `formSettings.modelType` binds the form to a type. **Favour the object shape `{ "name": "<ShortClass>", "module": "<Module>" }`** (the shape current Shesha builds emit, e.g. `{ "name": "Person", "module": "Shesha" }`). A bare full-class-name **string** (`"Shesha.Domain.Person"`) still renders and is accepted on legacy forms, but author new/edited forms with the object. Either way, resolve `name`+`module` (and the `fullClassName` you need for the metadata fetch) from `EntityConfig/GetMainDataList` — never assume a namespace. Reference-list dropdowns and entity pickers silently fail to bind if this is wrong — keep it in sync with the actual entity binding.
  > The metadata fetch still needs the class-name **string**: `GET /api/services/app/Metadata/GetProperties?container=<fullClassName>`. The object goes into `modelType`; the resolved `fullClassName` string is what you pass as `container`.

- **Two different `modelType`s.** `formSettings.modelType` lives inside the markup (object shape, above). The form-configuration **row** also has a `modelType` string, written by `UpdateMarkup` / `Create`. On 0.46 `UpdateMarkup` assigns the row value from the request, so an omitted or different `modelType` silently blanks or rewrites it: read it with `ConfigurationItem/GetCurrent`, send it back on every push, compare on read-back ([../api.md](../api.md) section 5).

### Loader / submitter — favour the default endpoints

`dataLoaderType` (how the form reads its bound entity) and `dataSubmitterType` (how it saves) decide whether the form talks to the entity's **default dynamic CRUD endpoints** or to a hand-wired custom URL. **When a form is bound to a type (`modelType` set), default to `"gql"` for both** — `"gql"` resolves to the entity's standard dynamic CRUD/GraphQL endpoints (`/api/dynamic/<module>/<Entity>/...`) automatically from `modelType`; you supply no URL.

| Value | Meaning | Use when |
|---|---|---|
| `"gql"` | **Default.** Entity's dynamic CRUD/GraphQL endpoints, resolved from `modelType`. | Any entity-bound create / edit / detail form. **This is the default — do not override it.** |
| `"none"` | No load / no save. | Card row templates, anonymous/action pages (login, OTP, search), forms that drive their own scripts. |
| `"custom"` (custom URL loader/submitter) | A hand-specified REST endpoint instead of the entity default. | **Only when the user explicitly asks** for a specific endpoint, or a documented forced case. Then build/verify the endpoint via `shesha-developer:shesha-app-layer` first. |

Do **not** wire a custom loader/submitter endpoint just because one exists — favour `"gql"` so the form stays in sync with the entity's CRUD API. A custom endpoint is opt-in, never the default.
- `formSettings.layout`: `"horizontal"` (default — labels left of inputs) | `"vertical"` (labels above). Setting `"inline"` rarely produces what users expect; use a `container` with horizontal direction instead.
- Empty form is `{ "components": [], "formSettings": { "modelType": "..." } }`. Don't push `null` or `""`.

---

## Component skeleton

Every component has:

```json
{
  "id": "uuid-v4-string",
  "type": "textField",
  "propertyName": "firstName",
  "label": "First Name",
  "parentId": "uuid-of-parent-or-'root'"
}
```

- `id` — unique GUID. **Stable; never regenerate on existing components.** When cloning, deep-clone with new ids; never touch originals.
- `type` — must be a valid component type. Look up the exact type string in `../../../clean-form-config/assets/groups/index.json` (bundled in this skill's assets); if the type is missing from the index, you have the wrong name.
- `propertyName` — for **input** components, the entity property to bind. **camelCase** (`firstName`); the underlying entity is PascalCase (`FirstName`); the framework maps automatically. Don't double-case.
- `parentId` — `'root'` for top-level, otherwise the parent container's id. Every child's `parentId` must reference an `id` that exists in the tree. After moving components, sweep to verify.
- `label` — display label. Hidden if `hideLabel: true`.

---

## IPropertySetting wrapper

Many string/number/boolean properties accept either a **plain value** or a **wrapped JS expression**:

```json
"visible": true                                                       // plain (0.46: `visible`, not `hidden`)
"visible": { "_mode": "value", "_value": true }                       // wrapped, equivalent
"visible": { "_mode": "code", "_code": "return data?.accountType === 'Corporate';", "_value": true }  // runtime JS
```

When `_mode === "code"`, `_code` is evaluated at runtime against the script context (see [scripts.md](scripts.md)). Use this for dynamic visibility, dynamic enabled, dynamic default values, dynamic labels.

When you write a wrapped value, **always include `_mode`** (and `_value` for code mode - it is the last evaluated result) — bare `{ _value: ... }` won't be recognized.

When editing existing markup: keep wrappers when present. Only convert to wrapped form when the user is asking for runtime behavior.

---

## Anonymous-access (`access: 5`)

`formSettings.access = 5` makes the form reachable without login (login, register, OTP pages). Served at `/no-auth/<module>/<form>`. Authenticated forms (`access: 3` default) live at `/dynamic/<module>/<form>`.

The `Create` endpoint may not honour `access` on initial create. After `POST /Create`, immediately call `PUT /UpdateMarkup` with `access: 5, permissions: []` to lock it in. Verify by re-fetching with `ConfigurationItem/GetCurrent` and checking `result.configuration.access === 5` (and that `modelType` survived).

---

## When in doubt

- The authoritative valid-keys-per-type list is in `../../../clean-form-config/assets/groups/` (bundled in this skill's assets). Look up the component type in `../../../clean-form-config/assets/groups/index.json` to find its group file, then check if the key exists in that group file. If a key isn't listed there, you're probably wrong.
- For component types not covered in any reference file (kanban, charts, queryBuilder, themeEditor, mainMenuEditor, processMonitor, kpi-style cards), inspect an existing form that uses them — the designer's output is canonical.
