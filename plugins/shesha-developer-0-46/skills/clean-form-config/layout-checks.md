# Layout Checks

All layout-level validation rules for the `clean-form-config` skill. Run during Step 4e. New checks can be appended as L3, L4, etc.

---

## Check L1 — Container dimension overflow

**Trigger:** `type === 'container'` with at least one direct child.

For each breakpoint `['desktop', 'tablet', 'mobile']`:

1. **Resolve flex direction** (priority): `comp[bp].flexDirection` → `comp[bp].direction` → `comp.direction` → default `"row"`
2. **Map to axis**: `"row"/"horizontal"` → `width`; `"column"/"vertical"` → `height`
3. **Resolve flexWrap**: `comp[bp].flexWrap` → `comp.flexWrap` → `"nowrap"`
4. **For each direct child**: read `child[bp]?.dimensions?.[axis]`. Parse `%` values; skip `"auto"`, `px`, `rem`, `em`, `vh`, `vw`, absent.
5. **Sum** parsed percentages. Flag if **sum > 100%**:
   - `flexWrap === "wrap"` → `[MANUAL REVIEW — wrap enabled, may be intentional]`
   - otherwise → `[MANUAL REVIEW]`
6. Also flag any **single child with individual value > 100%**.

Output format:

```
  • "Container1" (container) — desktop: children width = 200%
    (dropdown2: 100%, dropdown1: 100%) [wrap enabled — may be intentional] [MANUAL REVIEW]
```

---

## Check L2 — labelCol + wrapperCol span

**Trigger:** Check `formSettings` AND every component that has `labelCol` or `wrapperCol` at top-level.

Rules:

| labelCol.span | wrapperCol.span | Action |
|---|---|---|
| null/absent | null/absent | Skip |
| Number N (> 0) | null/absent | **AUTO-FIXABLE**: set wrapperCol.span = 24 − N |
| null/absent | Number M (> 0) | **AUTO-FIXABLE**: set labelCol.span = 24 − M |
| N + M = 24 | — | OK, skip |
| N + M ≠ 24 | — | **MANUAL REVIEW** |

Skip if either value is 0 (intentional full-width / labelless layouts).

Auto-fix: write `24 − knownSpan` to the absent/null span on the same object (`formSettings`, `component.labelCol`, or `component.wrapperCol`).

Output format:

```
  • formSettings: labelCol.span=8, wrapperCol.span=null → set wrapperCol.span=16 [AUTO-FIXABLE]
  • "First Name" (textField): labelCol.span=10 + wrapperCol.span=10 = 20 ≠ 24 [MANUAL REVIEW]
```

---

## Check L3 — Device-specific styles at wrong property path

**Trigger:** Any component (including containers).

Two sub-checks:

**L3a — Top-level `dimensions` without breakpoint wrapper**

1. Flag if `comp.dimensions.width` or `comp.dimensions.height` is set at the **top level** of the component (i.e. not nested inside `comp.desktop`, `comp.tablet`, or `comp.mobile`).
2. The correct path is `comp[bp].dimensions.width/height`. Top-level dimensions may be ignored or behave inconsistently across breakpoints.
3. Not auto-fixable — the intended breakpoint cannot be inferred.

**L3b — `style.width / style.height` conflicts with `[bp].dimensions`**

1. Flag if `comp.style.width` or `comp.style.height` is set **and** `comp[bp].dimensions.width` or `comp[bp].dimensions.height` is also set for **any** breakpoint `['desktop', 'tablet', 'mobile']`.
2. These two approaches conflict: `[bp].dimensions` is the Shesha layout system; `style` is raw CSS applied directly.
3. Not auto-fixable.

Output format:

```
  • "Panel" (container): dimensions.width="50%" set at top level — should be inside desktop/tablet/mobile [MANUAL REVIEW]
  • "Avatar" (image): style.width="100px" conflicts with desktop.dimensions.width="100%" [MANUAL REVIEW]
```

---

## Check L4 — Style properties differ between breakpoints

**Trigger:** Any component that has a `style` object set under two or more of `['desktop', 'tablet', 'mobile']`.

1. Collect every breakpoint `bp` where `comp[bp].style` exists and is a non-empty object.
2. If fewer than 2 such breakpoints exist, skip.
3. Build the union of all style keys across those breakpoints.
4. For each key, compare values across present breakpoints. Flag any key whose value differs.
5. **Colour-related keys** (`color`, `backgroundColor`, `borderColor`, `outlineColor`, `caretColor`, `fill`, `stroke`) are listed first — differences here are most likely accidental.
6. All other differing style keys are listed underneath as "non-colour style differences".

Never auto-fixable — differences may be intentional responsive theming.

Output format:

```
  • "Submit" (button) — colour styles differ between breakpoints [MANUAL REVIEW — confirm if intentional]:
      backgroundColor: desktop="#0070f3", mobile="#ff0000"
  • "Panel" (container) — non-colour style properties differ between breakpoints [MANUAL REVIEW — confirm if intentional]:
      padding: desktop="16px", tablet="8px"
```

---

## Check L5 — datatable / datalist outside a dataContext

**Trigger:** Any component whose `type` is `"datatable"` or `"datalist"`.

**Rule:** Both components require a `dataContext` ancestor (the data wrapper that fetches the rows) in order to receive data. A `datatable` or `datalist` placed at the root level, or nested only inside layout containers (card, panel, container, columns, tabs, etc.), will render but show no data.

**How to check:**

1. Walk the component's ancestor chain (via `parentId` lookups) up to the form root.
2. At each ancestor, check `ancestor.type`.
3. Pass if **any** ancestor has `type === "dataContext"`.
4. Fail (flag as `[MANUAL REVIEW]`) if no such ancestor is found.

Layout-only container types to skip past (not data contexts): `container`, `card`, `collapsiblePanel`, `columns`, `sizableColumns`, `tabs`, `wizard`, `drawer`, `subForm`, `space`, `section`, `sectionSeparator`.

0.46 note: a stored `datatableContext` is migrated to `dataContext` on load (type rewritten, version 8), so treat `datatableContext` as a data context too. Both are deprecated/legacy-named in the toolbox; new forms use `dataContext`.

Output format:

```
  • "MyTable" (datatable) — not inside a dataContext; will show no data [MANUAL REVIEW]
  • "ResultList" (datalist) — not inside a dataContext; will show no data [MANUAL REVIEW]
```

---

---

## Check L6 — subForm hides hosted field labels (0.46)

**Trigger:** `type === "subForm"`.

The sub-form label span is `hideLabel === true ? 0 : labelCol ?? 0` (`labelCol` / `wrapperCol` on a subForm are plain numbers, not `{ span }` objects) and it is applied to the hosted form's fields, so span 0 hides their labels. The 0.46 migration sets `hideLabel: true` on every sub-form (v4), so most migrated sub-forms are affected.

Flag `[MANUAL REVIEW]` when `hideLabel === true` or `labelCol` is falsy. Workaround when the hosted form should show labels: `labelCol: 8`, `wrapperCol: 16`, `hideLabel: false`. Not auto-fixable (some hosted forms are deliberately label-less). Same finding as `scan-046.mjs` check N6.

---

*(Future checks — e.g. minWidth > maxWidth, height: "100%" inside auto parent — append here as L7, L8, etc.)*
