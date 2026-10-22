# Merge-reconcile: make a feature branch's new form changes work on reconciled forms

Contents: 0 pin a run | 1 branch off and merge | 2 migrations | 3 snapshot and start the backend | 4 detect what the branch changed | 5 sync untouched forms | 6 three-way merge | 7 re-run the rules | 7b detect | 8 verify | 9 report | before the PR | 10 export, commit, PR | moved components

Use when a feature branch (or a newer `.shaconfig`) authored against the OLD framework version has to land on the upgrade branch whose forms were
already reconciled. The branch keeps authoring forms and migrations for the old version; the reconciled forms carry the rule fixes. A naive merge either loses the
branch's change or loses the reconciliation. The method below keeps both: merge safely, convert migrations, detect what the branch really changed, three-way merge
those forms onto the reconciled forms, re-run the rules on only those forms, detect the traps a faithful merge brings in, verify, then HAND OVER: print a summary of
the forms changed and what to export, and ask the user whether to export and open the PR. The tool never exports or opens a PR on its own, and never merges.

Prerequisite: the intake ([intake.md](intake.md)) is done: branch and target branch, environments, credentials, confirmed write target. Commands are
`python <skill>/scripts/shrec.py <command>` unless a `git` command says otherwise. Every tool command takes `--help` for its exact options.

```
0 pin run -> 1 branch off + merge -> 2 migrations -> 3 snapshot, start backend (ask) -> 4 detect -> 5 sync untouched forms
-> 6 three-way merge changed forms -> 7 rules on those forms -> 7b detect on every merged form -> 8 verify (Definition of Done)
-> 9 report + hand-over summary -> before the PR checklist -> 10 ONLY IF THE USER SAYS SO: export, commit, PR (never merge)
```

## 0. Pin one run id for the whole session

`export SHREC_RUN=merge-<branch>-<date>` (PowerShell `$env:SHREC_RUN = '...'`). Pilot, fleet, re-run, restore and the notes you record then share one backup folder
and one report.

## 1. Branch off the target and merge, in the project checkout (no git worktrees)

Do it in the user's own clone. Do NOT use `git worktree`: extra worktrees have no `node_modules`, their own build output and ports, and teammates get lost in them.
One checkout, one new branch.

```bash
git status --short                 # must be clean: if the user has uncommitted work, STOP and ask them to commit or stash it themselves
git fetch origin
git checkout -b <your-branch> origin/<target-branch>
git branch --unset-upstream        # REQUIRED: branching off origin/<target> makes the new branch TRACK it, and a bare push would push to the target
git merge --no-ff origin/<branch>  # do not push yet
```

Check with `git rev-parse --abbrev-ref @{u}`: it must fail ("no upstream configured"). The first push is explicit, `git push -u origin HEAD`, once the user has said
yes (step 10).

Tell the user before the checkout: switching branches changes the files under any backend or portal they run from this checkout (the running process keeps the old
build until they rebuild). Ask them to confirm, and never stop, restart or rebuild their backend yourself. When the work is finished, tell them how to go back
(`git checkout <their previous branch>`).

Conflict rules (decide, then tell the user what you decided):

| Conflict | Resolution |
|---|---|
| Application `.csproj` list of ConfigMigrations packages | union of both sides (keep every `None Remove` / `EmbeddedResource` pair, name-sorted) |
| `*.shaconfig` files | take the branch's files as they are (they are additive); never hand-edit one |
| Backend C# written against old-version APIs | keep the branch's intent, port to the target version (for 0.46: `GetAll()` awaited becomes `GetAllAsync()` (VSTHRD103), no `IsLast` / `VersionStatus` on configuration items, use the 0.46 enum helper). The build must pass with analyzers as errors before anything is started |
| Frontend packages | keep the target's API, re-apply the branch's functional change on top |
| Local-only config (connection strings, personal settings) | keep the local value; a real change goes in a commit of its own that says so |

Resolve the conflicts, `git status` to check, stage the resolved paths explicitly (`git add <path> ...`, never `git add -A`), then finish the merge with a plain
`git commit` WITHOUT path arguments (Git refuses a partial `git commit <paths>` while a merge is in progress), then build. Do not push.

