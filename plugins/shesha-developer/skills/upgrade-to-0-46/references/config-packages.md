# Config packages (`.shaconfig`)

Form configuration shipped in the repo is the fourth failure class, and the least visible. These
defects survive a clean build, a successful start-up and a green migration run. They are found by a
person looking at a screen.

---

## §1. Reading a `.shaconfig`

A `.shaconfig` is a ZIP of configuration items. Three details are easy to get wrong, and each one
silently yields zero results rather than an error:

- form entries live at `<ModuleName>/form/<name>.json` inside the archive;
- the markup key is **`Markup`** — PascalCase. A lowercase guess finds nothing;
- `Markup` is sometimes a JSON **string** that needs a second parse.

Walk components recursively: children hang off `components`, and containers nest.

---

## §2. Container layout is flattened, and the damage is in the database

**Symptom.** A horizontal container renders stacked after the upgrade — children full width, gap
gone, row reading as a column. Nothing errors.

**Cause.** The breakpoint block ends up `display: block`, or with no `display` at all, while still
carrying `justifyContent`, `gap`, `flexWrap` and sometimes `alignItems`. Those do nothing without
`display: flex`, so the intent survives in the config while the layout does not.

**Fix.** Set `display: flex` on the affected breakpoint block, keeping the existing gap and
justification.

### Where it actually hurts

**The upgrade writes the flattened blocks into the database copy of the form, not into the package
in the repo.** Consequences, in order of how much time each costs:

- The shipped package is usually *clean*. Reading it proves nothing about what the app renders.
- A developer who fixes the layout in the designer has fixed it **only in their own database**. On
  a fresh database the old package re-imports and the spacing is lost again.
- Re-exporting a form moves a fix into the repository — **and is also how the damage spreads**,
  because a form exported from an upgraded designer carries whatever the designer currently holds.

So: **fix the form, re-export it, commit the new package** — in that order. A layout fix that lives
only in a database is not a fix, and a package exported from an unrepaired form propagates the
defect to every environment that imports it.

### Scanning for it

For each `type === 'container'`, inspect each of `desktop` / `tablet` / `mobile`. Flag the block if
it carries any of `justifyContent`, `flexDirection`, `gap`, `alignItems`, `flexWrap` **and**
`display` is anything other than `flex` (including absent).

Calibration from one host app: **136 flagged blocks across 12 form entries** — `display: block` in
the majority, unset in the rest. The same sweep found **no** hits for the generic layout checks
(dimension overflow, top-level `dimensions`, `style.width` conflicts), so those are not a
substitute. A package passes every generic check and still renders flattened.

Two style generations coexist in the same packages, which is worth knowing before concluding
anything from a sample: legacy `className` / `stylingBox` / `style`-as-string, versus the newer
per-breakpoint `dimensions` / `border` / `background` / `font` / `shadow` blocks. Only forms
re-saved since the style model changed carry the latter.

---

## §3. `selectedRow` is scoped to the data context

**The change.** `selectedRow` and `selectedItem` resolve **only inside the data context** that owns
them — the table, list or picker and its descendants.

**Symptom.** Silence. An outside reference resolves to `undefined`, so a visibility expression
returns false and the component never appears, a query parameter goes out empty, a button stays
disabled. Nothing throws.

**Fix — publish the selection into form data.**

1. In the data component's select handler — `onSelect`, `onItemSelect`, or whatever that component
   calls it; the name varies, so read the component's own settings rather than assuming:

   ```js
   form.setFieldValue('dtxSelectValue', value);
   ```

2. Point every outside reader at that form-data variable instead of `selectedRow`.

One variable name per data context, kept stable — outside readers are usually spread across several
components and must all agree.

### Finding the out-of-context reads

Track data-context ancestry while walking the tree; a `selectedRow` / `selectedItem` string found
while **not** inside one is a break. Three access shapes count, and searching for one misses the
others:

| Shape | Example |
|---|---|
| bare identifier | `` `/dynamic/.../details?id=${selectedRow?.id}` `` |
| via global state, by context name | `globalState.<contextName>.selectedRow?.id` |
| mustache | `{{globalState.<contextName>.selectedRow.id}}` |

They hide in scriptable properties — measured frequency: `_code`, `expression`, `queryParams`,
`value`, `customVisibility`, `customEnabled`. Search property *values* generically rather than
working from a fixed list of names.

**Watch `_code`.** An earlier framework migration wrapped old expressions instead of rewriting
them, leaving bodies that open `// Automatically updated from 'customVisibility', please review`
with the original source preserved inside. Stale references survive there unreviewed, under a
property name that no longer matches what the designer shows. In one host app that accounted for 79
of 200 out-of-context references.

Calibration: **1,181 in-context references — all fine — against 200 out-of-context across 14 form
entries.** The ratio is the point. A scan that does not distinguish inside from outside returns
~1,400 hits and is unusable.

---

## §4. A framework-owned form loses local customisations

A form owned by a framework module is rewritten with an empty revision on every boot, so any
component an app added to it is dropped from the effective configuration after the upgrade.

Restoring the pre-upgrade revision is the wrong instinct — it also reverts the new design. Instead:
expose the form into a module the app owns, re-apply the customisation on top of the new version,
and ship that as a config package. Otherwise a fresh database renders the framework's version and
the customisation disappears again.

