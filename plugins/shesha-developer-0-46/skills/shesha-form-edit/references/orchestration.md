# Multi-agent orchestration for form fleets

When work spans many forms (or many full-stack pages), single-context editing degrades — context fills with markup, later forms get sloppier, and verification gets skipped. This file is the dispatch playbook. Mechanics of the transforms themselves: [bulk-operations.md](bulk-operations.md). Routing thresholds: SKILL.md Step R.

---

## The canonical fleet loop

```
audit-all (auditor fan-out, 1 agent/form)
   → classify failures, decide the transform
   → pilot (ONE fleet-transformer, 1 form) → browser-verify pilot (verification.md)
   → roll out (same transformer, same script, all targets)
   → re-audit (auditor fan-out)
   → synthesize report
```

Exit criteria per stage: audit = every target has a verdict; pilot = assertions pass AND browser checks pass (computed styles, not screenshots); rollout = every push re-fetched and asserted; re-audit = zero `fail` verdicts.

---

## The agents (defined in this plugin — dispatch via the Task tool)

| Agent | Use for | Model | Never |
|---|---|---|---|
| `shesha-developer-0-46:form-author` | Drafting genuinely distinct new forms, one agent per form, in parallel | inherit | pushing |
| `shesha-developer-0-46:form-auditor` | Read-only verdict per form, before bulk pushes and after rollouts | sonnet | editing |
| `shesha-developer-0-46:fleet-transformer` | ONE per bulk mutation — writes the transform script, pilots, rolls out | sonnet | one-per-form |
| `shesha-developer-0-46:fullstack-prereq-checker` | Backend readiness before entity-bound work | haiku | fixing |
| `shesha-developer-0-46:reconciliation-assessor` | Upgrade reconciliation: compares captured reference vs target renderings of the same pages (one agent per slice of pages) and maps each defect to a render hazard; run after a capture sweep and after each fleet rollout; dispatched by `shesha-developer:shesha-upgrade-reconciler` | sonnet | browsing, editing config |

---

## Shared state between agents

Authenticate ONCE; write the bearer token to **`$RUN_DIR/access-token`** (the run directory — see `shesha-claude-designer` SKILL.md Step 0) and pass that path in every dispatch prompt — agents `cat` it instead of re-authenticating. Put the audit spec / transform spec in a JSON file under `$RUN_DIR/` and pass its path too. Every dispatch prompt must include: `$RUN_DIR`, the skill root path, backend URL, token-file path, module, the form(s), and the expected output contract.

**Stamp `fetchedAt` next to the token and check it before use.** A cached token that had gone five days stale — alongside a cached password that was also wrong — cost a live debugging round-trip before anyone thought to suspect the cache. A cache with no freshness check is a trap, not an optimisation; re-authenticate rather than guess.

## Dispatch prompt template — auditor fan-out

> You are auditing one Shesha form. SKILL_ROOT: `<path>`. `$RUN_DIR`: `<path>`. Backend: `<url>`, bearer token in `$RUN_DIR/access-token`. Form: module `<module>`, name `<form>`. Audit spec: `<spec-file>` (run check families: `<families>`). Fetch via GetByName — `result.markup` is double-stringified (parse the envelope, then parse the markup string). Write any scratch under `$RUN_DIR/`. Return ONLY the JSON verdict contract from your agent definition, including its `coverage` block — a family that inspected nothing is not a pass.

## Dispatch prompt template — fleet transform

> SKILL_ROOT: `<path>`. `$RUN_DIR`: `<path>` (token at `$RUN_DIR/access-token`; write the transform script and all staged JSON under `$RUN_DIR/staged/`). Backend `<url>`. Targets: `<form list>`. Pilot: `<form>`. Approval mode: pilot-stop. Transform spec: `<spec-file>`. Assertions: `<list — e.g. field-set unchanged, component delta == N>`. Follow references/bulk-operations.md exactly.

## `SKILL_ROOT` means the shesha-form-edit skill directory

Everything an agent reads hangs off it — `SKILL_ROOT/scripts/…`, `SKILL_ROOT/../clean-form-config/assets/groups/…`,
`SKILL_ROOT/references/…`. It is **not** the `skills/` directory. Three docs briefly used the
other reading, which silently pointed the mandatory disk-verification gate at a path that does
not exist; if you add a new dispatch site, match the agents.

## Never accept an agent's word for an artifact — check the disk

**MUST, after every `form-author` dispatch, before the returned verdict counts for anything:**

```bash
node <SKILL_ROOT>/scripts/verify-artifact.mjs <outputPath> \
  --backend <url> --token <token-file> --json
```

Exit `0` pass · `1` fail · `2` the artifact could not be read · `3` partial (something was not inspected — [verification.md §0](verification.md)).

This is not belt-and-braces. Two build retrospectives recorded the same failure independently: once an agent spent 50 tool calls and **never wrote the file**, then reported completion; once it reported *"53 components... everything checks out"* for a form whose datalist pointed at a **row-template form that did not exist**, so the list would have rendered empty. Both were caught by a human reading JSON, neither by any gate. An agent's self-report is a claim; the file on disk is the evidence. `verify-artifact.mjs` resolves every referenced form against the backend, which is the specific check that would have caught the second case before the push.

Treat exit `2` as "the dispatch did not complete" and re-dispatch with *"you stopped before writing the file — finish and write it now"*, rather than re-running the whole build.

## Synthesis

One final agent (or do it inline): aggregate the verdicts; use ONLY the data provided — do not invent issues; report per-form pass/fail, the failure clusters, and what was NOT covered (no silent truncation). A `partial` from any gate is reported as partial, never rolled up into a pass.

---

## Cost guidance — when fan-out pays

| Situation | Do |
|---|---|
| ≤ 3 forms | Single context, no agents. Dispatch overhead exceeds the benefit. |
| Audits / verification, > 3 forms | Fan out `form-auditor`, one per form — read-heavy, independent, parallel. Proven at 16+ forms. |
| The same mechanical change on N forms | ONE `fleet-transformer`. The script costs the same for 1 or 50 forms; per-form agents multiply cost AND drift. |
| N genuinely distinct new forms | Parallel `form-author` dispatches (judgment is per-form; wall-clock wins). Push + audit centrally afterwards. |
| Entity-bound work, unverified backend | One `fullstack-prereq-checker` first — a haiku-priced gate that prevents authoring against missing entities. |

Pilot-first is itself a cost control: a wrong fleet rollout costs 2× (rollback + redo); the pilot caps the blast radius at one form.

---

## Permissions caveat

Plugin agents do not inherit a `permissionMode`. The fleet-transformer's `curl` pushes will hit permission prompts in strict sessions — pre-approve the Bash patterns (`curl` against the backend) or run fleet operations in an accept-edits/bypass session. In fully headless runs (test harness) this is already bypassed.

---

### Worked example (project-specific)

The RequirementsStudio 2026-06 rollouts that shaped this playbook: a 16-form auditor fan-out (sonnet) verified subtable canon with a strict verdict schema (`{form, pass, formLoads, checkResults[], summary}` — per-tab fields like `addForm/labelOk/iconOk/actionOk/formArgsParentFkOk`); the KIB divider redesign ran as ONE transform script (`transform-kib-all.js`) piloted on `module-definition-details` then rolled to 16 forms with component-count-delta guards; the create-forms cleanup fixed 33 forms in one scripted pass with field-set assertions, audited to 0 issues pre- and post-push.
