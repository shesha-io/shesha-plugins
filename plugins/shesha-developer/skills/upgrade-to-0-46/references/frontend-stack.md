# Frontend Stack and Configuration Studio

Phase 3. Independent of the backend — it rarely blocks start-up, so do it last.

## §1. Stack

```jsonc
"@shesha-io/reactjs": "0.46.0",
"react":      "^19.2.4",   "react-dom":          "^19.2.4",
"next":       "^16.3.1",   "antd":               "^6.6.2",
"antd-style": "^4.1.0",    "@ant-design/icons":  "^6.3.2",
"next-navigation-guard": "^0.2.0"
```

```jsonc
"overrides": {
  "@shesha-io/reactjs": "$@shesha-io/reactjs",
  "@antv/component": "2.1.7",              // 2.1.11 has a broken internal export that fatally fails the rollup build
  "next-navigation-guard": { "next": "$next" }
}
```

**Key rule:** regenerating `package-lock.json` drifts transitive versions. Pin anything that breaks via `overrides` rather than hand-editing the lock.

## §2. Next 16

### Turbopack is the default — add `--webpack`

```jsonc
"dev":           "next dev --webpack",
"build":         "next build --webpack",
"build:analyze": "ANALYZE=true next build --webpack"
```

The webpack config comes entirely from `@next/bundle-analyzer`. Without the flag, Next warns once and `build:analyze` **silently stops analysing anything** — it does not fail.

### `publicRuntimeConfig` and `next/config` are removed

Read configuration directly (env vars or a module constant). Strip `publicRuntimeConfig` from `next.config.js` and every `getConfig()` call.

### `tsconfig.json`

```jsonc
"jsx": "react-jsx",              // was "preserve"
"moduleResolution": "bundler",   // was "node"
"include": [..., ".next/dev/types/**/*.ts"]
```

`next-env.d.ts` regenerates itself — commit the result.

## §3. Configuration Studio

Consolidates four standalone admin pages. **Delete** these routes:

```
src/app/settings/entity-configs/configurator/page.tsx
src/app/settings/theme/page.tsx
src/app/shesha/forms-designer/page.tsx
src/app/shesha/settings/page.tsx
```

Add `src/app/configuration-studio/page.tsx` rendering `ConfigurationStudio` via `PageWithLayout`, then two wiring changes:

- **Root layout** — wrap in `NavigationGuardProvider` (from `next-navigation-guard`); the studio requires it.
- **App provider** — the studio must render **outside `MainLayout`**. Add its route to `fullScreenRoutes` / `withoutMainLayout`, and add `AttachmentsEditorProvider`, which 0.46.0 expects.

Reference implementation: PR shesha-io/shesha-framework#4905.

**Watch for** a malformed backend URL fallback such as `"https:localhost:44362"` — missing `//` after the protocol throws `Invalid URL` rather than falling back.

**Studio layout broken (toolbar squashed into the header, buttons cut off)** — check for a stale
`antd` 5 **nested under `@shesha-io/reactjs`**:

```bash
npm ls antd   # look for node_modules/@shesha-io/reactjs/node_modules/antd@5.x
```

reactjs 0.46 does not depend on antd (it is a dev dependency); the nested copy is left in
`package-lock.json` from the 0.43 install, where the app itself used antd 5. Node resolves the nearest
copy, so all Shesha UI renders with antd 5 inside an antd 6 app. `npm install` reports "up to date"
and never re-resolves it. Delete every `node_modules/@shesha-io/reactjs/node_modules/*` entry from the
lock, remove that folder, reinstall, and confirm a single antd.

**Designer canvas renders at "0px"** — a stale `shesha:designerWidth` in the browser's localStorage
(the default is computed from `screen.availWidth`, which can read 0 in an embedded or hidden
browser). Remove the key and reload; it is per browser, not a code defect.

## §4. Package workspaces

Sibling packages under `packages/` need the same reactjs bump plus their own API migration:

- Settings files → `SettingsFormMarkupFactory` with the typed builder (see *Component settings files* below)
- Form-builder and ajax helpers that were removed from reactjs now need local equivalents under `src/utils/`

**Stale dev tooling in a workspace blocks the whole install.** npm resolves workspace
`devDependencies` too, so an unused Storybook / styleguidist / enzyme toolchain pinned to React 18
stops the app you care about from installing. Before migrating any of it, check: does anything
import it outside the stories; does a pipeline build it; do the stories reference real components or
the module template's sample page; do the config aliases name directories that still exist. If it is
template boilerplate — sample page, story wrapper, story helper — **delete it rather than migrate
it.** A reliable tell is boilerplate still doing `require('antd/dist/antd.less')`, a file gone since
antd 4.

