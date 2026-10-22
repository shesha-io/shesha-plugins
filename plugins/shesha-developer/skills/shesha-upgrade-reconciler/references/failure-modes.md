# Failure modes of the process

Contents: trusting the wrong evidence | measuring | scope and ordering | merges and packages | people and caches | tooling

Every item below cost real time in a past reconciliation. Guard against all of them.

## Trusting the wrong evidence

- **Read-back, a 200, `forms changed 0` and component counts are not proof of function.** They prove the write persisted. A page can pass all of them while a panel is in the
  wrong place, Save does nothing and a list shows every record. Write "pushed and read back, UNVERIFIED in browser" until the Definition of Done is measured
  ([verification.md](verification.md)).
- **A data difference is not a defect.** The two databases hold different records. Before calling a table empty or a value wrong, read the record on both sides through the
  API.
- **"Same on the reference" or "legacy" without the identical action on both sites.** A verdict reached from code or memory hid a real defect for a day. Do the same action on
  both environments, side by side, on a record in the same status and type, and cite both captures.
- **Judging visibility by `innerText`.** Collapsed or clipped content still appears in it. Use a screenshot and geometry.
- **Half-loaded captures.** A page sitting on "Initializing..." or a `ChunkLoadError` is not a result. Reload and recapture; watch the settled UI for 30 seconds before
  diagnosing a sub-form's data context.

## Measuring

- **Guessing a fix and shipping it.** Each guessed fix (a different id expression, another getter, a sort mode) was wrong and needed a measurement to retire. Probe first
  (script-scope dump, request capture, DOM geometry), then change.
- **Single-load tests and de-duplicated request captures.** The first load after a push can look complete and later fresh loads not; a capture de-duplicated by path hides the
  second request. Load at least three times in fresh contexts and keep every request.
- **Skipping the data-scope check.** A data leak is invisible in layout screenshots: only comparing the rendered rows with the database finds it.
- **A missing record id that still returns 200.** Some endpoints fall back when the id is absent. Assert the id is present in the request URL and body.
- **Temporary instrumentation left behind.** Script-scope and row-data dumps injected for one measurement must always be removed afterwards.

## Scope and ordering

- **Restrict every scan.** A batch or rule that scans all forms must run with `--only` / `--only-file` when only some forms are in scope; an unrestricted run touches forms
  nobody planned to export.
- **Re-run marker rules after a merge.** A rule anchored on a marker comment finds nothing once a merge or an import has overwritten the form with unmarked markup; re-run it
  on the merged forms, and detect again.
- **Never replay superseded batches.** When a later fix replaces an earlier one (a temporary workaround retired by the proper fix), replaying the earlier one re-introduces the
  workaround. Check the defect log for supersessions before re-running anything old.
- **Two rules writing the same component.** When two rules emit the same output, run them in the proven order and never re-push the earlier one on top of the later one; reconcile
  their values so the pair reaches a fixed point (otherwise one keeps reporting changes against the other).
- **Fix what blocks the boot first.** A migration written for the old schema stops the backend from starting; forms cannot be measured until it does.
- **A passing build is not a passing start.** Build with analyzers as errors, then start against a real database.

## Merges and packages

- **Re-import on every boot.** Packages import in file-name order and skip by md5, so a later-named package overwrites the forms of earlier ones. The state before the first boot
  that includes your package says nothing about the state after it.
- **Starting a merged backend overwrites reconciled forms** with the old-version markup of the branch's packages. Snapshot "ours" first.
- **A faithful merge brings in the traps.** The branch's markup is correct for the old version; applying it faithfully re-introduces stale `parentId`s, scripts that read the wrong
  form's data, list endpoints with query text, hidden data holders. Run `detect` on every merged form.
- **Unscoped export.** An all-forms package silently reverts every form it carries that someone else changed after your last read. Export a subset, named later than every package
  on the target branch.
- **Local-only config in a commit.** The developer's `appsettings.json` and credentials file never get staged; keep the local value on every merge conflict.

## People and caches

- **The reviewer's browser cache.** Old markup in IndexedDB `forms` can make "it works" and a fresh-context measurement disagree. Ask the reviewer to clear it, close stale
  Configuration Studio tabs, and trust the fresh-context measurement.
- **A stale designer tab saves old markup over the push.** Close every tab open on the changed forms before pushing and before exporting.
- **The designer normalises after the fact.** It can re-nest a form some minutes after a push. Re-read and diff.
- **Moving the goalposts of "fixed".** A page is fixed only when every option, condition and scenario works and the alignment matches the reference; the default record alone is
  not enough.

## Tooling

- **Writing scripts with a shell heredoc.** Escapes (`\n`, `\"`, `\\n`) in generated files get corrupted. Create files with the editor / Write tool.
- **A syntax gate is not a run.** A script that parses can still fail at run time (use before declaration inside a `try` fails silently). Measure the downstream effect, not just
  the read-back.
- **Logging in per page.** Token requests are rate limited to 10 per minute; cache one token per role per process.
- **Starting, stopping or rebuilding a developer's backend yourself.** Ask the user.