## 2. Migrations: the boot breaker

Branch migrations that touch framework tables (`Frwk_*`, `Core_ShaRole*`, `dbo.Frwk_GetRefListItem` on the old schema) fail on a database of the newer schema and stop
the backend booting. A database that already applied them hides the problem: the TARGET database's `dbo.VersionInfo` is the truth.

```bash
SHREC_SQL='<connection string, in your own shell>' shrec.py migration-check        # or: --applied-file versions.txt; --tree <dir> overrides options.migrationPaths
```

It lists every `[Migration(n)]` in the tree that is not applied on the target and flags references to the old schema (the project's `options.migrationPaths` says
where migrations live). Convert each flagged migration in place (while unapplied there) to the new `frwk.*` schema: items need an item row plus a revision row plus
a type table with shared ids, `permissioned_objects` needs `md5=''` and `parent=''`, reference list items need `color/description/icon/short_alias=''`. Verify the
SQL against the live target schema, not from memory. Run this at EVERY merge, before the PR. See also `shesha-developer:upgrade-to-0-46`
(`references/migration-failures.md`).

## 3. Snapshot the reconciled forms, then start the merged backend (ask first)

- Take the "ours" snapshot BEFORE the merged backend starts: on its first start it imports the branch's new configuration packages and OVERWRITES those forms with
  old-version markup. `shrec.py snapshot` (deployed and/or local).
- Never start, stop or rebuild a developer's backend yourself. Ask the user to start the merged backend (on a second port pair, for example `:21031` / `:3001`, if
  the IDE owns `:21021` / `:3000`) and record that host (`shrec.py init --local-api ... --local-portal ...`, then `confirm-target`).
- After the start, check the imported packages appear in the import audit and the backend answers (`shrec.py probe-env local`).

## 4. Detect what the branch changed

```bash
shrec.py branch-changed --source-ref origin/<branch> --target-ref origin/<target> --extract
shrec.py merge3 delta --forms a,b --full  # component-level delta base -> branch: the branch's real intent, without migration noise
```

(`sprint-changed` is the old name of this command and still works as an alias. It compares git refs, not the working tree, and reads the package folder from `options.packageDir`; `options.sourceRef` / `options.targetRef` can supply the refs.) Output `work/merge/branch_changed.json` (`merge3` also reads an older `sprint_changed.json`): per form `changed` (really
different), `new_form` (no earlier export), or re-exported unchanged (skip). Raw exports go to `work/merge/base` and `work/merge/theirs`. For a single `.shaconfig`
instead of a branch: `branch-changed --package <file> --target-ref <ref>`. Report the number of forms: it is the export size and the review size.

## 5. Bring the already reconciled copies of the UNTOUCHED forms (decision point)

The deployed upgraded site may hold the team's later fixes (designer edits, hot fixes) that the local database lacks. For every form the branch did NOT change, the
newer copy wins:

```bash
shrec.py sync-forms --from deployed --to local --exclude-file <path printed by branch-changed>           # dry run: lists the forms that differ
shrec.py sync-forms --from deployed --to local --exclude-file <path printed by branch-changed> --push    # whole-run snapshot + backup per form
```

