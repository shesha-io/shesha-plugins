# Component knowledge base (`assets/components-kb/`)

Source-derived facts about every form-designer component, extracted from the Shesha framework source. Use it to settle "which prop shape is real" and "which `version` integer goes in markup". Ranking when sources disagree: a live form that already renders > this KB > `clean-form-config/assets/groups/` > a doc example.

## Provenance

| | |
|---|---|
| Source | `shesha-reactjs/src/designer-components` at tag `release-0.46.0` |
| Commit | `b28264efa2e4c7e78cadf1107ae9de7b66093c26` |
| Recorded in | `_meta.json` (`sourceBranch`, `commit`, `sourceCommitDate`, `componentCount`, `settingsCatalog`) |
| Count | 122 entries = the 121 toolbox types in the 0.46 registry + `threeStateSwitch` (defined in source, not registered; `registeredInToolbox:false`) |

`version` is the highest `.add(N, ...)` in the component migrator, i.e. the integer stored in markup. `null` means the component has no migrator: omit `version`.

## Regenerate

```
node scripts/generate-component-kb.js "<framework clone>/shesha-reactjs/src/designer-components" assets/components-kb --versions <component-versions.json>
node scripts/check-component-kb.mjs --versions <component-versions.json>
```

Dependency-free Node (fs/path/child_process). The generator clears the previous `*.json` files in the output dir first. `--versions` is optional but is what fills `renderImpact`, `reworked` from the migrator inventory and the gap cross-check. The check script is the acceptance gate: `componentCount >= 115`, every type in `component-versions.json` present or documented in `_gaps.json`, and `version === currentVersion` for every type in both. It exits 1 on failure.

Run the generator against a clean checkout of the tag, not a working tree with local edits (a detached checkout is named from `git describe --tags --exact-match`).

## Files

- `_index.json` - `type -> { version, name, isInput, file, settingsParseQuality, settingsFieldCount, hasStandardAppearance, reworked, deprecated?, isHidden? }`. Grep a type here, never read it whole.
- `<type>.json` - one per component (below).
- `_meta.json`, `_gaps.json` - provenance and extraction gaps.
- `_enums.json` - `type -> path -> { values, source }`, option values read from `dropdownOptions` / `buttonGroupOptions` literals in the settings form.
- `_shared-style-fields.json` - the 0.46 appearance model (see "Field-shape changes").

## Per-component fields

