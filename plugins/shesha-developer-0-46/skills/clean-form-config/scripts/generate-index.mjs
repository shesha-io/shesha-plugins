#!/usr/bin/env node
/*
 * generate-index.mjs - rebuild assets/groups/*.json (the clean-form-config valid-prop index) from the
 * shesha-form-edit component knowledge base (assets/components-kb/, source: shesha-reactjs release tag).
 *
 *   node scripts/generate-index.mjs [--kb <components-kb dir>] [--out <groups dir>] [--check]
 *
 * Defaults: --kb ../../shesha-form-edit/assets/components-kb   --out ../assets/groups   (relative to this file)
 *
 * What a component's VALID props are (anything else is reported as dead):
 *   settingsProps.resolvedProps (own + inherited interface props)  U  top-level segment of every
 *   settingsFields path  U  settingsProps.ownProps  -  the shared base props (kept once, in base.json).
 * The base set = props present in resolvedProps of >= BASE_THRESHOLD of all components.
 *
 * Descriptors ({name,type,desc,...}) are preserved from the previous index in --out when the prop is still
 * valid (idempotent re-runs keep hand-curated types/descriptions). A preserved type is dropped when the KB
 * editorType contradicts it. New props get a type only when the editorType is unambiguous
 * (switch/checkbox -> boolean, numberField -> number, textField/textArea/colorPicker/iconPicker/
 * *PropertyAutocomplete -> string, styleBox -> object) and are marked "inferred": true (never auto-fixed).
 *
 * --check regenerates in memory and exits 1 if the files on disk differ (CI gate). No dependencies.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const KB = path.resolve(opt('--kb', path.join(here, '../../shesha-form-edit/assets/components-kb')));
const OUT = path.resolve(opt('--out', path.join(here, '../assets/groups')));
const CHECK = argv.includes('--check');
const BASE_THRESHOLD = 0.8;

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
if (!fs.existsSync(path.join(KB, '_index.json'))) { console.error(`components-kb not found at ${KB}`); process.exit(2); }

const kbIndex = readJson(path.join(KB, '_index.json'));
const kbMeta = fs.existsSync(path.join(KB, '_meta.json')) ? readJson(path.join(KB, '_meta.json')) : {};
const types = Object.keys(kbIndex).sort((a, b) => a.localeCompare(b));
const comp = Object.fromEntries(types.map((t) => [t, readJson(path.join(KB, kbIndex[t].file))]));

// ---- previous index (curated descriptors) ---------------------------------------------------------------
const GROUPS = ['data-entry', 'data-display', 'advanced', 'entity-references', 'tables-and-lists', 'layout'];
const old = { base: {}, formSettings: {}, comps: {}, legacy: {}, rawBase: null };
if (fs.existsSync(OUT)) {
  const bp = path.join(OUT, 'base.json');
  if (fs.existsSync(bp)) {
    old.rawBase = readJson(bp);
    for (const p of old.rawBase.base?.props ?? []) old.base[p.name] = p;
  }
  for (const g of fs.readdirSync(OUT)) {
    if (!g.endsWith('.json') || g === 'base.json' || g === 'index.json') continue;
    const j = readJson(path.join(OUT, g));
    for (const [t, v] of Object.entries(j)) if (t !== '_meta') { old.comps[t] = Object.fromEntries((v.props ?? []).map((p) => [p.name, p])); old.legacy[t] = v.legacy ?? []; }
  }
}
const oldIndexComponents = fs.existsSync(path.join(OUT, 'index.json')) ? readJson(path.join(OUT, 'index.json')).components ?? {} : {};

// ---- type inference ---------------------------------------------------------------------------------------
const EDITOR_TYPE = {
  switch: 'boolean', checkbox: 'boolean',
  numberField: 'number',
  textField: 'string', textArea: 'string', colorPicker: 'string', iconPicker: 'string',
  propertyAutocomplete: 'string', contextPropertyAutocomplete: 'string',
  styleBox: 'object',
};
// verified against stored 0.45/0.46 markup (boolean|IPropertySetting values; strings; objects)
const BASE_TYPES = {
  visible: 'boolean', disabled: 'boolean', showAdvanced: 'boolean', noDefaultStyling: 'boolean',
  stylingBoxJson: 'object', direction: 'string', display: 'string',
};
const SCRIPT_CONTEXT = ['data', 'form', 'user', 'actions', 'utils', 'page', 'application', 'contexts', 'storage', 'query',
  'initialValues', 'parentFormValues', 'moment', 'http', 'message', 'modal', 'globalState', 'setGlobalState', 'selectedRow'];

const top = (p) => String(p).split('.')[0];
const editorOf = (c) => {
  const m = new Map();
  for (const f of c.settingsFields ?? []) {
    const k = top(f.path);
    if (f.path.includes('.') || !f.editorType) continue;
    if (!m.has(k)) m.set(k, f.editorType);
  }
  return m;
};
const labelOf = (c) => {
  const m = new Map();
  for (const f of c.settingsFields ?? []) if (!f.path.includes('.') && f.label && !m.has(f.path)) m.set(f.path, f);
  return m;
};

// ---- base set ----------------------------------------------------------------------------------------------
const count = {};
for (const t of types) for (const p of new Set(comp[t].settingsProps?.resolvedProps ?? [])) count[p] = (count[p] ?? 0) + 1;
// designer bookkeeping that is persisted on many components but is not a model prop
const BOOKKEEPING = ['settingsValidationErrors'];
const baseNames = [...new Set([...Object.keys(count).filter((p) => count[p] >= types.length * BASE_THRESHOLD), ...BOOKKEEPING])].sort();
const baseSet = new Set(baseNames);

function baseDescriptor(name) {
  const o = old.base[name];
  if (o) {
    const d = { ...o };
    if (d.context) d.context = d.type === 'script' && /^(onChange|onFocus|onBlur|onSelect)/.test(name) ? [...SCRIPT_CONTEXT, 'value'] : SCRIPT_CONTEXT;
    return d;
  }
  const d = { name };
  if (BASE_TYPES[name]) d.type = BASE_TYPES[name];
  return d;
}
const baseProps = baseNames.map(baseDescriptor);

// ---- per component -----------------------------------------------------------------------------------------
const GROUP_RULES = [
  [/^(datatable|dataTable|datalist|dataContext|dataSource|list$|childTable|kanban|tableViewSelector|dataSortingEditor|columnsEditor)/, 'tables-and-lists'],
  [/^(entity|attachments|fileUpload|autocompleteTagGroup|notes|refList|permission|referenceList|childEntities|configurableItem|formAutocomplete|endpointsAutocomplete)/i, 'entity-references'],
  [/^(container|columns|sizableColumns|card|collapsiblePanel|tabs|wizard|drawer|subForm|space|section|propertyRouter|searchableTabs|setting$|dynamicView|containerChecker|divider)/, 'layout'],
  [/^(textField|textArea|numberField|dropdown|checkbox|radio|switch|slider|rate|button|buttons|dateField|timePicker|phoneNumberInput|threeStateSwitch|editModeSelector|passwordCombo|labelConfigurator)/, 'data-entry'],
  [/^(text$|paragraph|title|alert|statusTag|statistic|progress|image|youtubeVideo|barChart|lineChart|pieChart|polarAreaChart|validationErrors|link|markdown|htmlRender|KeyInformationBar)/, 'data-display'],
];
const groupOf = (t) => oldIndexComponents[t] ?? (GROUP_RULES.find(([re]) => re.test(t))?.[1] ?? 'advanced');

const groupFiles = {}; for (const g of GROUPS) groupFiles[g] = { _meta: { version: 4, group: g } };
const indexComponents = {}; const indexMeta = {};
const stats = { dropped: 0, droppedTypes: 0, inferred: 0, kept: 0, typeConflicts: [] };

for (const t of types) {
  const c = comp[t];
  const ed = editorOf(c); const lb = labelOf(c);
  const valid = new Set([
    ...(c.settingsProps?.resolvedProps ?? []),
    ...(c.settingsProps?.ownProps ?? []),
    ...[...ed.keys()],
  ].filter((p) => p && !p.startsWith('settings') && !/^pnl[A-Z]/.test(p)));
  const own = [...valid].filter((p) => !baseSet.has(p)).sort();
  const props = own.map((name) => {
    const prev = old.comps[t]?.[name];
    const inferred = EDITOR_TYPE[ed.get(name)];
    if (prev) {
      const d = { ...prev };
      if (d.type && d.type !== 'script' && inferred && inferred !== d.type && !(d.type === 'array' || d.type === 'object')) {
        stats.typeConflicts.push(`${t}.${name}: was ${d.type}, editor ${ed.get(name)} -> ${inferred}`);
        delete d.type; delete d.JsReturnType; delete d.options;
        stats.droppedTypes++;
      }
      if (d.context) d.context = SCRIPT_CONTEXT;
      stats.kept++;
      return d;
    }
    const d = { name };
    if (inferred) { d.type = inferred; d.inferred = true; stats.inferred++; }
    const f = lb.get(name);
    if (f) d.desc = String(f.description ?? f.label).replace(/\s+/g, ' ').slice(0, 140);
    return d;
  });
  // Props the previous index (0.43/0.45) knew that 0.46 no longer declares: not dead while the component is
  // still stored below the current version (the migrator reads them), dead once it is at/above it.
  const legacy = [...new Set([...(old.legacy[t] ?? []), ...Object.keys(old.comps[t] ?? {})])]
    .filter((n) => !valid.has(n) && !baseSet.has(n)).sort();
  stats.dropped += legacy.length;
  const g = groupOf(t);
  indexComponents[t] = g;
  groupFiles[g][t] = legacy.length ? { props, legacy } : { props };
  const m = { version: c.version ?? null };
  if (c.deprecated) m.deprecated = true;
  if (c.isHidden) m.hidden = true;
  if (c.appearanceScope === 'per-device') m.perDevice = true;
  if (c.customContainerNames?.length) m.containers = c.customContainerNames;
  indexMeta[t] = m;
}

// ---- base.json ---------------------------------------------------------------------------------------------
const baseFile = {
  _meta: { version: 4, group: 'base' },
  base: { props: baseProps },
  legacyBase: [...new Set([...(old.rawBase?.legacyBase ?? []), ...Object.keys(old.base).filter((n) => !baseSet.has(n))])].sort(),
  _formSettings: old.rawBase?._formSettings ?? { props: [] },
  _types: old.rawBase?._types ?? {},
};

const indexFile = {
  _meta: {
    version: 4,
    source: { release: kbMeta.sourceBranch ?? null, commit: kbMeta.commit ?? null, kbComponentCount: types.length },
    baseThreshold: BASE_THRESHOLD,
  },
  groupFiles: ['base.json', ...GROUPS.map((g) => `${g}.json`)],
  components: indexComponents,
  meta: indexMeta,
};

// ---- write / check -----------------------------------------------------------------------------------------
const outputs = { 'base.json': baseFile, 'index.json': indexFile };
for (const g of GROUPS) outputs[`${g}.json`] = groupFiles[g];
const ser = (o) => JSON.stringify(o, null, 2) + '\n';

if (CHECK) {
  const bad = Object.entries(outputs).filter(([f, o]) => !fs.existsSync(path.join(OUT, f)) || fs.readFileSync(path.join(OUT, f), 'utf8') !== ser(o)).map(([f]) => f);
  console.log(bad.length ? `STALE: ${bad.join(', ')}` : 'index up to date');
  process.exit(bad.length ? 1 : 0);
}
fs.mkdirSync(OUT, { recursive: true });
for (const [f, o] of Object.entries(outputs)) fs.writeFileSync(path.join(OUT, f), ser(o));
console.log(`components: ${types.length}  base props: ${baseProps.length}  groups: ${GROUPS.length}`);
console.log(`descriptors kept: ${stats.kept}  new typed (inferred): ${stats.inferred}  props moved to legacy: ${stats.dropped}  types dropped on editor conflict: ${stats.droppedTypes}`);
if (stats.typeConflicts.length) console.log('type conflicts:\n  ' + stats.typeConflicts.slice(0, 30).join('\n  '));
