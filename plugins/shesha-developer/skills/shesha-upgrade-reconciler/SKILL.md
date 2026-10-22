---
name: shesha-upgrade-reconciler
description: Reconciles Shesha form configuration after a framework upgrade (e.g. 0.43 -> 0.46, or a patch release such as 0.46.0 -> 0.46.1) so forms look and behave as they did on the pre-upgrade reference site. Measures both sites page by page, applies version-aware, idempotent rule packs with mandatory backups, read-back and restore, retires workarounds once a release fixes the bug, merges branch form changes onto reconciled forms, and tracks everything in a committed ledger and defect register with a report and export list. Project-agnostic: each project keeps its own .shesha-reconcile/project.json. Use when forms differ after a Shesha upgrade (misaligned labels, phantom gaps, blank HTML renders, empty status tags, script errors, disabled fields, empty tables), when rolling a fix across many forms, when merging a branch built on the old version, when a new release may make workarounds obsolete, or when preparing the reconciled configuration for export.
---

# Shesha upgrade reconciler

Generic engine + version rule packs + a per-project profile. The framework knowledge for each target line lives in the
matching versioned plugin (0.46: `shesha-developer-0-46:shesha-form-edit` `references/render-hazards-046.md`); this
skill turns the hazards that recur across many forms into rules, applies them safely and tracks the result.

Run everything with `python <skill>/scripts/shrec.py <command>` from inside the project repository (or `--project <repo>`).

## Hard rules

1. **The reference site is never written.** Every reference host is GET-only in the API client, aborted for writes in
   the browser session, and refused by every write path. If asked to write there: refuse - it is what everyone compares against.
2. **Dry run is the default; a write needs `--push`.** Writes go to the ONE host the user confirmed this session
   (`confirm-target`). A deployed site is written only after the user says so in this session
   (`authorise-deployed`, expires after `SHREC_DEPLOY_TTL_MIN`, default 120) plus `SHREC_DEPLOY_CONFIRM=<exact deployed API url>`.
   Hosts are compared canonically (case, default port, trailing dot, loopback aliases), so a reference site cannot be
   written under another spelling; urls carrying user info are refused.
3. **Backups are mandatory and automatic.** A whole-run snapshot before the first write, a per-write backup verified
   from disk, a read-back after the write. No backup, no write. A write that was sent but not confirmed is ledgered
   `written-unverified`, never retried blindly, and still listed for export and restore. `restore` puts backups back
   (itself a write, same rules).
4. **Configuration level only.** Each component's own settings, theme settings, form structure. No portal CSS files,
   no framework patches, no new hidden stylesheet components. Prefer one theme-level change over a per-form fleet
   (`shesha-design-system`); every touched form must be re-exported.
5. **Pilot first.** Run a rule on 2-3 forms, let the reviewer check them in their own browser, then the fleet; run the
   fleet twice and expect `forms changed 0`. Report how many forms a rule touches (that is the export cost).
6. **Persistence is not function.** A 200, a read-back or `forms changed 0` proves the write persisted, not that the
   page works. Until the Definition of Done is measured ([references/verification.md](references/verification.md)),
   say "pushed and read back, UNVERIFIED in browser".
7. **Probe and measure; never guess.** Dump the real script scope (`probe-scope`), the real requests
   (`audit-requests`) or the real geometry (`dom-chain`, `compare`) before changing a script, filter or layout. Remove
   temporary instrumentation afterwards. A data difference between the two databases is not a defect.
