#!/usr/bin/env node
/*
 * verify-artifact.mjs — verify a form-markup artifact on DISK before anyone
 * believes an agent's "done" report.
 *
 * Why this exists. Two build retrospectives independently recorded the same
 * failure: a dispatched authoring agent reported success for work it had not
 * finished. Once the file had never been written at all (47 and 50 tool calls,
 * no output file); once it was written but its datalist pointed at a
 * row-template form that did not exist, so the list would have rendered empty.
 * Neither was caught by a gate — both were caught by a human reading JSON.
 * The agent's self-report is not evidence. The file on disk is.
 *
 * A second lesson from the same retrospectives shapes how this reports. A
 * sibling checker passed a form with "0 bindings, 0 reflists, 0 endpoints
 * checked" — not zero failures, zero coverage, because the constructs in that
 * form were invisible to its walker. A green light with no coverage behind it
 * is worse than no gate. So every family here reports three numbers:
 *
 *   walked        nodes this family actually visited
 *   checked       assertions it was able to evaluate
 *   uninspectable nodes it saw but structurally COULD NOT evaluate, each with
 *                 a named reason
 *
 * Any uninspectable node downgrades the verdict to `partial`, which exits
 * non-zero. This gate fails closed: it would rather send you to read the JSON
 * than tell you something is fine when it never looked.
 *
 * Families:
 *   file        the artifact exists, is non-empty, and parses (envelope,
 *               double-stringified markup, and bare component arrays all
 *               unwrap). A failure here is terminal — nothing else can run.
 *   structure   every component carries a real UUID `id` and a `parentId`.
 *               Missing/short ids are silently dropped by the renderer;
 *               missing parentIds crash it with no useful error.
 *   references  every `formId: {name, module}` in the tree resolves via
 *               ConfigurationItem/GetCurrent (0.46). An empty ABP `result` means the
 *               referenced form does not exist — hard failure.
 *
 * Known coverage limit, stated rather than hidden: a `formId` given as a bare
 * GUID string, or as a code-mode `{_mode,_code}` expression, is NOT resolved —
 * it is counted as uninspectable so the run reports `partial`.
 *
 * Usage:
 *   node verify-artifact.mjs <form.json> --backend <url> --token <token-file>
 *   node verify-artifact.mjs <form.json> --offline        # skip reference resolution
 *   node verify-artifact.mjs <form.json> ... --json       # machine-readable verdict
 *   node verify-artifact.mjs <form.json> ... --module <m> # module for refs that omit one
 *   node verify-artifact.mjs <seed.json>  --seed          # assets/examples seed, not a build
 *
 * Note on seeds: the canonical seeds under assets/examples carry unstamped
 * "{{GEN_KEY}}" ids on purpose. Without --seed those are hard failures, which
 * is correct for anything about to be pushed and wrong for a seed. Pass --seed
 * when the input really is a template.
 *
 * Exit codes:
 *   0  pass     every family fully covered, no failures
 *   1  fail     at least one assertion failed
 *   2  error    the artifact could not be read or parsed at all
 *   3  partial  no failures, but something could not be inspected
 *
 * No external dependencies (Node >=18 for global fetch).
 */

import fs from 'node:fs';
import path from 'node:path';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REQUEST_TIMEOUT_MS = 15000;

// ---------------------------------------------------------------- arg parsing

function parseArgs(argv) {
  const out = { file: null, backend: null, token: null, module: null, json: false, offline: false, seed: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') out.json = true;
    else if (a === '--offline') out.offline = true;
    else if (a === '--seed') out.seed = true;
    else if (a === '--backend') out.backend = argv[++i];
    else if (a === '--token') out.token = argv[++i];
    else if (a === '--module') out.module = argv[++i];
    else if (!a.startsWith('--') && !out.file) out.file = a;
    else throw new Error(`unrecognised argument: ${a}`);
  }
  if (!out.file) throw new Error('missing <form.json>');
  return out;
}

// ------------------------------------------------------------------- families

/**
 * A family accumulates its own coverage. `uninspectable` entries must always
 * carry a reason — an unexplained gap is the thing this script exists to stop.
 */
function family(name) {
  return {
    name,
    walked: 0,
    checked: 0,
    failures: [],
    uninspectable: [],
    fail(where, message) {
      this.failures.push({ where, message });
    },
    cannotInspect(where, reason) {
      this.uninspectable.push({ where, reason });
    },
  };
}

// --------------------------------------------------------------- file family

