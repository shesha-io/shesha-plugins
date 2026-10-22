/*
 * Bake each block's paired style overlay into the block subtree as literal values,
 * so composing a block yields a styled result with no separate overlay pass.
 *
 * Refuses to write anything unless every assertion holds:
 *   - every overlay target resolves to exactly one node (no silent no-ops)
 *   - node count is identical before and after (styling only, never structure)
 *   - the result round-trips through JSON
 *
 * Usage: node bake-overlays.mjs <blocksDir> <stylesDir> [--apply] [--only <block>]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/*
 * Paths default relative to THIS SCRIPT, never the caller's cwd — matching
 * validate-blocks.js. When they were bare positional args, running the documented
 * command from the wrong directory silently created a whole second
 * `plugins/shesha-design-system/` tree that nothing reads, and the overlays in it
 * then diverged from the real ones. Positional args still work for overrides.
 */
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const positional = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const flagValues = new Set(
  ['--only'].flatMap((f) => {
    const i = process.argv.indexOf(f);
    return i !== -1 && process.argv[i + 1] ? [process.argv[i + 1]] : [];
  })
);
const args = positional.filter((a) => !flagValues.has(a));

const BLOCKS = path.resolve(args[0] ?? path.join(SCRIPT_DIR, '..', 'assets', 'blocks'));
const STYLES = path.resolve(
  args[1] ?? path.join(SCRIPT_DIR, '..', '..', 'shesha-design-system', 'assets', 'block-styles')
);
const TOKENS = path.resolve(
  args[2] ?? path.join(SCRIPT_DIR, '..', '..', 'shesha-design-system', 'assets', 'themes', 'shesha.tokens.json')
);

for (const [label, p] of [['blocks', BLOCKS], ['styles', STYLES], ['tokens', TOKENS]]) {
  if (!fs.existsSync(p)) {
    console.error(`bake-overlays: ${label} path does not exist: ${p}`);
    console.error('  (paths default relative to the script; pass overrides positionally)');
    process.exit(2);
  }
}

const APPLY = process.argv.includes('--apply');
const ONLY = process.argv.includes('--only') ? process.argv[process.argv.indexOf('--only') + 1] : null;

/** Keys whose value legitimately differs per breakpoint — never mirrored from desktop. */
const RESPONSIVE = new Set(['dimensions', 'flexDirection']);

const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);

/* --- $role token resolution -------------------------------------------------
 * Overlays carry "$role:bodyText" style references. Baking a token string into a
 * block would produce a literally-invalid colour, so every one must resolve to a
 * concrete value from the brand file (roles -> dotted token path -> value).
 * An unresolvable role is a hard failure, never a passthrough.
 */
const theme = JSON.parse(fs.readFileSync(TOKENS, 'utf8'));
const getPath = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o);
const roleFailures = [];

function resolveRoles(value, where) {
  if (typeof value === 'string' && value.startsWith('$role:')) {
    const role = value.slice(6);
    const target = theme.roles?.[role];
    const literal = target ? getPath(theme, target) : undefined;
    if (typeof literal !== 'string') {
      roleFailures.push(`${where}: cannot resolve "${value}" (roles.${role} -> ${target ?? 'undefined'})`);
      return value;
    }
    return literal;
  }
  if (Array.isArray(value)) return value.map((v) => resolveRoles(v, where));
  if (isObj(value)) {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = resolveRoles(v, where);
    return out;
  }
  return value;
}

function deepMerge(base, over) {
  const out = { ...base };
  for (const [k, v] of Object.entries(over)) {
    out[k] = isObj(v) && isObj(out[k]) ? deepMerge(out[k], v) : v;
  }
  return out;
}

function findByComponentName(root, name) {
  const hits = [];
  (function walk(n) {
    if (Array.isArray(n)) return n.forEach(walk);
    if (!isObj(n)) return;
    if (n.componentName === name) hits.push(n);
    Object.values(n).forEach(walk);
  })(root);
  return hits;
}

function countNodes(root) {
  let c = 0;
  (function walk(n) {
    if (Array.isArray(n)) return n.forEach(walk);
    if (!isObj(n)) return;
    if (n.componentName) c++;
    Object.values(n).forEach(walk);
  })(root);
  return c;
}

let changedFiles = 0;
let appliedTargets = 0;
const failures = [];