8. **Never**: hand-build or commit a `.shaconfig` (export only through the ExportPackage API, on the user's go-ahead),
   publish a Draft to Live, stop/restart/rebuild a developer's backend, create backlog work items, merge a PR, stage
   everything, commit credentials or local-only config. Credentials are typed by the user into the gitignored
   `.shesha-reconcile/credentials.local.json` (`init-creds`); never ask for, print, log or read back a secret.
9. **Never touch the user's uncommitted work.** Ask before creating a branch or worktree; ask them to commit or stash.
10. After every push: clear the browser form caches (IndexedDB `form:<appKey>`, `form_lookup:<appKey>`, `forms`) and
    have every open Configuration Studio tab on that form closed - a stale designer tab saves the old markup over the push.

## Step 0 - detect, then ask once

Detect first: `shrec.py status`, `shrec.py versions` (configured versions, versions read from the repo's package
pins, and the pack that applies), git branches, whether the local stack answers (`probe-env local`; never start it).
Then ask EVERYTHING in ONE `AskUserQuestion` call (purpose, source, where to write, reference site), recommended
option first and detected values pre-filled, then ONE plan confirmation that also records the write target.
Full flow, options and the plan template: [references/intake.md](references/intake.md).

New project: `shrec.py init --name <n> --modules <A,B> --reference-api <url> --reference-portal <url>
--reference-version <v> --local-version <v>` creates `.shesha-reconcile/` (see [references/tracking.md](references/tracking.md)),
then `init-creds`, then `probe-env <role>` for each role.

## Workflows

| Purpose | Flow |
|---|---|
| Full upgrade of all forms | [references/full-upgrade.md](references/full-upgrade.md); procedure detail in [references/workflow.md](references/workflow.md) |
| Merge a branch built on the old version onto reconciled forms | [references/merge-reconcile.md](references/merge-reconcile.md) |
| One rule on some forms | `apply --rules <id> --only <forms>` (dry run, then `--push`), verify, report |
| Patch-release upgrade (e.g. 0.46.0 -> 0.46.1) | set the new target version (local/deployed) in project.json, `plan` (rules now fixed by the framework), prove each fix on the target, `retire --rules <ids>` pilot then fleet |

```bash
python shrec.py plan                                            # every rule's fate for reference -> target versions
python shrec.py snapshot reference local                        # read-only form snapshots
python shrec.py capture reference 0 25 ; python shrec.py capture local 0 25   # page sweep + defect probes
python shrec.py apply --rules <id> --only <formA>,<formB>       # dry run: notes + previews, nothing written
python shrec.py apply --rules <id> --only <formA>,<formB> --push
python shrec.py apply --rules <id> --push ; python shrec.py apply --rules <id>   # fleet, then must print "forms changed 0"
python shrec.py detect --role local                             # static hazard detectors on the target forms
python shrec.py restore --run <run id> --all                    # revert (dry run; add --push); also --form, --rule
python shrec.py report                                          # LAST STEP of every run
```

Set `SHREC_RUN=<name>` once per session so pilot, fleet, re-run, restore and report share one run and one backup
folder; `SHREC_BATCH=<name>` labels a rollout in the ledger.

## Versions and rule packs

- A pack (`scripts/packs/<line>/pack.json`) targets one framework line (`target: ">=0.46.0 <0.47.0"`) and an upgrade
  source (`sourceBelow`). `plan` selects it from the project's reference and target versions. A running 0.46
  backend exposes no framework-version endpoint: versions come from project.json and the repo's package pins - the `@shesha-io/reactjs` version is the framework
  version (backend NuGet packages number their patches separately).
- Every rule names its hazard, kind (`fleet` | `targeted` | `opt-in`), options and, once a framework release fixes
  the bug, `fixedIn` + `fixedEvidence`. `release-notes` = still applied with a warning; `verified` (proven on a
  running target) = skipped, and `retire` unwinds the workaround it wrote, found by its marker.
- Markers (`/*reconciler:046-<rule>*/` and the `-046` id suffixes) are never renamed: re-runs would double-apply.
- Project-specific values (label columns, panel padding, form maps, namespaces) are `options` in project.json;
  project-only rules live in `.shesha-reconcile/rules/*.py` with the same contract.
- The 0.46 pack: [references/pack-0.46.md](references/pack-0.46.md). Writing a rule or a new pack:
  [references/rule-authoring.md](references/rule-authoring.md).

## Tracking

Committed in the project repo, under `.shesha-reconcile/`: `project.json` (roles, versions, modules, options,
pages, noise list), `ledger.jsonl` (append-only: every run, form write, retire, restore, verification, note,
export), `defects.jsonl` (append-only register: `defect add|set|list`), `decisions.md` (the project's dated
decisions), `rules/`. Gitignored: `work/` (session state, snapshots, backups, sweeps, reports) and credentials.
Record what the ledger cannot know: `verify --kind <item> --result ok|fail|unverified`, `note --category <c> --text <t>`.
Schemas: [references/tracking.md](references/tracking.md).

## Last step of every run - report, then ask

`shrec.py report` (add `--html` for a shareable page) prints and saves the summary: where it wrote (role and host;
the reference used read-only), forms changed by rule and batch, skipped/failed, backups and the exact revert
command, FORMS TO EXPORT (checklist + plain list), other configuration touched, follow-ups, open defects by
hazard, retire candidates, and the Definition-of-Done table. The headline says UNVERIFIED IN BROWSER until a
browser verification follows the last push.

Then ask with `AskUserQuestion`: "Are you happy with the result and have you tested it?" - "Not yet, I will test
first" (default) / "Yes, export the package and open the PR for me" / "Yes, I will export and open the PR myself".
Export (`export-package --reviewer-approved`, then `verify-package`), commit, push and PR happen only after the second
answer ([references/packages-and-export.md](references/packages-and-export.md)). Never merge a PR.

## Commands

| Command | Purpose |
|---|---|
| `init`, `init-creds`, `status`, `probe-env`, `versions` | project profile, credentials template, configuration and reachability, version pair and pack |
| `confirm-target`, `authorise-deployed`, `revoke-deployed` | the write gates |
| `plan`, `apply`, `retire` | rule selection for the version pair; apply (fleet / targeted / opt-in); unwind fixed workarounds |
| `snapshot`, `capture`, `compare` | read-only snapshots; page sweep with defect probes; reference vs local geometry and labels |
| `e2e-save` | Edit -> Save unchanged on the local role - it SAVES records, so it is a dry run unless `--push` |
| `detect` | static hazard detectors (pack detectors + the versioned form-edit `scan-hazards.mjs` when installed) |
| `audit-requests`, `probe-scope`, `dom-chain` | measurement: every API call per load, a temporary script-scope dump (local only, always removed), DOM geometry chain |
| `branch-changed` (alias `sprint-changed`), `merge3`, `sync-forms` | forms a branch changed, from its packages; three-way merge by component id; copy untouched forms between roles |
| `restore` | restore a form / rule / run from backups (created forms: reported, never deleted) |
| `export-package`, `verify-package`, `migration-check`, `sqlq` | subset export after the go-ahead; package checks; unapplied migrations; read-only SQL |
| `defect`, `verify`, `note`, `report` | tracking |
| `leakcheck --deny-file <f>`, `selftest` | scan for terms that must not ship; offline rule self-tests |

## Agents and related skills

- `shesha-developer:reconciliation-assessor` - dispatch one per slice of ~9 captured pages after a sweep (and again
  after a fleet) with the noise list and the already-fixed defects; returns findings mapped to hazard ids.
- `shesha-developer-0-46:fleet-transformer` - a one-off transform that is not worth a rule.
- `shesha-developer-0-46:form-auditor` - audit forms after a fleet rollout.
- `shesha-developer-0-46:shesha-form-edit` - single-form edits and the hazard catalogue; `shesha-developer:upgrade-to-0-46`
  - the backend/package upgrade that comes BEFORE form reconciliation; `shesha-design-system` - theme-level fixes;
  `clean-form-config` - strip leftovers after a fleet; `shesha-configuration-items` - package and item semantics.

## References

- [references/intake.md](references/intake.md) - detect, the one question set, credentials, write gates, plan template.
- [references/workflow.md](references/workflow.md), [references/full-upgrade.md](references/full-upgrade.md), [references/merge-reconcile.md](references/merge-reconcile.md) - the flows.
- [references/verification.md](references/verification.md) - the Definition of Done and how to record it.
- [references/tracking.md](references/tracking.md) - `.shesha-reconcile/` files, ledger and defect schemas, options.
- [references/rule-authoring.md](references/rule-authoring.md) - rule contract, markers, retire lifecycle, new packs.
- [references/pack-0.46.md](references/pack-0.46.md) - the 0.46 rules, framework behaviours, withdrawn approaches.
- [references/api-by-version.md](references/api-by-version.md) - form API, auth, caches and settings per framework line.
- [references/packages-and-export.md](references/packages-and-export.md) - configuration package semantics and export.
- [references/failure-modes.md](references/failure-modes.md) - process mistakes to avoid; read before trying a new fix.