Ask first when the local database is itself the source of truth. Do NOT blind-import the deployed `.shaconfig` (it overwrites the branch's newer forms) and do NOT
replay only your own rules (it loses the reviewer's designer edits).

## 6. Three-way merge of the forms the branch changed

```bash
shrec.py merge3 merge --all --ours deployed             # dry run: conflicts listed per form ("ours kept" = a scalar both sides changed)
shrec.py merge3 merge --all --ours deployed --push      # backups first, read back
```

`--ours` selects the reconciled copy: `same` (the target row itself, the default, only when it still holds the reconciled markup), `local`, `deployed`, `reference`, or a
snapshot directory from step 3 (`dir:<path>`). Rule per node: one side changed, that side wins; both changed, recurse by key / component id; scripts are line-merged with `git merge-file`;
a scalar both sides changed keeps OURS and is reported. Decision points:

- Review every "ours kept" line. If the branch's value must win for a path, re-run with `--theirs-wins "<path fragment>|<fragment>"`.
- A NEW form needs no merge (the backend import created it): go to step 7.
- A branch edit on a form of a vendor module that the project overrides: `--prefer-module <Module>` applies it to the same-named copy in that module (the override).
- Hot fixes made on the reference site that no branch package carries yet must be carried by hand with an anchored transform (a project rule). Check the FINAL
  package after the first boot, because packages re-import on every boot; tell the branch's authors their source needs the same fix.
- The reference may have published newer versions than the branch knows: `shrec.py snapshot`, compare the `version` in the reference index with the branch's, and
  merge any newer one the same way (`merge3` with `--ours`).

## 7. Re-run the rule groups on only those forms

```bash
shrec.py apply --only-file <changed.json>                                    # dry run
shrec.py apply --only-file <changed.json> --rules <ruleA>,<ruleB> --only <2-3 forms>   # pilot (dry, then --push)
shrec.py apply --only-file <changed.json> --push                             # whole-run snapshot first
shrec.py apply --only-file <changed.json>                                    # must print "forms changed 0"
```

Always restrict (`--only` / `--only-file`): a rule that scans every form must not touch the rest. Marker rules must be re-run after a merge that overwrote a form
([failure-modes.md](failure-modes.md)). Pilot first, the reviewer checks, then the rest. Then scan the merged forms for the patterns a branch keeps
re-introducing (each has a rule or a documented fix in [pack-0.46.md](pack-0.46.md)):

| Grep in the merged markup | Mechanism |
|---|---|
| `{{data.id}}` / `data?.` inside a subform's filters, hidden/editMode code, queryParams | subform `data` is empty on 0.46 (H46, H49): read an id the host publishes in `page.state` |
| `globalState.` / `.selectedRow` / `refreshTable` | table contexts are not in `globalState` (H41) |
| `delete data.` followed by `...data` | the delete is ignored (H39) |
| an api `subForm` with a `properties` list | the list must name every field the hosted form binds or reads (`subfetch`, H28) |
| `readOnly` as a code property on buttons | buttons honour only `disabled` / `editMode` (H15) |
| `labelCol: 0` on a subForm | hides every label inside (H14) |
| a `subForm.formId` naming a framework form the target does not ship | empty box (H45) |
| a misspelled metadata or property key in a script or `saveMetadata` | the backend reads only the exact key; the call fails or sends no id (found by the request audit) |
| a `parentId` that names an old container | the designer re-nests the component (H47) |

## 7b. Detect: the traps a faithful merge brings in (run on EVERY merged form)

The branch's markup is correct for the OLD version; applying it faithfully is what breaks on the new one: a stale `parentId` re-nests a new panel, a sub-form Save
reads the wrong form, a Url list leaks other records. `shrec.py detect` is static and read-only: it reports, it never writes. Checks: `parent-id` (H47),
`url-endpoint-query` (H50), `subform-script-scope` (H49), `hidden-row-field` (H52), `required-mustache-subform` (H51).

```bash
shrec.py detect --role local --only <form>,<form>                      # or --markup <file|dir>; --help lists the options (hosted / row / nested forms)
shrec.py apply --only-file <changed.json> --rules normparent           # dry run, then --push: parentId normalised to the markup tree (H47)
```

Every finding is a hazard of the target version's catalogue ([pack-0.46.md](pack-0.46.md), `render-hazards-046.md` H47-H53): fix it with an anchored transform, then
MEASURE it (`probe-scope`, `audit-requests`, `dom-chain`), do not guess. A new or moved component needs its `parentId` set to the real parent BEFORE the push; re-read
the form some minutes later and diff it against what you wrote (the designer normalises and can re-nest).

**Re-import trap.** Packages import in file-name order on every boot and skip by md5: a later-named package overwrites the forms of earlier ones. After you export a
package (step 10) and the first boot that includes it, re-verify the changed forms and the branch's own: the boot may have replaced them with whichever package
sorts last. Never conclude from the state before that boot.

**Tell the branch authors (describe it for the PM; never create a work item).** Without a change in their source the next merge reintroduces every one of these:
stale `parentId`s in the package (H47), a Save script that reads a sub-form through `data` / `form.getFieldValue` (H49), a list `endpoint` that carries `filter=` /
`sorting=` / `properties=` query text (H50, a data leak on 0.46), hidden data-holder fields (H52), and `{{data.id}}` in nested sub-form filters (H51). Put this in the
hand-over message as "for the PM to triage".

## 8. Verify

See [verification.md](verification.md): the Definition of Done (fresh browser context, at least 3 loads) is the bar: placement, request audit, data audit against the
database, row content, write path with cleanup of only your own test row, read path, idempotence AND fixed point, re-read after minutes, the reviewer exercising it in
their own browser. Also: second run `forms changed 0`, a scenario matrix per page, side by side with the reference, the business test plan on localhost,
`shrec.py e2e-save ... --push` for forms with a Save. Record results with `shrec.py verify`. Without the measured points, say "pushed and read back, UNVERIFIED in browser",
never "done".

## 9. Report and hand over (the end of the cycle: NO export, NO PR)

`shrec.py report` prints the summary and saves it under `work/reports/`. Record follow-ups first: `shrec.py note --category backend-migration --text "..."`. The
summary tells the user, in plain language:

- WHERE the changes were written (local or deployed) and which environment was only the read-only reference;
- the forms that were changed (by rule), skipped and failed;
- the backups and the exact revert command;
- WHAT TO EXPORT: the list of changed forms (and any non-form configuration), plus the other things the PR will need (the merge, converted migrations);
- what is still unverified.

Do NOT export a package, commit, push or open a PR at this point. Ask with `AskUserQuestion`: "Are you happy with the result and have you tested it?" Options:
"Not yet - I will test first (default)" / "Yes - export the package and open the PR for me" / "Yes - I will export and open the PR myself". Only the second option lets
you continue to step 10. Repeat the question whenever the user comes back after testing.

## Before the PR (checklist, ask the user to do the browser parts)

- Re-run `shrec.py snapshot` for the reference and compare its `version` values with the branch's and with the last snapshot; a failed snapshot (HTTP 500) is not a
  pass: retry, and say so if an earlier snapshot was used. Merge any newer reference version the same way (`merge3` with `--ours`).
- Ask the user to CLOSE every Configuration Studio tab open on the changed forms (a stale tab saves old markup over the push) and to clear IndexedDB `forms` (and
  `form:<appKey>`, `form_lookup:<appKey>`); if their result disagrees with your fresh-context measurement, trust the measurement.
- `detect` clean, `normparent` dry run `forms changed 0`, every fix transform "already applied".
- Items not yet verified (other roles, mobile/tablet widths, empty lists, more than one page of rows, deleted or other-author rows, the business test plan) are listed
  as unverified in the PR body.
- The local `appsettings.json` and the credentials file are never staged (explicit paths only).

## 10. Only after the user says yes: export, commit, PR

1. Export a SUBSET package ([packages-and-export.md](packages-and-export.md)): packages import by ascending file name and skip by md5, so a later-named package
   overwrites earlier ones. Export ONLY the forms this run changed, named later than every package already on the target branch, AFTER the reconcile on top of the
   merged branch packages so it overwrites them last. `shrec.py export-package ... --apply --reviewer-approved` (the flag is the user's yes), then
   `shrec.py verify-package`.
2. Stage explicit paths only (the merge, the converted migrations, the package and csproj), commit (the hook runs in the project checkout; never bypass it), push.
3. Open the PR against the target branch, body = problem, root cause, fix, migration/deployment impact, verification evidence. Link it to its work item from the PR
   side only if the user gave the id. Never create a work item (describe the finding for the PM) and never merge the PR.
4. Tell the user how to return to their previous branch.

## Moved components

When the branch wraps existing components in a new container or moves them to another panel, `merge3 merge` treats that as a MOVE, not a delete plus add: the
component is dropped from its old parent, and at its new place our reconciled version is merged with the branch's changes (the branch's raw old-version copy is
never used for a component that already exists in the reconciled form). The dry run lists each one as `moved by theirs ...`. Before a `--push`, read those notes
and check the component count: nothing in `ours` may be lost (`merged = ours + the branch's new components`).
