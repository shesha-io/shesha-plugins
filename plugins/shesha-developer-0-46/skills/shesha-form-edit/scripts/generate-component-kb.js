#!/usr/bin/env node
/**
 * generate-component-kb.js
 *
 * Builds a source-derived component knowledge base for Shesha's form designer
 * by regex/string-parsing the renderer source (no TS compiler, no npm deps).
 *
 * Usage:
 *   node scripts/generate-component-kb.js "<designer-components source dir>" "<output dir>" [--versions <component-versions.json>]
 *
 * Handles the legacy registration (IToolboxComponent<IProps>) and the 0.46 one
 * (XComponentDefinition = ComponentDefinition<"type", IProps>, allowInherit, getDefaultStyles,
 * settings built via SettingsFormMarkupFactory + addSettingsInput / addSettingsInputRow / std* helpers).
 * --versions: optional component-versions.json; adds renderImpact[] per component.
 *
 * Example (0.46):
 *   node scripts/generate-component-kb.js \
 *     "<framework clone>/shesha-reactjs/src/designer-components" \
 *     "assets/components-kb" --versions component-versions.json
 *
 * For every IToolboxComponent definition found (including nested sub-component
 * folders like button/buttonGroup), emits <outdir>/<type>.json plus:
 *   _index.json  — type -> { version, name, isInput, file }
 *   _meta.json   — { sourceBranch, commit, generatedAt, componentCount }
 *   _gaps.json   — extraction failures / partial parses with reasons
 *
 * Deterministic and re-runnable (point it at a 0.45 source dir later).
 */

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

// ---------------------------------------------------------------------------
// CLI args
// ---------------------------------------------------------------------------
const posArgs = [];
let versionsFile = null;
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === '--versions') versionsFile = process.argv[++i];
  else posArgs.push(process.argv[i]);
}
const srcDir = posArgs[0];
const outDir = posArgs[1];
if (!srcDir || !outDir) {
  console.error('Usage: node generate-component-kb.js <designer-components-dir> <output-dir> [--versions <component-versions.json>]');
  process.exit(1);
}
if (!fs.existsSync(srcDir) || !fs.statSync(srcDir).isDirectory()) {
  console.error(`Source dir not found: ${srcDir}`);
  process.exit(1);
}
const SRC = path.resolve(srcDir);
// src root = two levels up from designer-components (src/designer-components)
const SRC_ROOT = path.resolve(SRC, '..');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const rel = (p) => path.relative(SRC, p).split(path.sep).join('/');
const relRoot = (p) => path.relative(SRC_ROOT, p).split(path.sep).join('/');

function walk(dir, exts, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === '__tests__' || e.name === 'node_modules') continue;
      walk(full, exts, out);
    } else if (exts.some((x) => e.name.endsWith(x))) {
      out.push(full);
    }
  }
  return out;
}

/** Extract a balanced-delimiter span starting at `openIdx` (which must point at the opening char). */
function balancedSpan(text, openIdx, open = '{', close = '}') {
  let depth = 0;
  let inStr = null;
  let inLineComment = false;
  let inBlockComment = false;
  for (let i = openIdx; i < text.length; i++) {
    const c = text[i];
    const c2 = text.substr(i, 2);
    if (inLineComment) { if (c === '\n') inLineComment = false; continue; }
    if (inBlockComment) { if (c2 === '*/') { inBlockComment = false; i++; } continue; }
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c2 === '//') { inLineComment = true; i++; continue; }
    if (c2 === '/*') { inBlockComment = true; i++; continue; }
    if (c === "'" || c === '"' || c === '`') { inStr = c; continue; }
    if (c === open) depth++;
    else if (c === close) {
      depth--;
      if (depth === 0) return text.slice(openIdx, i + 1);
    }
  }
  return null;
}

/** Blank out whole-line comments (keeps offsets/lines) so commented-out registrations are not picked up. */
function blankComments(src) {
  return src
    .replace(/^[ \t]*\/\/.*$/gm, (s) => ' '.repeat(s.length))
    .replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, (s) => s.replace(/[^\n]/g, ' '));
}

function readFile(p) {
  const text = fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
  return /\.tsx?$/.test(p) ? blankComments(text) : text;
}

// ---------------------------------------------------------------------------
// Interface index (best-effort): designer-components tree + shared model files
// ---------------------------------------------------------------------------
const interfaceIndex = new Map(); // name -> { file, extends: [], props: [] }
const definitionAliasIndex = new Map(); // XComponentDefinition -> props interface name (0.46 pattern)
const GENERIC_NOISE = new Set(['Omit', 'Partial', 'Pick', 'Required', 'Readonly', 'any', 'unknown', 'object', 'never', 'string']);

