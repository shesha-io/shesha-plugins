# Workflow

Contents: 0 preconditions | 1 snapshot | 2 sweep | 3 assess | 4 diagnose | 5 rule | 6 pilot | 7 fleet | 8 verify | 9 report | 10 export | caches | backups and restore | tooling traps

All commands are `python <skill>/scripts/shrec.py <command>`. The intake ([intake.md](intake.md)) decides where writes go: the confirmed LOCAL backend by default,
a deployed upgraded site only after the user's explicit go-ahead (`--target deployed`), the reference NEVER. Dry run is the default; a write needs `--push`.
Flow variants: [full-upgrade.md](full-upgrade.md), [merge-reconcile.md](merge-reconcile.md).

```
snapshot -> sweep (capture) -> assess -> diagnose -> rule -> pilot -> fleet -> verify -> report -> export
```

## 0. Preconditions

- The local backend answers (`shrec.py probe-env local`) and the portal renders a page. If not, ask the user; never start or restart it yourself.
- Credentials in `.shesha-reconcile/credentials.local.json`, the project configured (`init`), the write host confirmed (`confirm-target --api <host>`).
- Pin one run id for the session (`export SHREC_RUN=<name>`; PowerShell `$env:SHREC_RUN = '<name>'`) so pilot, fleet, re-run, restore and report share one backup
  folder and one ledger run. `SHREC_BATCH=<name>` labels one rule rollout or one merge inside the run.
- `shrec.py versions` shows the pack and the hazard catalogue of the TARGET version; `shrec.py plan` shows every rule's fate for it.

## 1. Snapshot (read-only)

`shrec.py snapshot [reference] [local] [deployed] [--modules A,B]` (default roles: reference and local) writes each role's forms under
`.shesha-reconcile/work/snapshots/<role>/<module>/<form>.json` plus an index per role. A role whose version is below 0.45 (a versioned 0.43 reference) keeps only
the Live rows (`versionStatus == 3`); from 0.45 on there is one row per form. Rules that compare with the reference (for example `layout`, which skips containers whose reference
counterpart stored its own minimum height) read the reference snapshot. Refresh it when the reference changes.

## 2. Sweep (read-only, headless)

`shrec.py capture <reference|local|deployed> [start] [end]` renders every page in the project's `pages.json` (module, form, and a real record id that exists in BOTH
databases for details pages) on one role and writes a full-page screenshot per page and per tab (nested tab sets too) plus a probe JSON under `work/sweep/<role>/`. The
viewport is `options.viewport` (default 1568 x 950). Slice the page list with start/end indexes and run slices in parallel on the remote reference; run at most two slices
against a local dev server. Add pages to `pages.json` when the user names a new
one.

The portal dev server is slow under load: if a page sits on "Initializing..." or throws `ChunkLoadError`, reload it. Never interpret a half-loaded capture.

## 3. Assess (fan out, read-only)

Dispatch the `shesha-developer:reconciliation-assessor` agent (Sonnet, read-only), one per slice of about 9 pages, in parallel, with:

- the screenshot pair and probe JSON pair per page and tab (reference and target);
- the **noise list** from `project.json` (`noise`: data differences between the two databases, environment badges, the upgraded default font, offsets under 6px,
  and whatever else the project listed);
- the **already-fixed list** from `defects.jsonl` (`shrec.py defect list --status fixed`);
- `HAZARDS` = the hazard catalogue of the target version named by the rule pack (`shrec.py versions` prints it).

Merge their findings into the defect log (`shrec.py defect add ...`, one entry per distinct defect, with the pages and components it affects). Never treat an
assessor finding as a fact: it is a hypothesis for the diagnose step.

## 4. Diagnose a new defect

- Reproduce on the running local app: computed styles, the component's `data-sha-c-id` / `data-sha-c-name` / `data-sha-c-type`, the owning form
  (`data-sha-c-form-name` on a subform wrapper, `data-sha-form-name` on the page form).
- Read the framework source of the TARGET release tag (the tag matching the target version, not a neighbouring one) and the hazard catalogue of the target version
  (`shesha-developer-0-46:shesha-form-edit` `references/render-hazards-046.md` for the 0.46 line).
