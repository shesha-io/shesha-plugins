# Tracking: the `.shesha-reconcile/` folder

Contents: folder layout | project.json | options | ledger.jsonl | defects.jsonl | decisions.md | report | importing an existing tool's history

Everything the reconciler remembers lives in `<project repo>/.shesha-reconcile/`, created by `shrec.py init`. Some of it is committed so the team shares one history;
the rest is local.

## Folder layout

| Path | Committed? | What |
|---|---|---|
| `project.json` | committed | the project's configuration (below). No credentials |
| `pages.json` | committed | the pages the sweep renders: a JSON list of `{module, form, id}` (`id` is `"-"` for no record); see `assets/pages.example.json` |
| `ledger.jsonl` | committed | append-only event log of every run (below) |
| `defects.jsonl` | committed | append-only defect log (below) |
| `decisions.md` | committed | the project's dated decisions and boundaries (below) |
| `rules/*.py` | committed | the project's own rules ([rule-authoring.md](rule-authoring.md)) |
| `.gitignore` | committed | keeps the local files below out of git |
| `work/` | gitignored | session state (`state.json`: confirmed write target, deployed authorisation), snapshots, backups, sweeps, previews, reports, exports, browser logins |
| `credentials.local.json` | gitignored | the user's own usernames and passwords per role (`shrec.py init-creds`); never committed, logged or pasted into chat |

`shrec.py init` writes the `.gitignore` (`work/` and `credentials.local.json`) and creates empty `ledger.jsonl` and `defects.jsonl`. The ledger and defect log are
committed so a teammate can see what ran where; because they only ever grow by whole lines, merges are line unions.

## project.json

Keys of `assets/project.example.json`:

