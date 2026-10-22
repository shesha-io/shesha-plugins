# Rule authoring

Contents: the rule contract | pack.json | markers | anchors | idempotence | never delete | author's value | syntax gate | options | project rules | retire lifecycle | self-tests | starting a new pack

A rule is a small, scripted, idempotent transform of ONE form's parsed markup. Every fix the reconciler applies is a rule, so it can be dry-run, pushed, re-run, ledgered
and, when the framework fixes the bug, retired. The engine (`scripts/core/engine.py`) applies the selected rules in order to each form through the guarded push layer;
the rule itself never talks to the network and never writes.

## The rule contract

```
apply(ctx, markup) -> int      mutate the parsed markup in place, return the number of changes, add one note per change with ctx.note();
                               refuse (raise WriteRefused via core.project.require) when an anchor is not what the rule expects;
                               return 0 when already applied (idempotent).
retire(ctx, markup) -> int     optional: undo exactly what apply wrote (found by its marker), once the framework fixed the bug.
                               retire(apply(x)) must equal x.
```

`ctx` (a `Ctx` per form) gives: `ctx.note(text)` for an edit; `ctx.info(text)` and `ctx.review(text)` for notes that never cause a write on their own (they
print as `INFO` / `INFO REVIEW`, for things the rule saw but will not change); `ctx.opt(key, default)` for project options; `ctx.role` and `ctx.versions`
(`{from, to}`); `ctx.form` (`Module/name`); `ctx.hosted_forms()` (the set of forms another form renders, for rules that only apply to hosted forms);
`ctx.reference_components()` (components of the reference snapshot by id, read-only, for rules that compare with the reference); `ctx.api()` (a read-only API client)
and `ctx.cache(key, fn)` (compute once per run).

A form whose only notes are `INFO` is not written. The engine counts each rule's changes (`by rule` in the run output) and records per-rule notes in the ledger.

## pack.json

A pack is a folder `scripts/packs/<pack>/` with `pack.json` and the rule modules:

```json
{"id": "0.46", "version": "1.0.0", "target": ">=0.46.0 <0.47.0", "sourceBelow": "0.46.0",
 "hazards": "shesha-developer-0-46:shesha-form-edit references/render-hazards-046.md",
 "rules": [ { "id": "editmode", "entry": "editmode:apply", "retire": "editmode:retire", "hazard": "H15",
              "title": "...", "kind": "fleet", "syntaxGate": true, "marker": "/*reconciler:046-editmode*/",
              "fixedIn": "0.46.1", "fixedEvidence": "release-notes", "options": [] } ] }
```

| Field | Meaning |
|---|---|
| `id`, `version` | the pack's id and its own version (shown as `<id>@<version>` in the ledger) |
| `target` | the version range the pack applies to; `shrec.py` picks the pack whose range holds the target version |
| `sourceBelow` | where the pack's upgrade rules start: a full upgrade comes from below it. A patch upgrade inside the line (source and target both in `target`) still uses the pack - that is when fixed rules are retired; only a source NEWER than the target disqualifies it |
| `hazards` | where the hazard catalogue of the target version lives (`shrec.py versions` prints it; the assessor maps findings to it) |
| `rules` | the list; **list order is application order** |
| rule `id` | the name used by `--rules` and `project.json` `rules.enable` / `disable` |
| rule `entry` / `retire` | `module:function` in the pack folder; `retire` may be null |
| rule `hazard` | the hazard id the rule addresses (H-number in the catalogue) |
| rule `kind` | `fleet` (applied on every form it applies to), `targeted` (needs measured inputs or form-specific anchors; runs only when named in `--rules`, and `apply` refuses it without `--only`), `opt-in` (runs only when enabled in `project.json` or named in `--rules`). The same holds for project rules: only `fleet` (or no kind) runs in a default fleet; any other kind runs only when named |
| rule `syntaxGate` | true when the rule writes or rewrites a script (the gate runs) |
| rule `marker` | the marker comment the rule writes into scripts, or null |
| rule `fixedIn`, `fixedEvidence` | the framework version that fixes the bug and how sure we are (see "Retire lifecycle") |
| rule `options` | the `project.json` option keys the rule reads |

