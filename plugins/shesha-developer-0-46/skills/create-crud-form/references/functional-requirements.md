# Functional requirements

What a "complete" canonical CRUD form must have. Every requirement here is either a rendering blocker (the form doesn't work) or a standard-of-record violation (the form works but doesn't look like the sample). Match your build to the [screenshots](../assets/screenshots/).

## Every input form needs a `validationErrors` component

If the form has any `required` input, add `validationErrors` (v=0, no props, component name `formErrors`). Convention: place it in the body, just before the button row (or in the create form, just after the subtitle text). Omit and the user experience on a failed submit is a dead form — the browser sees no error surface and the submit just doesn't happen visibly.

```jsonc
{
  "id": "<uuid>",
  "type": "validationErrors",
  "version": 1,
  "componentName": "formErrors",
  "propertyName": "formErrors",
  "parentId": "<pid>"
}
```

## `buttonGroup` — always `isInline: true`

Every buttonGroup that holds action buttons (page-header actions, hero lifecycle, toolbar actions, quick-actions bar) sets `isInline: true`. Without it, buttons collapse into a "..." dropdown menu — the user sees no button, just an ellipsis.

```jsonc
{ "type": "buttonGroup", "version": 16, "isInline": true, "items": [ … ] }
```

## Save + exit pair — every edit-mode form

Every editable form has BOTH a Save (Submit) button AND an exit button (Cancel / Back / Cancel Edit) in the SAME `buttonGroup`. Never a Save without a way out.

- **Details form**: Edit + Save + Cancel Edit trio in the header's buttonGroup — all `actionOwner: "shesha.form"`. All three always in the DOM; Shesha handles visibility.
- **Create form (in modal)**: **none** — the modal footer supplies Save/Cancel via `footerButtons: "default"`. Do NOT add an in-form button row.
- **Standalone create page** (rare — use `shesha-form-edit` instead): Save (primary, `Submit`/`shesha.form`) + Back (default, `Navigate`/`shesha.common`) in a single buttonGroup.

## Every action button lives inside a `buttonGroup` — never as a standalone `button`

The standalone `button` type is reserved for rare inline-in-content cases (a button next to a paragraph). For the form's action row, ALWAYS use `buttonGroup` with `items[]`. Downstream tooling reads form intent from `buttonGroup` items — a loose top-level `button` gets misread as read-only.

