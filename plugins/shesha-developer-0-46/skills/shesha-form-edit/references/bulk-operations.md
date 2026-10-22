# Bulk/fleet form transforms (pilot-first)

Mechanics for changing many forms at once without losing fields or regressing working wiring. Routing thresholds (when to go fleet-mode at all) live in SKILL.md Step R; agent dispatch lives in [orchestration.md](orchestration.md). This file is the HOW.

---

## Trigger

Read this file when:

| Condition | Why it qualifies |
|---|---|
| The same change touches **> 3 forms** | Manual per-form editing drifts; a script is cheaper and consistent |
| ANY restructure where **field loss is possible** (re-layout, tab re-bucketing, header transplant) — even on 1 form | Field loss is the #1 risk of bulk re-layouts; only a transform with assertions catches it |

---

## Pilot-first protocol

1. **Audit ALL targets in one pass first** (GetAll, below) — know the exact current state (header variant, subtable buttons, chip columns) before designing the transform.
2. **Prove uncertain markup on ONE pilot form** against the live runtime — browser-verified per [verification.md](verification.md) (computed styles, correct navigation path, cache cleared). Especially for un-attested mechanisms: link-existing dialogs, unlink actions, row drill-down, reflist chip columns.
3. **Lock the template** — extract the verified pilot's style/structure objects to a JSON file the script reads.
4. **Roll out via a deterministic transform script** — the SAME script that built the pilot, run over all targets.
5. **Re-audit everything** (auditor fan-out — [orchestration.md](orchestration.md)).

A wrong fleet rollout costs 2× (rollback + redo); the pilot caps the blast radius at 1 form. This is the only approach that has scaled to 17/33/68-target rollouts.

---

## Audit via GetAll

`FormConfiguration/GetAll` returns the **FULL markup inline for every form** — one call audits a whole module instead of N `ConfigurationItem/GetCurrent` round-trips (0.46 has no `GetByName`).

- In the GetAll response, `module` is a **plain string** (e.g. `"<module>"`), not an object — don't reuse `GetCurrent` envelope parsing blindly (`result.configuration.*`).
- Each item's `markup` is a JSON **string** — `JSON.parse` it per form.
- Alternative: `GET /api/services/Shesha/FormConfiguration/QueryAll` with an explicit `properties` parameter avoids the configurationForm sub-selection validation error.
- The live DB is the source of truth — never audit from stale local extracts (outdated GUIDs/wiring regress working forms).

---

## The transform recipe

Pipeline: **fetch → mutate in Node.js → write UTF-8 without BOM → double-stringify body → push from file**.

| Step | Rule |
|---|---|
| Mutate | In Node.js, never by hand-editing escaped JSON-in-JSON |
| Write | UTF-8 **WITHOUT BOM**. PowerShell `Out-File -Encoding utf8` AND `[System.Text.Encoding]::UTF8` both emit a BOM (EF BB BF) that breaks Node `JSON.parse`. Use `New-Object System.Text.UTF8Encoding $false` + `[System.IO.File]::WriteAllText`, or do ALL writes in Node (`fs.writeFileSync` is BOM-free) |
| Body | `JSON.stringify({ id, markup: JSON.stringify(form), modelType })` — **double-stringify**; `markup` is a string, passing the object gives `"Unexpected character encountered while parsing value: {"`. Always carry the stored `modelType` (H1): `UpdateMarkup` overwrites it with what is sent and clears it when omitted |
| Push | `curl --data-binary @req.json` or `Invoke-RestMethod -InFile req.json`. **Never inline PowerShell bodies** — encoding + size traps (`Invoke-WebRequest -Body` can prompt for credentials in NonInteractive mode on large payloads) |

```js
// per-target skeleton — EMBED ASSERTIONS; fail the run rather than push a lossy form
const before = snapshot(form);                     // field set + component count
mutate(form);                                      // idempotent: conditional checks, safe to re-run
const after = snapshot(form);
if (!sameFieldSet(before, after)) throw new Error(`${name}: field loss`);
if (after.count - before.count !== EXPECTED_DELTA) throw new Error(`${name}: count delta ${after.count - before.count} !== ${EXPECTED_DELTA}`);
// + structural rules for the specific transform, e.g.:
//   every non-final columns row has both cells filled; no columns row after a textArea within a section
fs.writeFileSync(`req-${name}.json`, JSON.stringify({ id, markup: JSON.stringify(form), modelType }));   // modelType = the value just read (H1)
```

Idempotence matters: rollouts get interrupted and re-run. Guard every mutation with a "already transformed?" check so a second pass is a no-op.

---

## Tree-walk correctness

Walkers that only follow `components` silently skip everything inside tabs/cards/columns — including all subtable internals. Recurse ALL child-holder paths:

```js
function* children(c) {
  yield* c.components ?? [];                                        // container, tab pane, column slot
  yield* c.content?.components ?? [];                               // card, collapsiblePanel
  yield* c.header?.components ?? [];                                // card / collapsiblePanel header strip
  for (const col of c.columns ?? []) yield* col.components ?? [];   // columns, KeyInformationBar
  for (const t of c.tabs ?? []) yield* t.components ?? [];          // tabs
  yield* c.items ?? [];                                             // buttonGroup items, datatable columns
}
```

| Rule | Why |
|---|---|
| Re-parenting must **REMOVE the node from the old parent's array** (explicit reset, e.g. `root.components = [inner]`) and update the node's `parentId` | Otherwise you create a duplicate in the tree |
| **Fresh GUIDs + fresh componentNames on clones ONLY** — never regenerate ids on existing components, never mutate the template's originals | Existing `parentId`/script references break; template corruption poisons later targets |
| **Stamp style fixes on base + `desktop` + `tablet` + `mobile`** | Breakpoint objects override base per-key at render — a base fix is dead if `desktop` still carries the old value |

