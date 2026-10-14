# Pre-flight sweep and test run

Phase 0 and the test procedure for phases 4–5. The sweep finds, from source alone, problems that
otherwise surface one start-up at a time; the test run is how the upgrade is actually proven.

## Contents

- §1. Pre-flight sweep — script
- §2. Reading the report
- §3. Database pre-checks
- §4. Test run procedure
- §5. Page comparison against the old version

---

## §1. Pre-flight sweep — script

Run after the version bump and `dotnet restore` (the clash check reads package DLLs listed in
`obj/project.assets.json`), and again after every new package or migration:

```bash
python scripts/preflight_sweep.py <backend-root> --app-module <AppModuleName>
python scripts/preflight_sweep.py <backend-root> --app-module <AppModuleName> --json > sweep.json
```

Standard library only. It checks the **latest shipped version** of each configuration item by
default (`--all-versions` checks every one); a form already fixed in a newer package is not
reported again.

| Area | Check | Leads to |
|---|---|---|
| Migrations | same version twice in the app | `DuplicateMigrationException` |
| Migrations | app version equal to a package migration version | `DuplicateMigrationException` — renumber the app's copy ([migration-failures.md](migration-failures.md) §6b) |
| Migrations | legacy table named after its rename point; `AddForeignKeyColumn` to `Frwk_StoredFiles` | fails on a fresh database (§6a) |
| Migrations | `Schema.Table(X)` guard inside the migration that creates `X` | index/column silently never created |
| Packages | removed setting reads, config-item versioning fields, moved entity namespaces, removed endpoints, navigation to removed forms, removed component types | runtime breaks ([config-packages.md](config-packages.md) §6) |
| Packages | `{{pageContext.…}}` in table filters; `<style>`-only HTML Render with Sanitize on; unitless legacy image width; flattened containers | silent layout/data breaks (§2, §6) |
| Packages | items whose module is not the app's | arrive as separate items, not overrides (§4) |
| Packages | roles shipped | feed the soft-deleted-role check in §3 |

The scan does not replace config-packages.md §3 (`selectedRow` outside its data context), which
needs data-context ancestry.

## §2. Reading the report

- **Clashes and duplicates are certain** — fix all of them before the first start.
- **Legacy-table hits are candidates.** A migration already applied on every environment never runs
  again; it only fails on a fresh database or a restore older than it. Hits inside migrations that
  deliberately bridge both schemas (guarded on table existence) are expected.
- **Package findings are per form, latest version.** Fix in the designer or markup, then ship in a
  **new** package — never edit an existing package in place.
- Report per package and form, not as a flat count; the same pattern usually repeats across a few
  forms owned by one area of the app.

## §3. Database pre-checks

Run against a fresh copy of the pre-upgrade database, and the post-upgrade queries after the first
start. SQL Server shown; adapt names for PostgreSQL.

```sql
-- Pre-upgrade: stored-file types the 0.46 copy truncates (file_type becomes nvarchar(50))
SELECT FileType, COUNT(*) FROM Frwk_StoredFiles WHERE LEN(FileType) > 50 GROUP BY FileType;

-- Post-upgrade: setting values duplicated by the framework copy (should return nothing)
SELECT setting_configuration_id, application_id, user_id, COUNT(*) AS copies
FROM frwk.setting_values GROUP BY setting_configuration_id, application_id, user_id HAVING COUNT(*) > 1;

-- Post-upgrade: modules soft-deleted at start-up that still own items
SELECT m.name, COUNT(*) AS live_items FROM frwk.modules m
JOIN frwk.configuration_items ci ON ci.module_id = m.id AND ci.is_deleted = 0
WHERE m.is_deleted = 1 GROUP BY m.name;

-- Post-upgrade: soft-deleted roles - compare with the roles the sweep lists as shipped
SELECT m.name AS module, ci.name FROM frwk.configuration_items ci
JOIN frwk.modules m ON m.id = ci.module_id WHERE ci.item_type = 'role' AND ci.is_deleted = 1;

-- Post-upgrade: root module must be the app's module
SELECT name FROM frwk.modules WHERE is_root_module = 1;
```

Migrations commit one by one while package imports roll back on failure, so a failed first start
still leaves the post-upgrade schema in place for these queries.

## §4. Test run procedure

1. **Restore a fresh copy of a pre-upgrade environment's database** for every run that is meant to
   prove the upgrade. A database that already went through a failed or partial start hides the
   failures a real environment will hit (applied migrations do not re-run).
2. **Point the app at it and start the backend in the foreground.** Watch the console *and* the
   log4net file (`<Web.Host>/bin/<config>/<tfm>/App_Data/Logs/`): package-seeder progress and
   per-package import failures are logged there, not to the console.
3. **First start** applies migrations, then seeds packages. On failure, find the failing migration
   or package in the log, fix it in code (migration or package — not by editing the database), then
   go back to step 1.
4. **Second start.** Some bootstrapping depends on data the first start creates (entity
   configurations, dynamic CRUD controllers, module rows); confirm the second start is clean too.
5. **Backend smoke:** an authenticated endpoint returns 200; the API root redirects or answers
   (not 401); if Swagger is enabled, every document under `/swagger` loads (a 500 usually names an
   app service exposing an entity parameter).
6. **Run the §3 post-upgrade queries.**
7. **Frontend:** production build (`npm run build`), start it with `NODE_ENV=production`, then check
   the login page signed out, the main layout and header signed in, and `/configuration-studio`
   (open a form in the designer and use Preview).
8. **Compare every page with the old version** (§5).
9. **Repeat from step 1 after fixes** until a fresh restore goes through cleanly in one pass. Only
   that run proves what other environments will see.

## §5. Page comparison against the old version

Use a running pre-upgrade environment as the reference, read-only — no saves, submits or designer
changes there.

- **List every menu target** from the rendered menu (expand collapsed groups) on both versions and
  diff the lists before comparing pages.
- **Navigate with the SPA router** (`window.next.router.push(path)`) rather than full reloads, and
  wait for spinners to clear plus a few seconds — slow pages otherwise report the previous page.
  Keep progress in `sessionStorage`; a route that 404s does a full reload and loses page state.
- **Capture per page:** column headers, row count, button labels, form labels, visible error
  alerts, and text such as `Component '…' not registered`.
- **Detail pages: compare the same record id** on both versions (copied databases share ids) and
  click through every top-level tab, choosing the outermost tab strip. Different records show
  different tabs by state and prove nothing.
- **Explain each difference before fixing it:** compare the form's version and markup hash on both
  sides first. A form can be newer in the repo than on the old site, or the old site can hold edits
  never exported — neither is an upgrade defect.