Save button MUST wire to `actionName: "Submit"` / `actionOwner: "shesha.form"`. See [action-configurations.md](action-configurations.md#detail-view-lifecycle--start-edit--submit--cancel-edit).

## Human-readable labels on every input

Labels are both user-facing AND how browser-based tests locate fields. A raw `propertyName` (`firstName`) as a label fails both — it reads as "first name" (lowercase, no punctuation), doesn't wrap correctly, and confuses accessibility tooling.

Rule: every input has a `label` in **sentence case** ("First name", "Physical address", "Notification type" — NOT "First Name", "physical_address", or "firstName").

Required inputs are marked with an asterisk automatically when `validate.required: true` — don't add "*" to the label yourself.

## Details form — the page-header block

Every details form has a header block at the top with:

- **Left**: a hero title text (`{{data.firstName}} {{data.lastName}}` for Patient; `{{data.name}}` for most other entities - 0.46 roots plain-string mustache at `data`) + optional inline `refListStatus` pill (status field) + optional meta-line text (using code-mode for `moment().diff` age, code composition, etc.).
- **Right**: the lifecycle `buttonGroup` (Edit / Save / Cancel Edit). See [action-configurations.md § Detail-view lifecycle](action-configurations.md#detail-view-lifecycle--start-edit--submit--cancel-edit).

Optionally a quick-actions bar (Book Appointment / Order lab test / etc.) below the header, in a second buttonGroup.

## Table form — the 3-layer visual sandwich

Every table form has the three nested container layers, matching the seed:

```
dataContext (root)
└─ container(pageShell)      bg #fafafa, padding 20            ← outer grey shell
   ├─ container(headerCard)  bg #ffffff, subtle shadow, padding 15   ← white card #1: page-header
   │  └─ [title-block + actions-block (Export + Add primary)]
   └─ container(tableSurface) bg #ffffff, subtle shadow, marginTop 15, paddingBottom 15   ← white card #2: table
      ├─ container(toolbarRow)  transparent, padding 15  → [quickSearch, Filters, Column Selector]
      ├─ datatable
      └─ datatable.pager
```

Byte-exact style blocks for the three layers live at `../assets/examples/sample-patient-table.json` (containers `pageShell` / `headerCard` / `tableSurface`). Copy them verbatim.

Missing layers produce visible defects:
- No `pageShell` → page-header floats bare on the canvas
- No `headerCard` → page-header has no white surface
- No `tableSurface` → toolbar+datatable+pager don't group visually

## Create form — card-content grid

Every `card` in a create form (or a details Overview tab) has this content pattern:

- **`card.content.components`** = a sequence of components. The FIELD-holding children are `container`s with `desktop.display: "grid"` + `gridColumnsCount: 2` (or 3 for rows like blood-type / height / weight). Standalone span-full siblings (`address`, `htmlRender`, `textArea`) sit as direct `card.content` children between the grid containers.

- **`gridColumnsCount` is 2 or 3**, never 1, never 4+.

- **Do NOT decompose into multiple horizontal-flex `row1` / `row2` containers**, each holding 2 fields. It renders 2 columns visually but loses the seed's field-spacing behavior and drifts from the standard.

Enforced by validator R6.

## Every form has a working push loop

- List form → its `Add` button opens `<entity>-create` in a modal → `onSuccess: Refresh table` reloads the list
- List form → its row-action column opens `<entity>-details?id={{selectedRow.id}}`
- Details form → header `Edit` (`Start Edit`) + `Save` (`Submit`) + `Cancel Edit` (`Cancel Edit`) — all `shesha.form`

Cross-form nav breaks silently if any of these are missing. Test the full loop before signing off.

## Optional — browser smoke recipe

After push, load the form in a headless browser to catch runtime errors JSON validation can't. **Clear the portal's IndexedDB form caches first** (`form:default-app`, `form_lookup:default-app`, legacy `forms`): the portal otherwise serves a stale copy of the form even though the API read-back shows your change (recipe: `../shesha-form-edit/references/verification.md` section 2). Use a fresh browser context at minimum.

```js
// smoke.js
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  // login
  await p.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await p.waitForTimeout(4000);
  await p.getByPlaceholder('Username').fill(process.env.SHESHA_USER);      // from the task's context block, never hard-coded
  await p.getByPlaceholder('Password').fill(process.env.SHESHA_PASSWORD);
  await Promise.all([
    p.waitForURL(u => !u.pathname.includes('/login'), { timeout: 30000 }).catch(()=>{}),
    p.getByRole('button', { name: /sign in/i }).click(),
  ]);
  await p.waitForTimeout(6000);
  // load the target form
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('response', r => { if (r.status() >= 400 && r.url().includes('/api/')) errs.push(`API ${r.status()} ${r.url()}`); });
  await p.goto('http://localhost:3000/dynamic/<Module>/<form-name>?id=<optional>', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await p.waitForTimeout(15000);
  await p.screenshot({ path: '<form-name>.png' });
  console.log('errors:', errs.length); errs.forEach(e => console.log(' -', e));
  await b.close();
})();
```

Compare the screenshot to the matching seed's [reference screenshot](../assets/screenshots/). Zero page errors + a rendered layout that matches the seed = form is done.

Load the details form via **table-row → click** (not a pasted `?id=`) whenever possible — subtable Add/Create submits 500 without the full page context.

## The five hard rules — repeated for emphasis

These are what break forms most often. If you get nothing else right, get these right:

1. **`displayComponent`/`editComponent`/`createComponent` with a real type → wrap in `settings`** (R3)
2. **Plain-string mustache = `{{data.name}}` on 0.46, NOT a bare `{{name}}`** (R2 / R11)
3. **`tab.key === tab.id`, all unique across `tabs.tabs[]`** (R4)
4. **`buttonGroup.isInline: true`** — every buttonGroup (R8)
5. **Create-form inputs use `editMode: "editable"`** (R9)

Everything else is polish. These five are correctness.
