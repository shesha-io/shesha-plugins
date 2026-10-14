# Start-up and Migration Failures

Phase 4. This is where the upgrade is actually tested, and where the hard problems live.

## §1. The rule that explains nearly all of it

**FluentMigrator applies any migration absent from `VersionInfo` in ascending order, regardless of how far ahead the database already is.**

So a migration written in 2024 runs today against a 2026 schema. Version numbers guarantee ordering only within one linear history. They guarantee nothing once:

- two release branches each contribute migrations, or
- a module is installed onto a database that is already past its migrations.

Every failure in this file is an instance of that. The shape is always: *a migration asserts a schema state it is not entitled to assume.*

## §2. Diagnose the database before the code

### Is `VersionInfo` real, or backfilled?

```sql
SELECT COUNT(*) AS rows, COUNT(DISTINCT CAST(AppliedOn AS date)) AS days FROM VersionInfo;
SELECT TOP 3 CAST(AppliedOn AS date), COUNT(*) FROM VersionInfo GROUP BY CAST(AppliedOn AS date) ORDER BY COUNT(*) DESC;
```

A few hundred rows stamped on one or two days means the history was **written in bulk, not earned** — typically a bacpac whose `VersionInfo` came along with it. Such a database can be missing schema its `VersionInfo` claims exists, and is a poor witness for upgrade testing. Genuine incremental execution shows dozens to hundreds of distinct days.

Check a specific migration:
```sql
SELECT AppliedOn FROM VersionInfo WHERE Version = {version};
```
A 2023 migration stamped 2026 never ran here — whatever it creates may simply not exist, however unconditional its code looks.

### Do not trust `column_id` gaps

A gap normally proves a column was dropped in place. **bacpac import renumbers ordinals contiguously**, destroying the evidence — a database that definitely dropped a column can show no gap. Verify the hypothesis another way, or say it is unknown.

## §3. `Invalid column name 'DefaultPriorityLkp'`

The framework failure to expect on an upgraded database.

