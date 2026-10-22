# Configuration packages and export

Contents: the rule | how packages behave | steps | not forms: the other things that must travel | backend first

Reconciled forms reach other environments only through a configuration package exported through the Shesha API (`ConfigurationStudio/ExportPackage`, what the
Configuration Studio Export dialog calls). **Never hand-build or hand-edit a `.shaconfig`.** The reconciler does not export by itself: at the end of a cycle it prints the
list of forms to export and asks the user whether they are happy and have tested; it exports (and opens the PR) only after the user says yes and chooses "do it for me".
The same rule is summarised for general configuration work in `shesha-developer:shesha-configuration-items`.

## Exporting yourself (manual)

The end-of-run report lists the forms. In Configuration Studio use the Export dialog with ONLY those forms selected and dependencies OFF (`exportDependencies` false),
save the downloaded package into the application's ConfigMigrations folder (its name must sort AFTER every package already there), and add the `None Remove` plus
`EmbeddedResource` pair for it to the Application `.csproj`, mirroring the previous package's entries. Or use `shrec.py export-package` below, which does the same
through the same API. `project.json` `options.packageDir` and `options.packageCsproj` say where the package and the project file are.

## How packages behave (why order and size matter)

- The backend imports `ConfigMigrations/*.shaconfig` on EVERY start, in **ascending file-name order**, skipping a package whose **md5** it already applied. A package
  already applied is not re-applied even if its forms were changed in the database since: only a changed package (new md5) is imported again.
- A LATER-named package overwrites the forms of an earlier one (**later name wins**).
- A form changed in the database but not carried by a package is lost on the next import or database reset. So every PR that changes forms ships a freshly exported
  package with ALL the forms it changed: that is how the forms stay in the repository as the reference.
- Therefore: name the package later than every package already on the target branch (`export-package` refuses otherwise), export AFTER the reconcile on top of the
  merged branch packages so it overwrites them last, and export a **subset** (only the forms you changed, dependencies off): the smallest blast radius. An all-forms
  package silently reverts every form it carries that someone else changed after your last read.
- Register the package in the Application `.csproj` (`None Remove` + `EmbeddedResource`, mirroring the previous entry): `export-package --apply` does it.
- Starting a backend that carries newer packages re-imports them and overwrites the forms they hold. Take the "ours" snapshot first ([merge-reconcile.md](merge-reconcile.md)
  step 3) and re-verify the changed forms after the first boot that includes your package.

## Steps

1. The report's section "what to export" lists the exact forms (generated from the ledger, [tracking.md](tracking.md)). Add forms of other modules explicitly when needed.
2. Close every Configuration Studio tab that was open before the pushes, then reopen: a stale designer tab saves its old markup over the reconciled form (hazard H27).
3. Verify the pass first: the rule's dry run must print `forms changed 0`.
4. Reference drift check right before exporting: the reference site keeps publishing versions. `shrec.py snapshot` and compare the versions with what you hold; merge any
   newer one ([merge-reconcile.md](merge-reconcile.md) step 6), re-run the rules, then export. For forms with an unpublished Draft on the reference, agree with their
   author whether it is published before or after the import.
5. `shrec.py export-package --target local|deployed (--forms Module/Form,... | --forms-file <file> | --only a,b [--module M] | --all-module M) [--extra Module/Form,...]
   [--target-branch <ref>] [--package-dir <dir>] [--csproj <file>] [--apply] --reviewer-approved`. Without `--apply` it is a dry run that writes only under `work/exports/`;
   with `--apply` it copies the package into the package directory and registers it in the csproj (both come from `options.packageDir` / `options.packageCsproj` or the flags;
   there is no default, repo-relative paths are joined onto the project root, absolute paths target another checkout). The server-generated package name must sort AFTER
   the newest package on the target branch (`--target-branch`, or `options.targetBranch`) and after the newest in the working tree; without a target branch the export is
   refused. `--reviewer-approved` (aliases `--approved`, `--owner-approved`) records the user's explicit go-ahead: pass it only after the user said to export in this session,
   never on your own judgement. `ExportPackage` itself is a read-only query; the export is logged as an `export` ledger event. Run `shrec.py export-package --help` for the exact
   options.
6. `shrec.py verify-package <package.shaconfig> --forms-file <list> --compare-role local`: every listed form is in the package and equals what that role's server holds (a stale
   export cannot ship); it also reports forms that still mention a pre-upgrade schema name for the target version. Add `--expect Form=substring` / `--forbid substring` for hot
   fixes that must not regress. Read-only; exit code 1 on any failed check.
7. Commit the package and the csproj by explicit path. Never commit credentials or local-only configuration. Never merge the PR.

## Not forms: the other things that must travel

Reconciliation can change configuration that is not a form. None of it is carried by the forms-only subset package, so record each item
(`shrec.py note --category follow-up --text "..."`, or `shrec.py other --kind <kind> --what "..."`) and say in the PR how it travels:

- **Theme settings** (Default UI theme: Components defaults such as Panel `accentStyle`, Data Table row geometry and header colours). They live in the database and travel
  with the settings, not with the form package. Read and write them with the `appKey` (`default-app` unless `project.json` says otherwise): without it the tenant-level
  object comes back, a different and stale value that must never be edited. Write through `Settings/UpdateValue {name, module, appKey, value}` after merging into the
  current value, backing it up and reading it back; record it with `shrec.py other --kind theme-settings --what "..." --backup <file>`.
- **Reference lists and their items.** Reference-list data repaired locally (for example soft-deleted items restored) is data: it is not exported if the reference already has
  it; a backend whose enum lacks the items can delete them again at startup. New or changed reference lists are configuration items: include them in the package or carry them
  through the backend migrations, and say which.
- **Notification templates and workflow definitions.** These are configuration items too. A package exported through Configuration Studio can include them; a workflow's BPMN
  schema is written through the workflow API (`UpdateSchema`, [api-by-version.md](api-by-version.md)) with the same backup and read-back guards. Record what you changed and
  how it travels.
- **File blobs** (document templates, workbook templates stored in the file store) are not configuration: the target's file store must hold them. Record any gap as a
  `file-blobs` note.
- **Backend migrations** travel with the backend, not the package: see below.

## Backend first, forms second

Deploy the backend that contains the target-version fixes AND the merged branch; then import the reconciled package. Importing the forms first would be undone by the
backend start. After import, smoke-test the high-focus cases of the business test plan on the target environment.
