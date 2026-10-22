# API by framework version

Contents: environment roles | authentication | 0.43: versioned configuration items | 0.45+ and 0.46: in-place forms | session and version endpoints | settings | metadata | dynamic CRUD | workflows | browser notes

The reconciler compares a reference site on an older framework line with a target on a newer one, so the same operation has two API shapes. The engine
(`scripts/core/api.py`, `scripts/core/push.py`) handles both for reads; ALL writes go through `push.py` on the in-place API of 0.45+/0.46. Confirm any endpoint you
have not seen working against a live instance before relying on it.

## Environment roles

| Role | What | Writes |
|---|---|---|
| `reference` | the deployed site on the older line that everyone compares against. For a versioned (0.43) reference read the Live versions only (`versionStatus == 3`) | **NEVER.** GET only (plus the token request and read-only queries); every write path refuses its hosts |
| `local` | the developer's upgraded build on a local copy of the database | yes, through `push.py` only, on the host the user confirmed (`confirm-target`) |
| `deployed` | a deployed upgraded site to repair | only after the user says so in this session and confirms the exact host (`authorise-deployed`, `SHREC_DEPLOY_CONFIRM`); every row is backed up first |

Nothing written locally reaches another environment: reconciled forms travel only through the configuration package ([packages-and-export.md](packages-and-export.md)).
Data writes for functional tests are safe on a local copy. The local backend is started from the developer's IDE: do not start, stop or rebuild it; ask. Before a
functional check, probe it: `shrec.py probe-env local`.

## Authentication

`POST /api/TokenAuth/Authenticate {userNameOrEmailAddress, password}`. **Rate limited: 10 logins per minute.** The API client caches one token per role per process, and
the browser helper caches the browser login under `work/.state/` for 40 minutes. A script that logs in per form or per page trips the limit. Credentials come from
`.shesha-reconcile/credentials.local.json` ([intake.md](intake.md)); they are never printed or logged.

## 0.43: versioned configuration items

On 0.43 a form is a versioned ConfigurationItem: one `Origin` (stable identity), a `versionNo`, and a `versionStatus`: 1 Draft, 2 Ready, **3 Live**, 4 Cancelled, 5 Retired.
Legal transitions are Draft to Ready to Live; publishing auto-retires the previous Live.

- Read: `FormConfiguration/GetByName?module=&name=` resolves the latest/Live version by default (optionally `version`); `FormConfiguration/Get?id=` for one version id;
  `FormConfiguration/GetAll` lists versions (the `module.name` projection can come back null; filter `isLast==true` for the latest per origin).
- The reference's forms the reconciler compares with are the Live versions (`versionStatus == 3`).
- The reconciler never writes a 0.43 site. For authoring on 0.43 use `shesha-developer-0-43:shesha-form-edit` (CreateNewVersion, UpdateMarkup on a Draft, publish).
- Browser: the 0.43 portal reads a localStorage key `CONFIGURATION_ITEM_MODE` to choose between live and draft versions. The browser helper sets it to `"live"` only when the
  browsed role's version is below 0.45, so a sweep renders Live forms.

## 0.45+ and 0.46: in-place forms

0.45+/0.46 has one row per form, edited in place: no Draft/Ready/Live, no `versionStatus`. History is an automatic revision table.