| Key | Meaning |
|---|---|
| `name` | the project's name, used in reports |
| `modules` | the configuration modules the project owns (`Configuration.Module` names). Fleet runs touch only forms of these modules; at least one is required |
| `appKey` | the front-end application key for settings and the browser form caches (`form:<appKey>`); default `default-app` |
| `environments` | per role `reference` / `local` / `deployed`: `api` (http(s)://host[:port], no path), `portal`, `version` (like `0.46.1`). The reference is read-only; a localhost address is only valid for `local`; a remote site must be https. Versions are never assumed: a local version may be detected from package pins, deployed and reference versions are declared here |
| `pages` | the pages file, a name relative to `.shesha-reconcile/` (default `pages.json`) |
| `rules` | `{"enable": [...], "disable": [...]}`: rule ids to switch on (opt-in rules) or off |
| `options` | rule and tool settings (next section) |
| `noise` | differences the assessor must ignore (data differences, environment badges, the upgraded default font, offsets under 6px, and anything project-specific) |
| `login` | the portal's login form: `userPlaceholder`, `passPlaceholder` (regexes against the input placeholders) and `submitText` (the button text) |
| `e2e` | `editText` and `saveText`: the button labels `shrec.py e2e-save` clicks |

## options

Rules and tools read project-specific values ONLY through `options` in `project.json`, never from constants. An absent option means the default; an invalid value
makes the rule refuse (it never guesses).

| Option | Used by | One line |
|---|---|---|
| `subformLabelCol` | `labelcol` (opt-in) | `[labelCol, wrapperCol]`, two positive integers summing to at most 24, written onto subForms still stored as 8/16 |
| `panelHeaderPadding` | `panels` (opt-in) | object with any of `paddingTop` / `paddingRight` / `paddingBottom` / `paddingLeft`; replaces a header padding that is still the migration default 8/8/8/8 |
| `formRefMap` | `formref` | list of `{"from": "Module/name", "to": "Module/name"}`; subForms naming a form the target does not ship are pointed at the project's copy; empty = no-op |
| `rowGap` | `rowgap` | the gap written onto horizontal containers that store none; default `"8px"` |
| `statusLabelPattern` | `status` | regex matching the label code of a status button; group 1 is the object the status is read from, an optional named group `prop` is the property (default `status`). Required for the status-button part of the rule, no default: unset, only the separator gap is applied |
| `typeMapExtra` | `types` | `{"Old.Full.TypeName": "New.Full.TypeName"}` added to the built-in map of renamed framework entity types; the new name must not contain the old one |
| `entityNamespaces` | `core/metadata.py` helpers (custom tools, project rules) | list of namespaces where the project's entities live, used to resolve an entity type from its name; default `["{module}.Domain"]`. Pack rules use `entityNamespacePatterns` instead |
| `labelSplitFont` | `split_labels` | optional font of the split-out label text `{size, weight, color, type}`; each key overrides one default; defaults to the Ant Design form label look: 14 / `"400"` / `rgba(0, 0, 0, 0.88)` / `"inherit"` (the theme font) |
| `footerGuardMessage` | `dialogfooter` | optional message shown when a guarded shared-dialog footer button is blocked; a neutral default is built in |
| `readPostExtra` | browser write guard | list of extra read-only POST endpoints of custom components, as final-path-segment regexes (e.g. `["Spreadsheet/Open"]`); matched against the end of the URL path only |
| `probeStyleClasses` | browser layout probe | list of CSS classes the probe counts as style carriers, in addition to style tags that mention `ant-tabs` |
| `viewport` | `capture` | `[width, height]` of the sweep's browser; default `[1568, 950]` |
| `packageDir` | `export-package`, `branch-changed` | repo-relative (or absolute) folder holding the configuration packages, normally the Application project's ConfigMigrations folder; no default |
| `packageCsproj` | `export-package` | the Application `.csproj` the package is registered in (`None Remove` plus `EmbeddedResource` pair); no default |
| `migrationPaths` | `migration-check` | list of repo-relative folders scanned for `[Migration(n)]` classes; default the whole repository |
| `sourceRef`, `targetRef` | `branch-changed` | default git refs for the branch carrying the new changes and the upgrade branch they land on |
| `targetBranch` | `export-package` | the branch whose packages the new package name must sort after |
| `labelSplit` | `split_labels` | the MEASURED list of wrapping labels: a list of label texts, or a path (absolute or relative to the project root) to a sweep measurement file or directory; unset = no-op |
| `refListDisplayTemplate` | `url_reflist_columns` | optional `displayComponent` dict `{"type": "dropdown", "settings": {...}}` used when the form has no working reference-list dropdown display to copy |
| `entityNamespacePatterns` | `readonly_strip` | optional extra type-name patterns, with `{module}` and `{type}` placeholders (for example `"{module}.Domain.Sales.{type}"`), tried after the two built-in ones when resolving a nested entity type |

## ledger.jsonl

Append-only, one JSON object per line, never rewritten. Every line carries `ts`, `run`, `batch`, `env` (role), `host`, `pack` (`<id>@<version>` or null) and
`versions` (`{from, to}`). No credential or token is ever written. Event shapes:

| Event | Fields |
|---|---|
| `run-start` | `script`, `mode` (`push`: a run-start is written only by runs that write), `reference_hosts`, `snapshot_dir`?, `forms`? |
| `form` | `module`, `form`, `form_id`, `rule`, `rules` (`{rule: [notes]}`), `notes`, `result`, `mode`, `reason`?, `backup`?, `before_sha256`?, `after_sha256`?. `result` is `pushed`, `dry-run`, `no-change`, `skipped-anchor`, `failed`, or `written-unverified` (the write request was sent but not confirmed - no response, an error status or a read-back mismatch: the backend may hold the new value, so the form counts as touched for the export list and `restore --rule`, the run never retries it blindly, and the report flags it for a check) |
| `retire` | the same fields as `form`, for a rule being unwound after the framework fixed it |
| `restore` | `module`, `form`, `source` (backup path), `result` |
| `other` | `kind` (`theme-settings`, `reference-list`, `entity`, `workflow`, ...), `what`, `backup`? |
| `note` | `category` (`backend-migration`, `follow-up`, `data`, ...), `text` |
| `verify` | `kind` (a Definition of Done item, or `browser`, `e2e`, `rerun`, `other`), `result` (`ok`, `fail`, `unverified`), `detail` |
| `export` | `package`, `forms` (`module/name`), `file`? |
| `summary` | `script`, `dry`, `rules`, `forms_changed`, `of`, `failed`, `by_rule` |

`run` is one id per process unless `SHREC_RUN` pins several processes to one run (pilot, fleet and re-run share it). `batch` names one rule rollout or merge
(`SHREC_BATCH`; defaults to the run id).

Environment variables: `SHREC_PROJECT` (project root; `--project` sets it), `SHREC_WORK` (work dir, default `.shesha-reconcile/work`),
`SHREC_CREDS` (an extra credentials file), `SHREC_TARGET` (`local` | `deployed`), `SHREC_DEPLOY_CONFIRM` and `SHREC_DEPLOY_TTL_MIN` (deployed
write gate), `SHREC_RUN` / `SHREC_BATCH` (ledger grouping), `SHREC_RULE` / `SHREC_SCRIPT` (ledger labels), `SHREC_CONSOLE_MAX` (browser
console capture length, default 2000), `SHREC_SCAN_HAZARDS` (path to the versioned form-edit `scan-hazards.mjs`), `SHREC_SQL` (read-only
SQL connection string for `sqlq` / `migration-check`; never stored).

## defects.jsonl

Append-only. Each line is a JSON object with an `id` (`D-<n>`) and any of `title`, `hazard`, `rule`, `where` (`{module, form, component}`), `status`, `evidence`,
`batch`, `updated`. **Later lines for an id win field by field**, so a change is a new line carrying only the changed fields; the earlier lines stay as history.

Statuses:

| Status | Meaning |
|---|---|
| `open` | seen, not diagnosed or not fixed |
| `pilot` | a rule is applied to named forms only |
| `fixed` | rolled out and verified |
| `framework` | caused by the framework; the workaround is a rule or there is none, and a framework fix is pending |
| `data` | a difference in the data, not a defect |
| `legacy` | exists identically on the reference (proved side by side, [verification.md](verification.md)) |
| `accepted` | a known difference the reviewer accepted |
| `verify` | a fix exists and needs verification in the browser |

Commands: `shrec.py defect add --title T [--hazard H] [--rule R] [--form Module/name] [--component C] [--status S] [--evidence E]`, `shrec.py defect set D-<n>
[--status S] [--rule R] [--evidence E] [--title T]`, `shrec.py defect list [--status S]`. The assessor's already-fixed list is `defect list --status fixed`. A
supersession is recorded as a new line, never by deleting the old one.

## decisions.md

The project's own dated decisions and boundaries from the repo owner and the reviewer (the target look, which settings may be changed, deployed-write rules,
accepted exceptions). A table of `date | decision`. **Newer entries win; superseded entries are kept** and marked as superseded by the newer one, so the history
of a reversal is visible and nobody re-litigates a settled point. Read it at the start of every session; add to it whenever the user states a boundary.

