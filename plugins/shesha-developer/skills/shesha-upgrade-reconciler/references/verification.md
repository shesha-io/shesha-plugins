# Verification bar

Contents: iron rule | Definition of Done | always | acceptance bar | side by side | business test plan | completion signal

A success toast, an HTTP 200 or a matching hash is not evidence. Verify against the running system with real calls and a real browser, and record what you verified
with `shrec.py verify --kind <item> --result ok|fail|unverified --detail "..."` so the end-of-run report lists it (and lists what is still unverified).

## Iron rule: persistence is not function

**Never write "done", "verified" or "fixed" for a user-visible feature unless the measured Definition of Done points below (placement through read-path) were
MEASURED.** Until then write exactly: "pushed and read back, UNVERIFIED in browser". That sentence is the headline of the hand-over message, not a footnote; record it
with `shrec.py verify --kind placement --result unverified --detail "<what was not measured>"`.

Read-back equality, an HTTP 200, `forms changed 0`, component counts and an idempotent second run all prove that the write PERSISTED. None of them proves the page
works: all of them can pass while a panel sits in the wrong place, Save does nothing and a list shows every record in the system.

A reconcile is NOT "make the markup equal". The tooling optimises for "the same markup as before, written safely", but a branch's markup was correct for the OLD
version, and applying it faithfully is what breaks on the new one. A merge-reconcile must end with **each changed feature exercised on the target**, including the
functionality the branch ADDED (Save, list, filter, ordering), not only layout.

**Probe first, then change.** Measure the running page (script-scope dump `shrec.py probe-scope`, request capture `shrec.py audit-requests`, DOM geometry
`shrec.py dom-chain`), then fix. A guessed fix is usually wrong and needs a measurement to retire.

## Definition of Done for a form reconcile

A form is done only when ALL points are VERIFIED, in a **fresh browser context** (no IndexedDB, no cached markup), with at least **3 loads** (the first load after a
push can look right and later loads wrong, hazard H53). Each point is a ledger `verify` kind:

| `--kind` | Point | What to measure |
|---|---|---|
| `placement` | Placement | Screenshot plus geometry of every new or moved component, compared with the reference screenshot at the same viewport. |
| `request-audit` | Request audit | Capture every XHR the component makes, **without de-duplicating by path** (a first capture can hide the second request), and check the query: the filter is present and names the right parent id, the sort is present, `properties` is not trimmed below what the row needs. **Record ids:** for EVERY action that sends a record id (every Save, Calculate, workbook save, dialog open) capture the request (hook `fetch` AND `XMLHttpRequest`) and assert the id is present and not `undefined`, in the URL AND the body. A 200 is not enough: a missing id can still return 200 on endpoints that fall back. |
| `data-audit` | Data audit | Compare the rendered set with the database for that record. Every rendered row must belong to the record, and the count must match the database count for that filter. This is the check that finds data leaks. |
| `row-content` | Row content audit | Every field of every row is non-default (no placeholder or default values, no blank cells, no "No data") and matches the database value. Judge by screenshot, never by `innerText` (collapsed or clipped content still appears in it). |
| `write-path` | Write path | Click the real Save / Add / Delete in the browser, read the row back through the API, check parent, author and ids, then clean up the test row you created, and ONLY that row (the user's own test rows stay). |
| `read-path` | Read path after the write | The new row appears, in the right position, and the input is cleared. A value that reached the database can still render blank: the read path is gated separately. |
| `idempotence-fixed-point` | Idempotence AND a fixed point | The rules report `forms changed 0` AND every fix transform you wrote reports "already applied". Two rules that disagree keep reporting changes (for example a margin of 0 against a rule's -3) until they are reconciled. |
| `reread` | Re-read after minutes | Read the form again some minutes after the push and diff it against what you wrote. The designer normalises and can re-nest (hazard H47). |
| `reviewer` | The reviewer exercises it | The reviewer exercises it in their own browser and says it works. Only then export, commit and PR. Ask them to close stale Configuration Studio tabs and clear IndexedDB `forms` first: their cache can disagree with a fresh-context measurement; trust the fresh measurement. |

Record each point (`shrec.py verify --kind <kind> --result ok|fail|unverified --detail "..."`); whatever was not measured is listed as unverified. A result recorded
BEFORE the last push is stale and does not count: re-verify after every push. `shrec.py report` shows the table and its headline says "PUSHED AND READ BACK - UNVERIFIED IN
BROWSER. Do not call this done." until `placement`, `request-audit`, `data-audit`, `row-content`, `write-path` and `read-path` are recorded ok after the last push. If the points from
`placement` to `read-path` are not recorded, the headline of your hand-over message says "UNVERIFIED IN BROWSER" (do not rely on the report to say it for you). Other
kinds exist for evidence that is not a Definition of Done point: `browser`, `e2e`, `rerun`, `other`.

## Always

1. **Idempotence and persistence.** After a push run the same command without `--push`: it must print `forms changed 0`. The push layer has already read every form
   back (markup and modelType) and backed up the row before writing.
2. **Caches.** Before concluding an edit "had no effect", clear the browser form caches (IndexedDB `form:<appKey>`, `form_lookup:<appKey>`, `forms`) and reload; close
   stale Configuration Studio tabs on the form (a stale tab saves old markup over the push, hazard H27). A stale cache is the most common false negative.
3. **Save paths.** For any form with a Save: `shrec.py e2e-save <module>/<form> <record id> --push` (it saves the record, so it is a dry run without `--push`; local role: Edit, Save unchanged, expect 200 writes and back to view; the
   button texts come from `project.json` `e2e`, and the outcome is logged as a `verify` event). A saved value that reached the database
   can still render blank: verify the read path separately.
4. **The settled UI.** Never diagnose a sub-form's data context from a network capture taken during hot reload or first paint; watch the element for 30 seconds or
   more (a single snapshot can be either state).

## Acceptance bar

A page is fixed only when every option, condition and scenario works AND the view is aligned like the reference, not just the default record. For each page:

- empty versus populated data; each status or stage; each type of record the page handles; each dropdown value that shows or hides components;
- each dialog and toolbar action (read-only), row selected versus none selected;
- alignment, overflow, inner scrollers and labels against the same view on the reference, side by side.

Report which scenarios were exercised and which could not be reached.

## Side by side, never by memory

Before writing "same on the reference" or "legacy": perform the **identical action on both environments** (read-only, write-guarded browser session) on a record in
the same status and type, capture both screenshots and the control state (disabled / readOnly), and cite them. If the reference cannot be exercised without writing,
mark it "verify on reference", not "legacy". A "same on the reference" verdict reached by reading code or by remembering has hidden real defects. Record
supersessions explicitly in `defects.jsonl` (`shrec.py defect set D-<n> ...`) rather than deleting the old note.

## Business test plan

When the project has an acceptance test plan, it is the acceptance bar: execute its cases (high focus first) on localhost with recordings before calling the
work complete; keep the original file unmodified and record per-case results in a copy. Your own smoke and end-to-end suites are pre-checks.

## Completion signal

For user-facing work the real signal is the reviewer exercising the pages in their own browser and saying it works. Wait for that before commit, push and PR.
