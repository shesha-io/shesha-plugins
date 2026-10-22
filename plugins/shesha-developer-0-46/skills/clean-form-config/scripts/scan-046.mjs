#!/usr/bin/env node
/*
 * scan-046.mjs - clean-form-config checks for Shesha 0.46 form markup (dead props, render-time script
 * hazards, htmlRender carriers, deprecated components, per-device spacing, legacy scripting names, ...).
 *
 *   node scan-046.mjs <markup.json | dir> [--json] [--fix] [--fix-legacy-names] [--dead-all] [--out <dir>] [--groups <dir>]
 *
 * Input: raw markup ({components, formSettings}), a stringified markup, or an API envelope
 * ({result:{configuration:{markup}}} / {result:{markup}} / {markup}). Read-only unless --fix.
 * --fix writes <name>.cleaned.json into --out (default: ./cleaned) and never overwrites the input. It applies
 * ONLY the conservative, idempotent fixes marked [FIXABLE] below; every edited script is re-parsed as an async
 * function body and the edit is discarded (and reported as manual) if it no longer parses.
 * Dead props (D1) are removed only from components already at the current KB version; below it they are
 * reported as D1-STALE and left alone (the migrator may read them). --dead-all removes them anyway (and dead
 * formSettings keys, D2) - use only on markup you know is final.
 * --fix-legacy-names additionally rewrites the two trivially-safe legacy scripting names (see N5).
 * Exit: 0 clean, 1 findings, 2 could not run.   No dependencies.
 *
 * Checks (ids are stable; see references in SKILL.md):
 *   D1  dead component property (index-driven; LEGACY props below the current version are left alone)  [FIXABLE]
 *   D2  dead formSettings property                                                                      [FIXABLE]
 *   N1  unsafe member chain in a render-time script (every `_code`, any depth, incl. desktop/tablet/mobile) [FIXABLE]
 *   N2  htmlRender carrier hazards (style + sanitize, style-only output, contentType html, hidden carrier)  [FIXABLE: sanitize:false]
 *   N3  deprecated / hidden / unregistered component type
 *   N4  per-device component whose spacing lives only in the legacy `stylingBox` string                    [FIXABLE]
 *   N5  legacy scripting names (pageContext, http, message, globalState, formData ...)                      [report; opt-in rewrite]
 *   N6  subForm whose effective label span is 0 (hosted field labels hidden)
 *   N7  ReferenceList/GetItems URL (404 on 0.46)
 *   N8  editMode returning boolean false (means DISABLED in 0.46)
 *   N9  pre-antd-6 tabs/collapse DOM selectors in CSS-bearing strings
 *   S1  script does not parse as an async function body
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const opt = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const target = argv.find((a, i) => !a.startsWith('--') && !['--out', '--groups'].includes(argv[i - 1]));
const GROUPS = path.resolve(opt('--groups', path.join(here, '../assets/groups')));
const OUT = path.resolve(opt('--out', 'cleaned'));
const FIX = flag('--fix');
const FIX_LEGACY = flag('--fix-legacy-names');
const DEAD_ALL = flag('--dead-all');
const JSON_OUT = flag('--json');
if (!target || !fs.existsSync(target)) { console.error('usage: scan-046.mjs <file.json|dir> [--json] [--fix] [--fix-legacy-names] [--dead-all] [--out dir] [--groups dir]'); process.exit(2); }

// ---- index ------------------------------------------------------------------------------------------------
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const INDEX = readJson(path.join(GROUPS, 'index.json'));
const BASE = readJson(path.join(GROUPS, 'base.json'));
const baseNames = new Set(BASE.base.props.map((p) => p.name));
const legacyBase = new Set(BASE.legacyBase ?? []);
const formSettingsNames = new Set(BASE._formSettings.props.map((p) => p.name));
const groupCache = {};
const compEntry = (type) => {
  const g = INDEX.components[type];
  if (!g) return null;
  groupCache[g] ??= readJson(path.join(GROUPS, `${g}.json`));
  return groupCache[g][type] ?? null;
};
const STRUCTURAL = new Set(['id', 'type', 'parentId', 'components']);

// ---- helpers ----------------------------------------------------------------------------------------------
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const parses = (code) => { try { new AsyncFunction(code); return null; } catch (e) { return e.message; } };
const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);
const isComp = (o) => isObj(o) && typeof o.type === 'string' && typeof o.id === 'string';

function unwrap(raw) {
  let v = raw;
  for (let i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  if (v?.result?.configuration?.markup) v = v.result.configuration.markup;
  else if (v?.result?.markup) v = v.result.markup;
  else if (v && !v.components && typeof v.markup === 'string') v = v.markup;
  for (let i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  if (Array.isArray(v)) v = { components: v, formSettings: {} };
  return v;
}

/** Replace comments and string/template text with spaces (same length) so regexes only see code. `${}` bodies stay. */
function maskNonCode(src) {
  const out = src.split('');
  const stack = []; // template literal nesting: each entry = brace depth inside ${ }
  let i = 0;
  const blank = (a, b) => { for (let k = a; k < b; k++) if (out[k] !== '\n') out[k] = ' '; };
  while (i < src.length) {
    const c = src[i]; const n = src[i + 1];
    if (c === '/' && n === '/') { let j = i; while (j < src.length && src[j] !== '\n') j++; blank(i, j); i = j; continue; }
    if (c === '/' && n === '*') { let j = src.indexOf('*/', i + 2); j = j < 0 ? src.length : j + 2; blank(i, j); i = j; continue; }
    if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < src.length && src[j] !== c && src[j] !== '\n') j += src[j] === '\\' ? 2 : 1;
      blank(i + 1, Math.min(j, src.length)); i = j + 1; continue;
    }
    if (c === '`') {
      let j = i + 1;
      while (j < src.length && src[j] !== '`') {
        if (src[j] === '\\') { blank(j, j + 2); j += 2; continue; }
        if (src[j] === '$' && src[j + 1] === '{') { // code island: find matching }
          let d = 1; let k = j + 2;
          while (k < src.length && d > 0) { if (src[k] === '{') d++; else if (src[k] === '}') d--; k++; }
          const inner = maskNonCode(src.slice(j + 2, k - 1));
          for (let q = 0; q < inner.length; q++) out[j + 2 + q] = inner[q];
          j = k; continue;
        }
        blank(j, j + 1); j++;
      }
      i = j + 1; continue;
    }
    i++;
  }
  void stack;
  return out.join('');
}

