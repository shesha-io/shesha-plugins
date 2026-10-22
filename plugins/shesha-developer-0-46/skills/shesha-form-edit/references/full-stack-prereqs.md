# Backend prerequisites — symptoms whose fix is NOT in the form

Read when a correctly-authored form misbehaves at runtime. Every section: **symptom → backend cause → handoff**. Do not iterate on markup for these — the markup is fine; the backend isn't. Hand off via the exact skill invocation given, then return to the form edit.

---

## 1. Reference lists — dropdown empty despite correct `referenceListId`

| Symptom | Backend cause |
|---|---|
| Dropdown shows "No matches" / renders empty, `referenceListId` config verified correct | The reflist has **no items** in the backend, or the C# declaration is missing `[ReferenceList("<Module>", "<Name>")]` (+ `using Shesha.Domain.Attributes`) so it is not discoverable at runtime |
| Form fails to render with `ConfigurationLoadingError` | `referenceListId.name` doesn't match any registered reflist — reflist names do NOT always match the property name |

**Verify before blaming the form:**
1. Property metadata: `GET /api/services/app/Metadata/GetProperties?container=<modelType>` → the property's `referenceListName` (full dotted name, use WITHOUT the `RefList` prefix) is the authoritative reflist name. Never derive it from the property name.
2. Backend reflist editor (or the reflist API): confirm items actually exist.

**Handoff (attribute missing / no items / new reflist needed):** `Skill(skill="shesha-developer:domain-model")`

---

## 2. Junction entity DTOs — Guid FKs arrive as numbers/booleans

**Symptom:** a junction-bound create dialog submits, but `Crud/Create` fails or the payload shows FK ids mistyped as **numbers/booleans** instead of Guids. Autocomplete payloads look mistyped. No amount of component config fixes it.

**Backend cause:** junction entities extending `Entity<Guid>` get **mistyped dynamic-CRUD DTOs** (root cause: missing audit columns).

**Fix (backend, three steps — all required):**
1. Promote `<Junction>` to `FullAuditedEntity<Guid>`.
2. Add the audit columns via a FluentMigrator migration.
3. Full rebuild (Ctrl+Shift+B) so the host picks up new DLLs and runs the migration.

**Handoff:** `Skill(skill="shesha-developer:domain-model")` — then re-test the dialog (see [add-dialogs.md](components/add-dialogs.md)).

---

## 3. Data-load failures — 400s, missing tables, mapping errors

| Symptom | Backend cause | Fix path |
|---|---|---|
| HTTP **400** on a `datatable`/`dataContext` data load | Entity has **no GQL query API enabled** | `Skill(skill="shesha-developer:domain-model")`; stop-gap: switch the context to `sourceType: "Url"` (see [components/data-tables.md](components/data-tables.md)) |
| `Invalid object name 'Frwk_ConfigurationItems'` on startup/load | **Framework migrations not run** (e.g. DB restored from an older backup) | Run pending FluentMigrator migrations — `Skill(skill="shesha-developer:domain-model")` |
| NHibernate `could not execute batch command [SQL: SQL not available]` on save | **Entity mapping bugs** (fluent FK mappings, reflist declarations) | `Skill(skill="shesha-developer:domain-model")` |
| Metadata endpoint 404 for the entity named by an FK property | Registered **class name diverges from the FK property name** | Resolve the real `className` via `GET /api/services/app/EntityConfig/GetMainDataList` before setting `entityType` / `modelType` |

**Diagnosis-first rule:** run `Skill(skill="shesha-developer:test-entity-crud-api", args="--no-fix")` to enumerate which entities' GET endpoints are broken **before** changing anything — a form bound to a broken entity looks fine in markup and fails only at runtime.

---

## 3b. Domain change made but not visible — backend not (properly) restarted

**Symptom:** you (or `domain-model`) created/changed an entity + migration, but the new entity/property
still 404s on `Metadata/GetProperties` or `…/Crud/GetAll`, OR the whole app returns
**`HTTP 500.0 — ANCM In-Process handler load failure`** after a restart attempt.

