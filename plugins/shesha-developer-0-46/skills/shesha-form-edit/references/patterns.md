# Pattern index — `assets/patterns/`

Seed forms shipped with this skill. Copy one as a starting point when creating a new form, then mutate. Always run an id-remap pass after deep-cloning (see [components/layout.md](components/layout.md)).

| Pattern | Use for | Notes |
|---|---|---|
| `auth-login.json` | Login, register, forgot-password, OTP, branded confirmation — any anonymous auth-style page | Outer container → card → image (logo) → inner container → fields → primary action → footer link row. The canonical reference for [components/layout.md](components/layout.md). sample-branded; swap logos and copy as needed. Set `formSettings.access = 5` for anonymous pages. |
| `dashboard.json` | Logged-in landing pages, entity-bound dashboards with a summary card + nested datalist + conditional empty state | Welcome banner (gradient) + action row + entity-bound `subscriptionCard` (with `dataContext` + sub-form-renderer `datalist` for benefits) + `noSubscriptionCard` empty state gated on `data?.hasSubscription`. Strong reference for "summary card + items list" layouts. Note the `onBeforeDataLoad` script pattern for hydrating form values from multiple `http.get` calls. |

---

## What belongs here

- **Generic structural patterns** — the *shape* is reusable across projects/entities even if entity names happen to be a sample app inside the seed.
- **Reference implementations of non-trivial mechanisms** — multi-step `onBeforeDataLoad`, action chaining (`onSuccess` / `onFail`), `permanentFilter` with code-mode IPropertySetting, sub-form-renderer datalists.

## What does NOT belong here

- Project-tied row templates (e.g. `tier-benefit-row`) — those go in `.claude/cache/shesha-form-edit/seeds/`.
- One-off PUT bodies, builder scripts, scratch JSON — those go in `.claude/cache/shesha-form-edit/_archive/`.
- Forms that only work because of project-specific entity binding — keep in `seeds/`.

## Promotion rule

To promote a seed from `seeds/` → `patterns/`: scrub project-specific entity refs (or tag them as "replace this with your entity"), confirm the structure has been used at least twice in different projects, and add a row above.