- A table with no rows: read the `Entities/GetAll` request body and the error text (intercept it, or read the browser network log) and compare with the same page
  on the reference. A 400 with `null` inside an `and` filter is hazard H34. Use `shrec.py audit-requests <page>` (loads the page several times in fresh browser contexts
  and never de-duplicates by path), `shrec.py probe-scope <Module>/<form> --component ... --prop ...` (a TEMPORARY dump of what a script really sees, local role only,
  always removed afterwards) and `shrec.py dom-chain <page>` (geometry and matched CSS rules per ancestor). Compare one page side by side with
  `shrec.py compare <page path> [--labels]`.
- Prove the fix without pushing when possible (route interception on `ConfigurationItem/GetCurrent` serving patched markup), otherwise on ONE local form.
- **A data difference is not a defect.** Check the record on both databases through the API first; a table that is empty on the target because the record has no
  rows is not a rendering bug.
- Measure, do not guess. Probe first, then change ([failure-modes.md](failure-modes.md)).

## 5. Rule

Write the fix as a rule: a pack rule when it is generic, a project rule in `.shesha-reconcile/rules/` when it is tied to this project's forms. The contract,
anchors, markers and self-tests are in [rule-authoring.md](rule-authoring.md). In short: anchored, idempotent, never deletes a component (hide it), keeps an
author's explicit value, syntax-gated, options instead of constants.

## 6. Pilot

```bash
shrec.py apply --rules <rule> --only <formA>,<formB>            # dry run: notes + preview files, nothing written
shrec.py apply --rules <rule> --only <formA>,<formB> --push     # whole-run snapshot first, backup per form, read-back
```

Then clear the browser form caches (see "Caches"), measure (screenshot, `shrec.py compare <page path>`, `shrec.py dom-chain`), and ask the reviewer to check the pilot forms in
their own browser. Do not roll out before they confirm. Record the defect as `pilot` (`shrec.py defect set D-<n> --status pilot`).

## 7. Fleet

```bash
shrec.py apply --rules <rule>               # dry run: forms changed N of M, changes per rule
shrec.py apply --rules <rule> --push
shrec.py apply --rules <rule>               # must print "forms changed 0"
```

Report the number of forms touched before pushing: it is the export cost, because every touched form must be re-exported. Always restrict a rule that scans every
form (`--only` / `--only-file`) when only some forms are in scope.

## 8. Verify

- The second dry run prints `forms changed 0` (persistence and idempotence only).
- Re-sweep the affected pages and re-run the assessor on them.
- Exercise the feature, not just the markup: the Definition of Done in [verification.md](verification.md) (fresh browser context, 3 loads, request audit, data
  audit, write and read path). Persistence checks alone never justify "done".
- Record each point with `shrec.py verify --kind <item> --result ok|fail|unverified --detail "..."`.
- The reviewer checks in their own browser: that is the completion signal.

## 9. Report (the last step of EVERY run)

`shrec.py report` (`--run <id>[,<id>]`, `--all`, `--html`, `--out <file>`; the default window is 12 hours before the latest push) prints a plain-language report derived from the ledger ([tracking.md](tracking.md)): where changes were written
(local or deployed, with the API url, and which host was only the read-only reference), forms updated (by rule), skipped (anchor missing / already applied) and
failed, the backup location and the exact revert command, WHAT TO EXPORT (forms and non-form configuration), retire candidates, rules applied and the defect each
addresses, verification results and what is still unverified, next steps. Record what the ledger cannot know first: `shrec.py note --category <backend-migration |
file-blobs | follow-up | data> --text "..."`.

## 10. Export

Only when the user says so after the end-of-run question ([intake.md](intake.md)). The method is in [packages-and-export.md](packages-and-export.md): a subset package of
the changed forms, `export-package --reviewer-approved`, `verify-package`, explicit paths on commit, never merge the PR.

## Caches after every push

A write that read back correctly can still look unchanged. After EVERY push:

- Browser: delete IndexedDB `form:<appKey>`, `form_lookup:<appKey>` (appKey is `default-app` unless `project.json` says otherwise) and the legacy `forms`, then reload.
  Delete them from a static page (for example `/favicon.ico`) where no app holds connections.
