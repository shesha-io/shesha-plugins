# Runtime verification and browser testing

Workflow for proving a push actually landed and smoke-testing it in the browser. Read after any push (Step 8/9) and before claiming success. Symptom→cause lookup lives in [debug.md](debug.md); API recipes in [api.md](api.md).

---

## 0. What a gate result is allowed to mean

Two failures cost real build time and both were caused by trusting a report instead of the thing it described. A binding checker passed a form having reported **"0 bindings, 0 reflists, 0 endpoints checked"** — not zero failures, zero *coverage*, because that form's constructs were invisible to its walker. A guardrail checker hard-FAILed on values that were byte-identical to the metadata it compared against. Between them they cost a session's confidence: *"the pipeline's own quality gates were not trustworthy for this build; manual reading did most of the real verification work."*

So every gate in this skill — script or human — reports three numbers per check family, and the reader is entitled to all three:

| | meaning |
|---|---|
| **walked** | nodes the family actually visited |
| **checked** | assertions it was able to evaluate |
| **uninspectable** | nodes it saw but structurally *could not* evaluate — each with a named reason |

The rules that follow from it:

- **Zero coverage is never a pass.** A family that checked nothing reports `no-coverage`, not success. "Nothing was wrong" and "nothing was examined" are different results and must never print the same.
- **Any uninspectable node downgrades the verdict to `partial`.** A partial is not a pass. Say so when reporting: name what was not covered and hand it to a human to read.
- **A gate names what it cannot see.** "Skipped 12 code-mode `text` components" is useful; silence is what produced the false green.
- **Don't assert what the codebase hasn't settled.** Ids are the standing example: `SKILL.md` says UUID, but shipped seeds and exported forms are full of nanoid (`8jJ1tFFwhdXB8tGQn7xbB2cwTvcPLe`) and truncated hex that render fine. Reporting those as defects yields ~110 confident findings against a canonical seed that is not wrong — and a gate that cries wolf gets ignored, which is how the previous validators lost trust. Report the count as coverage, not as a failure.
- **Transport failures are uninspectable, not passes.** A timeout, a 401, or an unreachable backend means the check did not run.

`scripts/verify-artifact.mjs` implements this contract and is the reference shape for anything added later; its suite in `tests/verify-artifact.test.mjs` pins each rule above to a test.

**`scripts/check-references.mjs` applies the same contract to the docs themselves.** Run it after editing any skill file:

```bash
node scripts/check-references.mjs
```

It proves that every pointer resolves — markdown links, backticked file paths, `Skill(...)` ids, dispatched agent names, `$role:` tokens (in **every** shipped brand, not just the default), block `$styleOverlay` files, component versions quoted in docs vs `components-kb/_index.json`, and the component index's type→group routing. Exit `0` pass · `1` failures · `3` partial.

It exists because this bug class kept recurring invisibly: 12 dead links, an `archetypes.md` eight files referenced that did not exist, `$role` tokens defined in no theme, six sites invoking a playwright *skill* that nobody ships, and four hand-maintained version lists that had drifted three ways — one telling you to use `numberField` v3, which silently discards a component's whole style block. Three careful manual passes still missed five of these; the script found them in one run. `tests/check-references.negative.mjs` injects one bug per family into a throwaway copy and asserts each is caught, so the gate is proven to fail when it should.

---

## 1. API-first verification

`UpdateMarkup` (`PUT /api/services/Shesha/FormConfiguration/UpdateMarkup`) is a **void endpoint**: it returns `success: true` with an **EMPTY/null `result`**. That is normal — it is NOT evidence your markup persisted.

| Signal | Means |
|---|---|
| HTTP 200 + `success: true` + empty `result` | Request accepted. Nothing more. |
| Re-fetch (`ConfigurationItem/GetCurrent` markup, or `GetJson`) shows your change; `modelType` unchanged | Push landed. The ONLY proof. |
| Re-fetch shows old markup | Push did not land (wrong id, wrong version, validation drop). |

**Never claim success from the 200 alone.** Always re-fetch and diff against what you sent — recipe and the list of harmless server normalizations (key reorder, stylingBox whitespace, `null`→`undefined`) are in [api.md section 8](api.md). Surface anything else as a real diff.