---

## Structural identification

Find target components by subtree **CONTENT/shape**, never by `componentName` conventions — names vary across forms built at different times (one fleet had `hdrBand`/`hdrLeft` vs `container60`/`container61` for the same banner; toolbars named `ctrl_*` vs `container13be03`). One structural matcher handles all variants without per-form special cases.

| Target | Structural signature |
|---|---|
| Subtable toolbar | the child container whose subtree contains `datatable.quickSearch` / `datatable.pager` |
| Add-button wrapper | the child container whose subtree contains the `buttonGroup` |
| Header banner | first container child of `components[0]` |
| Status chip | the `refListStatus` component |
| Title | `text` with `contentDisplay: "name"` |
| Subtitle | the gray `#c7c7c7` text |
| Divider (to delete) | band child whose subtree has NO content leaf (only containers/sectionSeparators) |
| Content columns | the remaining band children |
| Page-content wrapper | the container whose `className` contains `sha-page-content` (find by className, not name) |

---

## Style-transplant methodology

Clone the template's FULL style objects onto each target's analogous component — never hand-author "equivalent" CSS.

- **Overwrite ONLY style keys**: `direction` / `flex*` / `display` / `justifyContent` / `alignItems` / `gap` / `dimensions` / `border` / `background` / `font` / `shadow` / `stylingBox` / `desktop` / `tablet` / `mobile` / `className` / `style` (the legacy JS-string channel — diff it too, it renders inline and overrides everything; see `style-channels.md` in `shesha-design-system`).
- **Preserve identity + data keys**: `id`, `parentId`, `componentName`, `propertyName`, `version`, plus data bindings (`referenceListId`, `entityType`, bound `content`).
- `clean-form-config` flags some template-origin props as issues — **FALSE POSITIVES, do NOT strip**: gap-as-string, `text` `level` as number, sectionSeparator `lineThickness`, and composite object values (style-config / border-config / dimensions shapes — one audit produced 338 bogus "type mismatches"). Stripping them breaks template parity. See [form-quality.md](form-quality.md).
- When parity must be **pixel-identical**: do a **bidirectional full-key JSON diff** (a 167-key designer-bloat component vs the template's clean ~32 keys — one extra `font.color` renders pure black) AND compare computed styles in-browser ([verification.md](verification.md)). Often a full component **transplant** (keep target `id`/`parentId`/`componentName`/`propertyName`) beats property tweaks.
- Squeeze/scrollbar fixes go through `dimensions.minHeight: 'fit-content'` (runtime-verified; not in the groups index — clean-form-config may flag it; do NOT strip) — `dimensions` is the only channel reaching a container's outer div. Canonical target layout: [detail-page-pattern.md](components/detail-page-pattern.md); subtable shape: [junction-subtables.md](components/junction-subtables.md); dialogs: [add-dialogs.md](components/add-dialogs.md).

---

## Verification at fleet scale

- **Auditor fan-out**: one read-only auditor agent per form, strict JSON verdict schema (loose prose output can't be filtered/counted). Dispatch templates and the agent table live in [orchestration.md](orchestration.md) — do not restate them here.
- **Compare exports by component count, not file size** — formatting/normalization changes size without changing structure.
- **Re-fetch after every push** — `UpdateMarkup` returning 200 + empty `result` is not proof the markup persisted ([verification.md](verification.md) §1).
- **Pilot/browser checks**: `getBoundingClientRect` / `getComputedStyle` exact-value assertions, never scaled screenshots; clear the IndexedDB form cache from `/favicon.ico` between re-tests ([verification.md](verification.md) §2/§4).
- Backend readiness for entity-bound fleets: [full-stack-prereqs.md](full-stack-prereqs.md).

---

### Worked example (project-specific)

RequirementsStudio 2026-06 rollouts that proved this playbook:

- **KIB divider redesign (17 detail forms)**: `transform-kib.js` piloted on `module-definition-details`, then `transform-kib-all.js` rolled to the 16 others — dividers identified structurally (KIB child with no content leaf) and deleted with a component-count-delta guard; stretch + `border.border.left = {width:"1px", style:"solid", color:"#d9d9d9"}` stamped on base+desktop+tablet+mobile of columns 2+.
- **Create-forms cleanup (33 forms)**: `transform-creates.js` + `audit-creates2.js` normalized everything to the `module-definition-create` canon in one pass — 19 broken reflist dropdowns fixed, base-project-detail variants REBUILT wholesale from their transformed standalone twin minus `baseProject` (guard: bpd fields ⊆ twin fields), audited to 0 issues pre- AND post-push.
- **Layout v2 (32 forms)**: `transform-layout-v2.js` with in-script assertions — non-final rows must have both cells filled; no columns row after a textArea within a section; field-set unchanged.
- **Subtable toolbars (68 Add-bearing subtables)**: add-button wrapper moved into the toolbar row — toolbar/addWrapper located by subtree quickSearch/pager/buttonGroup content because names diverged (`ctrl_*` vs `container13be03`); a follow-up pass stamped the `sha-index-table-control` / `index-table-controls-right` classes, verified by quick-search x-offset going −8px → +4px (= template).
- **Per-entity templating**: new detail forms were generated by fetching `module-definition-details` and mutating `formSettings.modelType`, subtitle text, KIB columns, Details-tab rows, and subtable tabs in one Node script — pushed via `Invoke-RestMethod -InFile` with no-BOM writes.
