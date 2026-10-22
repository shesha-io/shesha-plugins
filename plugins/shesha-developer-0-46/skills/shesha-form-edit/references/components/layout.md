# Layout pattern: container → card → inner container → sections

The project's house pattern for full-page forms (auth pages, registration, single-record edit screens). Mirror it for any new page-style form so it looks consistent with the rest. The reference implementation is `auth-login` in module `MyApp.Membership` (also bundled at `assets/patterns/auth-login.json`) — copy its JSON when starting a new page.

```
[root]
└── container "outer"            ← page-level wrapper. centers the card.
    ├── direction: vertical
    ├── display: grid
    ├── justifyContent: center
    ├── alignItems: center
    ├── dimensions.height: 100svh
    └── stylingBox padding: 15px
        │
        └── card                  ← Shesha card component (white box with shadow)
            ├── header.components: []          ← usually empty
            └── content.components:
                ├── image                       ← logo at top of card
                │   ├── dataSource: "url"
                │   └── url: "/images/app-logo.png"
                │
                └── container "innerContent"   ← form content wrapper
                    ├── text "heading"          ← page title
                    ├── text "subtitle"
                    │
                    ├── columns "rowOfFields"   ← side-by-side inputs (firstName + lastName)
                    │   ├── col.components: [textField]
                    │   └── col.components: [textField]
                    │
                    ├── textField "field1"      ← editMode: "editable"
                    ├── textField "field2"      ← editMode: "editable"
                    │
                    ├── container "groupBlock"  ← a semantic div
                    │   ├── checkbox "consent1" ← editable
                    │   └── checkbox "consent2" ← editable
                    │
                    ├── button "submit"         ← editable, primary action
                    │
                    ├── container "footerRow"   ← inline text + link row
                    │   ├── text "Already have an account?"
                    │   └── link "Sign in"      ← editable
                    │
                    └── text "footer"           ← copyright line
```

> The `editMode: "editable"` annotations above are action-page components (auth-login is an anonymous action page — hence `"editable"` per the form-type rule); detail forms use `"inherited"` — see [edit-mode.md](edit-mode.md).

---

## Key conventions

1. **`card` is a real component** with `header: { id, components: [] }` and `content: { id, components: [...] }` slots. "Children of the card go in `content.components`, **never** directly on the card." The header slot is usually empty for full-page forms; only use it for a card title bar. See [containers.md](containers.md#card).

2. **The inner `container`** inside `content.components` exists so you can scope padding, background, and spacing for the form-content area separately from the card chrome itself. Without it, padding fights with the card's built-in padding.

3. **Sub-containers as semantic divs** — wrap related rows in their own `container` (consents block, action row, footer row). Each sub-container can carry its own `desktop.flexDirection`, `justifyContent`, `alignItems` for horizontal layout where needed.

4. **`columns` is LEGACY — don't author it.** You'll meet it in existing forms (a grid row of firstName + lastName, two buttons, label + value; "total `flex` must be 24"). New splits are flex `container` rows sized via `desktop.dimensions.width` — see [containers.md](containers.md). For a simple inline text + link row, prefer a sub-`container` with `flexDirection: "row"` and `alignItems: "baseline"` — wraps cleaner on narrow viewports.

5. **`link` for inline anchors** — "for 'Sign in' / 'Forgot password' / 'Create one' links inline with text, use the `link` component" (see [actions.md](actions.md)), not a button styled as link. Buttons in a flex row don't align well with surrounding text.

6. **Don't recreate page chrome from scratch** — copy `auth-login`'s JSON, deep-copy, regenerate ids on the cloned subtree (preserving `parentId` references via an id-remap pass), and replace just the inner content. The designer-tweaked styles for the outer container, card, image, and inner container are tedious to author by hand.

---

## Tree id-remap when cloning forms

When copying a form's JSON as a starting point, regenerating ids requires **two passes**:

1. **Pass 1**: assign new ids and build an `old → new` map.
2. **Pass 2**: rewrite every `parentId`, every `containerId`, and any other id reference using the map.

"A single-pass approach drops parent-child relationships." Skeleton:

```js
const template = JSON.parse(GET_FORM_MARKUP("auth-login"));
const idMap = {};
walkTree(template, n => { const old = n.id; n.id = uuid(); idMap[old] = n.id; });
walkTree(template, n => { if (idMap[n.parentId]) n.parentId = idMap[n.parentId]; });

const inner = template.components[0]   // outer container
              .components[0]            // card
              .content.components[1];   // inner container
inner.components = buildMyFields({ parentId: inner.id });

PUT(/UpdateMarkup, { id: myFormId, markup: JSON.stringify(template), access: 5 });
```

For a fully-worked builder example, see `.claude/cache/shesha-form-edit/_archive/build-dashboard.js` (project-specific reference).

---

## When NOT to use this pattern

Single-component forms (a sub-form embedded somewhere else, a row template for a `datalist`), data-list/data-table host pages, dashboards with multiple top-level cards. For dashboards, see `assets/patterns/dashboard.json` for the canonical entity-bound dashboard layout.
