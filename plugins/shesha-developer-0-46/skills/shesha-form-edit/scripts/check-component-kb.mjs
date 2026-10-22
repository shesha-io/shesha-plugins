#!/usr/bin/env node
/*
 * check-component-kb.mjs - acceptance gate for assets/components-kb.
 *
 * Usage:
 *   node scripts/check-component-kb.mjs --versions <component-versions.json> [--kb <dir>] [--min 115]
 *
 * Checks (exit 1 on any failure):
 *   1. _meta.json.componentCount >= --min (default 115) and equals the number of <type>.json files
 *   2. every type in component-versions.json is present in _index.json, or is documented in
 *      _gaps.json (entry with that `type` and a reason)
 *   3. for every type present in both, version === currentVersion
 *   4. every present component records reworked (bool), customContainerNames (array|null) and renderImpact (array)
 *   5. _meta.json names sourceBranch and commit
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const kbDir = path.resolve(opt('--kb', path.join(here, '..', 'assets', 'components-kb')));
const versionsFile = opt('--versions');
const min = Number(opt('--min', '115'));
if (!versionsFile) { console.error('Usage: node check-component-kb.mjs --versions <component-versions.json> [--kb <dir>] [--min 115]'); process.exit(2); }

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const meta = readJson(path.join(kbDir, '_meta.json'));
const index = readJson(path.join(kbDir, '_index.json'));
const gaps = readJson(path.join(kbDir, '_gaps.json'));
const truth = readJson(versionsFile).components;

const failures = [];
const fileCount = fs.readdirSync(kbDir).filter((f) => f.endsWith('.json') && !f.startsWith('_')).length;
console.log(`source: ${meta.sourceBranch} @ ${meta.commit}`);
console.log(`componentCount: meta=${meta.componentCount} index=${Object.keys(index).length} files=${fileCount} (min ${min})`);
if (!(meta.componentCount >= min)) failures.push(`componentCount ${meta.componentCount} < ${min}`);
if (meta.componentCount !== Object.keys(index).length || fileCount !== Object.keys(index).length) failures.push('componentCount / _index / file count disagree');
if (!meta.sourceBranch || !meta.commit) failures.push('_meta.json is missing sourceBranch or commit');

const documented = new Set(gaps.filter((g) => g.type && g.reason).map((g) => g.type));
let missing = 0;
let versionChecked = 0;
let versionMismatch = 0;
for (const c of truth) {
  const e = index[c.type];
  if (!e) {
    if (documented.has(c.type)) { console.log(`  gap (documented): ${c.type}`); continue; }
    missing++;
    failures.push(`missing type ${c.type} (not in _index.json, not documented in _gaps.json)`);
    continue;
  }
  versionChecked++;
  if (e.version !== c.currentVersion) {
    versionMismatch++;
    failures.push(`version mismatch ${c.type}: kb=${e.version} currentVersion=${c.currentVersion}`);
  }
  const k = readJson(path.join(kbDir, e.file));
  if (k.version !== c.currentVersion) failures.push(`${c.type}.json version ${k.version} != ${c.currentVersion}`);
  if (typeof k.reworked !== 'boolean') failures.push(`${c.type}: reworked is not a boolean`);
  else if (k.reworked !== (c.reworked === true)) failures.push(`${c.type}: reworked ${k.reworked} != component-versions.json ${c.reworked}`);
  if (!('customContainerNames' in k)) failures.push(`${c.type}: customContainerNames not recorded`);
  if (!Array.isArray(k.renderImpact)) failures.push(`${c.type}: renderImpact is not an array`);
}
const reworkedCount = Object.values(index).filter((e) => e.reworked).length;
console.log(`types in component-versions.json: ${truth.length}; present: ${truth.length - missing - [...documented].filter((t) => truth.some((c) => c.type === t) && !index[t]).length}; missing undocumented: ${missing}`);
console.log(`version checked: ${versionChecked}; mismatches: ${versionMismatch}; reworked=true in KB: ${reworkedCount}`);

if (failures.length) {
  console.log(`\nFAIL (${failures.length})`);
  for (const f of failures) console.log('  - ' + f);
  process.exit(1);
}
console.log('\nPASS');
