# Templates — natural-language inference

Two of Shesha's stock templates are first-class in this skill:

- **`Shesha/details-view`** — single-record details / edit page. Substitution catalog has four slots (TITLE, KEYINFOBAR, DETAILSPANEL, CHILDTABLES).
- **`Shesha/table-view`** — entity list with filter selector + table. Substitution catalog has two slots (TABLEFILTER, TABLECOLUMNS).

Everything else → seed = **blank** (no `templateId` on Create, build the markup from scratch in Step 6). This includes create-only forms, login / register / OTP / anonymous pages, dashboards, reports, and any custom layout that doesn't fit the two patterns above. The other stock template forms on the backend (`blank-view`, `create-view`, `*-extension-json`) exist but are not promoted — `blank-view` is redundant with a blank seed, and `create-view`'s slots haven't been catalogued.

---

## Decision table

| User intent (paraphrased) | Triggering phrases | Template | Seed |
|---|---|---|---|
| View / edit / display a **single** record of an entity | "details", "view page", "edit X", "X profile", "X page", "form for the X" (singular) | `Shesha/details-view` | template |
| Browse / list / search a **collection** of records | "list of Xs", "X table", "browse Xs", "manage Xs", "search/filter X", "all Xs", plural noun | `Shesha/table-view` | template |
| Login / register / OTP / public-access form | "login", "sign in", "register", "OTP", "verify", "anonymous", "public", "no-auth" | — | blank (set `access: 5`) |
| Custom dashboard / report / non-CRUD layout | "dashboard", "report", "summary", "homepage", "landing" | — | blank |
| Create-only form for adding new records | "form to create a new X", "X creation form", "add a new X" | — | blank (not first-class — substitution catalog doesn't cover `create-view` yet) |
| Unclear / mixed signals | anything else | — | blank, **then ask** whether the user wants `details-view` or `table-view` |

The decision is **inferred first, asked second**. If the prompt clearly matches one of the two template intents AND the form is entity-bound, proceed directly. If the signal is ambiguous, default to blank and confirm.

---

## Classification rules

A request maps to a **template** seed only when **all three** hold:

1. **Intent matches** the details or table row above.
2. **Form is entity-bound** — user supplied a `modelType`, or the form name strongly implies one (e.g. `person-details-test` → Person). Non-entity forms always go blank.
3. **User didn't explicitly say "blank" / "from scratch" / "empty"** — explicit override wins.

When the user **explicitly names** a template (`"based on the details-view template"`, `"copy from blank-view"`, `"using table-view"`), **respect their choice** — even if intent classification would have picked differently. Explicit naming is the strongest signal.

---

## Worked examples

| Prompt | Inferred intent | Entity-bound? | → Seed |
|---|---|---|---|
| "Create a `person-details` form bound to `Shesha.Domain.Person`" | details (singular) | yes | `details-view` template |
| "Build a form for browsing all Customers" | table (plural / browse) | yes (Customer) | `table-view` template |
| "Make a `person-quickview` page for the Person entity" | details (page = view-single) | yes | `details-view` template |
| "Create a Persons table in `Forms.Optimization`" | table (plural noun + "table") | yes (Person) | `table-view` template |
| "Create a login form called `auth-login` reachable without login" | login | no | blank, `access: 5` |
| "Build a dashboard showing key membership stats" | dashboard | no | blank |
| "Form to add a new member" | create-only (not first-class) | yes | blank |
| "Form for managing person details" | view-single vs. browse-all — **ambiguous** | yes | blank, **ask** "details (one record) or table (browse all)?" |
| "Create a form based on the `blank-view` template" | explicit naming | n/a | blank (explicit override) |
| "Build a `customer-edit` form for Customer" | details (edit one) | yes | `details-view` template |
| "Create `person-test` in Forms.Optimization, no entity" | unspecified intent, no entity | no | blank |

---

## Resolving the template id at runtime

Don't bake template ids into the skill — they vary across environments. Resolve via `GetByName`:

```bash
curl -s -G "$BASE_URL/api/services/Shesha/FormConfiguration/GetByName" \
  --data-urlencode "module=Shesha" \
  --data-urlencode "name=details-view" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Capture `result.id` → pass as `templateId` on the Create payload.

If `GetByName` returns null for one of the two canonical templates, the backend doesn't have it (uncommon — surface the issue to the user and fall back to blank seed).

---

## When the skill uses this

**Step 3b.3 — Pick a seed strategy** — before deciding between template / inline-markup / blank:

1. Did the user **explicitly name** a template (e.g. "details-view")? → Use it. Fuzzy names resolve via [semantic-search.md](semantic-search.md) on the form list.
2. Otherwise, classify intent against the decision table above:
   - **details/table match + entity-bound + no explicit blank override** → seed = template; resolve `Shesha/details-view` or `Shesha/table-view` via `GetByName`; capture the id.
   - **anything else** → seed = blank.
3. Proceed to Step 3b.4 (`POST /Create`).

The substitution in Step 6 then follows [template-placeholders.md](template-placeholders.md) — four slots for `details-view`, two for `table-view`.

---

## Notes & gotchas

- **`formSettings.modelType` must be set inside the markup**, not just on the Create payload. The substitution catalog depends on it (DETAILSPANEL field set, CHILDTABLES filter, KEYINFOBAR picks). Step 3b.2 already captures this.
- **A form with no `modelType` cannot meaningfully use either template** — the substitution catalog has nothing to substitute with. Force the seed to blank for non-entity forms.
- **The `isTemplate` boolean on FormConfigurationDto is not used** for identification — Shesha doesn't set it on the stock templates. Identification is by name + module convention only.
- **Don't treat user-created forms as templates** unless the user explicitly names them. Just because a form exists called `some-team/details-template` doesn't mean it has the same placeholder catalog — only `Shesha/details-view` and `Shesha/table-view` are guaranteed to.