| Operation | Endpoint |
|---|---|
| Resolve by module + name | `GET /api/services/app/ConfigurationItem/GetCurrent?itemType=form&module=<m>&name=<n>` (lowercase parameter names work) |
| Read one form | `GET /api/services/Shesha/FormConfiguration/Get?id=<id>` (a flat DTO with `markup` and `modelType`) |
| List forms | `GET /api/services/Shesha/FormConfiguration/GetAll?MaxResultCount=<n>` (page with `SkipCount` until `totalCount`; the engine's `get_all` does this) |
| Write | `PUT /api/services/Shesha/FormConfiguration/UpdateMarkup {id, markup, modelType}`: in place, no revision, no Draft |
| Create | `FormConfiguration/Create` |

Traps:

- **`FormConfiguration/GetByName` is a 404 on 0.46** (it exists on 0.43: use it on the reference). The same goes for `CreateNewVersion` and `UpdateStatus`, and
  `ReferenceList/GetItems` is gone (use `ReferenceList/GetByName`).
- **`UpdateMarkup` overwrites `modelType`** with what is sent, and clears it when omitted. **Always carry `modelType` forward**: send the stored value you just read. The push layer
  does, then reads the form back and compares markup and modelType.
- A form read through `GetCurrent` and one through `Get?id=` are the same row; a write is visible to both immediately, but the browser serves its cached copy until the caches
  are cleared ([workflow.md](workflow.md)).

## Session and version endpoints

- `Session/GetCurrentLoginInfo` on 0.45+/0.46; `Session/GetCurrentLoginInformations` on 0.43. `probe-env` tries both (GET only) and reports which answered.
- **There is no framework-version endpoint on 0.46**: the login-info DTO carries no application block. Versions therefore come from the repository's package pins for a local
  stack - the frontend `@shesha-io/reactjs` version FIRST (framework releases and their release notes are tagged with it),
  the backend `Shesha.*` NuGet pin only as a fallback (backend packages follow their own patch numbering: a backend on
  0.46.4 can sit beside a frontend on 0.46.0; `$(SheshaVersion)`-style MSBuild properties are resolved) - and from `project.json` `environments.<role>.version` for deployed and reference sites
  (`shrec.py versions`). Never infer which environment is "ahead" from a version number: diff the actual content.

## Settings

Theme settings are per front-end application: read and write them **with `appKey`** (`default-app` is the Default UI). Without it the tenant-level object comes back, a
different and stale value: never edit that one.

- Read: `GET /api/services/app/Settings/GetValue?name=Shesha.ThemeSettings&module=Shesha&appKey=<appKey>`.
- Write: `POST /api/services/app/Settings/UpdateValue {name, module, appKey, value}`: merge into the current value, back it up, read it back, record it with `shrec.py other --kind theme-settings --what "..." --backup <file>`.
- Settings are not part of the form package ([packages-and-export.md](packages-and-export.md)).

## Metadata

- `Metadata/GetProperties?container=<fullClassName>` works on both versions.
- `Metadata/Get` needs `entityType=<fullClassName>` (or `module` + `name`) on 0.46; `container=` answers 400.
- `Metadata/GetNonFrameworkRelatedProperties?container=` is new in 0.46 (business properties only).
- A 404 on an all-zero-GUID probe means "entity not found", not "route does not exist": read the error body and probe with a real id.

## Dynamic CRUD

Entities are read and written through `/api/dynamic/<Module>/<Entity>/Crud/Get`, `Crud/GetAll` and `Crud/Update`, and listed with `/api/services/app/Entities/GetAll?entityType=`. The push layer
writes an entity through `Crud/Update` after a verified backup and an independent read-back that checks the other fields did not change. 0.46 dynamic CRUD rejects properties
that metadata marks `readonly` (hazard H42) and a request body whose filter carries `null` (hazard H34); 0.43 accepted both.

## Workflows

For `Shesha.Workflow` definitions, the designer saves the BPMN schema with `PUT /api/services/SheshaWorkflow/WorkflowDefinition/UpdateSchema {id, workflowSchema}`; read it with
`WorkflowDefinition/Get?id=`. The push layer backs up the full row, writes the schema, and reads it back by id.

## Browser notes

- The portal caches forms in IndexedDB (`form:<appKey>`, `form_lookup:<appKey>`, legacy `forms`): clear them after every push (hazard H2).
- The headless admin session shows the "form info card" (the `Module/form` name with an edit icon): designer chrome, ignore it.
- Login selectors differ between portals: `project.json` `login` holds the placeholders and the submit text.