**Settings-form specifics**, beyond swapping the builder: ids are generated rather than written out
and `fbf(tabId)` is what parents a tab's children (so children set no `parentId`); `description` →
`tooltip`, `values` → `dropdownOptions` (the option type carries no `id`), `items` →
`buttonGroupOptions`, `hidden` → `visibleJs`; `settingsFormMarkup` and
`validateConfigurableComponentSettings` take the **factory**, not its result. `settingsInput` has no
`defaultValue` — move the default into the component (`prop={model?.prop ?? 'post'}`) and say so,
because it is a real relocation. Check the valid `inputType` union against the installed typings
rather than guessing; it is long and it changes.

**Key rules:**
- The root app and each workspace typecheck independently. Root-clean does not imply workspace-clean.
- `IToolboxComponent` variance and `IConfigurableFormComponent<IStyleValue>` mismatches (e.g. `Border<string|number>` vs `IBorderValue`) are genuine API changes, not oversights — they need per-component work.
- Fix pre-existing typing bugs you uncover, but list them separately: `IUseMutateResponseFixedEndpoint<T>` with the response in the *input* slot should be `<void, T>`.

### Component settings files

Every designer component's `settings.ts` must be migrated to the 0.46 settings-panel shape — a straight API port of the old builder calls is not enough.

**Rules:**
- **Tabs are mandatory.** The root of `fbf()` is a single `.addSearchableTabs({ propertyName: 'settingsTabs', parentId: 'root', hideLabel: true, tabs: [...] })`. Every setting lives inside a tab (typically *Common*, *Data*, *Events*, *Appearance*, *Security*) — no settings at the root, no flat lists, no `addSectionSeparator` used as a substitute for tabs.
- **Inputs use `settingsInput`.** Replace legacy per-type builders (`addTextField`, `addDropdown`, `addCheckbox`, `addCodeEditor`, `addPermissionAutocomplete`, …) with `.addSettingsInput({ inputType: '...', ... })`. Set `jsSetting: true` where the value may be JS-driven.
- **Group related inputs with `settingsInputRow`.** Put small related inputs side by side via `.addSettingsInputRow({ inputs: [{ type: '...', ... }, ...] })` (e.g. Edit Mode + Hide) instead of stacking them.
- Each input's `parentId` is its **tab's id**, not `'root'`.

```typescript
.addSearchableTabs({ id: tabsId, propertyName: 'settingsTabs', parentId: 'root', label: 'Settings', hideLabel: true, tabs: [
  { key: '1', title: 'Common', id: commonTabId, components: [...fbf()
    .addSettingsInput({ id: nanoid(), parentId: commonTabId, inputType: 'textField', propertyName: 'label', label: 'Label', jsSetting: true })
    .addSettingsInputRow({ id: nanoid(), parentId: commonTabId, inputs: [
      { id: nanoid(), type: 'editModeSelector', propertyName: 'editMode', label: 'Edit Mode' },
      { id: nanoid(), type: 'switch', propertyName: 'hidden', label: 'Hide', jsSetting: true },
    ] })
    .toJson()] },
  { key: '2', title: 'Security', id: securityTabId, components: [...fbf()
    .addSettingsInput({ id: nanoid(), parentId: securityTabId, inputType: 'permissions', propertyName: 'permissions', label: 'Permissions', jsSetting: true })
    .toJson()] },
] })
```

Full template: the `create-custom-component` skill (*settings.ts Template (Tabbed)*).

## §5. Windows gotchas

- Ports **21021** and **44362** may sit in Windows' excluded port range — `netsh int ipv4 show excludedportrange protocol=tcp`. Nothing can bind them; they show as held by PID 4 (System). Use another port rather than hunting a phantom process.
- `dotnet run` leaves `*.Web.Host.exe` alive after its wrapper exits, holding both `bin/` (MSB3021) and the port. Kill strays before rebuilding.
- `MSB3021` in a repo with Visual Studio open is almost always a file lock, not a regression. Retry before investigating.
- npm `file:` specs break on paths containing spaces.
- `"start": "NODE_ENV=production node server.js"` is POSIX syntax; `cmd` cannot parse it and reports
  `'NODE_ENV' is not recognized`. Prefix with `cross-env` — and check it is **declared**, not merely
  present transitively, or it disappears at the next lockfile regeneration.
- A `pre-commit` hook running lint blocks every commit touching matched files if the lint config
  imports a plugin that was never a dependency. Check the committed lockfile before blaming the
  upgrade — it is often long-standing breakage that had not been triggered. Fix the dependency
  rather than passing `--no-verify`.
- Hooks that stash and restore the tree can rewrite line endings, turning a two-line change into a
  whole-file diff. Check real changes with `git diff --ignore-cr-at-eol`.
