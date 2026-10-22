# Full upgrade of ALL forms

Use for the first reconciliation of a Shesha application after a framework upgrade (for example 0.43 to 0.46), or to re-run the whole rule set after the framework or
the forms moved a lot. For a feature branch's new changes on an already reconciled site use [merge-reconcile.md](merge-reconcile.md) instead.

Prerequisites: the intake ([intake.md](intake.md)) is done with purpose "full upgrade", and the backend upgrade is finished. A reference site (read-only) is
strongly recommended. The target look is "the reference layout with the upgraded fonts; similar, neat, aligned, well spaced", not a pixel copy: agree this bar with
the reviewer up front and record it in `decisions.md` ([tracking.md](tracking.md)).

Commands are `python <skill>/scripts/shrec.py <command>`; step-by-step detail, diagnosis and revert are in [workflow.md](workflow.md). Pin one run first
(`export SHREC_RUN=full-<name>`) so every step shares one backup folder and one report.

## Phase 0: backend upgrade first

Reconcile forms only after the backend and portal of the target version start cleanly against an upgraded database. Run `shesha-developer:upgrade-to-0-46` (or the
matching upgrade skill for the target line) first: feeds, pinned versions, compile, migrations, a real database. A backend that does not boot gives the sweep nothing
to measure. Check pending migrations against the target database with `shrec.py migration-check` ([merge-reconcile.md](merge-reconcile.md) step 2). Never start,
stop or rebuild a developer's backend yourself: ask.

## Phases

| Phase | What | Gate |
|---|---|---|
| 0. Backend upgrade | `shesha-developer:upgrade-to-0-46` (or the matching upgrade skill); migrations applied; backend and portal start | the backend answers `probe-env` |
| 1. Snapshot (read-only) | `shrec.py snapshot` (reference current versions, target forms) | none |
| 2. Sweep (read-only) | `shrec.py capture` on the reference and on the target over `pages.json`: screenshots per tab plus defect probes | none |
| 3. Assess | fan out `shesha-developer:reconciliation-assessor` (Sonnet, read-only), one per slice of about 9 pages, with the noise list and the already-fixed list | none |
| 4. Diagnose a NEW defect | on the running app (computed styles, request bodies); the target version's hazard catalogue first; prove the fix by request interception or on ONE form | none |
| 5. Theme-level fixes | settings that fix a whole class of symptoms at once (row geometry, panel accents, component defaults), BEFORE any per-form fleet; see below | the reviewer agrees |
| 6. Rule | anchored, idempotent transform ([rule-authoring.md](rule-authoring.md)) | none |
| 7. Pilot | `shrec.py apply --rules <rule> --only <2-3 forms>` dry, then `--push`; measure; the reviewer checks in their own browser | reviewer |
| 8. Fleet | `shrec.py apply --rules <rule> --push`, then run again: `forms changed 0`; report how many forms it touched (= export cost) | reviewer confirmed the pilot |
| 9. Verify | [verification.md](verification.md): scenario matrix, side by side with the reference, the business test plan on localhost, write and read paths | the reviewer exercised it |
| 10. Report and hand-over | `shrec.py report` prints the summary: forms changed, what to export, how to revert. Then ask: "happy and tested?" | the user |
| 11. Only if the user says yes | subset export of every changed form ([packages-and-export.md](packages-and-export.md)), verify, explicit paths, commit, push, PR; never merge | the user, then the repo owner merges |

## Order of work

Visual issues first (sweep all pages, pilot, assess, roll out), then functionality (saves, dialogs, tables that fetch, workflows). Then prefer a global
configuration lever over editing every form.

**Theme-level fixes before per-form fleets.** Theme settings (Components defaults, app settings under `appKey`) fix a whole class of symptoms with one settings
write and no per-form export. A per-form fleet touches every form it changes, and every touched form must be re-exported. Try the global lever first, prove the
effect on individual forms, and roll out per form only when the theme cannot reach the symptom (a migration writes `desktop` values that beat the theme for tabs,
text, container and htmlRender; row geometry and panel accents are theme-reachable). Settings are not part of the form package: record them
(`shrec.py note --category theme-settings --text "..."`) and see [packages-and-export.md](packages-and-export.md). Do not add framework or application CSS, and do
not add hidden stylesheet components, unless the repo owner agrees and records it in `decisions.md`.

## Rule groups: pack order

The rule groups of the pack run in pack order, the order they were proven (`shrec.py plan` prints it for the target version). For the 0.46 pack:
`scripts, textvis, textsize, carriers, rlshidden, layout, tabs, status, hints, labelcol, subfetch, rowgap, tabgap, tablectl, tagnull, types, panels, optfilter,
editmode, acsort, payload, urlwait, afterload, formref, gsrefresh, normparent`, then the targeted rules that need measured inputs or form-specific anchors
(`split_labels`, `hide_empty_buttons`, `dialogfooter`, `url_reflist_columns`, `readonly_strip`, `urlfilter`). Symptom, cause and what each writes:
[pack-0.46.md](pack-0.46.md). Later one-off mechanisms are written per form as anchored project rules ([rule-authoring.md](rule-authoring.md)), not as fleet groups.
Order matters: a rule may rely on an earlier rule's output. Never reorder a shipped pack.

## Lessons that apply to every upgrade

- Never decide "same on the reference / legacy" without the identical action on both sites, side by side ([verification.md](verification.md)).
- A page counts as fixed only when every option, condition and scenario works and the alignment matches the reference, not just the default record.
- Bugs that exist on the reference but that the target version can fix are fixed on the target, not copied.
- The deployed site keeps changing while you work: re-check the reference's newest published versions right before exporting and merge any newer one.
- Starting a backend that contains newer configuration packages re-imports them and overwrites the forms they carry: deploy the backend first, import the
  reconciled package after, so it overwrites last ([packages-and-export.md](packages-and-export.md)).
- Fix what blocks the build and the boot first (migrations, packages), then forms.