// ---- N1: unsafe chains ----------------------------------------------------------------------------------
// root -> number of leading hops that may use a plain '.' (the root object itself is always defined)
const ROOTS = { 'form.data': 1, 'page.state': 1, data: 1, contexts: 1, initialValues: 1, parentFormValues: 1, query: 1, selectedRow: 0 };
const ROOT_RE = /(?<![\w$.])(form\.data|page\.state|data|contexts|initialValues|parentFormValues|query|selectedRow)(?![\w$])/g;
const shadowed = (masked, root) => {
  const r = root.split('.')[0];
  return new RegExp(`\\b(?:const|let|var)\\s+${r}\\b|\\bfunction\\b[^({]*\\([^)]*\\b${r}\\b|\\(\\s*[^)]*\\b${r}\\b[^)]*\\)\\s*=>|(?<![\\w$.])${r}\\s*=>|\\{[^{}]*\\b${r}\\b[^{}]*\\}\\s*=\\s*`).test(masked);
};
/** returns [{start,end,text,inserts:[positions of '?']}] for chains with an unguarded hop */
function findUnsafeChains(src) {
  const masked = maskNonCode(src);
  const found = [];
  for (const m of masked.matchAll(ROOT_RE)) {
    const root = m[1];
    if (shadowed(masked, root)) continue;
    let p = m.index + m[0].length;
    const hops = [];
    for (;;) {
      let q = p;
      while (/\s/.test(masked[q] ?? '')) q++;
      let optional = false;
      if (masked[q] === '?' && masked[q + 1] === '.') { optional = true; q += 2; while (/\s/.test(masked[q] ?? '')) q++; }
      else if (masked[q] === '.') { q += 1; while (/\s/.test(masked[q] ?? '')) q++; }
      else if (masked[q] === '[') { /* bracket hop without '.' */ }
      else break;
      if (masked[q] === '[') {
        let d = 0; let k = q;
        for (; k < masked.length; k++) { if (masked[k] === '[') d++; else if (masked[k] === ']' && --d === 0) break; }
        if (k >= masked.length) break;
        hops.push({ optional, at: optional ? q - 2 : q, bracket: true, opPos: q });
        p = k + 1; continue;
      }
      const id = /^[A-Za-z_$][\w$]*/.exec(masked.slice(q));
      if (!id) break;
      hops.push({ optional, at: optional ? q - 2 : q - 1, bracket: false, opPos: q - 1 });
      p = q + id[0].length;
    }
    if (!hops.length) continue;
    const tail = masked.slice(p, p + 4);
    if (/^\s*(=(?!=)|\+=|-=|\*=|\/=|\+\+|--)/.test(tail) || /(\+\+|--|delete)\s*$/.test(masked.slice(Math.max(0, m.index - 8), m.index))) continue; // assignment target
    const safe = ROOTS[root];
    const bad = hops.map((h, idx) => ({ ...h, idx })).filter((h) => h.idx >= safe && !h.optional);
    if (!bad.length) continue;
    found.push({ start: m.index, end: p, text: src.slice(m.index, p).replace(/\s+/g, ' ').slice(0, 80), inserts: bad.map((h) => (h.bracket ? h.opPos : h.opPos)), bracketAt: bad.filter((h) => h.bracket).map((h) => h.opPos) });
  }
  return found;
}
function applyOptionalChaining(src, chains) {
  const ins = new Map(); // position -> text to insert
  for (const c of chains) for (const pos of c.inserts) ins.set(pos, c.bracketAt.includes(pos) ? '?.' : '?');
  let out = src;
  for (const pos of [...ins.keys()].sort((a, b) => b - a)) out = out.slice(0, pos) + ins.get(pos) + out.slice(pos);
  return out;
}

