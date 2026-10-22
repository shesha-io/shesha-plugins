#!/usr/bin/env node
/*
 * scan-hazards.mjs - run the references/render-hazards-046.md detectors over stored form markup.
 *
 *   node scan-hazards.mjs <file.json | dir> [--json] [--syntax]
 *
 * Accepts: raw markup ({components, formSettings}), a stringified markup, or an API envelope
 * ({result:{configuration:{markup}}} / {result:{markup}} / {markup}).
 * --syntax additionally syntax-checks every code-mode setting (`_code`) and formSettings script.
 * Exit: 0 clean, 1 findings, 2 could not run.   No dependencies.
 * A finding is a hypothesis - confirm in the browser before rewriting a working form.
 */
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const target = args.find((a) => !a.startsWith('--'));
const JSON_OUT = args.includes('--json');
const SYNTAX = args.includes('--syntax');
if (!target || !fs.existsSync(target)) {
  console.error('usage: scan-hazards.mjs <file.json|dir> [--json] [--syntax]');
  process.exit(2);
}

const files = fs.statSync(target).isDirectory()
  ? fs.readdirSync(target).filter((f) => f.endsWith('.json')).map((f) => path.join(target, f))
  : [target];

function unwrap(raw) {
  let v = raw;
  for (let i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  if (v?.result?.configuration?.markup) v = v.result.configuration.markup;
  else if (v?.result?.markup) v = v.result.markup;
  else if (v && !v.components && typeof v.markup === 'string') v = v.markup;
  for (let i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  return v;
}

const isComp = (o) => o && typeof o === 'object' && !Array.isArray(o) && typeof o.type === 'string' && typeof o.id === 'string';
const codeOf = (s) => (s && typeof s === 'object' && s._mode === 'code' ? s._code : typeof s === 'string' ? s : undefined);

function* walk(node, ptr = '', ancestors = []) {
  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i++) yield* walk(node[i], `${ptr}/${i}`, ancestors);
  } else if (node && typeof node === 'object') {
    const comp = isComp(node);
    if (comp) yield { comp: node, ptr, ancestors };
    const next = comp ? [...ancestors, node] : ancestors;
    for (const [k, v] of Object.entries(node)) if (v && typeof v === 'object') yield* walk(v, `${ptr}/${k}`, next);
  }
}

// every script owned by this component: {_mode:'code',_code} objects anywhere, plus plain-string scripts under
// known keys (renderer, style, expression, on*). Does not descend into child components (they are scanned on their own).
const SCRIPT_KEY = /^(renderer|style|wrapperStyle|expression|customVisibility|customEnabled|on[A-Z]w*)$/;
function* codeSettings(obj, ptr = '', top = true) {
  if (!obj || typeof obj !== 'object') return;
  if (!top && isComp(obj)) return;
  if (Array.isArray(obj)) { for (let i = 0; i < obj.length; i++) yield* codeSettings(obj[i], `${ptr}/${i}`, false); return; }
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string' && SCRIPT_KEY.test(k) && v.trim() && !/^s*[{<]/.test(v)) yield { ptr: `${ptr}/${k}`, code: v };
    else if (v && typeof v === 'object') {
      if (!Array.isArray(v) && v._mode === 'code' && typeof v._code === 'string') yield { ptr: `${ptr}/${k}`, code: v._code };
      else yield* codeSettings(v, `${ptr}/${k}`, false);
    }
  }
}

const unsafeChain = /(?<![\w$.])(data|contexts\.\w+|page\.state)((?:\?\.|\.)\w+)((?:\?\.|\.)\w+)/g;
function hasUnguardedChain(code) {
  const stripped = code.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const m of stripped.matchAll(unsafeChain)) {
    // flag when a hop after the first member is a plain '.' (not '?.') and the match is a read
    const tail = stripped.slice(m.index + m[0].length, m.index + m[0].length + 3);
    const isAssign = /^\s*=[^=]/.test(tail);
    if (!isAssign && (m[2].startsWith('.') || m[3].startsWith('.')) && !(m[2].startsWith('?.') && m[3].startsWith('?.'))) return m[0];
  }
  return null;
}

function syntaxError(code) {
  try {
    // eslint-disable-next-line no-new-func
    new Function(`return (async function(){\n${code}\n})`);
    return null;
  } catch (e) {
    return e.message;
  }
}