function readArtifact(file, fam) {
  let raw;
  try {
    raw = fs.readFileSync(file, 'utf8');
  } catch (e) {
    fam.fail(file, `cannot read file: ${e.code === 'ENOENT' ? 'does not exist (the agent never wrote it)' : e.message}`);
    return null;
  }
  fam.walked = 1;

  raw = raw.replace(/^﻿/, '').trim();
  if (!raw) {
    fam.fail(file, 'file is empty');
    return null;
  }

  let doc;
  try {
    doc = JSON.parse(raw);
  } catch (e) {
    fam.fail(file, `not valid JSON: ${e.message}`);
    return null;
  }

  // Unwrap the shapes this artifact legitimately arrives in: an ABP envelope,
  // a markup string that is itself stringified JSON, or a bare array.
  let hops = 0;
  while (hops++ < 4) {
    if (typeof doc === 'string') {
      try {
        doc = JSON.parse(doc);
        continue;
      } catch (e) {
        fam.fail(file, `nested markup string is not valid JSON: ${e.message}`);
        return null;
      }
    }
    if (doc && typeof doc === 'object' && !Array.isArray(doc)) {
      const inner = doc.result ?? doc.markup;
      if (inner !== undefined && inner !== null && (typeof inner === 'string' || typeof inner === 'object')) {
        doc = inner;
        continue;
      }
    }
    break;
  }

  if (Array.isArray(doc)) doc = { components: doc };
  if (!doc || typeof doc !== 'object') {
    fam.fail(file, 'parsed artifact is not an object');
    return null;
  }
  fam.checked = 1;
  return doc;
}

// ---------------------------------------------------------- structure family

/**
 * Components are the elements of any array under a `components` key. That is
 * the canonical nesting in Shesha markup and it stays correct for containers,
 * tabs and column children alike.
 */
function collectComponents(node, out, trail = '$') {
  if (Array.isArray(node)) {
    node.forEach((child, i) => collectComponents(child, out, `${trail}[${i}]`));
    return out;
  }
  if (!node || typeof node !== 'object') return out;

  for (const [key, value] of Object.entries(node)) {
    const here = `${trail}.${key}`;
    if (key === 'components' && Array.isArray(value)) {
      value.forEach((comp, i) => {
        if (comp && typeof comp === 'object' && !Array.isArray(comp)) out.push({ comp, where: `${here}[${i}]` });
      });
    }
    collectComponents(value, out, here);
  }
  return out;
}

const labelOf = (c) => (c.type ? `${c.type}${c.propertyName ? ` "${c.propertyName}"` : ''}` : 'untyped component');
const isTemplateToken = (s) => /\{\{.*\}\}/.test(s);

/**
 * What this family will and will not assert, and why.
 *
 * It asserts only things that are unambiguously broken:
 *   - a missing or empty `id`            (renderer drops the component)
 *   - an unreplaced "{{TOKEN}}" id       (stampTree never ran over that node)
 *   - a duplicate `id`                   (two nodes claiming one identity)
 *   - a missing `parentId`               (crashes the renderer, no useful error)
 *
 * It deliberately does NOT judge whether a non-UUID id is "valid enough".
 * SKILL.md says ids must be UUIDs, but the shipped seeds and real exported
 * forms are full of nanoid-style ids ("8jJ1tFFwhdXB8tGQn7xbB2cwTvcPLe") and
 * truncated hex ("237fe6c4df8d4c81b0dc65845d") that render fine — a sibling
 * branch already had to walk back its own "UUID-only" assertion to
 * "UUID-or-nanoid". Since the real rule is unsettled, asserting it would
 * generate ~110 confident findings against a canonical seed that is not wrong.
 * A gate that cries wolf gets ignored, which is how the previous validators
 * lost the team's trust. So the count is reported as a coverage note instead:
 * visible, honest, and not dressed up as a defect.
 */