for (const f of fs.readdirSync(BLOCKS).filter((x) => x.endsWith('.block.json')).sort()) {
  const p = path.join(BLOCKS, f);
  const block = JSON.parse(fs.readFileSync(p, 'utf8'));
  if (ONLY && block.$block !== ONLY) continue;

  const overlayPath = path.join(STYLES, `${block.$styleOverlay}.style.json`);
  if (!block.$styleOverlay || !fs.existsSync(overlayPath)) {
    console.log(`${block.$block.padEnd(26)} skip — no overlay file`);
    continue;
  }
  const overlay = JSON.parse(fs.readFileSync(overlayPath, 'utf8'));
  const roots = [block.subtree, block.$rowTemplate].filter(Boolean);
  const before = roots.reduce((s, r) => s + countNodes(r), 0);

  let applied = 0;
  let advisory = 0;
  for (const [name, styles] of Object.entries(overlay.targets ?? {})) {
    const hits = roots.flatMap((r) => findByComponentName(r, name));
    if (hits.length !== 1) {
      // A target carrying its own $note describes components the FORM adds at
      // compose time (e.g. "each meta text component the form adds inside rowMeta"),
      // so having no node in the block is correct, not a defect. Anything else
      // that fails to resolve is a silent no-op and must fail loudly.
      if (hits.length === 0 && typeof styles.$note === 'string') {
        advisory++;
        continue;
      }
      failures.push(`${block.$block}: target "${name}" matched ${hits.length} nodes (need exactly 1)`);
      continue;
    }
    const node = hits[0];

    // 1. Overlay values win, per breakpoint — with $role tokens resolved to literals.
    for (const bp of ['desktop', 'tablet', 'mobile']) {
      if (!styles[bp] || !Object.keys(styles[bp]).length) continue;
      const resolved = resolveRoles(styles[bp], `${block.$block}/${name}/${bp}`);
      node[bp] = deepMerge(node[bp] ?? {}, resolved);
    }
    // 2. Mirror desktop onto tablet/mobile for non-responsive keys the overlay left unset.
    //    A value present only on desktop leaves tablet/mobile falling back to the base node —
    //    the same per-key override trap that left the page shell bordered on tablet.
    const desktop = node.desktop ?? {};
    for (const bp of ['tablet', 'mobile']) {
      node[bp] = node[bp] ?? {};
      for (const [k, v] of Object.entries(desktop)) {
        if (RESPONSIVE.has(k)) continue;
        if (!(k in node[bp])) node[bp][k] = JSON.parse(JSON.stringify(v));
      }
    }
    applied++;
  }

  // 3. Resolve any $role token ALREADY in the subtree, not just ones arriving via
  //    the overlay. Two blocks shipped with "$role:progressAccent" / "$role:addButtonText"
  //    against roles that were never defined, so the renderer received the literal
  //    string "$role:…" as a colour and silently fell back to an AntD default.
  for (let i = 0; i < roots.length; i++) {
    const resolved = resolveRoles(roots[i], `${block.$block}/subtree`);
    if (roots[i] === block.subtree) block.subtree = resolved;
    else block.$rowTemplate = resolved;
    roots[i] = resolved;
  }

  const after = roots.reduce((s, r) => s + countNodes(r), 0);
  if (after !== before) {
    failures.push(`${block.$block}: node count changed ${before} -> ${after} (styling must not touch structure)`);
    continue;
  }

  const serialised = JSON.stringify(block, null, 2) + '\n';
  try {
    JSON.parse(serialised);
  } catch (e) {
    failures.push(`${block.$block}: result does not round-trip: ${e.message}`);
    continue;
  }

  const totalT = Object.keys(overlay.targets ?? {}).length;
  console.log(
    `${block.$block.padEnd(26)} baked ${String(applied).padStart(2)}/${totalT} targets  nodes ${before}` +
      (advisory ? `  (+${advisory} advisory, applied by the form at compose time)` : '')
  );
  appliedTargets += applied;
  if (APPLY) {
    fs.writeFileSync(p, serialised);
    changedFiles++;
  }
}

console.log(`\n${APPLY ? 'WROTE' : 'DRY RUN'} — ${appliedTargets} targets baked across ${APPLY ? changedFiles : 'n/a'} files`);
if (roleFailures.length) {
  console.log('\nUNRESOLVED $role TOKENS (these would render as an invalid colour string):');
  [...new Set(roleFailures)].forEach((x) => console.log('  - ' + x));
  process.exit(1);
}
if (failures.length) {
  console.log('\nASSERTION FAILURES (nothing written for these blocks):');
  failures.forEach((x) => console.log('  - ' + x));
  process.exit(1);
}
