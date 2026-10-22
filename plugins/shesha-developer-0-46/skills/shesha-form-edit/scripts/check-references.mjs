#!/usr/bin/env node
/*
 * check-references.mjs — prove that every pointer in this plugin resolves.
 *
 * Why this exists. A three-way audit of the design pipeline found the same bug
 * class over and over, and each instance was invisible until something forced a
 * look: 12 dead markdown links; an `archetypes.md` that eight files referenced
 * and which did not exist; a `page-header-band.style.json` that a block declared
 * and which lived only in an unregistered folder; `$role:progressAccent` and
 * `$role:addButtonText` defined in no theme, so the renderer received the literal
 * string "$role:…" as a colour; `Skill(skill="playwright")` at six sites naming a
 * skill nobody ships; two `superpowers:*` entries marked MUST that no agent could
 * satisfy; and FOUR hand-maintained component-version lists that had drifted three
 * different ways — one of them telling you to use `numberField` v3, which silently
 * discards the component's entire style block.
 *
 * None of those are subtle once you look. The problem is that looking was a habit
 * rather than a command. This is the command.
 *
 * It follows the coverage contract it exists to enforce
 * (references/verification.md §0): every family reports how many pointers it
 * walked, how many it could evaluate, and what it could not evaluate and why.
 * A family that checked nothing is reported as no-coverage, never as a pass.
 *
 * Families
 *   links     relative markdown links resolve (fence-aware — a regex inside a JS
 *             code block is not a link)
 *   paths     backticked file paths in prose resolve
 *   skills    every Skill(...) / plugin:skill id ships in this marketplace
 *   agents    every dispatched agent name has a definition
 *   roles     every $role: token resolves in EVERY shipped brand, not just the default
 *   overlays  every block's $styleOverlay file exists
 *   versions  every component version quoted in a doc matches components-kb/_index.json
 *   groups    every type in the component index resolves to an entry in its group file
 *
 * Usage
 *   node check-references.mjs                 # defaults to this plugin
 *   node check-references.mjs --root <dir>
 *   node check-references.mjs --json
 *
 * Exit: 0 clean · 1 failures · 2 could not run · 3 partial (something uninspectable)
 * No dependencies.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const argVal = (flag, fallback) => {
  const i = process.argv.indexOf(flag);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
// scripts/ -> shesha-form-edit -> skills -> shesha-developer
const ROOT = path.resolve(argVal('--root', path.join(SCRIPT_DIR, '..', '..', '..')));
const JSON_OUT = process.argv.includes('--json');

if (!fs.existsSync(path.join(ROOT, 'skills'))) {
  console.error(`check-references: no skills/ under ${ROOT} — is --root a plugin directory?`);
  process.exit(2);
}

// ----------------------------------------------------------------- families

/*
 * Three outcomes, deliberately distinct — collapsing them is how a gate becomes noise:
 *   failures      a pointer that should resolve and doesn't
 *   uninspectable a real pointer this script COULD NOT evaluate. Downgrades the
 *                 verdict to `partial`, because "I didn't look" must never print
 *                 the same as "nothing was wrong" (references/verification.md §0).
 *   notApplicable something that matched a pattern but isn't a pointer at all —
 *                 `[text](url)` in a table explaining markdown syntax. Reported for
 *                 transparency, but it does not touch the verdict. A checker that
 *                 permanently reads PARTIAL over prose examples gets muted, and then
 *                 the real findings go with it.
 */
const families = new Map();
function fam(name) {
  if (!families.has(name)) {
    families.set(name, { name, walked: 0, checked: 0, failures: [], uninspectable: [], notApplicable: [] });
  }
  return families.get(name);
}
const fail = (n, where, message) => fam(n).failures.push({ where, message });
const skip = (n, where, reason) => fam(n).uninspectable.push({ where, reason });
const na = (n, where, reason) => fam(n).notApplicable.push({ where, reason });

// -------------------------------------------------------------------- files

function walkFiles(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name === '.git') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walkFiles(p, out);
    else out.push(p);
  }
  return out;
}
const ALL = walkFiles(ROOT);
const MD = ALL.filter((f) => f.endsWith('.md'));
const rel = (p) => path.relative(ROOT, p).replace(/\\/g, '/');

/** Blank out fenced code blocks so their contents can't masquerade as prose. */
function stripFences(text) {
  return text.replace(/^```[\s\S]*?^```/gm, (m) => m.replace(/[^\n]/g, ' '));
}

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));

// ------------------------------------------------------------- 1. md links