| Field | Meaning |
|---|---|
| `type`, `name`, `icon`, `isInput`, `isOutput`, `canBeJsSetting` | Registration values |
| `version` | Current migrator version (see above) |
| `reworked` | `true` for the 43 components on the 0.46 common pattern (`allowInherit: true`: model assembled from `getDefaultStyles` + theme + desktop/tablet/mobile blocks; Common/Events/Appearance settings tabs) |
| `allowInherit`, `styleGroup`, `isHidden`, `deprecated` | Registration flags. `isHidden`/`deprecated` components should not be authored |
| `registeredInToolbox` | Present in `component-versions.json` (only set when `--versions` is given) |
| `customContainerNames`, `hasGetContainers`, `slots` | Where child components live. `customContainerNames` is the list of child-container property names (`tabs`, `columns`, `header`/`content`, `steps` ...); `null` means the plain `components` array. `hasGetContainers` is true when the component also computes containers from its model |
| `renderImpact` | Compact array `{ toVersion, category, what }` of migrations that change rendering (from `component-versions.json`). Read it before trusting a stored markup version: a form at an older version gets these applied on load |
| `initModel` | `defaults` = statically readable literal defaults dropped with the component; `raw` = source snippet (defaults built from functions, e.g. action configuration, are only in `raw`) |
| `settingsProps` | `interfaceName`, `ownProps` (props declared on that component's interface: the ones that genuinely exist), `resolvedProps` (own + inherited), `unresolvedExtends` |
| `settingsForm` | `source`, `mechanism` (`fluent-builder` / `json-markup` / `react-factory` / `none`), `parseQuality` |
| `settingsFields` | Settings paths with `label`, `editorType`, `group`, `defaultValue`, `options`, `permissionSettings` (per-setting permission lock), `required` |
| `hasStandardAppearance`, `appearanceFieldPaths`, `appearanceScope` | Standard style panels exposed (`layout`, `dimensions`, `border`, `background`, `shadow`, `font`, `stylingBoxJson`, `style`); `per-device` means they are written under `desktop` / `tablet` / `mobile` |
| `defaultStylesFrom` | The `getDefaultStyles` expression (the defaults applied before the stored model) |
| `sourceFiles` | Files the entry was read from, relative to `designer-components` |

## Field-shape changes vs the 0.45 KB

- Added: `reworked`, `allowInherit`, `styleGroup`, `isHidden`, `deprecated`, `registeredInToolbox`, `customContainerNames` (top level), `hasGetContainers`, `defaultStylesFrom`, `renderImpact`, `appearanceScope`, and per-field `permissionSettings` / `required` / `options`. Existing fields keep their names and nesting (`ownProps` and `resolvedProps` are still under `settingsProps`).
- `hasStandardAppearance` now means "uses the std*Panel helpers" and `appearanceFieldPaths` lists panel roots (`dimensions`, `border` ...), not the flat 0.43 style paths. `_shared-style-fields.json` is now `{ description, stylingBoxJsonShape, panels }` (not a flat `fields` list). Reworked components store style in device blocks and margins/paddings as the object `stylingBoxJson`, not the `stylingBox` string.
- Event handlers are settings paths like `onClickCustom` / `onFocusCustom` (group `Events`).
- Props changed shape in 0.46 even where the name survives (example: `refListStatus` now has `itemDisplay`, replacing `showIcon` + `showReflistName`). Always read `ownProps`, not memory.
- Set of types differs from 0.45: new `addressInput`, `containerChecker`, `expressionEditor`, `youtubeVideo`; gone `chart`, `childEntitiesTagGroup`, `imageAnnotation`.

## Known gaps (`_gaps.json`)

All 121 registered types are extracted; nothing is missing. The gap list is informational:

- No settings form (14): internal, hidden, deprecated or legacy components (`list`, `paragraph`, `title`, `dataContextSelector`, `columnsEditorComponent`, `datatable_template`, `datatableContext`, `formAutocomplete`, `notificationAutocomplete`, `permissionTagGroup`, `referenceListAutocomplete`, `scheduledJobExecutionLog`, `settingsInput`, `settingsInputRow`). `settingsFields` is empty; fall back to `ownProps`.
- React-factory settings not parsed (2): `toolbar`, `childTable` (both hidden/legacy).
- `initModel` has no literal defaults (17): defaults are computed (nanoid ids, action configuration); use `initModel.raw`.
- `dataContext`: two source files declare it; the one imported by `providers/form/defaults/toolboxComponents.ts` (`dataTable/tableContext/tableContextComponent.tsx`, version 5) is kept; `dataContextComponent/index.tsx` is unregistered.
- Folders with no toolbox definition (5): `dataContextComponent`, `inputComponent`, `itemListConfigurator`, `multiColorInput`, `requestConfigButton` (helper/settings-only folders).
- `threeStateSwitch` is defined in source but not registered in the 0.46 toolbox.
- Settings are parsed statically: `settingsFields` are literal `propertyName`s only. Settings built from a runtime-computed path or a shared helper that is not a `std*` call can be missing; `ownProps` is the authority for what exists on the model. Per-device panel sub-fields are not enumerated per component (see `_shared-style-fields.json`).
- Version extraction for a component whose migrator chain lives in sibling files takes the highest index in that component folder (flagged by `migratorNote`); `check-component-kb.mjs` cross-checks all of them against `component-versions.json`.