**Backend causes + fixes:**
- A code-first domain change only applies after a **rebuild + restart** (Shesha runs migrations + seeds `EntityConfig` on startup). Runtime/`ModelConfigurations` entities are metadata-only (no table) — not a no-restart shortcut.
- **`500.0 ANCM in-process`** = IIS Express was relaunched outside Visual Studio (`hostingModel=InProcess` needs VS's `%LAUNCHER_PATH%`). Don't relaunch IIS Express; use the Kestrel `dotnet` path.
- **New entity still 404s after one restart** = the dynamic CRUD controller registers only on the boot *after* `EntityConfig` is seeded — restart **twice** for a brand-new entity.
- **A previously-edited form looks reverted after a restart** = module bootstrapping re-imported a shipped form over your in-place edit (0.46 has no Draft/Live, and `GetByName` no longer exists) - re-read with `ConfigurationItem/GetCurrent`, compare, re-push `UpdateMarkup` (with `modelType`) if needed.

**Full procedure (headless takeover vs VS hand-off, the 2-boot lag, form re-verify):** [backend-restart.md](backend-restart.md).

---

## 4. Dynamic CRUD is not interceptable

**Symptom:** you write a custom app service to add server-side behavior (e.g. block delete when children exist) and the form's table still hits the old behavior.

**Backend cause:** custom app services do **not** serve the `/api/dynamic/<module>/<Entity>/Crud/*` route — they land at `/api/services/...`. The dynamic route's `SheshaCrudServiceBase.DeleteAsync` calls `DeleteCascadeAsync` pre-flush, but that only acts on `[CascadeUpdateRules(DeleteUnreferenced=true)]` props and is not per-entity overridable on the dynamic route.

**Consequence — per-entity guards live elsewhere:**

| Guard type | Where it lives |
|---|---|
| Block-delete-when-children-exist (needs a pre-flush query) | **Frontend** button script on the table's delete action — see the delete section of [junction-subtables.md](components/junction-subtables.md) |
| Post-delete cleanup (cascade junctions/children) | Backend `Entity*ed` event handlers — section 5 |

---

## 5. Cascade-delete handler rules (condensed)

Backend rules that constrain what the form/table layer can rely on:

- **NEVER query or mutate the DB inside an `Entity*ing*` handler** (`EntityDeletingEventData<T>`, updating, etc.). They fire **mid-flush** (raised from `SheshaNHibernateInterceptor.OnFlushDirty`/`OnDelete` during the NHibernate session flush); with `MultipleActiveResultSets=False` a second command on the busy connection **reentrant-deadlocks and hangs the whole server** (only a restart recovers). A `RequiresNew` UoW does NOT escape it — ABP reuses the flushing session.
- **Do cleanup in the `*ed` handler** (`EntityDeletedEventData<T>`) with a **fresh unit of work** (`_unitOfWorkManager.Begin()`), using the captured id. Deleting an owned child there re-fires its own `*ed` handler — recursion is automatic.
- Handler shape: implement `IAsyncEventHandler<EntityDeletedEventData<T>>` + `ITransientDependency` (auto-registers via `RegisterAssemblyByConvention`); resolve the many repositories via `IIocResolver.ResolveAsDisposable<IRepository<T,Guid>>()`, not constructor injection.
- Dynamic-CRUD `Delete` is a **soft delete** (`IsDeleted=true` for `ISoftDelete`/`FullAuditedEntity`), so no FK error fires and junction rows orphan silently unless cleaned. Junction FKs typically **RESTRICT** — clean `<Junction>` rows before their parents.
- **Verifying a soft delete:** `Crud/Get?id=` does NOT apply the soft-delete filter (returns soft-deleted rows); `Crud/GetAll?filter=...` DOES. Assert deletion via GetAll `totalCount == 0`, never via `Get?id=` returning null. See [verification.md](verification.md).
- JsonLogic filters do NOT support `like`; filter by FK with `{"==":[{"var":"<parentFk>.id"}, "<guid>"]}`.

**Handoff (writing the handlers):** `Skill(skill="shesha-developer:shesha-app-layer")` for the application-layer pieces; `Skill(skill="shesha-developer:domain-model")` if entities/migrations change.

---

## 6. Permission inheritance — unexpected 401 on a child endpoint

**Symptom:** a child endpoint (e.g. a `GetCurrent`-style action) returns **401** for a user who plainly should have access, and the form's component config is correct.

**Backend cause:** Shesha endpoints **inherit permission restrictions from their parent service**. If the parent app service is hardened (e.g. `access_lkp=4` with a specific permission), child endpoints inherit that restriction. Check the **parent** service's access level and permission tags in **permissioned-objects** — not the child.

**Handoff (hardening / fixing permissioned-objects):** `Skill(skill="shesha-developer-0-43:harden-permissions")`

---

## 7. When to dispatch the prereq checker

For **new entity-bound forms** or any entity you have not verified this session, dispatch the `shesha-developer-0-46:fullstack-prereq-checker` agent (via the Task tool) **before authoring** — it front-loads sections 1–3 (entity exists, metadata resolves, reflists populated, CRUD endpoints answer) instead of you discovering them one runtime failure at a time. See SKILL.md **Step 4.5** for the inline fallback (entity existence check via `Metadata/GetProperties`, `modelType` resolution, `test-entity-crud-api --no-fix`).

---

### Worked example (project-specific)

From RequirementsStudio (memory: `feedback-shesha-form-edit-gotchas` #3/#4, `feedback-shesha-delete-cascade-gotchas`):

- **§1 wrong reflist name:** `ViewDefinition.existsInDevOps` binds to `Shesha.RequirementsStudio.RsDevOpsStatus`, NOT `RsExistsInDevOps` — using the property-derived name caused a `ConfigurationLoadingError` that blocked the whole form. Metadata `referenceListName` had the truth.
- **§3 class/property divergence:** `Shesha.RequirementsStudio.Domain.Release` 404s on the Metadata endpoint; the registered class is `ReleaseDefinition` — found via `EntityConfig/GetMainDataList`, then used as the autocomplete `entityType` for `viewDefinition.release`.
- **§4 frontend guard:** "block BaseProject delete when children exist" could not be done backend-side on the dynamic route — implemented as a script on the table delete button.
- **§5 restore an accidental soft delete:** `UPDATE <Table> SET IsDeleted=0, DeletionTime=NULL, DeleterUserId=NULL WHERE Id='...'` (sqlcmd; DB name in Web.Host appsettings `ConnectionStrings:Default`).