`shrec.py plan` prints every rule's fate for the target version: `apply`, `apply-claimed-fixed` (release notes say fixed, not verified: still applied, with a
warning), `skip-fixed` (fix verified on the target: not applied), `opt-in` (not enabled), `disabled`.

## Markers

A rule that writes into a script marks its output with a comment so it can find, skip and unwind its own work:

```
/*reconciler:<target-tag>-<rule>*/          e.g. /*reconciler:046-editmode*/
```

- The marker is how `apply` recognises "already applied" and how `retire` finds exactly what to remove.
- **NEVER rename a shipped marker.** A form pushed with the old marker would not be recognised by the renamed rule, and a re-run would apply the fix a second time
  on top of the first (double-wrapped scripts). If a rule must change its output, keep the old marker recognised and migrate it, or add a new rule.
- A rule that wraps a block ends it with a matching closing marker (`/*end:<target-tag>-<rule>*/`) when `retire` needs to find where the block stops.
- Rules that write settings rather than scripts (for example a padding) have no marker; they are idempotent because the new value is no longer the migration's
  default.
- Stashing an original instead of destroying it: keep it under a `_reconciler...` key (for example `_reconcilerOriginal`); keys starting with `_` are not part of the
  component tree.

## Anchors: require, never assert

A rule states what it expects to find (a component type, a stored default, a script shape) and **refuses** when the form is not what it expects, instead of guessing:

- Use `core.project.require(cond, message)`. It raises `WriteRefused` and survives `python -O`; a bare `assert` is removed by the optimiser and silently disables the
  guard. The form is then reported as `skipped-anchor` and not written.
- Resolve things by name at runtime (component type, `componentName`, property path), never by a hard-coded component id: ids differ between environments and
  designs.
- Rewrite only values that are the migration's own output or unset.

## Idempotence

Run the rule twice: the second run must change nothing and return 0. Make that true by construction: either the output no longer matches the rule's input pattern
(a replaced old type name), or the marker is present, or the value written is no longer the default that triggers the rule. Two rules that write the same property
differently never settle: reconcile their values so the pair reaches a fixed point.

## Never delete a component: hide it

A rule may hide or collapse a component, wrap it, or stash its original under a `_reconciler...` key. It never removes a component from the tree: a component can be
referenced by scripts or by the layout, and a deletion cannot be undone from the ledger. Hidden components are not mounted on 0.46, so hiding is not free either: say
so in the rule's docstring when it matters.

## Keep an author's explicit value

When a stored value differs from what the migration would have written, an author set it on purpose: leave it. Rules replace only the exact migration default (for
example a header padding of 8/8/8/8) or an unset value, and report anything ambiguous with `ctx.review(...)` for a person to decide.

## Syntax gate

Every script a rule writes or rewrites must parse as an async function body, the way Shesha evaluates it. Use `core.gate.syntax_errors(snippets)` or
`core.gate.require_clean(new_snippets, old_snippets, what)`; it refuses when the new scripts introduce a syntax error that the old ones did not have. Node 18+ must
be on `PATH`. The gate proves the script parses, not that it works: a use-before-declaration still fails at run time, silently inside a `try`. Measure the effect in
the browser ([verification.md](verification.md)).

## Options instead of constants

A value that differs between projects (a gap, a label split, a form replacement map, a regex) is a `project.json` option read with `ctx.opt('key', default)`,
validated with `require` (an invalid option makes the rule refuse, it never guesses), and listed in the rule's `options` field and in [tracking.md](tracking.md). A
rule whose fix is a project decision (which form replaces a removed framework form) is a no-op without its option. Never hard-code a project's module, form name, entity
or id in a pack rule.

## Project rules

