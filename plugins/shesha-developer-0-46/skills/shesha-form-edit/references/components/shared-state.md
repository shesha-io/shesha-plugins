# Shared state - appContext / page.state / form data / storage (0.46)

**Banned:** `globalState`, `setGlobalState(...)` — Shesha's older, weaker primitive, superseded by `contexts.appContext`.

**`localStorage` / `sessionStorage`: use sparingly, only when justified.** `localStorage` is XSS-readable — never store auth tokens, PII, or anything sensitive there. But it's the right tool when state must survive a hard refresh (F5, new tab, browser restart) AND server-side persistence isn't appropriate. See §"When localStorage is OK" below.

**Default to the three context primitives. Pick by scope:**

| Primitive | Where to use it | Lifetime |
|---|---|---|
| `data` / `form.data` | State that lives in *this form only* - the form's own field values, transient UI flags scoped to one form. Read via `data?.fieldName`; write via `form.setFormData({ values, mergeValues: true })`. | One form instance |
| `page.state` (was `pageContext`) | State shared between **two pages** — a value set on page A that page B needs to read. **Prefer this over `appContext` for inter-page passing.** Same object as the legacy `pageContext`, which still resolves. | One page navigation chain in the SPA |
| `contexts.appContext` | State that's genuinely **app-wide** — needed in many places, no clear page boundary. The currently-selected tier across pricing → auth → wizard, the active brand variant. | The SPA session. **Cleared on full page reload.** |

---

## appContext — read/write syntax

Direct property access. There's no setter function:

```js
// READ
const org = contexts.appContext.selectedOrg;
const tier = contexts.appContext.selectedTier;

// WRITE
contexts.appContext.selectedOrg = data.organisationId;
contexts.appContext.selectedTier = {
  id: data.id,
  name: data.name,
  mode: data.mode
};
```

Available inside any embedded script. Values are shared across all forms — set on one form, read on another.

---

## Caveat — appContext does NOT survive a hard refresh

`contexts.appContext` is in-memory only. F5 / Ctrl+R / opening in a new tab → values are gone. For a typical SPA flow (`application.navigator.navigateToUrl(...)` — soft navigation), it survives fine.

If you need state that survives a hard refresh: **don't** stash it in `localStorage`. Either pass it through the URL (`?tierId=...`) and re-read via the form's `formArguments`, or persist server-side (a draft entity row, a user-preference setting).

---

## Picking between page.state and appContext

From the Shesha docs: *"For inter-page data passing, Page Context is advised over App Context unless the value is genuinely global."*

Concrete: a selected tier carried from `tier-pricing` → `auth-login` → `member-registration` arguably crosses three pages, but it's a single user-flow concept — `page.state` would be enough. Use `appContext` only when *every* form in the app might need to read it (brand variant, language, current organisation).

---

## When localStorage IS OK

Use `localStorage` (or `sessionStorage`) when **all** of the following hold:

- The value must survive a **hard refresh** (F5 / new tab / browser restart). `appContext` and `page.state` are in-memory only; they don't.
- Server-side persistence isn't appropriate (no draft entity row, no user-preference setting fits the use case, or the round-trip cost would hurt UX).
- The value is **not sensitive** — no auth tokens (Shesha already manages those), no PII, no secrets.

Concrete green-light examples:
- A pending registration intent the user is mid-flow on, surviving an accidental F5.
- "Last selected tier" UX preference on the public landing page.
- An OTP `operationId` that needs to survive between the send-pin page and the verify-pin page even if the user reloads.
- Theme preference, language preference (when not yet logged in to set it server-side).

Use `sessionStorage` when the value should die when the tab closes (more conservative than `localStorage`). Always namespace keys (`app_pendingRegister`, not `pendingRegister`).

## Common-mistake mapping

| Old pattern (don't write) | Better pattern |
|---|---|
| `setGlobalState({ key: 'selectedTier', data: tier })` | `contexts.appContext.selectedTier = tier` (or `page.state.x = ...`) |
| `pageContext.x` | `page.state.x` |
| `globalState?.selectedTier` | `contexts.appContext.selectedTier` |
| `localStorage.setItem('accessToken', ...)` | Use Shesha's built-in token mechanism — never store auth tokens client-side yourself |
| `localStorage.setItem('userProfile', JSON.stringify(user))` (PII) | `user` (the typed current-user object, in-memory only) or fetch from `/Session/GetCurrentLoginInformations` on demand |
| `localStorage.setItem('pendingRegister', ...)` (mid-flow intent) | OK if it must survive refresh — namespace the key (`app_pendingRegister`) and clear it once consumed |

Reference: https://shesha-grads.vercel.app/docs/shesha-basics/appContext