- Designer: close the form's Configuration Studio tab and reopen it. **A stale designer tab saves its old markup over the push** when it is saved or auto-saved
  (hazard H27). Ask the reviewer to close every Configuration Studio tab open on the changed forms BEFORE the push and again before export.
- The reviewer's browser cache can disagree with a fresh-context measurement (old markup in their IndexedDB `forms`): ask them to clear it and trust the
  fresh-context measurement (a new browser context, at least 3 loads).
- The designer can also normalise and re-nest a form some time after a push (stale `parentId`, hazard H47): re-read the form a few minutes later and diff it
  against what you wrote.
- Before concluding an edit "had no effect", clear the caches. A stale cache is the most common false negative.

## Backups and restore (mandatory, automatic)

Nothing is written without a backup, and the push layer does it itself:

1. At the start of a `--push` run the full row of EVERY form about to be touched is saved to `work/backups/<role>/<run id>/snapshot/` with a `manifest.json`
   (module, name, id, modelType, sha256 of the markup, host). Any other write path gets the same snapshot lazily, form by form.
2. Immediately before each write the current row (markup, modelType, id, module, name, timestamp, role, host) is saved to `.../before/`, re-read from disk and
   compared. If that fails the write is refused. The markup sent is kept in `.../after/`; dry runs leave only previews.
3. After the write the form is read back by id: markup and modelType must equal what was sent, else the attempt is logged as failed.
4. `UpdateMarkup` overwrites `modelType` with the value sent (null when omitted), so the stored value is always carried forward.

Revert with `shrec.py restore` (itself a write: dry run by default, same host confirmation, backs up the current row first, reads back, logs). Run
`shrec.py restore --help` for the selectors:

```bash
shrec.py restore --list [--target local|deployed]                                        # runs that have backups
shrec.py restore --run <run id> --target local --form <Module/name> [--source before|snapshot] [--push]   # one form
shrec.py restore --run <run id> --target local --rule <rule> [--source ...] [--push]                       # every item that rule pushed
shrec.py restore --run <run id> --target local --all [--source ...] [--push]                               # the whole run (omit --run for the newest run)
```

A form the run CREATED is never deleted automatically: the tool reports it and prints the id so it can be deleted by hand in the designer once the user agrees.
`before` (default) returns each form to its state immediately before the run first wrote it; `snapshot` returns it to its state at the start of the run. A blanket
restore also undoes later rules that touched the same form: prefer restoring one rule and re-run the other rules' dry run afterwards. Only markup and modelType
are restorable (what `UpdateMarkup` writes). A backup refuses to restore on another role or host. Clear the browser form caches afterwards.

To unwind a workaround the framework has since fixed, use `shrec.py retire` instead of restore ([rule-authoring.md](rule-authoring.md)).

## Tooling traps

- **Create scripts and form files with the editor / Write tool, never with a shell heredoc** when the content has escapes (`\n`, `\"`, `\\n`): they get
  corrupted.
- **Absolute paths for another checkout.** Tools that join a package directory or project file onto the repository root keep an absolute second argument and
  resolve a relative one inside the skill's own checkout. Pass absolute paths to target another checkout.
- **Console capture is limited.** Browser helpers keep only the first part of each `console.error` / `console.warn` message. In a probe print the value first and
  the key list second, or raise the limit.
- **The headless admin session shows Shesha's "form info card"** (the `Module/form` name with an edit icon). It is designer chrome, not a bug and not what end
  users see: ignore it in screenshots and geometry.
- **Local config never gets committed.** The developer's local `appsettings.json` (their own database and connection string) and the credentials file are never
  staged: stage explicit paths only, and keep the local value on every merge conflict.
- **Read-only helpers.** `shrec.py sqlq "<single SELECT>"` runs one SELECT against a SQL Server (the connection string only from `SHREC_SQL` in the user's own shell; it is never printed
  or stored). `shrec.py leakcheck --deny-file <path>` scans a tree for terms that must not appear in it (client names, hostnames, record ids; add `--guid` for GUID literals); the
  deny list lives in the private project, never in the skill.
- **Temporary instrumentation is removed after the measurement.** Script-scope and row-data dumps injected into a component script for one measurement must be
  taken out again; the push log shows each add and remove.
- **The adminportal dev server under load** produces half-loaded captures: reload and recapture.