Rules that are tied to one project's forms live in `<project>/.shesha-reconcile/rules/*.py`, are committed with the project, and run AFTER the pack rules in file-name
order. A file defines `RULE` (the same fields as a pack entry; `id` defaults to the file name) and `apply`, optionally `retire`:

```python
from core.project import require
from core.tree import walk

RULE = {"id": "fix-status-chip", "hazard": "H33", "title": "Status chip bound to the wrong list", "kind": "targeted",
        "marker": None, "options": []}

def apply(ctx, markup):
    n = 0
    for c, _, _ in walk(markup):
        ...                      # anchored, idempotent, notes via ctx.note
    return n
```

`shrec.py plan` lists them as `project-rule`. A project rule that turns out to be generic belongs in the pack: move it, keep its marker, and delete the project copy in
the same change.

## Retire lifecycle: `fixedIn` and `fixedEvidence`

Many rules are workarounds for framework bugs. When the framework fixes the bug the workaround must be unwound, otherwise it keeps rewriting forms and may fight the fix.

1. **release-notes.** The target version's release notes report the fix. Set `fixedIn` to that version and `fixedEvidence` to `"release-notes"`. The rule is still applied
   (`apply-claimed-fixed`), with a warning: a release note is a claim, not a proof.
2. **Prove it on the target.** On a running instance of the fixed version, reproduce the symptom with a form that does NOT carry the workaround (measure it, the way the hazard's
   Detect line says). Only then set `fixedEvidence` to `"verified"`.
3. **Verified.** The plan now reports `skip-fixed`: the rule is no longer applied to new forms.
4. **Retire.** Unwind the workaround on the forms that carry it: `shrec.py retire --rules a,b [--only ...] [--target local|deployed] [--push]`. It runs each rule's `retire`
   function (dry run by default, same guards, backups and ledger as `apply`). It refuses a rule that is not a retire candidate for the target version, or whose fix is only
   `release-notes`, unless the user agrees and you pass `--claimed`. `shrec.py report` lists the retire candidates.

A rule with no `retire` function (it rewrote values without a marker) cannot be retired; its docstring says why and what to do instead (usually: nothing, it is harmless).

## Self-tests

`shrec.py selftest` runs the offline fixtures under `scripts/tests/` (no backend needed) plus the syntax gate. Every rule ships with:

1. **apply**: on a fixture that has the symptom, `apply` changes it as documented and returns the expected count;
2. **idempotence**: a second `apply` on the result returns 0 and changes nothing;
3. **retire round-trip**: for a rule with `retire`, `retire(apply(x))` equals `x`;

plus a negative fixture: a form that must NOT be touched (an author's explicit value, an anchor that is missing) stays unchanged or is refused. A rule without these is not
ready for a fleet.

## Starting a new pack for a future target line

When the framework line changes (the next minor after 0.46), add a pack instead of editing the shipped one:

1. Create `scripts/packs/<new>/` (for example `v0_47`) and copy `pack.json` from the shipped pack as the skeleton. Change `id`, `version`, `target` (the new range, for example
   `>=0.47.0 <0.48.0`) and `sourceBelow` (the version at which the old behaviour no longer needs reconciling).
2. Write the new hazard catalogue in the matching versioned plugin (`shesha-developer-<x>-<y>:shesha-form-edit` `references/render-hazards-<xy>.md`) and point the pack's
   `hazards` at it. Hazards are found by measuring the new release against the old one, the same way the 0.46 catalogue was ([workflow.md](workflow.md) step 4).
3. Carry over only the rules whose hazard still exists on the new line, with a NEW marker tag (`/*reconciler:047-<rule>*/`). Never reuse or rename a marker of the old pack.
4. Add the self-tests, run `shrec.py selftest`, then `shrec.py versions` and `shrec.py plan` against a project configured for the new versions.
5. Document the pack in a `references/pack-<line>.md` beside [pack-0.46.md](pack-0.46.md), with the same columns.