```js
// Node diff skeleton — walk both trees in component-id order
const sent  = JSON.parse(fs.readFileSync('form-sent.json', 'utf8'));
const after = JSON.parse(JSON.parse(fs.readFileSync('form-after.json', 'utf8')).result.markup);
// assert: every property you changed survived; count components before/after (no field loss)
```

---

## 2. IndexedDB form cache

The frontend caches form configurations in **IndexedDB** (`form:default-app`, `form_lookup:default-app` and the legacy `forms` / `form` / `form_lookup` databases). After a successful, API-verified push, the browser can keep rendering the **stale cached markup** — you will chase ghosts, "fixing" markup that is already correct.

| Trap | Rule |
|---|---|
| `indexedDB.deleteDatabase(...)` from inside the app | **BLOCKS silently** — the running app holds open connections; the delete never completes. |
| Clearing from a static page | Works. Navigate to a page where the app isn't running — e.g. `<FRONTEND_URL>/favicon.ico` — run the delete there, then navigate back and reload. |
| `localStorage.clear()` | **LOGS YOU OUT** — the auth token lives there. Don't use it as a cache-buster. |

```js
// Run in DevTools console ON <FRONTEND_URL>/favicon.ico (app not running there):
for (const n of ['form:default-app', 'form_lookup:default-app', 'forms', 'form', 'form_lookup']) indexedDB.deleteDatabase(n);
// list what exists first: (await indexedDB.databases()).map(d => d.name)
// then navigate back to the form and hard-reload
```

**When to run:** whenever the browser disagrees with a verified API re-fetch. Order of escalation: hard-refresh (Ctrl+Shift+R, [debug.md row 12](debug.md)) → IndexedDB clear from `/favicon.ico` → re-test. Run the clear after **every** re-push in a fix loop (see §6).

---

## 3. Navigating for tests

Test `*-details` forms via the table row's view/eye link, **NOT** by pasting a direct `?id=` URL.

| Path | Renders? | Subtable Add/Create submit |
|---|---|---|
| `<module>/<entity>-table` → row eye/view link → details | yes | works |
| Direct `/dynamic/<module>/<form>-details?id=<guid>` | yes (looks fine) | **HTTP 500** on `<Junction>/Crud/Create` — parent page context missing |
| `*-details` with NO `?id=` at all | blank | n/a — **blank is NORMAL** (gql loader has no id), not a bug; don't "fix" component config for it |

A 500 on a freshly wired Add button under direct `?id=` load is most likely a **test-navigation artifact**, not a form bug — re-test via table→details before touching the dialog wiring (see [add-dialogs.md](components/add-dialogs.md), [junction-subtables.md](components/junction-subtables.md)).

Playwright smoke recipe: start at `<module>/<entity>-table`, click the first row's eye/view action (the leftmost `columnType:"action"` item — icon `EyeOutlined`, minWidth/maxWidth 35), wait for the `-details` URL/render, then exercise the Add buttons.

---

## 4. Measure, don't screenshot

Assert layout with `getBoundingClientRect` / `getComputedStyle` against **exact expected values**. Scaled screenshots make 0px offsets look like 10–15px and cause false alarms.

```js
// DevTools / playwright evaluate — exact-value assertions, not eyeballing
const band = document.querySelector('<band-selector>');
const col  = document.querySelector('<kib-column-selector>');
col.getBoundingClientRect().height === band.getBoundingClientRect().height; // flush divider proof
getComputedStyle(col).borderLeft   === '1px solid rgb(217, 217, 217)';      // #d9d9d9
getComputedStyle(document.querySelector('.sha-page-content')).padding === '0px'; // no-padding applied
```

Example assertions that have caught real regressions:
- KIB column height `===` band height (stretch + border-left divider pattern — see [detail-page-pattern.md](components/detail-page-pattern.md)).
- `border-left: 1px solid rgb(217,217,217)` on KIB columns 2+.
- `.sha-page-content` padding `12px → 0px` after appending the `no-padding` class.
- Toolbar↔table left alignment via the `sha-index-table-control` class: measure the quick-search box's x-offset relative to the datatable edge (a −8px overhang means the class is missing).
- Squeezed/scrolling header containers: fix is `dimensions.minHeight: 'fit-content'` (runtime-verified; not in the groups index — clean-form-config may flag it; do NOT strip) — `dimensions` is the only channel reaching the container's outer div; see `style-channels.md` (in `shesha-design-system`).