// ---- N5: legacy scripting names ---------------------------------------------------------------------------
const LEGACY = [
  { id: 'pageContext', re: /(?<![\w$.])pageContext\b/g, to: 'page.state', safe: true },
  { id: 'fileSaver', re: /(?<![\w$.])fileSaver\s*\(/g, to: 'utils.saveAs(', safe: true },
  { id: 'http', re: /(?<![\w$.])http\.(get|post|put|patch|delete|request)\b/g, to: 'actions.callApi.<verb>', safe: false },
  { id: 'message', re: /(?<![\w$.])message\.(success|error|warning|info|loading|open|destroy)\b/g, to: 'actions.showMessage.<level>', safe: false },
  { id: 'modal.showForm', re: /(?<![\w$.])(?:utils\.)?modal\.showForm\b/g, to: 'actions.showDialog', safe: false },
  { id: 'modal.confirm', re: /(?<![\w$.])(?:utils\.)?modal\.confirm\b/g, to: 'actions.showConfirmation', safe: false },
  { id: 'moment', re: /(?<![\w$.])moment(?=\s*[(.])/g, to: 'utils.moment', safe: false },
  { id: 'globalState', re: /(?<![\w$.])(globalState|setGlobalState)\b/g, to: 'page.state / a named data context (migrate every reader and writer together)', safe: false },
  { id: 'selectedRow', re: /(?<![\w$.])selectedRow\b/g, to: 'components.<table>.selectedRow or a data-table data context', safe: false },
  { id: 'formData', re: /(?<![\w$.])formData\b/g, to: 'form.data', safe: false },
  { id: 'setFormData', re: /(?<![\w$.])setFormData\b/g, to: 'form.setFormData', safe: false },
  { id: 'formMode', re: /(?<![\w$.])formMode\b/g, to: 'form.formMode', safe: false },
  { id: 'application.user', re: /(?<![\w$.])application\.user\b/g, to: 'user', safe: false },
  { id: 'application.navigator', re: /(?<![\w$.])application\.navigator\.(navigateToUrl|navigateToForm|getFormUrl|prepareUrl)\b/g, to: 'actions.navigateToUrl/navigateToForm, utils.getFormUrl/prepareUrl', safe: false },
  { id: 'evaluateString', re: /(?<![\w$.])evaluateString\s*\(/g, to: 'utils.evaluateString(', safe: false },
];

// ---- N3 hints ---------------------------------------------------------------------------------------------
const REPLACEMENT_HINT = {
  datatableContext: 'dataContext (auto-migrated on load)', list: 'datalist', title: 'text', paragraph: 'text',
  passwordCombo: 'two textField components (auto-migrated on load)', divider: 'see KB entry (sectionSeparator for headed separators)',
};

// ---- scan -------------------------------------------------------------------------------------------------
const SCRIPT_KEY = /^(on[A-Z]\w*|customVisibility|customEnabled|renderer|expression|style|wrapperStyle|preparedValues|getData|postData|customValidators)$/;
const looksLikeCode = (s) => typeof s === 'string' && s.trim() !== '' && !/^\s*[{<[]/.test(s) && !/^\s*\/[\w-]/.test(s) && /[;=(]|return|=>/.test(s);
const NOT_COMPONENT_TYPES = new Set(['item', 'group']); // button-group items, not form components

function scanMarkup(markup, fileLabel) {
  const findings = [];
  const fixes = [];
  const add = (id, sev, fixable, ptr, comp, msg) => findings.push({ id, sev, fixable, ptr, component: comp ? `${comp.componentName ?? comp.propertyName ?? comp.id} (${comp.type})` : null, message: msg });
  const fixed = FIX ? structuredClone(markup) : null;
  const fixedByPtr = (ptr) => ptr.split('/').filter(Boolean).reduce((o, k) => o?.[k], fixed);

  // ---- form settings
  const fs0 = markup.formSettings ?? {};
  for (const k of Object.keys(fs0)) {
    if (k.startsWith('_') || k.startsWith('shesha:')) continue;
    if (!formSettingsNames.has(k)) {
      add('D2', 'warn', DEAD_ALL, `/formSettings/${k}`, null, `dead formSettings property "${k}"${DEAD_ALL ? '' : ' (reported only; --dead-all removes it)'}`);
      if (FIX && DEAD_ALL) delete fixed.formSettings[k];
    }
  }
  for (const [k, v] of Object.entries(fs0)) {
    if (typeof v === 'string' && /^on[A-Z]/.test(k) && v.trim()) scanScript(v, `/formSettings/${k}`, null, false, (nv) => { if (FIX) fixed.formSettings[k] = nv; });
  }

  // ---- script scanning (shared by components and formSettings)
  function scanScript(code, ptr, comp, renderTime, apply) {
    const err = parses(code);
    if (err) { add('S1', 'error', false, ptr, comp, `script does not parse as an async function body: ${err}`); return; }
    if (renderTime) {
      const chains = findUnsafeChains(code);
      if (chains.length) {
        let note = `unguarded chain "${chains[0].text}"${chains.length > 1 ? ` (+${chains.length - 1} more)` : ''}: a throw here is swallowed and a throwing visibility means VISIBLE`;
        let ok = false;
        if (FIX) {
          const next = applyOptionalChaining(code, chains);
          const e2 = parses(next);
          if (!e2 && findUnsafeChains(next).length === 0) { apply(next); ok = true; code = next; } else note += ' [auto-fix rejected: result did not parse/converge]';
        }
        add('N1', 'warn', ok || !FIX, ptr, comp, note);
      }
    }
    const masked = maskNonCode(code);
    for (const L of LEGACY) {
      L.re.lastIndex = 0;
      if (!L.re.test(masked)) continue;
      if (L.safe && FIX_LEGACY && FIX && !new RegExp(`\\b(?:const|let|var)\\s+${L.id}\\b`).test(masked)) {
        const rewritten = rewriteTokens(code, masked, L);
        if (!parses(rewritten)) { apply(rewritten); code = rewritten; add('N5', 'info', true, ptr, comp, `legacy name "${L.id}" rewritten to ${L.to}`); continue; }
      }
      add('N5', 'info', false, ptr, comp, `legacy scripting name "${L.id}" (still resolves on 0.46) -> ${L.to}`);
    }
    if (/ReferenceList\/GetItems/.test(code)) add('N7', 'error', false, ptr, comp, 'ReferenceList/GetItems is gone (404): use ConfigurationItem/GetCurrent?ItemType=reference-list&Module=&Name= (items under result.configuration) or a dropdown with a reference-list data source');
  }
  function rewriteTokens(code, masked, L) {
    const edits = [];
    L.re.lastIndex = 0;
    for (const m of masked.matchAll(L.re)) edits.push({ s: m.index, e: m.index + m[0].length, t: m[0].replace(L.re, L.to) });
    let out = code;
    for (const e of edits.sort((a, b) => b.s - a.s)) out = out.slice(0, e.s) + e.t + out.slice(e.e);
    return out;
  }

  // ---- component walk
  function walk(node, ptr, owner, ancestors) {
    if (Array.isArray(node)) { node.forEach((x, i) => walk(x, `${ptr}/${i}`, owner, ancestors)); return; }
    if (!isObj(node)) return;
    let comp = owner; let anc = ancestors;
    if (isComp(node)) { comp = node; anc = [...ancestors, node]; if (!NOT_COMPONENT_TYPES.has(node.type)) checkComponent(node, ptr, anc); }
    for (const [k, v] of Object.entries(node)) {
      if (typeof v === 'string') {
        if (/ReferenceList\/GetItems/.test(v) && !(isObj(node) && node._mode === 'code')) {
          if (!SCRIPT_KEY.test(k)) add('N7', 'error', false, `${ptr}/${k}`, comp, 'ReferenceList/GetItems is gone (404)');
        }
        if (comp && SCRIPT_KEY.test(k) && looksLikeCode(v)) {
          const renderKey = /^(customVisibility|customEnabled|renderer|style|wrapperStyle)$/.test(k);
          scanScript(v, `${ptr}/${k}`, comp, renderKey, (nv) => { const t = FIX ? fixedByPtr(ptr) : null; if (t) t[k] = nv; });
        }
        if (/ant-tabs-(content-holder|tabpane)|ant-collapse-content-box/.test(v)) add('N9', 'warn', false, `${ptr}/${k}`, comp, 'selector uses pre-antd-6 tabs/collapse DOM (.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content, .ant-collapse-body); prefer [data-sha-c-name="..."] anchors');
      } else if (isObj(v) && v._mode === 'code' && typeof v._code === 'string' && v._code.trim()) {
        scanScript(v._code, `${ptr}/${k}/_code`, comp, true, (nv) => { const t = FIX ? fixedByPtr(`${ptr}/${k}`) : null; if (t) t._code = nv; });
        if (k === 'editMode' && /return\s+(true|false)\b/.test(v._code)) add('N8', 'warn', false, `${ptr}/${k}`, comp, "editMode script returns a boolean; false now means DISABLED (not read-only). Return 'editable' | 'readOnly' | 'disabled' | 'inherited'");
      } else if (v && typeof v === 'object') {
        walk(v, `${ptr}/${k}`, comp, anc);
      }
    }
  }

  function checkComponent(c, ptr, anc) {
    const entry = compEntry(c.type);
    const meta = INDEX.meta?.[c.type];
    // N3
    if (!entry) add('N3', 'warn', false, ptr, c, `type "${c.type}" is not a 0.46 core component (custom/unregistered/removed): not cleaned, check the module that provides it`);
    else if (meta?.deprecated || meta?.hidden) add('N3', 'warn', false, ptr, c, `${meta.deprecated ? 'deprecated' : 'hidden'} component "${c.type}"${REPLACEMENT_HINT[c.type] ? ` -> ${REPLACEMENT_HINT[c.type]}` : ''}: do not author new ones`);
    // D1
    if (entry) {
      const own = new Set(entry.props.map((p) => p.name));
      const legacy = new Set([...(entry.legacy ?? []), ...legacyBase]);
      const current = meta?.version ?? null;
      for (const k of Object.keys(c)) {
        if (k.startsWith('_') || k.startsWith('shesha:') || STRUCTURAL.has(k) || baseNames.has(k) || own.has(k)) continue;
        const stale = current === null || typeof c.version !== 'number' || c.version < current;
        if (stale && !DEAD_ALL) {
          // below the current version the migrator may still read the key: never remove, only report
          add('D1-STALE', 'info', false, `${ptr}/${k}`, c, `unrecognised property "${k}"${legacy.has(k) ? ' (known legacy key)' : ''}; component is at version ${c.version ?? 'none'} < ${current}: left alone, re-save in the 0.46 designer or run with --dead-all`);
          continue;
        }
        add('D1', 'warn', true, `${ptr}/${k}`, c, `dead property "${k}"${legacy.has(k) ? ' (legacy key on a component already at the current version)' : ''}`);
        if (FIX) delete fixedByPtr(ptr)[k];
      }
    }
    // N2
    if (c.type === 'htmlRender') {
      const code = isObj(c.renderer) ? c.renderer._code ?? '' : String(c.renderer ?? '');
      const body = `${c.html ?? ''}${code}`;
      if (/<style/i.test(body) && c.sanitize !== false) {
        add('N2', 'warn', true, ptr, c, 'htmlRender carries <style> but sanitize is not false: DOMPurify drops a leading <style> (CSS lost, placeholder shown)');
        if (FIX) fixedByPtr(ptr).sanitize = false;
      }
      if (c.contentType === 'html' && !String(c.html ?? '').trim()) add('N2', 'warn', false, ptr, c, "contentType 'html' with no html property: the renderer script is ignored");
      const stripped = body.replace(/<style[\s\S]*?<\/style>/gi, '');
      if (!body.trim()) add('N2', 'warn', false, ptr, c, 'empty htmlRender renders the "Please, provide some content" placeholder');
      else if (/<style/i.test(body) && !/<[a-z]/i.test(stripped)) add('N2', 'info', false, ptr, c, 'style-only htmlRender: emit at least <div></div> after the <style> so the placeholder never shows, and keep the carrier mounted and collapsed');
      if (c.hidden === true || c.visible === false) add('N2', 'warn', false, ptr, c, 'hidden htmlRender is never mounted in 0.46, its CSS cannot inject: keep it visible and collapse it (height 0, overflow hidden)');
    }
    // N4
    if (meta?.perDevice) {
      const parseBox = (s) => { try { const o = JSON.parse(s); return isObj(o) ? Object.fromEntries(Object.entries(o).filter(([k, v]) => k !== '_type' && v !== '' && v != null)) : {}; } catch { return {}; } };
      const hasKeys = (o) => isObj(o) && Object.keys(o).some((k) => k !== '_type');
      const target = FIX ? fixedByPtr(ptr) : null;
      if (typeof c.stylingBox === 'string' && Object.keys(parseBox(c.stylingBox)).length && !hasKeys(c.desktop?.stylingBoxJson)) {
        add('N4', 'warn', true, `${ptr}/stylingBox`, c, `per-device component keeps spacing only in the legacy stylingBox string (${c.stylingBox.slice(0, 60)}); 0.46 reads desktop.stylingBoxJson`);
        if (FIX) { target.desktop = { ...(target.desktop ?? {}), stylingBoxJson: { _type: 'styleBox', ...parseBox(c.stylingBox) } }; }
      }
      for (const bp of ['desktop', 'tablet', 'mobile']) {
        const blk = c[bp];
        if (isObj(blk) && typeof blk.stylingBox === 'string' && Object.keys(parseBox(blk.stylingBox)).length && !hasKeys(blk.stylingBoxJson)) {
          add('N4', 'warn', true, `${ptr}/${bp}/stylingBox`, c, `${bp}.stylingBox string without ${bp}.stylingBoxJson (spacing ignored)`);
          if (FIX) target[bp] = { ...target[bp], stylingBoxJson: { _type: 'styleBox', ...parseBox(blk.stylingBox) } };
        }
        if (isObj(blk) && typeof blk.stylingBoxJson === 'string') add('N4', 'warn', false, `${ptr}/${bp}/stylingBoxJson`, c, 'stylingBoxJson must be an object { _type: "styleBox", ... }, not a string');
      }
      if (typeof c.stylingBoxJson === 'string') add('N4', 'warn', false, `${ptr}/stylingBoxJson`, c, 'stylingBoxJson must be an object');
    }
    // N6
    if (c.type === 'subForm') {
      const span = c.hideLabel === true ? 0 : Number(c.labelCol?.span ?? c.labelCol ?? 0);
      if (!(span > 0)) add('N6', 'warn', false, ptr, c, `subForm effective label span is 0 (hideLabel=${c.hideLabel}, labelCol=${JSON.stringify(c.labelCol ?? null)}): hosted field labels are hidden. Workaround: labelCol 8, wrapperCol 16 and hideLabel false (check the hosted form really wants labels)`);
    }
    // N8 (plain value)
    if (c.editMode === false) add('N8', 'warn', false, ptr, c, "editMode false now means DISABLED (0.43: read-only): use 'readOnly'");
    void anc;
  }

  walk(markup.components ?? [], '/components', null, []);
  return { findings, fixed };
}

// ---- main --------------------------------------------------------------------------------------------------
const files = fs.statSync(target).isDirectory() ? fs.readdirSync(target).filter((f) => f.endsWith('.json')).map((f) => path.join(target, f)) : [target];
const results = [];
for (const f of files) {
  let markup;
  try { markup = unwrap(fs.readFileSync(f, 'utf8')); } catch (e) { console.error(`scan-046: cannot read ${f}: ${e.message}`); process.exit(2); }
  if (!markup || !Array.isArray(markup.components)) { console.error(`scan-046: ${f} has no components array`); process.exit(2); }
  const { findings, fixed } = scanMarkup(markup, f);
  let written = null;
  if (FIX && fixed && findings.some((x) => x.fixable)) {
    fs.mkdirSync(OUT, { recursive: true });
    written = path.join(OUT, path.basename(f).replace(/\.json$/, '') + '.cleaned.json');
    fs.writeFileSync(written, JSON.stringify(fixed, null, 2));
  }
  results.push({ file: f, findings, written });
}
const total = results.reduce((n, r) => n + r.findings.length, 0);
if (JSON_OUT) console.log(JSON.stringify(results, null, 2));
else {
  for (const r of results) {
    console.log(`${r.file}: ${r.findings.length} finding(s)${r.written ? `  -> ${r.written}` : ''}`);
    for (const x of r.findings) console.log(`  [${x.id}${x.fixable ? ' FIXABLE' : ''}] ${x.ptr} ${x.component ? `(${x.component}) ` : ''}${x.message}`);
  }
}
process.exit(total ? 1 : 0);