function checkStructure(components, fam, { seed = false } = {}) {
  fam.walked = components.length;

  const seen = new Map();
  let nonUuid = 0;
  let nonUuidSample = null;
  let unstamped = 0;
  let unstampedSample = null;

  for (const { comp, where } of components) {
    fam.checked++;
    const id = comp.id;
    if (typeof id !== 'string' || !id) {
      fam.fail(where, `${labelOf(comp)}: missing "id" — the renderer drops components without one`);
    } else if (isTemplateToken(id)) {
      // In a build output an unreplaced token is a hard defect. In a seed it is
      // the whole point of the file, so --seed groups them into one honest note.
      if (seed) {
        unstamped++;
        unstampedSample ??= id;
      } else {
        fam.fail(
          where,
          `${labelOf(comp)}: "id" is the unreplaced template token "${id}" — stampTree did not run over this node`
        );
      }
    } else {
      if (seen.has(id)) {
        fam.fail(where, `${labelOf(comp)}: duplicate "id" "${id}", already used at ${seen.get(id)}`);
      } else {
        seen.set(id, where);
      }
      if (!UUID_RE.test(id)) {
        nonUuid++;
        nonUuidSample ??= id;
      }
    }

    fam.checked++;
    if (typeof comp.parentId !== 'string' || !comp.parentId) {
      fam.fail(
        where,
        `${labelOf(comp)}: missing "parentId" (root-level components need "root") — crashes the renderer with no useful error`
      );
    }
  }

  if (unstamped > 0) {
    fam.cannotInspect(
      '$',
      `--seed: ${unstamped} component ids are unreplaced template tokens (e.g. "${unstampedSample}"). ` +
        `Expected in a seed; these become hard failures once this is a build output.`
    );
  }

  if (nonUuid > 0) {
    fam.cannotInspect(
      '$',
      `${nonUuid} of ${components.length} component ids are not UUIDs (e.g. "${nonUuidSample}"). ` +
        `Not judged: nanoid and truncated-hex ids are used by real Shesha forms and render fine, ` +
        `so this gate cannot tell a legitimate nanoid from a lazy placeholder like "btn1". ` +
        `If this is a build output rather than a seed, eyeball the list.`
    );
  }
}

// --------------------------------------------------------- references family

function collectFormRefs(node, fam, trail = '$', found = []) {
  if (Array.isArray(node)) {
    node.forEach((child, i) => collectFormRefs(child, fam, `${trail}[${i}]`, found));
    return found;
  }
  if (!node || typeof node !== 'object') return found;

  for (const [key, value] of Object.entries(node)) {
    const here = `${trail}.${key}`;
    if (key === 'formId' && value !== null && value !== undefined && value !== '') {
      fam.walked++;
      classifyRef(value, fam, here, found);
    }
    collectFormRefs(value, fam, here, found);
  }
  return found;
}

function classifyRef(value, fam, where, found) {
  if (typeof value === 'string') {
    if (UUID_RE.test(value)) {
      fam.cannotInspect(where, 'formId is a bare GUID; this gate resolves {name, module} references only');
    } else {
      fam.cannotInspect(where, `formId is the string "${value}" with no module; cannot resolve by name alone`);
    }
    return;
  }
  if (typeof value !== 'object') {
    fam.cannotInspect(where, `formId is a ${typeof value}, not a {name, module} object`);
    return;
  }
  if (value._mode === 'code' || typeof value._code === 'string') {
    fam.cannotInspect(where, 'formId is a code-mode expression, only resolvable at runtime');
    return;
  }
  const { name, module } = value;
  if (typeof name === 'string' && name && typeof module === 'string' && module) {
    found.push({ where, name, module });
    return;
  }
  if (typeof name === 'string' && name) {
    found.push({ where, name, module: null });
    return;
  }
  fam.cannotInspect(where, `formId object has no usable "name" (keys: ${Object.keys(value).join(', ') || 'none'})`);
}