/** Pick the props type out of a generic argument list, e.g. `"alert", IAlertProps, ICalc` -> IAlertProps. */
function propsIdentFromGenerics(generics, skipFirstLiteral) {
  const args = [];
  let depth = 0;
  let cur = '';
  for (const c of generics) {
    if (c === '<' || c === '(' || c === '{' || c === '[') depth++;
    if (c === '>' || c === ')' || c === '}' || c === ']') depth--;
    if (c === ',' && depth === 0) { args.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  if (cur.trim()) args.push(cur.trim());
  const cands = skipFirstLiteral && args.length && /^['"]/.test(args[0]) ? args.slice(1) : args;
  for (const a of cands) {
    const ids = [...a.matchAll(/[A-Za-z_$][\w$]*/g)].map((x) => x[0]).filter((x) => !GENERIC_NOISE.has(x));
    if (ids.length) return ids[0];
  }
  return null;
}

/** `A, Omit<B, 'x'>, C<D>` -> ['A', 'B', 'C'] (top-level split; Omit/Pick/Partial unwrap to their first type argument). */
function parseExtendsList(src) {
  const parts = [];
  let depth = 0;
  let cur = '';
  for (const c of src) {
    if (c === '<') depth++;
    if (c === '>') depth--;
    if (c === ',' && depth === 0) { parts.push(cur); cur = ''; continue; }
    cur += c;
  }
  if (cur.trim()) parts.push(cur);
  return parts.map((p) => {
    const t = p.trim();
    const wrapped = t.match(/^(?:Omit|Pick|Partial|Required|Readonly)\s*<\s*([A-Za-z_$][\w$.]*)/);
    if (wrapped) return wrapped[1];
    return t.replace(/<[\s\S]*$/, '').trim();
  }).filter(Boolean);
}

function indexInterfacesInFile(file) {
  let text;
  try { text = readFile(file); } catch { return; }
  // 0.46: export type XDefinition = ComponentDefinition<"x", IProps, ...> | IToolboxComponent<IProps>
  const aliasRe = /(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=\s*(ComponentDefinition|IToolboxComponent)\s*<([^;]*?)>\s*(?:;|&|\n)/g;
  let am;
  while ((am = aliasRe.exec(text)) !== null) {
    const ident = propsIdentFromGenerics(am[3], am[2] === 'ComponentDefinition');
    if (ident && !definitionAliasIndex.has(am[1])) definitionAliasIndex.set(am[1], ident);
  }
  // type aliases used as props types: `type X = Y;`  `type X = A & B & { ... };`  `type X = { ... };`
  const typeRe = /(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*(?:<[^>=]*>)?\s*=\s*((?:[A-Za-z_$][\w$.]*(?:<[^{};]*?>)?\s*&\s*)*)(?:([A-Za-z_$][\w$.]*)\s*;|(\{))/g;
  let tm;
  while ((tm = typeRe.exec(text)) !== null) {
    const name = tm[1];
    if (interfaceIndex.has(name) || /Definition$/.test(name)) continue;
    const parents = [...(tm[2] || '').matchAll(/([A-Za-z_$][\w$]*)(?:<[^{};]*?>)?\s*&/g)].map((x) => x[1]);
    if (tm[3]) parents.push(tm[3]);
    let props = [];
    if (tm[4]) {
      const body = balancedSpan(text, tm.index + tm[0].length - 1);
      if (body) {
        let flat = '';
        let depth = 0;
        for (const c of body.slice(1, -1)) { if (c === '{') { depth++; continue; } if (c === '}') { depth--; continue; } if (depth === 0) flat += c; }
        for (const pm of flat.matchAll(/^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*[?]?\s*[:(]/gm)) if (!props.includes(pm[1])) props.push(pm[1]);
      }
    }
    if (parents.length || props.length) interfaceIndex.set(name, { file: relRoot(file), extends: parents, props });
  }
  const re = /(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)\s*(?:<[^>{]*>)?\s*(extends\s+[^\{]+)?\{/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const name = m[1];
    const braceIdx = m.index + m[0].length - 1;
    const body = balancedSpan(text, braceIdx);
    if (!body) continue;
    const extendsList = m[2] ? parseExtendsList(m[2].replace(/^extends\s+/, '')) : [];
    // property / method names at top level of the interface body
    const props = [];
    const inner = body.slice(1, -1);
    // strip nested object-literal type bodies so nested keys aren't captured
    let flat = '';
    let depth = 0;
    for (let i = 0; i < inner.length; i++) {
      const c = inner[i];
      if (c === '{') { depth++; continue; }
      if (c === '}') { depth--; continue; }
      if (depth === 0) flat += c;
    }
    const propRe = /^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*[?]?\s*[:(]/gm;
    let pm;
    while ((pm = propRe.exec(flat)) !== null) {
      if (!props.includes(pm[1])) props.push(pm[1]);
    }
    if (!interfaceIndex.has(name)) {
      interfaceIndex.set(name, { file: relRoot(file), extends: extendsList, props });
    }
  }
}

function buildInterfaceIndex() {
  const candidates = [];
  candidates.push(...walk(SRC, ['.ts', '.tsx']));
  // 0.46 props types are spread over the whole src tree (providers/, components/, interfaces/, ...);
  // designer-components is walked first so its declarations win on a name clash.
  const shared = [
    path.join(SRC_ROOT, 'providers', 'form', 'models.ts'),
    path.join(SRC_ROOT, 'interfaces'),
    path.join(SRC_ROOT, 'providers'),
    path.join(SRC_ROOT, 'components'),
    SRC_ROOT,
  ];
  for (const s of shared) {
    if (!fs.existsSync(s)) continue;
    if (fs.statSync(s).isDirectory()) candidates.push(...walk(s, ['.ts', '.tsx']));
    else candidates.push(s);
  }
  for (const f of new Set(candidates)) indexInterfacesInFile(f);
}

/** Resolve an interface's full property list by following extends (best-effort). */
function resolveInterface(name, seen = new Set(), depth = 0) {
  if (seen.has(name) || depth > 6) return { props: [], unresolved: [] };
  seen.add(name);
  const decl = interfaceIndex.get(name);
  if (!decl) return { props: [], unresolved: [name] };
  const props = [...decl.props];
  const unresolved = [];
  for (const parent of decl.extends) {
    const r = resolveInterface(parent, seen, depth + 1);
    for (const p of r.props) if (!props.includes(p)) props.push(p);
    unresolved.push(...r.unresolved);
  }
  return { props, unresolved };
}

// ---------------------------------------------------------------------------
// Toolbox component extraction
// ---------------------------------------------------------------------------
const gaps = [];
const entries = new Map(); // type -> entry

function extractStringProp(objSrc, key) {
  const m = objSrc.match(new RegExp(`(?:^|[,{\\s])${key}\\s*:\\s*(['"])((?:\\\\.|(?!\\1).)*)\\1`, 'm'));
  return m ? m[2] : undefined;
}

function extractBoolProp(objSrc, key) {
  const m = objSrc.match(new RegExp(`(?:^|[,{\\s])${key}\\s*:\\s*(true|false)\\b`, 'm'));
  return m ? m[1] === 'true' : undefined;
}

/** Extract the value snippet of a top-level object property (arrow fn or literal). */
function extractPropSnippet(objSrc, key) {
  const re = new RegExp(`(?:^|[,{\\n])\\s*${key}\\s*:`, 'm');
  const m = re.exec(objSrc);
  if (!m) return null;
  let i = m.index + m[0].length;
  // skip whitespace
  while (i < objSrc.length && /\s/.test(objSrc[i])) i++;
  // Consume until we hit a comma/close-brace at depth 0
  let depth = 0;
  let inStr = null;
  const start = i;
  for (; i < objSrc.length; i++) {
    const c = objSrc[i];
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') { inStr = c; continue; }
    // NOTE: '<'/'>' are NOT bracket-tracked (they appear in arrows `=>` and comparisons);
    // generics with top-level commas (e.g. Omit<A, 'b'>) may truncate — acceptable for
    // the properties this is used on (initModel, customContainerNames).
    if (c === '(' || c === '{' || c === '[') depth++;
    else if (c === ')' || c === '}' || c === ']') depth--;
    else if ((c === ',' && depth === 0)) break;
    if (depth < 0) break;
  }
  return objSrc.slice(start, i).trim();
}

/** Parse statically-readable literal keys out of an initModel body. */
function parseInitModelDefaults(snippet) {
  if (!snippet) return null;
  // find the object literal returned: ({ ... }) or => { return {...} }
  let objStart = -1;
  const parenObj = snippet.match(/=>\s*\(\s*\{/);
  if (parenObj) objStart = snippet.indexOf('{', parenObj.index);
  else {
    const ret = snippet.match(/return\s*\{/);
    if (ret) objStart = snippet.indexOf('{', ret.index);
  }
  if (objStart < 0) {
    // 0.46 style: `const xModel: IProps = { ...model, a: 1, ... }; return xModel;`
    const spread = snippet.match(/=\s*\{\s*\.\.\.\s*\w*[mM]odel\s*,/);
    if (spread) objStart = snippet.indexOf('{', spread.index);
  }
  if (objStart < 0) return null;
  const body = balancedSpan(snippet, objStart);
  if (!body) return null;
  const inner = body.slice(1, -1);
  const defaults = {};
  // match simple `key: <literal>` pairs at top level
  let depth = 0;
  let cur = '';
  const parts = [];
  let inStr = null;
  for (let i = 0; i < inner.length; i++) {
    const c = inner[i];
    if (inStr) {
      cur += c;
      if (c === '\\') { cur += inner[++i] ?? ''; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') { inStr = c; cur += c; continue; }
    if (c === '{' || c === '[' || c === '(') depth++;
    if (c === '}' || c === ']' || c === ')') depth--;
    if (c === ',' && depth === 0) { parts.push(cur); cur = ''; continue; }
    cur += c;
  }
  if (cur.trim()) parts.push(cur);
  for (const part of parts) {
    const pm = part.trim().match(/^([A-Za-z_$][\w$]*)\s*:\s*([\s\S]+)$/);
    if (!pm) continue;
    const key = pm[1];
    const raw = pm[2].trim();
    let val;
    if (/^(['"])(?:\\.|(?!\1).)*\1$/.test(raw)) val = raw.slice(1, -1);
    else if (/^-?\d+(\.\d+)?$/.test(raw)) val = Number(raw);
    else if (raw === 'true' || raw === 'false') val = raw === 'true';
    else if (raw === 'null') val = null;
    else continue; // not statically readable -> skip (raw snippet is preserved separately)
    defaults[key] = val;
  }
  return Object.keys(defaults).length ? defaults : null;
}

/** Count migrator versions: highest .add<...>(N in the snippet(s). */
function highestAddIndex(text) {
  const re = /\.add(?:\s*<[^>]*>)?\s*\(\s*(\d+)\s*,/g;
  let max = -1;
  let m;
  while ((m = re.exec(text)) !== null) max = Math.max(max, Number(m[1]));
  return max;
}

// ---------------------------------------------------------------------------
// Settings-field catalog extraction (0.43)
//
// In 0.43 a component's settings panel is defined by ONE of:
//   1. `settingsFormMarkup: <jsonImport>`  — a raw Shesha form-markup JSON file
//      (e.g. textField/settingsForm.json). Parsed as JSON -> quality "full".
//   2. `settingsFormMarkup: (data) => getSettings(data)` — a DesignerToolbarSettings
//      fluent-builder chain in settingsForm.ts / settings.ts. Parsed by scanning
//      `.addXxx({...})` calls -> quality "full".
//   3. `settingsFormFactory: (props) => <XxxSettingsForm/>` — a React settings form
//      (settings.tsx). Parsed by grepping `<SettingsFormItem name="..." label="...">`
//      -> quality "partial".
// There is NO shared appearance module in 0.43 — every settings form repeats the
// flat IInputStyles "Style" panel (providers/form/models.ts). That repeated set is
// emitted once as _shared-style-fields.json and per-component flagged via
// hasStandardAppearance + appearanceFieldPaths.
// ---------------------------------------------------------------------------

/** Flat 0.43 style/appearance model (IInputStyles + style/stylingBox). NOTE: no
 * desktop./tablet./mobile. breakpoint paths in 0.43 — that structure is 0.45+. */
const SHARED_STYLE_FIELDS = [
  { path: 'size', label: 'Size', editorType: 'dropdown', group: 'Style', description: 'Control size: small | middle | large' },
  { path: 'height', label: 'Height', editorType: 'textField', group: 'Style', description: 'CSS height (number = px, or any CSS size string). Also acts as max content height on inputs.' },
  { path: 'width', label: 'Width', editorType: 'textField', group: 'Style', description: 'CSS width (number = px, or any CSS size string)' },
  { path: 'hideBorder', label: 'Hide border', editorType: 'checkbox', group: 'Style', description: 'When true, border is not rendered' },
  { path: 'borderSize', label: 'Border Width', editorType: 'numberField', group: 'Style', description: 'Border width in px' },
  { path: 'borderRadius', label: 'Border Radius', editorType: 'numberField', group: 'Style', description: 'Border radius in px' },
  { path: 'borderType', label: 'Border Type', editorType: 'dropdown', group: 'Style', description: 'Border style: solid | dashed | dotted | double | none ...' },
  { path: 'borderColor', label: 'Border Color', editorType: 'colorPicker', group: 'Style' },
  { path: 'backgroundColor', label: 'Background Color', editorType: 'colorPicker', group: 'Style' },
  { path: 'fontSize', label: 'Font Size', editorType: 'numberField', group: 'Style' },
  { path: 'fontColor', label: 'Font Color', editorType: 'colorPicker', group: 'Style' },
  { path: 'fontWeight', label: 'Font Weight', editorType: 'dropdown', group: 'Style' },
  { path: 'style', label: 'Style', editorType: 'codeEditor', group: 'Style', description: 'JS script returning a CSSProperties object, e.g. return { backgroundColor: "#fff" };' },
  { path: 'stylingBox', label: 'Margin & Padding', editorType: 'styleBox', group: 'Style', description: 'JSON string of margins/paddings, e.g. "{\\"marginTop\\":\\"8\\",\\"paddingLeft\\":\\"16\\"}" — keys: marginTop/Right/Bottom/Left, paddingTop/Right/Bottom/Left' },
];
const SHARED_STYLE_PATHS = new Set(SHARED_STYLE_FIELDS.map((f) => f.path));

/** 0.46 std*Panel contents (form-factory/implementation.ts). Paths are relative to the device block (desktop/tablet/mobile) or the model root. */
const SHARED_STYLE_PANELS = {
  layout: ['display', 'flexDirection', 'flexWrap', 'justifyContent', 'alignItems', 'alignSelf', 'justifyItems', 'justifySelf', 'gap', 'gridColumnsCount', 'gridRowsCount', 'gridColumnsWidth', 'gridRowsHeight', 'showAdvanced'],
  dimensions: ['dimensions.width', 'dimensions.minWidth', 'dimensions.maxWidth', 'dimensions.height', 'dimensions.minHeight', 'dimensions.maxHeight', 'dimensions.gridColumn', 'dimensions.gridRow'],
  border: ['border.border.{all|top|right|bottom|left}.{width|style|color}', 'border.radius.{all|topLeft|topRight|bottomLeft|bottomRight}'],
  background: ['background.type', 'background.color', 'background.gradient.colors', 'background.gradient.direction', 'background.url', 'background.uploadFile', 'background.storedFile.id', 'background.size', 'background.position', 'background.repeat'],
  shadow: ['shadow.offsetX', 'shadow.offsetY', 'shadow.blurRadius', 'shadow.spreadRadius', 'shadow.color'],
  font: ['font.type', 'font.size', 'font.weight', 'font.color', 'font.align'],
  stylingBoxJson: ['stylingBoxJson'],
  style: ['style'],
};

/** Settings-form layout components that do not bind a model property. */
const NONFIELD_TYPES = new Set([
  'collapsiblePanel', 'sectionSeparator', 'divider', 'propertyRouter',
  'container', 'columns', 'tabs', 'alert', 'text', 'paragraph', 'title', 'button', 'buttons',
]);
const FLUENT_LAYOUT_METHODS = new Set([
  'addCollapsiblePanel', 'addSectionSeparator', 'addDivider', 'addPropertyRouter',
  'addContainer', 'addAlert', 'addButtons',
]);

/** addTextField -> textField, addEditMode -> editModeSelector, etc. */
function editorTypeFromMethod(method) {
  const overrides = {
    addEditMode: 'editModeSelector',
    addEditableTagGroupProps: 'editableTagGroup',
    addConfigurableActionConfigurator: 'configurableActionConfigurator',
    addButtons: 'buttonGroup',
  };
  if (overrides[method]) return overrides[method];
  const raw = method.slice(3);
  return raw.charAt(0).toLowerCase() + raw.slice(1);
}

function parseLiteral(raw) {
  if (raw === undefined || raw === null) return undefined;
  const t = String(raw).trim();
  if (/^(['"])(?:\\.|(?!\1).)*\1$/.test(t)) return t.slice(1, -1);
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  if (t === 'true' || t === 'false') return t === 'true';
  if (t === 'null') return null;
  return undefined;
}

function mkField(path_, label, editorType, defaultValue, group, description) {
  const f = { path: path_ };
  if (label !== undefined && label !== null && label !== '') f.label = label;
  if (editorType) f.editorType = editorType;
  if (defaultValue !== undefined) f.defaultValue = defaultValue;
  if (group) f.group = group;
  if (description) f.description = description;
  return f;
}

const joinPath = (prefix, name) => (prefix ? `${prefix}.${name}` : name);

/** 1. JSON form-markup settings file -> fields. */
function fieldsFromMarkupJson(json) {
  const fields = [];
  const visitChildren = (node, group, prefix) => {
    for (const key of Object.keys(node)) {
      const v = node[key];
      if (key === 'content' && v && Array.isArray(v.components)) visit(v.components, group, prefix);
      else if (Array.isArray(v) && v.some((x) => x && typeof x === 'object' && x.type && x.id)) visit(v, group, prefix);
      else if (v && typeof v === 'object' && !Array.isArray(v) && key !== 'content' && Array.isArray(v.components)) visit(v.components, group, prefix);
    }
  };
  const visit = (node, group, prefix) => {
    if (Array.isArray(node)) { node.forEach((n) => visit(n, group, prefix)); return; }
    if (!node || typeof node !== 'object') return;
    const type = node.type;
    if (type === 'collapsiblePanel') { visitChildren(node, node.label || group, prefix); return; }
    if (type === 'propertyRouter') {
      // propertyRouteName may be a JS-setting object ({_code,_mode,_value}) — only
      // prefix when it resolves to a plain non-empty string.
      let routeName = node.propertyRouteName;
      if (routeName && typeof routeName === 'object') routeName = typeof routeName._value === 'string' ? routeName._value : null;
      const p = typeof routeName === 'string' && routeName ? joinPath(prefix, routeName) : prefix;
      visitChildren(node, group, p);
      return;
    }
    if (type && node.propertyName && !NONFIELD_TYPES.has(type)) {
      fields.push(mkField(joinPath(prefix, node.propertyName), node.label, type,
        node.defaultValue !== undefined && ['string', 'number', 'boolean'].includes(typeof node.defaultValue) ? node.defaultValue : undefined,
        group, node.description || node.tooltip));
    }
    visitChildren(node, group, prefix);
  };
  visit(json.components || [], undefined, '');
  return fields;
}

/** Standard event sets (designer-components/_common/events.ts). */
const EVENT_SETS = {
  ALL_INPUT_EVENTS: ['onChange', 'onFocus', 'onBlur', 'onClick', 'onDoubleClick', 'onMouseEnter', 'onMouseMove', 'onMouseLeave', 'onKeyDown', 'onKeyUp'],
};
EVENT_SETS.ALL_INPUT_EVENTS_WITHOUT_CHANGE = EVENT_SETS.ALL_INPUT_EVENTS.filter((e) => e !== 'onChange');
EVENT_SETS.ALL_INPUT_EVENTS_WITHOUT_DOUBLE_CLICK = EVENT_SETS.ALL_INPUT_EVENTS.filter((e) => e !== 'onDoubleClick');
EVENT_SETS.ALL_INPUT_EVENTS_WITHOUT_CHANGE_AND_DOUBLE_CLICK = EVENT_SETS.ALL_INPUT_EVENTS_WITHOUT_CHANGE.filter((e) => e !== 'onDoubleClick');
EVENT_SETS.FILE_EVENTS = EVENT_SETS.ALL_INPUT_EVENTS_WITHOUT_DOUBLE_CLICK.filter((e) => e !== 'onKeyDown' && e !== 'onKeyUp');
EVENT_SETS.FILE_EVENTS_WITHOUT_CHANGE = EVENT_SETS.FILE_EVENTS.filter((e) => e !== 'onChange');

/** std* helpers that add fixed, named settings (form-factory/implementation.ts, 0.46). */
const STD_FIELD_HELPERS = {
  stdPropertyLabelInputs: [
    { path: 'propertyName', label: 'Property Name', editorType: 'contextPropertyAutocomplete', required: true },
    { path: 'hideLabel', label: 'Label', editorType: 'labelConfigurator' },
  ],
  stdPlaceholderDescriptionInputs: [
    { path: 'placeholder', label: 'Placeholder', editorType: 'textField' },
    { path: 'description', label: 'Tooltip', editorType: 'textArea' },
  ],
  stdVisibleEditableInputs: [
    { path: 'visible', label: 'Visible', editorType: 'switch', permissionSettings: true },
    { path: 'editMode', label: 'Interaction Mode', editorType: 'editModeSelector', permissionSettings: true },
  ],
  stdPrefixSuffixInputs: [
    { path: 'prefix', label: 'Prefix', editorType: 'textField' },
    { path: 'prefixIcon', label: 'Prefix Icon', editorType: 'iconPicker' },
    { path: 'suffix', label: 'Suffix', editorType: 'textField' },
    { path: 'suffixIcon', label: 'Suffix Icon', editorType: 'iconPicker' },
  ],
};

/** std*Panel helpers -> the style/model root they edit (device-scoped when under a style property router). */
const STD_PANEL_ROOTS = {
  stdLayoutPanel: 'layout', stdDimensionsPanel: 'dimensions', stdBorderPanel: 'border', stdBackgroundPanel: 'background',
  stdShadowPanel: 'shadow', stdMarginPaddingPanel: 'stylingBoxJson', stdFontPanel: 'font', stdCustomStylePanel: 'style',
};
const APPEARANCE_PANEL_NAMES = {
  background: 'background', shadow: 'shadow', marginPadding: 'stylingBoxJson', customStyle: 'style', font: 'font', dimensions: 'dimensions', border: 'border',
};

/** Parse the top-level `{...}` elements of an `inputs: [ ... ]` array literal. */
function parseInputsArray(argSrc) {
  const out = [];
  const m = /\binputs\s*:\s*(?:\w+\s*\()?\s*\[/.exec(argSrc);
  if (!m) return out;
  const open = argSrc.indexOf('[', m.index);
  const arr = balancedSpan(argSrc, open, '[', ']');
  if (!arr) return out;
  let i = 1;
  while (i < arr.length - 1) {
    if (arr[i] === '{') {
      const obj = balancedSpan(arr, i);
      if (!obj) break;
      out.push(obj);
      i += obj.length;
    } else i++;
  }
  return out;
}

function fieldFromObjectSrc(obj, typeKey, group) {
  const propertyName = (obj.match(/\bpropertyName\s*:\s*['"]([^'"]+)['"]/) || [])[1];
  if (!propertyName) return null;
  const type = (obj.match(new RegExp(`\\b${typeKey}\\s*:\\s*['"]([^'"]+)['"]`)) || [])[1];
  const label = (obj.match(/\blabel\s*:\s*(['"])((?:\\.|(?!\1).)*)\1/) || [])[2];
  const dv = (obj.match(/\bdefaultValue\s*:\s*((['"])(?:\\.|(?!\2).)*\2|-?\d+(?:\.\d+)?|true|false|null)\s*(?:,|\n|\})/) || [])[1];
  const desc = (obj.match(/\b(?:description|tooltip)\s*:\s*(['"])((?:\\.|(?!\1).)*)\1/) || [])[2];
  const f = mkField(propertyName, label, type, parseLiteral(dv), group, desc);
  const optKey = /\b(dropdownOptions|buttonGroupOptions)\s*:\s*\[/.exec(obj);
  if (optKey) {
    const arr = balancedSpan(obj, obj.indexOf('[', optKey.index), '[', ']') || '';
    const vals = [...arr.matchAll(/\bvalue\s*:\s*(['"])((?:\\.|(?!\1).)*)\1/g)].map((x) => x[2]);
    if (vals.length) f.options = [...new Set(vals)];
  }
  if (/\bpermissionSettings\s*:\s*true/.test(obj)) f.permissionSettings = true;
  if (/\bvalidate\s*:\s*\{\s*required\s*:\s*true/.test(obj)) f.required = true;
  return f;
}

/** 2. DesignerToolbarSettings / FormBuilder fluent chain -> { fields, appearancePanels, perDevice }. */
function fieldsFromFluent(text) {
  const fields = [];
  const panels = []; // { start, end, label }
  const appearance = new Set();
  const re = /\.(add|std)([A-Z][\w$]*)\s*(?:<[^>(]*>)?\s*\(/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const kind = m[1];
    const method = kind + m[2];
    const openParen = m.index + m[0].length - 1;
    const span = balancedSpan(text, openParen, '(', ')');
    if (!span) continue;
    const arg = span;
    const push = (f) => fields.push({ pos: m.index, field: f });

    if (kind === 'std') {
      if (STD_FIELD_HELPERS[method]) {
        for (const s of STD_FIELD_HELPERS[method]) {
          const f = mkField(s.path, s.label, s.editorType);
          if (s.permissionSettings) f.permissionSettings = true;
          if (s.required) f.required = true;
          push(f);
        }
      } else if (STD_PANEL_ROOTS[method]) {
        appearance.add(STD_PANEL_ROOTS[method]);
      } else if (method === 'stdAppearancePanels') {
        for (const nm of arg.matchAll(/['"]([A-Za-z]+)['"]/g)) if (APPEARANCE_PANEL_NAMES[nm[1]]) appearance.add(APPEARANCE_PANEL_NAMES[nm[1]]);
      } else if (method === 'stdEventHandlers') {
        const first = arg.slice(1).trimStart();
        let events = [];
        if (first.startsWith('[')) {
          const arrSrc = balancedSpan(first, 0, '[', ']') || '';
          events = [...arrSrc.matchAll(/['"](on\w+)['"]/g)].map((x) => x[1]);
          for (const sp of arrSrc.matchAll(/\.\.\.\s*([A-Z_]+)/g)) if (EVENT_SETS[sp[1]]) events = events.concat(EVENT_SETS[sp[1]]);
        } else {
          const id = (first.match(/^([A-Za-z_$][\w$]*)/) || [])[1];
          if (id && EVENT_SETS[id]) events = EVENT_SETS[id];
          else if (id) {
            const decl = text.match(new RegExp(`(?:const|let)\\s+${id}\\b[^=]*=\\s*\\[`));
            if (decl) {
              const arr = balancedSpan(text, text.indexOf('[', decl.index + decl[0].length - 1), '[', ']') || '';
              events = [...arr.matchAll(/['"](on\w+)['"]/g)].map((x) => x[1]);
            }
          }
        }
        for (const ev of events) push(mkField(`${ev}Custom`, undefined, 'codeEditor', undefined, 'Events'));
      } else if (method === 'stdEventHandler') {
        const nm = arg.match(/^\(\s*['"]([^'"]+)['"]\s*,\s*(?:['"]([^'"]*)['"])?/) || [];
        if (nm[1]) push(mkField(nm[1], nm[2], 'codeEditor', undefined, 'Events'));
      } else if (method === 'stdFontControls') {
        appearance.add((arg.match(/^\(\s*['"]([^'"]+)['"]/) || [])[1] || 'font');
      } else if (method === 'stdCollapsiblePanel') {
        const label = (arg.match(/^\(\s*(['"])((?:\\.|(?!\1).)*)\1/) || [])[2];
        panels.push({ start: openParen, end: openParen + span.length, label });
      }
      continue;
    }

    const propertyName = (arg.match(/propertyName\s*:\s*['"]([^'"]+)['"]/) || [])[1];
    const label = (arg.match(/label\s*:\s*(['"])((?:\\.|(?!\1).)*)\1/) || [])[2];
    if (method === 'addCollapsiblePanel') {
      panels.push({ start: openParen, end: openParen + span.length, label });
      continue;
    }
    if (method === 'addSettingsInputRow') {
      for (const obj of parseInputsArray(arg)) { const f = fieldFromObjectSrc(obj, 'type'); if (f) push(f); }
      continue;
    }
    if (method === 'addSettingsInput') {
      const f = fieldFromObjectSrc(arg, 'inputType');
      if (f) push(f);
      continue;
    }
    if (FLUENT_LAYOUT_METHODS.has(method) || !propertyName) continue;
    const dv = (arg.match(/defaultValue\s*:\s*((['"])(?:\\.|(?!\2).)*\2|-?\d+(?:\.\d+)?|true|false|null)\s*(?:,|\n|\})/) || [])[1];
    const desc = (arg.match(/(?:description|tooltip)\s*:\s*(['"])((?:\\.|(?!\1).)*)\1/) || [])[2];
    push(mkField(propertyName, label, editorTypeFromMethod(method), parseLiteral(dv), undefined, desc));
  }
  for (const { pos, field } of fields) {
    if (field.group) continue;
    let best = null;
    for (const p of panels) {
      if (pos > p.start && pos < p.end && p.label) {
        if (!best || (p.end - p.start) < (best.end - best.start)) best = p;
      }
    }
    if (best) field.group = best.label;
  }
  const perDevice = appearance.size > 0 && !/removeStyleRouter\s*[:=]\s*true/.test(text);
  return { fields: fields.map((f) => f.field), appearancePanels: [...appearance], perDevice };
}

/** 3. React settings.tsx -> best-effort fields (partial). */
function fieldsFromTsx(text) {
  const fields = [];
  const panels = [...text.matchAll(/<SettingsCollapsiblePanel[^>]*header\s*=\s*[{'"]+([^'"}]+)/g)]
    .map((m) => ({ start: m.index, label: m[1] }));
  const re = /<(?:SettingsFormItem|Form\.Item|FormItem)\b([^>]*)>/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const attrs = m[1];
    const name = (attrs.match(/\bname\s*=\s*(?:"([\w.]+)"|'([\w.]+)'|\{\s*['"]([\w.]+)['"]\s*\})/) || []);
    const path_ = name[1] || name[2] || name[3];
    if (!path_) continue;
    const label = (attrs.match(/\blabel\s*=\s*(?:"([^"]*)"|'([^']*)')/) || []);
    const tooltip = (attrs.match(/\btooltip\s*=\s*(?:"([^"]*)"|'([^']*)')/) || []);
    let group;
    for (const p of panels) if (p.start < m.index) group = p.label;
    fields.push(mkField(path_, label[1] || label[2], undefined, undefined, group, tooltip[1] || tooltip[2]));
  }
  return fields;
}

/** Resolve an import specifier to an existing file path. */
function resolveSpec(fromFile, spec) {
  let base = null;
  if (spec.startsWith('@/')) base = path.join(SRC_ROOT, spec.slice(2));
  else if (spec.startsWith('.')) base = path.resolve(path.dirname(fromFile), spec);
  if (!base) return null;
  for (const ext of ['', '.json', '.ts', '.tsx', '/index.ts', '/index.tsx']) {
    const p = base + ext;
    if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  }
  return null;
}

/** Find the module file an identifier is imported from (default or named, incl. alias). */
function resolveImportedIdentifier(fromFile, text, identifier) {
  const re = /import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"]/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const clause = m[1];
    const names = [];
    const def = clause.match(/^([A-Za-z_$][\w$]*)/);
    if (def && !clause.trimStart().startsWith('{')) names.push(def[1]);
    const named = clause.match(/\{([\s\S]*?)\}/);
    if (named) {
      for (const part of named[1].split(',')) {
        const p = part.trim();
        if (!p) continue;
        const as = p.match(/^[\w$]+\s+as\s+([\w$]+)$/);
        names.push(as ? as[1] : p.split(/\s+/)[0]);
      }
    }
    if (names.includes(identifier)) return resolveSpec(fromFile, m[2]);
  }
  return null;
}

/**
 * Extract the settings-field catalog for one toolbox component.
 * Returns { source, mechanism, parseQuality, fields } (fields possibly []).
 */
function extractSettingsCatalog(file, text, objSrc) {
  // --- settingsFormMarkup ---
  let ident = null;
  const mm = objSrc.match(/settingsFormMarkup\s*:\s*([^,\n]+)/);
  if (mm) {
    const expr = mm[1].trim();
    const fnCall = expr.match(/^(?:\(?\s*[\w$]*\s*\)?\s*=>\s*)?([A-Za-z_$][\w$]*)\s*\(/);
    const bare = expr.match(/^([A-Za-z_$][\w$]*)\s*$/);
    ident = fnCall ? fnCall[1] : bare ? bare[1] : null;
  } else if (/(?:^|[,{\s])settingsFormMarkup\s*[,}]/.test(objSrc)) {
    ident = 'settingsFormMarkup';
  }

  if (ident) {
    // follow one local alias hop: const settingsForm = settingsFormJson as FormMarkup;
    let target = resolveImportedIdentifier(file, text, ident);
    if (!target) {
      const alias = text.match(new RegExp(`(?:const|let|var)\\s+${ident}\\s*(?::[^=]+)?=\\s*([A-Za-z_$][\\w$]*)\\s*(?:as\\b|;|,|\\n)`));
      if (alias) target = resolveImportedIdentifier(file, text, alias[1]);
    }
    if (target && target.endsWith('.json')) {
      try {
        const json = JSON.parse(readFile(target));
        return { source: rel(target), mechanism: 'json-markup', parseQuality: 'full', fields: fieldsFromMarkupJson(json) };
      } catch {
        return { source: rel(target), mechanism: 'json-markup', parseQuality: 'none', fields: [] };
      }
    }
    const chainText = target ? readFile(target) : text; // chain may be defined in the component file itself
    const fl = fieldsFromFluent(chainText);
    if (fl.fields.length || fl.appearancePanels.length) {
      return { source: rel(target || file), mechanism: 'fluent-builder', parseQuality: 'full', fields: fl.fields, appearancePanels: fl.appearancePanels, perDevice: fl.perDevice };
    }
    // fall through to factory detection if the chain produced nothing
  }

  // --- settingsFormFactory ---
  const factorySnippet = extractPropSnippet(objSrc, 'settingsFormFactory');
  if (factorySnippet) {
    // find capitalized JSX components in the factory; resolve to a settings .tsx
    const jsxNames = [...new Set([...factorySnippet.matchAll(/<([A-Z][\w$]*)/g)].map((x) => x[1]))];
    for (const name of jsxNames) {
      const target = resolveImportedIdentifier(file, text, name);
      if (!target) continue;
      const fields = fieldsFromTsx(readFile(target));
      if (fields.length) return { source: rel(target), mechanism: 'react-factory', parseQuality: 'partial', fields };
    }
    // inline factory or same-file settings component
    const inline = fieldsFromTsx(factorySnippet.length > 200 ? factorySnippet : text);
    const fallback = inline.length ? inline : fieldsFromTsx(text);
    if (fallback.length) return { source: rel(file), mechanism: 'react-factory', parseQuality: 'partial', fields: fallback };
    return { source: rel(file), mechanism: 'react-factory', parseQuality: 'none', fields: [] };
  }

  // last resort: a settingsForm.json sitting in the component folder (covers
  // composite wrappers like notes/notesComponent.tsx building the markup object inline)
  if (ident) {
    const dirJson = path.join(path.dirname(file), 'settingsForm.json');
    if (fs.existsSync(dirJson)) {
      try {
        const json = JSON.parse(readFile(dirJson));
        const fields = fieldsFromMarkupJson(json);
        if (fields.length) return { source: rel(dirJson), mechanism: 'json-markup', parseQuality: 'full', fields };
      } catch { /* fall through */ }
    }
    return { source: rel(file), mechanism: 'fluent-builder', parseQuality: 'none', fields: [] };
  }
  return { source: null, mechanism: 'none', parseQuality: 'none', fields: [] };
}

/** Dedupe by path (first wins), split shared appearance set out. */
function buildSettingsSection(catalog) {
  const seen = new Set();
  const fields = [];
  for (const f of catalog.fields) {
    if (seen.has(f.path)) continue;
    seen.add(f.path);
    fields.push(f);
  }
  const panels = catalog.appearancePanels || [];
  if (panels.length) {
    // 0.46 pattern: std*Panel helpers. The style model lives in per-device blocks (desktop/tablet/mobile)
    // when the panels sit under a style property router; see _shared-style-fields.json.
    return {
      settingsForm: { source: catalog.source, mechanism: catalog.mechanism, parseQuality: catalog.parseQuality },
      hasStandardAppearance: true,
      appearanceFieldPaths: panels,
      appearanceScope: catalog.perDevice ? 'per-device' : 'flat',
      settingsFields: fields,
    };
  }
  const appearancePaths = fields.filter((f) => SHARED_STYLE_PATHS.has(f.path)).map((f) => f.path);
  const hasStandardAppearance = appearancePaths.length >= 6;
  // when the standard appearance panel is present, represent those fields by path
  // only (full definitions live in _shared-style-fields.json); otherwise keep inline.
  const settingsFields = hasStandardAppearance
    ? fields.filter((f) => !SHARED_STYLE_PATHS.has(f.path))
    : fields.map((f) => (SHARED_STYLE_PATHS.has(f.path) ? { ...f, shared: true } : f));
  return {
    settingsForm: { source: catalog.source, mechanism: catalog.mechanism, parseQuality: catalog.parseQuality },
    hasStandardAppearance,
    appearanceFieldPaths: appearancePaths,
    settingsFields,
  };
}

const SLOT_KEYS = ['components', 'childItems', 'tabs', 'columns', 'panels', 'steps', 'header', 'content', 'footer'];

function detectSlots(objSrc, componentDirFiles, propsResolved) {
  const slots = {
    hostsChildren: false,
    customContainerNames: null,
    detectedSlotKeys: [],
    usesComponentsContainer: false,
  };
  const ccn = extractPropSnippet(objSrc, 'customContainerNames');
  if (ccn && ccn.startsWith('[')) {
    const names = [...ccn.matchAll(/['"]([\w.]+)['"]/g)].map((x) => x[1]);
    if (names.length) slots.customContainerNames = names;
  }
  const dirText = componentDirFiles.map((f) => { try { return readFile(f); } catch { return ''; } }).join('\n');
  if (/ComponentsContainer\b/.test(dirText)) slots.usesComponentsContainer = true;
  for (const key of SLOT_KEYS) {
    const inProps = propsResolved && propsResolved.includes(key);
    const inModelUse = new RegExp(`model\\.${key}\\b`).test(dirText) ||
      new RegExp(`\\b${key}\\s*:\\s*I[\\w]*(Component|Tab|Column|Panel|Step)[\\w]*\\[\\]`).test(dirText);
    if (inProps || inModelUse) slots.detectedSlotKeys.push(key);
  }
  slots.hostsChildren = slots.usesComponentsContainer || !!slots.customContainerNames ||
    slots.detectedSlotKeys.some((k) => ['components', 'tabs', 'columns', 'panels', 'steps'].includes(k));
  return slots;
}

let _registeredFiles = null;
/** Absolute paths of the component files imported by the framework toolbox registry (best effort). */
function getRegisteredFiles() {
  if (_registeredFiles) return _registeredFiles;
  _registeredFiles = new Set();
  const regFile = path.join(SRC_ROOT, 'providers', 'form', 'defaults', 'toolboxComponents.ts');
  if (fs.existsSync(regFile)) {
    const txt = readFile(regFile);
    for (const m of txt.matchAll(/from\s+['"]([^'"]+)['"]/g)) {
      const p = resolveSpec(regFile, m[1]);
      if (p) _registeredFiles.add(path.resolve(p));
    }
  }
  return _registeredFiles;
}

function readRaw(p) {
  return fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
}

function processFile(file) {
  let text;
  try { text = readFile(file); } catch { return; }
  // generic content may nest (e.g. Omit<IWizardComponentProps, 'size'>) — anything but `=`/`{`/`;`
  // IToolboxComponent<IProps> | ComponentDefinition<"t", IProps> | XxxDefinition / XxxComponentDefinition (0.46)
  const re = /(?:const|export\s+const|let|var)\s+([A-Za-z_$][\w$]*)\s*:\s*(IToolboxComponent|ComponentDefinition|[A-Za-z_$][\w$]*Definition)\s*(<[^={};]*>)?\s*=\s*\{/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const varName = m[1];
    const annotation = m[2];
    let propsInterface = null;
    if (m[3]) propsInterface = propsIdentFromGenerics(m[3].slice(1, -1), annotation === 'ComponentDefinition');
    else if (definitionAliasIndex.has(annotation)) propsInterface = definitionAliasIndex.get(annotation);
    else if (annotation === 'IToolboxComponent') propsInterface = 'IConfigurableFormComponent'; // no generic => base model
    const braceIdx = m.index + m[0].length - 1;
    const objSrc = balancedSpan(text, braceIdx);
    if (!objSrc) {
      gaps.push({ file: rel(file), variable: varName, reason: 'Could not extract balanced object literal for IToolboxComponent definition' });
      continue;
    }

    const type = extractStringProp(objSrc, 'type');
    if (!type) {
      gaps.push({ file: rel(file), variable: varName, reason: 'IToolboxComponent object has no statically-readable type string' });
      continue;
    }
    if (entries.has(type)) {
      // two files declare the same type: keep the one the toolbox registry imports
      const reg = getRegisteredFiles();
      const prev = entries.get(type);
      const prevAbs = path.resolve(SRC, prev.sourceFiles[0]);
      if (reg.has(path.resolve(file)) && !reg.has(prevAbs)) {
        gaps.push({ file: prev.sourceFiles[0], type, reason: `Duplicate type '${type}' — not imported by providers/form/defaults/toolboxComponents.ts; ${rel(file)} (registered) kept instead` });
        entries.delete(type);
      } else {
        gaps.push({ file: rel(file), variable: varName, type, reason: `Duplicate type '${type}' — first definition kept (${prev.sourceFiles[0]})` });
        continue;
      }
    }

    const componentDir = path.dirname(file);
    const componentDirFiles = walk(componentDir, ['.ts', '.tsx']);

    // --- version (migrator chain) ---
    let version = null;
    let migratorNote;
    if (/(?:^|[,{\s])migrator\s*:/m.test(objSrc)) {
      let max = highestAddIndex(objSrc);
      if (max < 0) {
        // chain may live in another file within the component folder (e.g. migrations/)
        for (const f of componentDirFiles) {
          if (f === file) continue;
          max = Math.max(max, highestAddIndex(readFile(f)));
        }
        migratorNote = max >= 0 ? 'migrator chain resolved from sibling file(s), not inline' : undefined;
      }
      if (max >= 0) version = max;
      else gaps.push({ file: rel(file), type, reason: 'migrator present but no .add(N, ...) indices found' });
    }

    // --- initModel ---
    const initModelSnippet = extractPropSnippet(objSrc, 'initModel');
    const initModelDefaults = parseInitModelDefaults(initModelSnippet);
    if (initModelSnippet && !initModelDefaults && !/\.\.\.\s*model\s*[,}]?\s*\}?\s*\)?$/.test(initModelSnippet.replace(/\s+/g, ' '))) {
      // only flag when there was something to parse beyond spread
      if (!/^\(?\s*\(?model\)?\s*\)?\s*=>\s*\(\s*\{\s*\.\.\.model\s*,?\s*\}\s*\)$/.test(initModelSnippet.replace(/\s+/g, ' '))) {
        gaps.push({ file: rel(file), type, reason: 'initModel present but no statically-readable literal defaults parsed (raw snippet recorded)' });
      }
    }

    // --- settings props interface ---
    let settingsProps = null;
    if (propsInterface) {
      const decl = interfaceIndex.get(propsInterface);
      const resolved = resolveInterface(propsInterface);
      settingsProps = {
        interfaceName: propsInterface,
        interfaceFile: decl ? decl.file : null,
        ownProps: decl ? decl.props : [],
        extends: decl ? decl.extends : [],
        resolvedProps: resolved.props.sort(),
        unresolvedExtends: [...new Set(resolved.unresolved)].sort(),
      };
      if (!decl) gaps.push({ file: rel(file), type, reason: `Props interface '${propsInterface}' declaration not found in indexed sources` });
    } else {
      gaps.push({ file: rel(file), type, reason: 'IToolboxComponent has no generic props interface parameter' });
    }

    // --- slots ---
    const slots = detectSlots(objSrc, componentDirFiles, settingsProps ? settingsProps.resolvedProps : null);

    // --- settings-field catalog ---
    let settingsSection;
    try {
      const catalog = extractSettingsCatalog(file, text, objSrc);
      settingsSection = buildSettingsSection(catalog);
      if (catalog.parseQuality === 'none') {
        gaps.push({ file: rel(file), type, reason: catalog.mechanism === 'none' ? 'Settings catalog: component declares no settings form (internal, hidden, deprecated or legacy component)' : `Settings catalog: no fields extracted (mechanism: ${catalog.mechanism})` });
      }
    } catch (err) {
      settingsSection = {
        settingsForm: { source: null, mechanism: 'error', parseQuality: 'none' },
        hasStandardAppearance: false, appearanceFieldPaths: [], settingsFields: [],
      };
      gaps.push({ file: rel(file), type, reason: `Settings catalog extraction threw: ${err.message}` });
    }

    // --- source files ---
    const sourceFiles = [rel(file)];
    if (settingsProps && settingsProps.interfaceFile) {
      const asDesignerRel = path.relative(SRC, path.join(SRC_ROOT, settingsProps.interfaceFile)).split(path.sep).join('/');
      if (!sourceFiles.includes(asDesignerRel)) sourceFiles.push(asDesignerRel);
    }

    // --- 0.46 registration metadata ---
    const rawText = readRaw(file);
    // only the comment block directly above the declaration (not an earlier member's JSDoc)
    const before = rawText.slice(0, m.index);
    const cut = Math.max(before.lastIndexOf(String.fromCharCode(10, 10)), before.lastIndexOf(";" + String.fromCharCode(10)), before.lastIndexOf("}" + String.fromCharCode(10)), 0);
    const preamble = before.slice(cut);
    const deprecated = /@deprecated/.test(preamble) || /deprecated/i.test(extractStringProp(objSrc, 'name') || '') || undefined;
    const allowInherit = extractBoolProp(objSrc, 'allowInherit');
    const getContainersSnippet = extractPropSnippet(objSrc, 'getContainers');
    const getDefaultStylesSnippet = extractPropSnippet(objSrc, 'getDefaultStyles');

    const entry = {
      type,
      name: extractStringProp(objSrc, 'name') ?? null,
      isInput: extractBoolProp(objSrc, 'isInput') ?? null,
      isOutput: extractBoolProp(objSrc, 'isOutput') ?? null,
      canBeJsSetting: extractBoolProp(objSrc, 'canBeJsSetting') ?? null,
      icon: (objSrc.match(/(?:^|[,{\s])icon\s*:\s*<\s*([A-Za-z_$][\w$]*)/m) || [])[1] ?? null,
      version, // null => component has no migrator; OMIT the version prop in markup
      allowInherit: allowInherit === true,
      styleGroup: extractStringProp(objSrc, 'styleGroup') ?? null,
      isHidden: extractBoolProp(objSrc, 'isHidden') === true,
      ...(deprecated ? { deprecated: true } : {}),
      customContainerNames: slots.customContainerNames,
      hasGetContainers: !!getContainersSnippet,
      defaultStylesFrom: getDefaultStylesSnippet ? getDefaultStylesSnippet.replace(/\s+/g, ' ').slice(0, 120) : null,
      ...(migratorNote ? { migratorNote } : {}),
      initModel: initModelSnippet
        ? { defaults: initModelDefaults, raw: initModelSnippet.length > 2000 ? initModelSnippet.slice(0, 2000) + ' /* truncated */' : initModelSnippet }
        : null,
      settingsProps,
      ...settingsSection,
      slots,
      sourceFiles,
    };
    entries.set(type, entry);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
buildInterfaceIndex();

for (const file of walk(SRC, ['.ts', '.tsx'])) processFile(file);

// Folders with no toolbox component at all -> gaps
for (const e of fs.readdirSync(SRC, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
  if (!e.isDirectory() || e.name.startsWith('_') || e.name === '__tests__') continue;
  const folder = path.join(SRC, e.name);
  const hasEntry = [...entries.values()].some((en) => en.sourceFiles[0].startsWith(e.name + '/'));
  if (!hasEntry) {
    gaps.push({ file: e.name + '/', reason: 'No IToolboxComponent definition found in this component folder' });
  }
}

// ---------------------------------------------------------------------------
// Write output
// ---------------------------------------------------------------------------
fs.mkdirSync(outDir, { recursive: true });
// clear previous generated component files so stale types never survive a regeneration
for (const f of fs.readdirSync(outDir)) if (f.endsWith('.json')) fs.unlinkSync(path.join(outDir, f));

// --- merge component-versions.json (reworked flag + render-impacting migrations) ---
let versionsByType = null;
if (versionsFile) {
  const vj = JSON.parse(fs.readFileSync(versionsFile, 'utf8'));
  versionsByType = new Map((vj.components || []).map((c) => [c.type, c]));
}
for (const entry of entries.values()) {
  const v = versionsByType ? versionsByType.get(entry.type) : null;
  entry.reworked = v ? v.reworked === true : entry.allowInherit === true;
  if (v) {
    entry.registeredInToolbox = true;
    if (entry.version !== v.currentVersion) {
      entry.versionSourceMismatch = { extracted: entry.version, expected: v.currentVersion };
      gaps.push({ file: entry.sourceFiles[0], type: entry.type, reason: `Extracted version ${entry.version} differs from component-versions.json currentVersion ${v.currentVersion}` });
    }
    entry.renderImpact = (v.notableMigrations || [])
      .filter((n) => n.renderImpact !== false)
      .map((n) => ({
        toVersion: n.toVersion,
        category: n.category,
        what: String(n.what).replace(/\s+/g, ' ').slice(0, 220),
      }));
  } else if (versionsByType) {
    entry.registeredInToolbox = false;
    entry.renderImpact = [];
    gaps.push({ file: entry.sourceFiles[0], type: entry.type, reason: 'Not listed in component-versions.json (not in the toolbox registry); entry kept for reference' });
  }
}
if (versionsByType) {
  for (const t of versionsByType.keys()) {
    if (!entries.has(t)) gaps.push({ type: t, reason: 'Listed in component-versions.json but no definition extracted from source' });
  }
}

const sortedTypes = [...entries.keys()].sort();
const index = {};
for (const type of sortedTypes) {
  const entry = entries.get(type);
  const fileName = type.replace(/[^\w.-]/g, '_') + '.json';
  fs.writeFileSync(path.join(outDir, fileName), JSON.stringify(entry, null, 2) + '\n');
  index[type] = {
    version: entry.version, name: entry.name, isInput: entry.isInput, file: fileName,
    settingsParseQuality: entry.settingsForm ? entry.settingsForm.parseQuality : 'none',
    settingsFieldCount: (entry.settingsFields ? entry.settingsFields.length : 0) + (entry.hasStandardAppearance ? entry.appearanceFieldPaths.length : 0),
    hasStandardAppearance: !!entry.hasStandardAppearance,
    reworked: entry.reworked === true,
    ...(entry.deprecated ? { deprecated: true } : {}),
    ...(entry.isHidden ? { isHidden: true } : {}),
  };
}

// _enums.json: option values read from dropdownOptions/buttonGroupOptions literals in the settings forms
const enums = {};
for (const entry of entries.values()) {
  for (const fld of entry.settingsFields || []) {
    if (!fld.options || !fld.options.length) continue;
    (enums[entry.type] = enums[entry.type] || {})[fld.path] = { values: fld.options, source: 'source-parsed' };
  }
}
fs.writeFileSync(path.join(outDir, '_enums.json'), JSON.stringify(enums, null, 2) + '\n');
fs.writeFileSync(path.join(outDir, '_index.json'), JSON.stringify(index, null, 2) + '\n');

fs.writeFileSync(path.join(outDir, '_shared-style-fields.json'), JSON.stringify({
  description: 'Standard 0.46 appearance model. Components with hasStandardAppearance:true list the panels they expose in appearanceFieldPaths '
    + '(layout, dimensions, border, background, shadow, font, stylingBoxJson, style). When appearanceScope is "per-device" the panels edit '
    + 'the desktop / tablet / mobile blocks: write paths as desktop.dimensions.width, tablet.font.size etc. '
    + 'Source: form-factory/implementation.ts std*Panel helpers. The 0.43 flat style model (size, height, borderSize, ...) no longer applies.',
  stylingBoxJsonShape: {
    note: 'stylingBoxJson is an OBJECT (not a string); the legacy stylingBox string is migrated into it by the VISIBLE_STYLINGJSON migration.',
    example: { _type: 'styleBox', marginBottom: 5, paddingLeft: 16 },
  },
  panels: SHARED_STYLE_PANELS,
}, null, 2) + '\n');

let commit = null;
let sourceBranch = null;
try {
  commit = execSync('git rev-parse HEAD', { cwd: SRC, encoding: 'utf8' }).trim();
  const b = execSync('git branch --show-current', { cwd: SRC, encoding: 'utf8' }).trim();
  sourceBranch = b || null;
  if (!sourceBranch) {
    // detached HEAD (worktree) — find a branch containing this commit
    const branches = execSync('git branch -a --contains HEAD', { cwd: SRC, encoding: 'utf8' })
      .split('\n').map((s) => s.replace(/^[*+\s]+/, '').trim()).filter(Boolean);
    sourceBranch = branches.find((x) => /releases\//.test(x)) || branches[0] || null;
    try {
      // a release tag (e.g. release-0.46.0) is the authoritative source name for a detached checkout
      const tag = execSync('git describe --tags --exact-match', { cwd: SRC, encoding: 'utf8' }).trim();
      if (tag) sourceBranch = tag;
    } catch { /* no exact tag */ }
  }
} catch { /* not a git repo */ }

let generatedAt = null;
try {
  generatedAt = execSync('git log -1 --format=%cI', { cwd: SRC, encoding: 'utf8' }).trim();
} catch { /* ignore */ }

fs.writeFileSync(path.join(outDir, '_meta.json'), JSON.stringify({
  sourceDir: (() => { try { const top = execSync('git rev-parse --show-toplevel', { cwd: SRC, encoding: 'utf8' }).trim(); return path.relative(top, SRC).split(path.sep).join('/'); } catch { return 'designer-components'; } })(),
  sourceBranch,
  commit,
  sourceCommitDate: generatedAt,
  generatedAt: new Date().toISOString(),
  componentCount: sortedTypes.length,
  settingsCatalog: (() => {
    const all = [...entries.values()];
    const q = (x) => all.filter((e) => e.settingsForm && e.settingsForm.parseQuality === x).length;
    const totalFields = all.reduce((s, e) => s + (e.settingsFields ? e.settingsFields.length : 0) + (e.hasStandardAppearance ? e.appearanceFieldPaths.length : 0), 0);
    return {
      full: q('full'), partial: q('partial'), none: q('none'),
      withStandardAppearance: all.filter((e) => e.hasStandardAppearance).length,
      totalFields,
      avgFieldsPerComponent: Math.round((totalFields / all.length) * 10) / 10,
    };
  })(),
}, null, 2) + '\n');

fs.writeFileSync(path.join(outDir, '_gaps.json'), JSON.stringify(gaps, null, 2) + '\n');

console.log(`Extracted ${sortedTypes.length} toolbox components -> ${outDir}`);
console.log(`Gaps/warnings: ${gaps.length} (see _gaps.json)`);
