# Regenerate the valid-property index

`assets/groups/*.json` is the list of properties that are real for each Shesha component. It is **generated**, not hand-written: from the 0.46 component knowledge base that ships with `shesha-form-edit` (`../shesha-form-edit/assets/components-kb/`, extracted from the `release-0.46.0` source).

## When to run

- After the component KB is regenerated for a new Shesha release (new commit in `components-kb/_meta.json`).
- When `node scripts/generate-index.mjs --check` exits 1 (the files on disk differ from what the KB produces).

## Run

```bash
cd plugins/shesha-developer-0-46/skills/clean-form-config
node scripts/generate-index.mjs            # rewrites assets/groups/*.json
node scripts/generate-index.mjs --check    # exit 0 = up to date, 1 = stale
```

Defaults: `--kb ../shesha-form-edit/assets/components-kb` (resolved from the script), `--out assets/groups`. Dependency-free Node. Re-running is idempotent (no timestamps).

## What it does

A component's **valid** properties are `settingsProps.resolvedProps` (own + inherited interface props) + `settingsProps.ownProps` + the first path segment of every `settingsFields` entry, minus the **base** set. The base set (`base.json` -> `base.props`) is every prop present in the `resolvedProps` of at least 80% of the components, plus the designer bookkeeping key `settingsValidationErrors`.

- **Per-component entries** go into the group files (`data-entry`, `data-display`, `advanced`, `entity-references`, `tables-and-lists`, `layout`); a component keeps its previous group, new components are placed by name rules in the script (default `advanced`).
- **Curated descriptors are preserved**: when a prop is still valid, its previous `{type, desc, options, JsReturnType, async, context ...}` is kept. A preserved type is dropped when the KB editor type contradicts it (the run prints each conflict). Script `context` lists are replaced by the 0.46 runtime names (`data, form, user, actions, utils, page, application, contexts, storage, query, initialValues, parentFormValues, moment, http, message, modal, globalState, setGlobalState, selectedRow`).
- **New props** get a type only when the editor is unambiguous (`switch`/`checkbox` boolean, `numberField` number, `textField`/`textArea`/`colorPicker`/`iconPicker`/property autocompletes string, `styleBox` object) and are marked `"inferred": true`. The checker never auto-fixes a type mismatch on an inferred prop.
- **Legacy props**: names the previous index knew but 0.46 no longer declares (for example `refListStatus.showIcon`, the old flat style keys) are not deleted from history; they are listed in `legacy` per component and `legacyBase` in `base.json`. The scanner never removes a unrecognised key from a component stored below the current version, because the migrator may still read it.
- `index.json` also carries `meta: { type: { version, deprecated?, hidden?, perDevice?, containers? } }` straight from the KB: `version` is the current component version (the dead-property version rule), `perDevice` marks the 37 components whose style lives under `desktop` / `tablet` / `mobile` (check N4).
- `_formSettings` and `_types` in `base.json` are carried over unchanged (the 0.46 `IFormSettings` set did not change).

## Verify after regenerating

1. `node scripts/generate-index.mjs --check` exits 0.
2. Scan a few real forms: `node scripts/scan-046.mjs <markup.json>`. Real 0.46 props (for example `refListStatus.itemDisplay`, `datatable` `striped`, anything under `desktop`) must not appear as `D1`.
3. Spot-check a component whose settings changed shape in the release (`index.meta[type].version` moved) against its KB entry.