const LINKABLE = /\.(md|json|mjs|js|ps1|sh|py)$/;
for (const file of MD) {
  const body = stripFences(fs.readFileSync(file, 'utf8'));
  for (const m of body.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
    const target = m[1].split('#')[0].trim();
    if (!target || /^(https?:|mailto:|#)/.test(target)) continue;
    const f = fam('links');
    f.walked++;
    // Only judge things that actually look like a path: an extension, or a slash.
    if (!LINKABLE.test(target) && !target.includes('/')) {
      na('links', `${rel(file)} -> ${target}`, 'not a file path (prose or a markdown-syntax example)');
      continue;
    }
    f.checked++;
    if (!fs.existsSync(path.resolve(path.dirname(file), target))) {
      fail('links', rel(file), `link target does not exist: ${target}`);
    }
  }
}

// ------------------------------------------- 2. backticked paths in prose

const PATH_RE = /`((?:\.\.\/|\.\/)?(?:assets|references|scripts|tests|skills|agents)\/[A-Za-z0-9._/-]+\.(?:md|json|mjs|js))`/g;
for (const file of MD) {
  const body = stripFences(fs.readFileSync(file, 'utf8'));
  for (const m of body.matchAll(PATH_RE)) {
    const target = m[1];
    const f = fam('paths');
    f.walked++;
    f.checked++;
    // A bare `references/foo.md` in prose is written relative to whichever skill the
    // surrounding sentence is talking about — an agent file means SKILL_ROOT
    // (shesha-form-edit), the designer's README means design-system. Resolving that
    // from text is guesswork, so the check is deliberately weaker than it looks: the
    // file must exist under SOME skill. That still catches the bug class this exists
    // for (a path naming a file that exists nowhere, like the old archetypes.md)
    // without inventing failures for correctly-written cross-skill prose.
    const skillRoots = fs.readdirSync(path.join(ROOT, 'skills')).map((s) => path.join(ROOT, 'skills', s));
    const candidates = [path.resolve(path.dirname(file), target), path.resolve(ROOT, target), ...skillRoots.map((r) => path.resolve(r, target))];
    if (!candidates.some((c) => fs.existsSync(c))) {
      fail('paths', rel(file), `no file at this path under any skill: ${target}`);
    }
  }
}

// ------------------------------------------------------- 3. skill ids

const localSkills = new Set(fs.readdirSync(path.join(ROOT, 'skills')));

// The plugin's own name comes from its manifest, NOT its directory name — a
// renamed or copied checkout would otherwise reject its own skills as unknown.
let thisPlugin = path.basename(ROOT);
const manifest = path.join(ROOT, '.claude-plugin', 'plugin.json');
if (fs.existsSync(manifest)) {
  try {
    thisPlugin = readJson(manifest).name ?? thisPlugin;
  } catch {
    /* fall back to the directory name */
  }
}

// Sibling plugins: prefer the marketplace manifest (authoritative), fall back to
// scanning ../ for plugin directories.
const siblingPlugins = new Map(); // pluginName -> Set(skills) | null when unlistable
const pluginsDir = path.resolve(ROOT, '..');
if (fs.existsSync(pluginsDir)) {
  for (const p of fs.readdirSync(pluginsDir)) {
    const sk = path.join(pluginsDir, p, 'skills');
    if (fs.existsSync(sk)) siblingPlugins.set(p, new Set(fs.readdirSync(sk)));
  }
}
let marketplaceFound = false;
for (let dir = ROOT, i = 0; i < 4; i++, dir = path.dirname(dir)) {
  const mk = path.join(dir, '.claude-plugin', 'marketplace.json');
  if (!fs.existsSync(mk)) continue;
  try {
    for (const p of readJson(mk).plugins ?? []) {
      if (p.name && !siblingPlugins.has(p.name)) siblingPlugins.set(p.name, null); // known, contents unlistable
    }
    marketplaceFound = true;
  } catch {
    /* ignore a malformed marketplace file */
  }
  break;
}

for (const file of MD) {
  const body = stripFences(fs.readFileSync(file, 'utf8'));
  const ids = new Set();
  // Skill(skill="…") is unambiguous.
  for (const m of body.matchAll(/Skill\(\s*skill\s*=\s*["']([^"']+)["']/g)) ids.add(m[1]);
  // A bare `a:b` is only a skill id if `a` looks like a plugin namespace. Without
  // this guard, CSS in prose (`flex:1`, `overflow:auto`, `min-height:0`) is read as
  // a skill reference — a checker that cries wolf gets switched off.
  const NAMESPACE = /^(?:[a-z0-9]+-)*(?:plugin|developer|utils|superpowers|design|forms?|dev)[a-z0-9-]*$|-\d+-\d+$/;
  for (const m of body.matchAll(/`([a-z][a-z0-9-]*):([a-z][a-z0-9-]*)`/g)) {
    const [, ns, name] = m;
    // IndexedDB database names (`form:default-app`, `form_lookup:default-app`) are not skill ids.
    if (name === 'default-app') continue;
    if (siblingPlugins.has(ns) || ns === thisPlugin || NAMESPACE.test(ns)) ids.add(`${ns}:${name}`);
  }

  for (const id of ids) {
    const f = fam('skills');
    f.walked++;
    const [a, b] = id.includes(':') ? id.split(':') : [null, id];
    const plugin = a ?? thisPlugin;
    const skillName = b;
    // An agent name is not a skill; the agents family covers those.
    if (plugin === thisPlugin && fs.existsSync(path.join(ROOT, 'agents', `${skillName}.md`))) continue;
    // Two cases where absence is not evidence of a bug:
    //  - the plugin IS in the marketplace but isn't checked out beside us, so we
    //    cannot enumerate its skills;
    //  - we never found a marketplace manifest at all, so we cannot claim to know
    //    what this marketplace contains. Asserting "not in this marketplace" from
    //    an incomplete view is exactly the false-confidence this script exists to
    //    prevent — it has to hold itself to the same standard.
    if (plugin !== thisPlugin && (siblingPlugins.get(plugin) === null || !marketplaceFound)) {
      skip(
        'skills',
        rel(file),
        siblingPlugins.has(plugin)
          ? `"${id}" — plugin "${plugin}" is in the marketplace but its skills aren't available here`
          : `"${id}" — no marketplace manifest reachable, so membership can't be judged`
      );
      continue;
    }
    f.checked++;
    const known =
      (plugin === thisPlugin && localSkills.has(skillName)) ||
      (siblingPlugins.get(plugin)?.has(skillName) ?? false);
    if (!known) {
      fail(
        'skills',
        rel(file),
        `"${id}" is not a skill in this marketplace — declare the dependency or drop the reference`
      );
    }
  }
}

// ------------------------------------------------------------- 4. agents

const agentNames = new Set(
  fs.existsSync(path.join(ROOT, 'agents'))
    ? fs.readdirSync(path.join(ROOT, 'agents')).filter((f) => f.endsWith('.md')).map((f) => f.replace(/\.md$/, ''))
    : []
);
for (const file of MD) {
  const body = stripFences(fs.readFileSync(file, 'utf8'));
  for (const m of body.matchAll(/`shesha-developer(?:-0-46)?:([a-z0-9-]+)`\s*(?:agent|fan-out)/g)) {
    const f = fam('agents');
    f.walked++;
    f.checked++;
    if (!agentNames.has(m[1]) && !localSkills.has(m[1])) {
      fail('agents', rel(file), `dispatches "${m[1]}" but there is no agents/${m[1]}.md`);
    }
  }
}

// -------------------------------------------------------------- 5. $role

const themeDir = path.join(ROOT, 'skills', 'shesha-design-system', 'assets', 'themes');
const themes = fs.existsSync(themeDir)
  ? fs.readdirSync(themeDir).filter((f) => f.endsWith('.tokens.json')).map((f) => ({ name: f, doc: readJson(path.join(themeDir, f)) }))
  : [];
const getPath = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o);

if (!themes.length) {
  skip('roles', 'assets/themes', 'no brand token files found');
} else {
  const roleUsers = ALL.filter((f) => f.endsWith('.json') || f.endsWith('.md'));
  for (const file of roleUsers) {
    const text = fs.readFileSync(file, 'utf8');
    for (const m of new Set([...text.matchAll(/\$role:([A-Za-z0-9_]+)/g)].map((x) => x[1]))) {
      const f = fam('roles');
      f.walked++;
      // A role must resolve in EVERY shipped brand — requirements-studio was missing
      // 12 of 24, so re-baking under it aborted on $role:bodyInk.
      for (const t of themes) {
        f.checked++;
        const target = t.doc.roles?.[m];
        if (typeof getPath(t.doc, target ?? '') !== 'string') {
          fail('roles', rel(file), `$role:${m} does not resolve in ${t.name}`);
        }
      }
    }
  }
}

// ----------------------------------------------------------- 6. overlays

const blocksDir = path.join(ROOT, 'skills', 'shesha-form-edit', 'assets', 'blocks');
const stylesDir = path.join(ROOT, 'skills', 'shesha-design-system', 'assets', 'block-styles');
if (fs.existsSync(blocksDir)) {
  for (const bf of fs.readdirSync(blocksDir).filter((f) => f.endsWith('.block.json'))) {
    const block = readJson(path.join(blocksDir, bf));
    const f = fam('overlays');
    f.walked++;
    if (block.$styleOverlay == null) continue; // explicitly self-styled
    f.checked++;
    if (!fs.existsSync(path.join(stylesDir, `${block.$styleOverlay}.style.json`))) {
      fail('overlays', `assets/blocks/${bf}`, `declares $styleOverlay "${block.$styleOverlay}" but no such .style.json exists`);
    }
  }
}

// ----------------------------------------------------------- 7. versions

const kbIndexPath = path.join(ROOT, 'skills', 'shesha-form-edit', 'assets', 'components-kb', '_index.json');
if (!fs.existsSync(kbIndexPath)) {
  skip('versions', 'components-kb/_index.json', 'KB index not found — cannot check version drift');
} else {
  const kb = readJson(kbIndexPath);
  for (const file of MD) {
    const text = fs.readFileSync(file, 'utf8');
    // Markdown table cells: | `type` | 5 |   (the cheatsheet's mirrored table)
    for (const m of text.matchAll(/\|\s*`([A-Za-z][A-Za-z0-9.]*)`\s*\|\s*(\d+)\s*\|/g)) {
      const [, type, n] = m;
      if (!(type in kb)) continue; // not a component type — some other table
      const f = fam('versions');
      f.walked++;
      f.checked++;
      if (kb[type].version !== Number(n)) {
        fail('versions', rel(file), `says ${type} is version ${n}; components-kb says ${kb[type].version}`);
      }
    }
    // Inline claims: `dataContext` (v8)  /  "type": "dropdown", "version": 11
    for (const m of text.matchAll(/"type":\s*"([A-Za-z][A-Za-z0-9.]*)",\s*"version":\s*(\d+)/g)) {
      const [, type, n] = m;
      if (!(type in kb)) continue;
      const f = fam('versions');
      f.walked++;
      f.checked++;
      if (kb[type].version !== Number(n)) {
        fail('versions', rel(file), `sample shows ${type} at version ${n}; components-kb says ${kb[type].version}`);
      }
    }
  }
}

// ------------------------------------------------------------- 8. groups

const groupsDir = path.join(ROOT, 'skills', 'clean-form-config', 'assets', 'groups');
if (!fs.existsSync(groupsDir)) {
  skip('groups', 'clean-form-config/assets/groups', 'component index not found');
} else {
  const index = readJson(path.join(groupsDir, 'index.json'));
  const cache = new Map();
  for (const [type, group] of Object.entries(index.components ?? {})) {
    const f = fam('groups');
    f.walked++;
    const gp = path.join(groupsDir, `${group}.json`);
    if (!fs.existsSync(gp)) {
      fail('groups', 'index.json', `${type} routes to ${group}.json, which does not exist`);
      continue;
    }
    if (!cache.has(group)) cache.set(group, readJson(gp));
    f.checked++;
    if (!(type in cache.get(group))) {
      fail('groups', `${group}.json`, `index routes "${type}" here but the file has no such entry`);
    }
  }
}

// -------------------------------------------------------------- reporting

const list = [...families.values()].sort((a, b) => a.name.localeCompare(b.name));
const anyFail = list.some((f) => f.failures.length);
const anySkip = list.some((f) => f.uninspectable.length);
const zeroCoverage = list.filter((f) => f.walked > 0 && f.checked === 0);
const verdict = anyFail || zeroCoverage.length ? 'fail' : anySkip ? 'partial' : 'pass';

if (JSON_OUT) {
  console.log(JSON.stringify({ root: rel(ROOT) || '.', verdict, families: list }, null, 2));
} else {
  console.log(`check-references — ${path.basename(ROOT)}\n`);
  for (const f of list) {
    console.log(
      `  ${f.name.padEnd(9)} walked ${String(f.walked).padStart(4)}   checked ${String(f.checked).padStart(4)}` +
        `   n/a ${String(f.notApplicable.length).padStart(3)}` +
        `   uninspectable ${String(f.uninspectable.length).padStart(3)}   failures ${String(f.failures.length).padStart(3)}`
    );
  }
  for (const f of list) {
    if (!f.failures.length) continue;
    console.log(`\n  FAIL — ${f.name}`);
    for (const { where, message } of f.failures) console.log(`    ${where}\n      ${message}`);
  }
  for (const f of zeroCoverage) {
    console.log(`\n  NO COVERAGE — ${f.name} walked ${f.walked} pointers and evaluated none.`);
  }
  console.log(`\n  verdict: ${verdict.toUpperCase()}`);
  if (verdict === 'partial') {
    console.log('  Partial is not a pass — see the uninspectable counts above (--json for detail).');
  }
}

process.exit({ pass: 0, fail: 1, partial: 3 }[verdict]);