For pixel-parity work ("match the reference form"), compare **computed** styles in-browser AND do a bidirectional full-key JSON diff — identical-looking designer props can render differently because of one extra key (e.g. a stray `font.color`).

### Clicking dynamically-loading content — one atomic script, not coordinates

A coordinate captured by one `getBoundingClientRect()` call and clicked by a *separate* `computer.left_click` call has real network and render time between the two round-trips. If images or lazy content are still reflowing, the element moves and the click lands on nothing — **silently**, with no error and nothing to see.

For automated verification, find and click in a **single** `javascript_exec`, so there is no gap:

```js
document.querySelector('<selector>').dispatchEvent(new MouseEvent('click', { bubbles: true }));
```

Reserve coordinate-based clicking for the rare case that genuinely needs a trusted OS-level click. This is a different failure from stale element refs (re-find before clicking); the fix for coordinate staleness is atomicity, not re-finding.

### Screenshot / evaluate timeouts are usually not a frozen page

`Page.captureScreenshot` and `Runtime.evaluate` time out at 30–45s with "the renderer may be frozen or unresponsive" around **any large or animated repaint** — modal open/close, many concurrent external image loads, and the already-documented zoom/screenshot sequences. In every observed case the renderer was fine: a 3–10s wait and a trivial `1+1` eval confirmed it, and subsequent calls worked.

Treat these as expected and recoverable. Wait briefly, probe with a trivial expression, and only then conclude something is actually broken — a session hit this 6–8 times, and each premature diagnosis costs a full round-trip.

---

## 5. Don't misattribute

Frontend dev-server compile errors (missing chunks, stuck initialization, blank pages) **look exactly like form bugs**. Before editing markup:

1. Confirm the form's server-side state via API re-fetch (§1) — independently of the browser.
2. If the API state is correct but the browser misrenders: cache (§2), then dev-server health, then [debug.md](debug.md).
3. Only then consider the markup wrong.

In embedded scripts, prefer `formArguments?.id` over parsing `window.location.search` — Shesha-idiomatic and robust across navigation patterns (direct URL, table→details, dialog). See [components/scripts.md](components/scripts.md).

---

## 6. Smoke-failure loop

When a browser smoke test fails, run this exact cycle — no shortcuts:

1. **Capture verbatim** — console errors and network responses with status ≥ 400, quoted exactly.
2. **Consult [debug.md](debug.md)** — match the symptom row; if no row matches, don't guess — report "no match" and ask.
3. **Fix markup** — apply the row's fix (or the diagnosed cause).
4. **Re-push** — [api.md §5](api.md).
5. **Re-fetch verify** — §1; confirm the fix persisted server-side.
6. **Clear the IndexedDB cache** — §2, from `/favicon.ico`. Never skip this after a re-push.
7. **Re-test** — via the correct navigation path (§3).

Never silently retry the same push. Never report success without steps 5–7 passing.

---

### Worked example (project-specific)

From the RequirementsStudio fleet work (2026-06):

- **§3 navigation artifact:** `service-definition-project-add`'s "Add Project" submit 500'd on `ServiceDefinitionProject/Crud/Create` under direct `?id=` load — the same link worked when reached via table→details in MS Edge. The form was never broken.
- **§4 measured proof:** after the `module-definition-details` KIB rebuild, computed column height `===` KIB band height (84px) and `border-left: 1px solid rgb(217,217,217)` on columns 2+ proved the flush-divider pattern; `getComputedStyle('.sha-page-content').padding` went `12px → 0px` across all 16 non-MDD forms after the `no-padding` class.
- **§4 false alarm:** during the all-17-forms KIB rollout, scaled screenshots suggested 10–15px label/value misalignment; `getBoundingClientRect` showed 0px offsets — no fix needed.
- **§2 ghost-chasing:** post-push verification repeatedly stalled on stale renders until the `form`/`form_lookup` IndexedDB databases were cleared from `/favicon.ico`; in-app `deleteDatabase` calls blocked silently.