`M20250623120199` copies `Core_NotificationChannelConfigs` into `frwk.notification_channel_revisions`, selecting `DefaultPriorityLkp`. On `releases/0.43`, `M20260614111200` (PR shesha-io/shesha-framework#5025) *moves* that column onto `Core_NotificationTypeConfigs` and drops it from the channel table. It was never forward-ported, so 0.46 still reads a column the 0.43 line has removed.

Version ordering does not protect you: `20250623120199` is the **lower** number and is meant to run first, while the column still existed — but databases fed from 0.43 applied the higher-numbered migration first and have yet to run the lower-numbered one.

```sql
-- local unblock; re-run after any database re-import
IF OBJECT_ID('Core_NotificationChannelConfigs') IS NOT NULL
   AND COL_LENGTH('Core_NotificationChannelConfigs','DefaultPriorityLkp') IS NULL
    ALTER TABLE Core_NotificationChannelConfigs ADD DefaultPriorityLkp BIGINT NULL;
```

Nothing is lost by the column being NULL: the two tables share no relating column, so the "move" carries no per-row data across.

**Diagnostic that settles it**, if you need to prove the correlation across several databases:

```sql
SELECT CASE WHEN EXISTS(SELECT 1 FROM VersionInfo WHERE Version=20260614111200)
            THEN 'applied' ELSE 'pending' END,
       CASE WHEN COL_LENGTH('Core_NotificationChannelConfigs','DefaultPriorityLkp') IS NULL
            THEN 'MISSING' ELSE 'present' END;
```

Every database that applied the move is missing the column; every one that has not still has it. Databases where the legacy table is already dropped pass regardless, because the script's *table* guard skips them.

## §4. Guard in C#, never in SQL

The single most transferable rule here.

```csharp
// WRONG - the batch is compiled before the IF is evaluated
Execute.Sql("IF COL_LENGTH('t','c') IS NOT NULL BEGIN UPDATE t SET ... ; ALTER TABLE t DROP COLUMN c; END");

// RIGHT
if (Schema.Table("t").Column("c").Exists()) { Execute.Sql("..."); }
```

SQL Server's **deferred name resolution covers tables, not columns of an existing table**. A column reference in a static statement is resolved at compile time even in a branch that is never taken, so the batch fails with `Invalid column name` regardless of the guard.

PL/pgSQL parses statements lazily, so the *same pattern works on PostgreSQL* — which is exactly why it survives review. Code that is correct on one provider and fatal on another is worse than code that is uniformly wrong. Put the check in C#, where it behaves identically on both.

If you must guard inside SQL Server SQL, build the statement as **dynamic SQL** (`sp_executesql`) so the column name only appears in the text when it exists. On PostgreSQL, `to_jsonb(t) ->> 'Column'` reads a possibly-absent column without naming it — it yields NULL for a missing key and never fails to parse.

## §5. Installing a module replays its whole history

Adding a module package puts **all** of its migrations into the candidate set at once, and they run against today's schema. A module that was never installed has none of its migrations in `VersionInfo`, so there is nothing to skip — they are simply absent, and appear the moment the package is referenced.

Expect historical migrations to fail on renamed tables. The Configuration Items rewrite moved `Frwk_ConfigurationItems`, `Frwk_ReferenceLists` and `Frwk_Modules` to `frwk.*`, and `Shesha.FluentMigrator 0.46.0`'s own reference-list helpers still emit the **pre-rename** names — so `this.Shesha().ReferenceListCreate(...)` fails on any post-rewrite database. That affects every module with reflist migrations, not one application.

Weigh the cost before adding a module to satisfy a single migration: you may trade one error for a chain of them.

## §6. Skipping a migration safely

Last resort, and per-database.

```sql
INSERT INTO VersionInfo (Version, AppliedOn, Description)
VALUES ({version}, GETUTCDATE(), 'M{version} (skipped locally: {reason})');
```

**Key rules:**
- **Read the migration first.** Most do several things; skipping the whole thing to dodge one broken statement silently drops the rest. A migration that also adds columns will leave entities mapping to columns that do not exist.
- Never blanket-skip a module's migrations — you will skip the table creation you needed.
- Prefer *making the migration runnable* over skipping it. Adding a missing column so a batch compiles lets the migration execute and reach its intended end state, which beats a `VersionInfo` row that hides unfinished work.
- Always write the reason into `Description`. An unexplained row is indistinguishable from a real one later.
- Raise a ticket. A skipped migration is a database that no longer matches its own history.

## §6a. Renamed framework tables — the migration-number test

The Configuration Items rewrite renames tables, and each one renames at a **specific migration
number**. So the test is per table, not per repo:

| Table family | Renamed at | Becomes |
|---|---|---|
| configuration items / reference lists / form configurations | `20250623120399` | `frwk.*`, snake_case |
| stored files | `20251024104999` | `frwk.stored_files` |

An app migration numbered **after** the threshold must use the new name; one numbered before it must
keep the old name, because on a fresh database it runs while the old name still exists.

Sweep every repo after the bump:

```bash
grep -rl "Frwk_ConfigurationItems\|Frwk_ReferenceLists\|Frwk_StoredFiles" --include=M2*.cs .
```

then compare each hit's number against the threshold for the table it names.

**Why it hides.** On a database that already applied those migrations they are recorded and never
re-run, so an existing environment starts perfectly while a fresh database — or one restored from an
older backup — dies on first boot. **A migration added since the last deployment fails first**,
having been applied nowhere. One host app was found carrying nine such migrations, all latent.

### Writing the fix

`AddForeignKeyColumn` **cannot name a schema.** Add the column plainly, then create the constraint
against whichever table the database actually has, resolving the primary-key spelling too rather
than assuming it:

```csharp
Alter.Table(TableName).AddColumn("ImportedFileId").AsGuid().Nullable();

if (Schema.Schema("frwk").Table("stored_files").Exists())
{
    var pk = Schema.Schema("frwk").Table("stored_files").Column("id").Exists() ? "id" : "Id";
    Create.ForeignKey($"FK_{TableName}_ImportedFileId_frwk_stored_files")
        .FromTable(TableName).ForeignColumn("ImportedFileId")
        .ToTable("stored_files").InSchema("frwk").PrimaryColumn(pk);
}
else if (Schema.Table("Frwk_StoredFiles").Exists()) { /* pre-rewrite database */ }
```

Amend the offending migration in place rather than adding a replacement, so hosts that already
applied it do not re-run it.

**If merged migrations must not be edited** (a common team rule), use a *superseding* migration
instead: number it just before the broken one, do the 0.46 equivalent, then insert the broken one's
version into `VersionInfo`. The runner reloads `VersionInfo` after every migration, so the original
is skipped. Guard every statement on `VersionInfo` at execution time so a database that already
applied the original (on 0.43) is untouched. For an `AddForeignKeyColumn` against a dropped table,
a *prerequisite* migration that adds the column first is enough — the original's own column guard
then skips it.

## §6b. Duplicate migration versions

`DuplicateMigrationException` at start-up means an app migration shares its number with one the new
module packages ship (ServiceManagement and Enterprise both reuse round numbers such as
`yyyyMMdd100000`). Renumber the **app's** copy — never the package's — and avoid round numbers for
new migrations. A renumbered migration runs again on databases that applied the old number, so it
must be idempotent.

## §6c. Framework data defects that need an app-side repair migration

These are not schema errors: the framework migrations *succeed* and leave bad data, or stop on data
an app is likely to have. Number each repair just before or after the framework migration named.

| Symptom | Cause | Repair |
|---|---|---|
| `entity_config_id` cannot be NULL (`M20250912170999`) | orphaned `entity_properties` with no config revision | delete properties whose `entity_config_id` is NULL, just before it |
| `String or binary data would be truncated` copying stored files (`M20251023114499`) | `file_type` is `nvarchar(50)`; the xlsx MIME type is 65 chars | store the extension (`.xlsx`/`.xlsm`) — in the data before the copy **and** in code that saves files |
| Most notification templates missing after `M20260121101699` drops `Core_NotificationTemplates` | `M20250908141499` joined on the item's revision, copying only templates that were themselves items | back the table up just before the drop, restore templates onto the type's latest revision |
| Old main menu / theme come back; settings edits do not stick | `15-copy-setting_values.sql` compares `UserId = prev.UserId`, never true for NULL, so **every historical value** of app-wide settings is copied and one is read at random | keep the newest row per `(setting_configuration_id, application_id, user_id)` — `ROW_NUMBER() OVER (PARTITION BY …)` treats NULLs as equal |
| A module's settings copy silently skipped (e.g. AzureAD → `Shesha.MicrosoftAuthentication`) | module rows are created by the bootstrapper **after** migrations; the copy needs the row | `this.Shesha().ModuleEnsureExists("<module>")` in a migration numbered just before the copy |
| `TransientObjectException … ShaRole` at start-up | an app package re-adds a role that is **soft-deleted**; the importer ignores deleted items, treats it as new, and queries its permissions before saving it | un-delete the role (item **and** its revisions) in a migration — migrations run before package seeding |
| Every form of a configuration-only module "not found" (often one created from a starter template) | the bootstrapper **soft-deletes every module with no code module behind it** (configuration-only modules from 0.43) and resolves forms only through the code module hierarchy | declare a `SheshaModule` with that module name (and add it to `DependsOn`) |

Companion packages can ship migrations still written against the 0.43 tables (ServiceManagement
2.5 betas, including the case-type conversion that `Invalid column name 'SM_OrderIndex'` reveals).
Stand in for them with a superseding migration (§6a) and raise it with the package owner.

## §7. Escalating upstream

These are framework defects, not application bugs. When reporting:

- Give the **root cause**, not the symptom — which branch has the migration, which does not, and which is missing the forward-port.
- Name the **reproduction condition** ("a database fed from the 0.43 line"), not your own database, which may be backfilled and invites "cannot reproduce".
- Recommend **forward-porting over re-implementing**. A cherry-pick keeps the version number, so `VersionInfo` dedupes and databases from either line converge. A re-implementation creates a second version number that *will* meet a database that already did the work — the direct cause of this class of failure.
- Where a migration must tolerate an absent column or table, ask for the **C# guard**, not an in-SQL one (§4).