function scan(markup) {
  const out = [];
  const add = (id, ptr, comp, msg) => out.push({ id, ptr, component: comp?.componentName ?? comp?.type, message: msg });

  const settings = markup?.formSettings ?? {};
  for (const [k, v] of Object.entries(settings)) {
    const code = typeof v === 'string' && /^on[A-Z]/.test(k) ? v : codeOf(v);
    if (SYNTAX && typeof code === 'string' && code.trim()) {
      const err = syntaxError(code);
      if (err) add('syntax', `/formSettings/${k}`, null, err);
    }
  }
  if (markup?.formSettings && !settings.modelType && settings.dataLoaderType !== 'none') add('H1', '/formSettings/modelType', null, 'entity-bound form without modelType');

  for (const { comp: c, ptr, ancestors } of walk(markup?.components ?? [], '/components')) {
    const label = c;
    if (c.type === 'htmlRender') {
      const body = String(c.renderer ?? c.html ?? '');
      if (/<style/i.test(body) && c.sanitize !== false) add('H3', ptr, label, 'htmlRender carries <style> but sanitize is not false (DOMPurify drops a leading <style>)');
      if (c.contentType === 'html' && !c.html) add('H5', ptr, label, "contentType 'html' with no html property (renderer ignored)");
      const code = codeOf(c.renderer) ?? '';
      if (!String(c.html ?? '').trim() && !code.trim()) add('H4', ptr, label, 'empty htmlRender -> "Please, provide some content" placeholder');
      else if (body && !/<(?!\/?style)[a-z]/i.test(body.replace(/<style[\s\S]*?<\/style>/gi, ''))) add('H4', ptr, label, 'style-only renderer: output is empty if the CSS is sanitised away');
    }
    const hiddenish = c.hidden === true || c.visible === false;
    if (hiddenish) {
      if (c.type === 'htmlRender') add('H6', ptr, label, 'hidden htmlRender is never mounted - its CSS cannot inject');
      else if (c.defaultValue !== undefined || c.initialValue !== undefined) add('H6', ptr, label, 'hidden input with defaultValue/initialValue is not mounted');
    }
    if (c.type === 'tabs' && typeof c.style === 'string' && /counter-?reset/i.test(c.style)) add('H7', ptr, label, 'tabs style counterReset: no longer inline on panes (antd 6 DOM)');
    if (c.type === 'text') {
      if ((c.stylingBox || c.fontSize || c.padding) && !c.desktop?.stylingBoxJson) add('H8', ptr, label, 'legacy text style keys without desktop.stylingBoxJson / desktop.font.size');
      if ((c.version ?? -1) < 7 && c.contentDisplay !== 'name' && /\{\{\s*(data|contexts)\./.test(String(c.content ?? ''))) add('H18', ptr, label, 'text < v7 with {{data.}} content: migration prefixes data. again');
    }
    if (c.type === 'container' && !c.desktop) add('H9', ptr, label, 'container without structured desktop block: style migration will inject minHeight 32px etc.');
    if (c.type === 'subForm') {
      if (!(c.labelCol > 0)) add('H14', ptr, label, 'subForm labelCol is 0/unset: hosted field labels are hidden');
    }
    if (c.type === 'refListStatus' && ancestors.some((a) => a.type === 'subForm')) add('H13', ptr, label, 'refListStatus inside subForm throws "Component with id ... is not found"');
    if (c.editMode === false || (c.editMode?._mode === 'code' && /return\s+(true|false)\b/.test(c.editMode._code ?? ''))) add('H15', ptr, label, 'editMode boolean false means DISABLED in 0.46; return string modes');
    if (c.type === 'columns' && Number(c.gutterX) > 0) add('H16', ptr, label, 'columns gutterX > 0 insets content by gutter/2; use flex containers');
    if (c.type === 'datatable' && (c.striped === undefined || c.hoverHighlight === undefined)) add('H17', ptr, label, 'datatable without explicit striped/hoverHighlight: migrations may force defaults (check version vs KB)');
    if (c.defaultValue !== undefined && typeof c.defaultValue !== 'string') add('migration', ptr, label, 'non-string defaultValue (e.match is not a function)');
    if (c.version === undefined) add('migration', ptr, label, 'component has no integer version (re-runs the whole legacy migration chain)');

    // scripts anywhere in this component's own settings
    for (const { ptr: sp, code } of codeSettings(c, ptr)) {
      const chain = hasUnguardedChain(code);
      if (chain) add('H10', sp, label, `render-time script reads an unguarded chain "${chain}" (use ?. on every hop)`);
      if (/ReferenceList\/GetItems/.test(code)) add('H12', sp, label, 'ReferenceList/GetItems is gone (404)');
      if (/\b(=|\()\s*(data|value)\b[\w.?]*\s*[;)]/.test(code) && /\.(push|splice|sort|reverse)\(/.test(code)) add('H11', sp, label, 'array from data/value is mutated or stored without a copy (.slice())');
      if (SYNTAX) {
        const err = syntaxError(code);
        if (err) add('syntax', sp, label, err);
      }
    }
    for (const [k, v] of Object.entries(c)) {
      if (typeof v === 'string' && /ReferenceList\/GetItems/.test(v)) add('H12', `${ptr}/${k}`, label, 'ReferenceList/GetItems is gone (404)');
      if (typeof v === 'string' && /ant-tabs-(content-holder|tabpane)|ant-collapse-content-box/.test(v)) add('H7', `${ptr}/${k}`, label, 'selector uses pre-antd-6 tabs/collapse DOM');
    }
  }
  return out;
}

const results = [];
for (const f of files) {
  try {
    const markup = unwrap(fs.readFileSync(f, 'utf8'));
    results.push({ file: f, findings: scan(markup) });
  } catch (e) {
    console.error(`scan-hazards: cannot read ${f}: ${e.message}`);
    process.exit(2);
  }
}
const total = results.reduce((n, r) => n + r.findings.length, 0);
if (JSON_OUT) console.log(JSON.stringify(results, null, 2));
else {
  for (const r of results) {
    console.log(`${r.file}: ${r.findings.length} finding(s)`);
    for (const x of r.findings) console.log(`  [${x.id}] ${x.ptr} (${x.component}) ${x.message}`);
  }
}
process.exit(total ? 1 : 0);
