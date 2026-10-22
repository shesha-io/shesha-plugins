/* Negative test: inject one bug per family into a COPY of the plugin and assert
 * check-references catches each. Proves the gate fails when it should — the
 * property that matters, and the one a green run can never demonstrate. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Defaults resolve from THIS FILE, not the caller's cwd, and the scratch tree goes
// to the OS temp dir so it can never land inside the tree being copied.
const HERE = path.dirname(fileURLToPath(import.meta.url)); // …/shesha-form-edit/tests
const DEFAULT_SRC = path.resolve(HERE, '..', '..', '..'); // …/plugins/shesha-developer
const DEFAULT_TMP = path.join(os.tmpdir(), 'shesha-check-references-negative');

// SRC = the real plugin dir; REPO = its repo root (marketplace + sibling plugins).
// The copy must reproduce that layout, or the checker sees no marketplace and
// correctly declines to judge cross-plugin skill ids.
const SRC = path.resolve(process.argv[2] ?? DEFAULT_SRC);
const TMP = path.resolve(process.argv[3] ?? DEFAULT_TMP);
const REPO = path.resolve(SRC, '..', '..');
const PLUGIN = path.join(TMP, 'plugins', path.basename(SRC));

function reset() {
  fs.rmSync(TMP, { recursive: true, force: true });
  fs.mkdirSync(path.join(TMP, 'plugins'), { recursive: true });
  fs.cpSync(path.join(REPO, '.claude-plugin'), path.join(TMP, '.claude-plugin'), { recursive: true });
  for (const p of fs.readdirSync(path.join(REPO, 'plugins'))) {
    // Sibling plugins only need their skills/ listing, not their contents.
    const src = path.join(REPO, 'plugins', p);
    if (p === path.basename(SRC)) fs.cpSync(src, PLUGIN, { recursive: true });
    else if (fs.existsSync(path.join(src, 'skills')))
      for (const s of fs.readdirSync(path.join(src, 'skills')))
        fs.mkdirSync(path.join(TMP, 'plugins', p, 'skills', s), { recursive: true });
  }
}
reset();

const SCRIPT = path.join(PLUGIN, 'skills', 'shesha-form-edit', 'scripts', 'check-references.mjs');
const f = (...p) => path.join(PLUGIN, ...p);
const edit = (file, from, to) => {
  const t = fs.readFileSync(file, 'utf8');
  if (!t.includes(from)) throw new Error(`fixture anchor not found in ${file}: ${from}`);
  fs.writeFileSync(file, t.replace(from, to));
};

const cases = [
  ['links', () => edit(f('skills/shesha-form-edit/references/block-library.md'), '](archetypes.md)', '](archetypes-GONE.md)')],
  ['paths', () => edit(f('skills/shesha-form-edit/SKILL.md'), '`assets/components-kb/_index.json`', '`assets/components-kb/_index-GONE.json`')],
  ['skills', () => edit(f('skills/shesha-form-edit/SKILL.md'), 'Skill(skill="shesha-developer:domain-model"', 'Skill(skill="superpowers:writing-plans"')],
  ['agents', () => edit(f('skills/shesha-form-edit/SKILL.md'), '`shesha-developer-0-46:form-author` per form', '`shesha-developer:ghost-agent` agent')],
  ['roles', () => edit(f('skills/shesha-design-system/assets/block-styles/meta-strip.style.json'), '$role:bodyInk', '$role:nonexistentRole')],
  ['overlays', () => edit(f('skills/shesha-form-edit/assets/blocks/status-pill.block.json'), '"$styleOverlay": "status-pill"', '"$styleOverlay": "status-pill-GONE"')],
  ['versions', () => edit(f('skills/shesha-form-edit/references/component-cheatsheet.md'), '| `dropdown` | 11 |', '| `dropdown` | 7 |')],
  ['groups', () => edit(f('skills/clean-form-config/assets/groups/index.json'), '"alert":', '"ghostType": "data-display",\n    "alert":')],
];

const run = () => {
  try {
    return { code: 0, out: execFileSync(process.execPath, [SCRIPT, '--root', PLUGIN, '--json'], { encoding: 'utf8' }) };
  } catch (e) {
    return { code: e.status, out: e.stdout ?? '' };
  }
};

const base = run();
if (base.code !== 0) {
  console.log(`  BASELINE NOT CLEAN (exit ${base.code}) — fix that before trusting this test`);
  process.exit(2);
}
console.log('  baseline copy: PASS\n');

let bad = 0;
for (const [family, inject] of cases) {
  reset();
  inject();
  const r = run();
  const j = r.out ? JSON.parse(r.out.replace(/^﻿/, '')) : { families: [] };
  const hits = (j.families.find((x) => x.name === family)?.failures ?? []).length;
  const ok = r.code === 1 && hits > 0;
  if (!ok) bad++;
  console.log(`  ${ok ? 'caught  ' : 'MISSED  '} ${family.padEnd(9)} exit=${r.code}  ${family} failures=${hits}`);
}

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`\n  ${cases.length - bad}/${cases.length} bug classes caught`);
process.exit(bad ? 1 : 0);