The same happens to **companion-module** forms an app edited in place on 0.43: the module's package
import on first boot writes a new revision over them. Find them by their latest revision being an
import (`creation_method_lkp = 3`) on top of a manual one, then check whether the manual one carried
app-specific content.

Two prerequisites make the exposed copy actually replace the original:

- **The app module must be the root module.** Overrides are ranked by module level relative to the
  root, and the root comes from the ABP *startup* module. The template's Web.Host module is a plain
  `AbpModule`, so the root silently falls back to `Shesha` and every override loses. Make the host
  module implement `ISheshaSubmodule` with `ModuleType => typeof(<AppModule>)`. Check
  `SELECT name FROM frwk.modules WHERE is_root_module = 1`.
- **A package cannot carry the exposure.** `DistributedConfigurableItemBase` has no field for it and
  the importer never sets `ExposedFrom` / `SurfaceStatus`; only `IConfigurationItemManager.ExposeAsync`
  (Configuration Studio's Expose) does. Shipped alone, the form arrives as an unrelated form in the
  app module. Expose it in code before the app's packages import — in the app module's
  `InitializeConfigurationAsync`, before `ImportConfigurationAsync()` — and **commit that in its own
  `RequiresNew` unit of work**: the seeder imports each package in a new transaction that otherwise
  blocks on the uncommitted rows until it times out. The import then finds the item by module + name
  and only updates its markup, label and description, so the override survives.

---

## §5. Shipping the fix

Changed forms go out as a **new** package, never by editing an existing one in place.

An existing package is a historical record that has already been applied: rewriting it does not
re-run it, and the edit is lost at the next export. Generate a new package carrying the changed
forms and register it alongside the others.

**Key rules:**
- Anything corrected only in a database is not corrected. It must reach a package.
- Re-export is the delivery mechanism *and* the contamination mechanism — never re-export a form
  you have not checked.
- One host app can hold 150+ packages and ~850 form entries. Report findings per form entry and per
  package, not as a flat list.

### How the seeder treats a package

- A package is skipped only when an import result exists with the **same resource name and MD5**;
  embedded packages are only checked when the host assembly changed since the last start.
- The 0.46 item layout is `Module/form/<name>.json` with `Markup`, `ModelType`, `Access`,
  `Permissions`, `Id`, `OriginId`, `Name`, `Label`, `ModuleName`, `FolderPath`, `BaseModules`,
  `ConfigHash`. `Access` above 2 is written to the form's permissioned object — keep a login form at
  `5` (anonymous) or nobody can reach it.
- Reading markup out of SQL Server with `sqlcmd` silently drops non-ASCII (emoji in script comments
  are common). Read through `SqlClient` or the API when building a package or comparing markup.

---

## §6. Breaks only visible at runtime

Found by comparing each page with the 0.43 site, not by any scan above.

| Symptom | Cause | Fix |
|---|---|---|
| Table shows "No Data" and sends **no** request | permanent filter reads `{{pageContext.x}}` set in `onAfterDataLoad`; 0.46 runs the table query first and does not re-run it | read the source directly, e.g. `{{application.user.personId}}` |
| Logo fills the container; a background no longer covers the page | image v6 / container v7 migrations default `dimensions` to `width: 100%` / content width and ignore unitless legacy `width: "170"` and size set by a `style` script | set `desktop`/`tablet`/`mobile` `dimensions` explicitly |
| CSS injected by an HTML Render has no effect (custom chevron tabs, ad-hoc modals) | 0.46 `htmlRender` sanitises output unless `sanitize: false`; a `<style>`-only result is stripped | turn **Sanitize** off on renderers that emit fixed CSS |
| Login form blank: `Setting with name 'azureAdSettings' not found` | Azure AD moved to `Shesha.MicrosoftAuthentication` (`IsEnabled`, tenant, client, redirect) | read the new setting, in try/catch so the form still loads; the External Sign In action now needs `provider: 'Microsoft'` |
| Table empty: `Failed to fetch metadata of type … ConfigurationItems.ConfigurationPackageImportResult` | class moved to `Shesha.Domain` | update `entityType` / `modelType` |
| `Component 'map' not registered` | Enterprise 8 dropped the Leaflet `map` component (only `mapBoundary` remains) | owner decision — no drop-in replacement |
| Dashboards / report categories empty; `ReferenceList/GetByName` 404 | endpoint removed in 0.46, still called by `@shesha-io/dep` 2.5 and `@shesha-io/devexpressreporting` 4 betas | app-side compatibility endpoint over `IReferenceListHelper` until the packages are fixed |
| Menu items open "form not found" | Roles, Forms, Reference Lists, Notification Type/Channel, Workflow Definitions and File Templates are edited in Configuration Studio; `shesha/scheduled-job` is `Shesha/scheduled-jobs` | repoint `Shesha.MainMenuSettings` by **target**, not title, in a migration (`Execute.WithConnection` + JSON) |

When querying forms over the API, `FormConfiguration/GetByName` returns 404 on 0.46 — read with
`FormConfiguration/GetJson?id=` and write with `UpdateMarkup` (or multipart `ImportJson`, which
overwrites without a revision — back up first). Send `sha-frontend-application: <app key>` on
reads; without it forms and app-scoped settings resolve against the swagger application and
report "not found".
