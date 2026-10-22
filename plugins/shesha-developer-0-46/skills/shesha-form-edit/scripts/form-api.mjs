#!/usr/bin/env node
/*
 * form-api.mjs - safe get / backup / push / verify for Shesha 0.46 forms.
 *
 *   BASE_URL=http://localhost:21021 ACCESS_TOKEN=... [RUN_DIR=.claude/shesha/runs/x] node form-api.mjs <cmd> [flags]
 *
 *   get     --module M --name N            GetCurrent; writes backup envelope + staged markup, prints id/modelType/size
 *   push    --module M --name N --edited F [--apply]
 *                                          gates (JSON round trip, script syntax) then, ONLY with --apply, backs up,
 *                                          PUTs UpdateMarkup {id, markup, modelType} (modelType carried forward) and verifies
 *   verify  --module M --name N --edited F independent re-read and compare (modelType, access, markup by component id)
 *
 * Token: ACCESS_TOKEN env or --token-file. Never authenticates (login is rate limited: 10/min).
 * Dry-run is the default for push. No dependencies (Node 18+).
 */
import fs from 'node:fs';
import path from 'node:path';

const argv = process.argv.slice(2);
const cmd = argv[0];
const flag = (n) => { const i = argv.indexOf(`--${n}`); return i > -1 ? argv[i + 1] : undefined; };
const has = (n) => argv.includes(`--${n}`);
const BASE = (process.env.BASE_URL ?? flag('base') ?? 'http://localhost:21021').replace(/\/$/, '');
const RUN = process.env.RUN_DIR ?? '.claude/shesha/runs/adhoc';
const tokenFile = flag('token-file');
const TOKEN = process.env.ACCESS_TOKEN ?? (tokenFile ? fs.readFileSync(tokenFile, 'utf8').trim() : '');
const die = (m, code = 2) => { console.error(`form-api: ${m}`); process.exit(code); };
if (!['get', 'push', 'verify'].includes(cmd)) die('usage: form-api.mjs get|push|verify --module M --name N [--edited F] [--apply]');
if (!TOKEN) die('no ACCESS_TOKEN / --token-file (authenticate once, reuse the token)');
const module = flag('module') ?? '';
const name = flag('name');
if (!name) die('--name is required');

const H = { Authorization: `Bearer ${TOKEN}` };
async function getCurrent() {
  const q = new URLSearchParams({ ItemType: 'form', Module: module, Name: name });
  const r = await fetch(`${BASE}/api/services/app/ConfigurationItem/GetCurrent?${q}`, { headers: H });
  const body = await r.json().catch(() => null);
  if (!r.ok || !body?.success || !body.result?.configuration) {
    die(`GetCurrent ${module}/${name} -> HTTP ${r.status}: ${body?.error?.message ?? 'no configuration in response'}`, 1);
  }
  return body;
}
const stamp = () => new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
function save(rel, text) { const p = path.join(RUN, rel); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, text); return p; }

function stable(o) { return JSON.stringify(o, (k, v) => (v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.keys(v).sort().map((x) => [x, v[x]])) : v)); }
function index(tree) {
  const m = new Map();
  (function w(n) {
    if (Array.isArray(n)) n.forEach(w);
    else if (n && typeof n === 'object') {
      if (typeof n.id === 'string' && typeof n.type === 'string') { const { components, columns, tabs, content, header, ...own } = n; m.set(n.id, stable(own)); }
      Object.values(n).forEach(w);
    }
  })(tree.components ?? []);
  return m;
}
function syntaxProblems(tree) {
  const bad = [];
  (function w(n, ptr) {
    if (Array.isArray(n)) n.forEach((x, i) => w(x, `${ptr}/${i}`));
    else if (n && typeof n === 'object') {
      if (n._mode === 'code' && typeof n._code === 'string') { try { new Function(`return (async function(){\n${n._code}\n})`); } catch (e) { bad.push(`${ptr}: ${e.message}`); } }
      for (const [k, v] of Object.entries(n)) w(v, `${ptr}/${k}`);
    }
  })(tree, '');
  return bad;
}

const cur = await getCurrent();
const cfg = cur.result.configuration;