## What `report` derives

`shrec.py report` (`--run <id>` for one run, `--all` for every run, `--html` for a page) reads the ledger and prints:

- the **window**: by default everything within 12 hours before the latest push (pilot, fleet, notes, verification re-runs); with no push at all, the latest run;
  `--run <id>[,<id>]` selects runs and `--all` takes the whole ledger. Output goes to `work/reports/<timestamp>.md` (`--html` adds one self-contained page, `--out` names the
  file);
- the **export list**: forms pushed since the last `export` event, de-duplicated, with the rules that touched them, plus the non-form items recorded as `other` events;
  it is also saved as `<report>-export-list.txt`. This is exactly what to put in the subset package ([packages-and-export.md](packages-and-export.md)). A temporary probe or
  diagnostic note that is the LAST note for a form is reported as a probe left behind and kept out of the export list;
- **retire candidates**: rules the ledger shows as applied whose pack says the framework fixed the bug in a version at or below the target's (`fixedIn`), with their evidence
  level (`release-notes` or `verified`); unwind them with `shrec.py retire` ([rule-authoring.md](rule-authoring.md));
- where changes were written, forms by rule and batch, backups and the revert commands, defects by status and hazard, `note` follow-ups, and the `verify` results as a
  Definition-of-Done table with what is still unverified, then next steps.

The headline: when anything was pushed and no `browser` verification was recorded ok AFTER the last push, the report says "PUSHED AND READ BACK - UNVERIFIED IN BROWSER. Do not
call this done." A form is DONE only when `placement`, `request-audit`, `data-audit`, `row-content`, `write-path` and `read-path` are all recorded ok after the last push; an ok
recorded before the last push is stale and does not count.

## Importing an existing tool's history

A project that already has its own reconciliation scripts, push log or defect list keeps its history: convert it once into the three append-only files instead of
starting empty. Map each past push to a `form` event (`module`, `form`, `rule`, `result: pushed`, `ts`, `env`), each past defect to a `defects.jsonl` line (mapping its
status words to the statuses above), and the written-down decisions to `decisions.md` with their original dates; append the lines (never rewrite the files) and run
`shrec.py report --all` to check the export list matches what the old tool said. Port the old tool's per-project transforms to `.shesha-reconcile/rules/` with the
`RULE` metadata ([rule-authoring.md](rule-authoring.md)); keep their shipped marker comments unchanged so a re-run does not double-apply.