async function resolveRefs(refs, fam, { backend, token, module: fallbackModule }) {
  // One request per distinct form, not per reference site.
  const distinct = new Map();
  for (const ref of refs) {
    const mod = ref.module ?? fallbackModule;
    if (!mod) {
      fam.cannotInspect(ref.where, `form "${ref.name}" has no module and no --module fallback was given`);
      continue;
    }
    const key = `${mod}/${ref.name}`;
    if (!distinct.has(key)) distinct.set(key, { name: ref.name, module: mod, sites: [] });
    distinct.get(key).sites.push(ref.where);
  }

  for (const [key, entry] of distinct) {
    const url =
      `${backend.replace(/\/$/, '')}/api/services/app/ConfigurationItem/GetCurrent` +
      `?ItemType=form&Module=${encodeURIComponent(entry.module)}&Name=${encodeURIComponent(entry.name)}`;

    let res;
    try {
      res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (e) {
      // A transport failure is NOT a passing check and NOT a missing form.
      entry.sites.forEach((s) => fam.cannotInspect(s, `request for "${key}" failed: ${e.message}`));
      continue;
    }

    if (res.status === 401 || res.status === 403) {
      entry.sites.forEach((s) => fam.cannotInspect(s, `not authorised to resolve "${key}" (HTTP ${res.status}) — token stale?`));
      continue;
    }

    let body;
    try {
      body = await res.json();
    } catch {
      entry.sites.forEach((s) => fam.cannotInspect(s, `non-JSON response resolving "${key}" (HTTP ${res.status})`));
      continue;
    }

    fam.checked++;
    if (!res.ok || body?.success === false || body?.result?.configuration == null) {
      entry.sites.forEach((s) =>
        fam.fail(s, `referenced form "${key}" does not exist on the backend — whatever points at it will render empty`)
      );
    }
  }
}

// -------------------------------------------------------------------- verdict

function verdictOf(families) {
  if (families.some((f) => f.failures.length)) return 'fail';
  if (families.some((f) => f.uninspectable.length)) return 'partial';
  return 'pass';
}

const EXIT = { pass: 0, fail: 1, error: 2, partial: 3 };

function report(families, verdict, file) {
  const lines = [];
  lines.push(`verify-artifact — ${path.basename(file)}`);
  lines.push('');
  for (const f of families) {
    lines.push(
      `  ${f.name.padEnd(11)} walked ${String(f.walked).padStart(4)}   checked ${String(f.checked).padStart(4)}` +
        `   uninspectable ${String(f.uninspectable.length).padStart(3)}   failures ${String(f.failures.length).padStart(3)}`
    );
  }
  for (const f of families) {
    if (f.failures.length) {
      lines.push('', `  FAIL — ${f.name}`);
      for (const { where, message } of f.failures) lines.push(`    ${where}`, `      ${message}`);
    }
  }
  for (const f of families) {
    if (f.uninspectable.length) {
      lines.push('', `  NOT INSPECTED — ${f.name} (read these by hand; this gate did not cover them)`);
      for (const { where, reason } of f.uninspectable) lines.push(`    ${where}`, `      ${reason}`);
    }
  }
  lines.push('');
  lines.push(`  verdict: ${verdict.toUpperCase()}`);
  if (verdict === 'partial') {
    lines.push('  A partial verdict is NOT a pass. Something here was never checked — say so when reporting.');
  }
  return lines.join('\n');
}

// ----------------------------------------------------------------------- main

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(`verify-artifact: ${e.message}`);
    console.error(
      'usage: node verify-artifact.mjs <form.json> [--backend <url>] [--token <file>] [--module <m>] [--offline] [--seed] [--json]\n' +
        '  exit: 0 pass · 1 fail · 2 error (unreadable) · 3 partial (something was not inspected)'
    );
    process.exit(EXIT.error);
  }

  const fileFam = family('file');
  const doc = readArtifact(args.file, fileFam);

  if (!doc) {
    const verdict = 'error';
    if (args.json) console.log(JSON.stringify({ artifact: args.file, verdict, families: [fileFam] }, null, 2));
    else console.log(report([fileFam], verdict, args.file));
    process.exit(EXIT.error);
  }

  const structureFam = family('structure');
  const components = collectComponents(doc, []);
  if (components.length === 0) {
    // Zero components is never a legitimate "nothing to check" for a form.
    structureFam.fail('$', 'no components found anywhere in the artifact — this is not a usable form');
  } else {
    checkStructure(components, structureFam, { seed: args.seed });
  }

  const refsFam = family('references');
  const refs = collectFormRefs(doc, refsFam);

  let token = null;
  if (args.token) {
    try {
      token = fs.readFileSync(args.token, 'utf8').replace(/^﻿/, '').trim();
    } catch (e) {
      refsFam.cannotInspect('--token', `cannot read token file ${args.token}: ${e.message}`);
    }
  }

  if (args.offline) {
    refs.forEach((r) => refsFam.cannotInspect(r.where, '--offline: reference not resolved against a backend'));
  } else if (!args.backend) {
    refs.forEach((r) => refsFam.cannotInspect(r.where, 'no --backend given, so this reference was never resolved'));
  } else {
    await resolveRefs(refs, refsFam, { backend: args.backend, token, module: args.module });
  }

  const families = [fileFam, structureFam, refsFam];
  const verdict = verdictOf(families);

  if (args.json) {
    console.log(
      JSON.stringify(
        {
          artifact: args.file,
          verdict,
          families: families.map((f) => ({
            name: f.name,
            walked: f.walked,
            checked: f.checked,
            failures: f.failures,
            uninspectable: f.uninspectable,
          })),
        },
        null,
        2
      )
    );
  } else {
    console.log(report(families, verdict, args.file));
  }
  process.exit(EXIT[verdict]);
}

main().catch((e) => {
  console.error(`verify-artifact: unexpected error: ${e.stack || e.message}`);
  process.exit(EXIT.error);
});