if (cmd === 'get') {
  const env = save(`backup/${module}.${name}.${stamp()}.envelope.json`, JSON.stringify(cur, null, 2));
  const staged = save(`staged/${name}.current.json`, JSON.stringify(JSON.parse(cfg.markup), null, 2));
  console.log(JSON.stringify({ id: cfg.id, module: cfg.module, name: cfg.name, modelType: cfg.modelType, access: cfg.access, markupChars: cfg.markup.length, backup: env, staged }, null, 2));
  process.exit(0);
}

const editedPath = flag('edited');
if (!editedPath) die('--edited <file.json> is required');
let edited;
try { edited = JSON.parse(fs.readFileSync(editedPath, 'utf8')); } catch (e) { die(`edited file is not valid JSON: ${e.message}`); }
if (typeof edited === 'string') edited = JSON.parse(edited);
if (!Array.isArray(edited.components)) die('edited markup has no components[]');

if (cmd === 'verify') process.exit(report(edited, cfg) ? 0 : 1);

// push
try { JSON.parse(JSON.stringify({ markup: JSON.stringify(edited) })); } catch (e) { die(`JSON round trip failed: ${e.message}`, 1); }
const bad = syntaxProblems(edited);
if (bad.length) { console.error(`script syntax gate FAILED (${bad.length}):\n  ${bad.join('\n  ')}`); process.exit(1); }
const before = index(JSON.parse(cfg.markup)); const after = index(edited);
const added = [...after.keys()].filter((k) => !before.has(k)).length;
const removed = [...before.keys()].filter((k) => !after.has(k)).length;
const changed = [...after.keys()].filter((k) => before.has(k) && before.get(k) !== after.get(k)).length;
console.log(`plan: ${added} added, ${removed} removed, ${changed} changed components; modelType carried forward: ${cfg.modelType ?? '(none)'}; access ${cfg.access}`);
if (!has('apply')) { console.log('dry run (no --apply): nothing written.'); process.exit(0); }

const backup = save(`backup/${module}.${name}.${stamp()}.envelope.json`, JSON.stringify(cur, null, 2));
console.log(`backup: ${backup}`);
const body = { id: cfg.id, markup: JSON.stringify(edited), modelType: cfg.modelType ?? null };
if (cfg.access > 2) { body.access = cfg.access; body.permissions = cfg.permissions ?? []; }
const r = await fetch(`${BASE}/api/services/Shesha/FormConfiguration/UpdateMarkup`, { method: 'PUT', headers: { ...H, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const res = await r.json().catch(() => null);
if (!r.ok || !res?.success) die(`UpdateMarkup -> HTTP ${r.status}: ${res?.error?.message ?? ''} ${res?.error?.details ?? ''}`, 1);
console.log('UpdateMarkup accepted (HTTP 200) - this is NOT proof; verifying by independent read...');
const fresh = (await getCurrent()).result.configuration;
process.exit(report(edited, fresh, cfg) ? 0 : 1);

function report(sent, got, prev) {
  let ok = true;
  const sentIdx = index(sent); const gotIdx = index(JSON.parse(got.markup));
  const missing = [...sentIdx.keys()].filter((k) => !gotIdx.has(k));
  const extra = [...gotIdx.keys()].filter((k) => !sentIdx.has(k));
  const diff = [...sentIdx.keys()].filter((k) => gotIdx.has(k) && gotIdx.get(k) !== sentIdx.get(k));
  if (prev && got.modelType !== prev.modelType) { ok = false; console.error(`FAIL modelType changed: ${prev.modelType} -> ${got.modelType}`); }
  if (prev && got.access !== prev.access) { ok = false; console.error(`FAIL access changed: ${prev.access} -> ${got.access}`); }
  if (missing.length || extra.length || diff.length) { ok = false; console.error(`FAIL markup differs: ${missing.length} missing, ${extra.length} unexpected, ${diff.length} changed (first: ${[...missing, ...extra, ...diff].slice(0, 5).join(', ')})`); }
  console.log(ok ? `VERIFIED: read-back matches (${sentIdx.size} components, modelType ${got.modelType ?? '(none)'}, access ${got.access}). Clear the portal IndexedDB cache before judging the render.` : 'NOT VERIFIED - restore from the backup envelope if the form is broken.');
  return ok;
}
