#!/usr/bin/env node
/*
 * validate-blocks.js — sanity-check the authored block library against the
 * style capability matrix before the blocks are composed into a form.
 *
 * For every assets/blocks/*.block.json it checks four things:
 *   1. The skeleton's "subtree" (and "$rowTemplate", if present) is valid JSON
 *      that JSON.parse round-trips. Already-parsed in the file, but we re-stringify
 *      and re-parse the node to guarantee it is a clean, serialisable tree.
 *   2. Every "$validatedAgainst" entry names a (component:channel) pair that EXISTS
 *      in capability-matrix.json with verdict "renders"/"gotcha" (also accepts
 *      "renders-via-app-theme"/"partial"). An entry that maps to a "no-op" row, or to
 *      no matrix row at all, is a HARD FAILURE — the block is claiming to rely on a
 *      channel the framework silently ignores. Two exceptions, downgraded to WARN:
 *        - the entry explicitly DOCUMENTS the no-op it avoided ("(no-op -> ...)",
 *          "is inert") — that is intentional documentation, not a reliance claim;
 *        - the entry's channel is flex/display/justifyContent/gap behaviour, which is
 *          governed by matrix.crossCuttingRules rather than a matrix row.
 *      Compound matrix channels (e.g. "bg/border/radius/width/font",
 *      "fontSize/fontWeight/color/align") match if the entry's channel token is one
 *      of the slash-separated parts; paired components ("datatable/datalist") match
 *      on any shared alias.
 *   3. Structural smells (WARN): any container with flexDirection:"row"/"column" but
 *      no display:"flex" (flex props inert without it); any "columns"-type component
 *      (banned — build splits with flex containers).
 *   4. Any literal hex colour (#rgb / #rrggbb / #rrggbbaa) in a subtree (WARN) —
 *      brand colour belongs in the design-system overlay via $role tokens, not a block.
 *
 * Exit code is non-zero ONLY if a block has a hard failure (bad skeleton JSON, or a
 * $validatedAgainst entry pointing at a missing/no-op matrix row). Warnings never fail.
 *
 * Usage:
 *   node validate-blocks.js
 *   node validate-blocks.js --blocks <dir> --matrix <path>   # override defaults
 *
 * Defaults resolve relative to this script:
 *   blocks  = ../assets/blocks
 *   matrix  = ../../shesha-design-system/assets/capability-matrix.json
 *
 * No external dependencies (Node fs/path only). Authored as an ES module because
 * the skill's package.json declares "type":"module".
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// ---- arg / path resolution -------------------------------------------------

function argVal(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const BLOCKS_DIR = path.resolve(argVal('--blocks', path.join(SCRIPT_DIR, '..', 'assets', 'blocks')));
const MATRIX_PATH = path.resolve(
  argVal('--matrix', path.join(SCRIPT_DIR, '..', '..', 'shesha-design-system', 'assets', 'capability-matrix.json'))
);

// Blocks known to carry structural-neutral hexes (surface/hairline defaults the
// overlay overrides). Their hex warnings get a softer note; still warnings, never fatal.
const ALLOW_HEX = new Set(['card-with-header-strip']);

// ---- helpers ---------------------------------------------------------------

function readJson(p) {
  let raw = fs.readFileSync(p, 'utf8');
  if (raw.charCodeAt(0) === 0xfeff) raw = raw.slice(1); // strip BOM
  return JSON.parse(raw);
}

// Split a "$validatedAgainst" entry into { component, channel }.
// Entry looks like: "container:dimensions.width (% and calc) — note"
//                or "container:font(no-op -> font on text child)"
//                or "buttonGroup:buttonType colour (renders-via-app-theme, v15)"
function parseEntry(entry) {
  const colon = entry.indexOf(':');
  if (colon === -1) return null;
  const component = entry.slice(0, colon).trim();
  let rest = entry.slice(colon + 1);
  // cut at the first descriptive delimiter: " — ", " -> ", " (", ","
  rest = rest.split(/\s+—\s+| -> |\(/)[0];
  rest = rest.split(',')[0];
  // cut trailing prose verbs ("font is a no-op", "customStyle.flex is inert")
  // so the channel token resolves to the bare path the matrix indexes.
  rest = rest.split(/\s+is\s+/i)[0];
  const channel = rest.trim();
  return { component, channel, raw: entry };
}

// Normalise a channel string into comparable tokens.
function tokens(channelStr) {
  return channelStr
    .toLowerCase()
    .split(/[\s/+]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

// Find matrix rows whose component matches AND whose channel covers the entry channel.
// Returns array of matched rows (may be >1 for fuzzy compound channels).
function matchRows(matrixRows, entry) {
  // entry component may itself be a paired alias e.g. "datatable/datalist"
  const compTokens = entry.component.toLowerCase().split('/');
  const entTokens = tokens(entry.channel);
  return matrixRows.filter((row) => {
    // matrix may pair components e.g. "datatable/datalist"; match on any shared alias
    const rowComps = row.component.toLowerCase().split('/');
    if (!compTokens.some((c) => rowComps.includes(c))) return false;

    const rowChan = row.channel.toLowerCase();
    const rowTokens = tokens(row.channel);

    // exact channel match
    if (rowChan === entry.channel.toLowerCase()) return true;
    // entry channel is a single token that is one of the row's slash/plus parts
    if (entTokens.length === 1 && rowTokens.includes(entTokens[0])) return true;
    // every entry token present in the row's tokens (compound -> compound)
    if (entTokens.length && entTokens.every((t) => rowTokens.includes(t))) return true;
    // dotted-path leading match (e.g. entry "dimensions.minHeight" vs row "dimensions.minHeight")
    if (rowChan.startsWith(entry.channel.toLowerCase())) return true;
    return false;
  });
}

// Walk every object node in a subtree, invoking visit(node).
function walk(node, visit) {
  if (Array.isArray(node)) {
    node.forEach((n) => walk(n, visit));
    return;
  }
  if (node && typeof node === 'object') {
    visit(node);
    for (const k of Object.keys(node)) walk(node[k], visit);
  }
}

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/;

// ---- per-block validation --------------------------------------------------

function validateBlock(blockPath, matrix) {
  const name = path.basename(blockPath).replace(/\.block\.json$/, '');
  const result = { name, fails: [], warns: [] };

  let block;
  try {
    block = readJson(blockPath);
  } catch (e) {
    result.fails.push(`block JSON does not parse: ${e.message}`);
    return result;
  }

  // (1) skeleton subtree(s) JSON.parse round-trip
  for (const key of ['subtree', '$rowTemplate']) {
    if (block[key] === undefined) continue;
    try {
      const round = JSON.parse(JSON.stringify(block[key]));
      if (round === null || typeof round !== 'object') {
        result.fails.push(`"${key}" is not an object subtree`);
      }
    } catch (e) {
      result.fails.push(`"${key}" failed JSON round-trip: ${e.message}`);
    }
  }

  // (2) $validatedAgainst -> matrix verdicts
  const entries = Array.isArray(block.$validatedAgainst) ? block.$validatedAgainst : [];
  if (!entries.length) {
    result.warns.push('no $validatedAgainst entries');
  }
  for (const raw of entries) {
    // some blocks list plain bullet strings under $bindings-style notes; only
    // entries that look like "component:channel" are matrix claims.
    if (typeof raw !== 'string' || raw.indexOf(':') === -1) continue;
    // skip cross-cutting-rule / version notes that aren't component:channel claims
    if (/^(crosscuttingrule|versions)\b/i.test(raw.trim())) continue;
    const entry = parseEntry(raw);
    if (!entry || !entry.channel) {
      result.warns.push(`unparseable $validatedAgainst entry: "${raw}"`);
      continue;
    }
    // Does the entry explicitly document a no-op channel it AVOIDED?
    // (e.g. "container:font(no-op -> font on text child)"). Such entries are
    // intentional documentation, not a reliance claim — flag as warn, not fail.
    const documentsNoop = /no-?op|inert/i.test(raw);
    // Is the entry backed by a cross-cutting rule rather than a matrix row?
    // (flex/display/flexDirection/justifyContent/gap behaviour is in
    // matrix.crossCuttingRules, not matrix.rows.)
    const RULE_CHANNELS = /^(display|flexdirection|justifycontent|alignitems|gap|flexwrap)/i;
    const ruleBacked = RULE_CHANNELS.test(entry.channel.replace(/[\s=].*$/, ''));

    const rows = matchRows(matrix.rows, entry);
    if (!rows.length) {
      if (ruleBacked) {
        result.warns.push(
          `"${entry.component}:${entry.channel}" has no matrix row but is backed by a crossCuttingRule (from "${raw}")`
        );
      } else {
        result.fails.push(`no matrix row for "${entry.component}:${entry.channel}" (from "${raw}")`);
      }
      continue;
    }
    const GOOD = new Set(['renders', 'gotcha', 'renders-via-app-theme', 'partial']);
    const good = rows.filter((r) => GOOD.has(r.verdict));
    const noop = rows.filter((r) => r.verdict === 'no-op');
    if (!good.length && noop.length) {
      const msg = `"${entry.component}:${entry.channel}" maps ONLY to no-op matrix row(s) [${noop
        .map((r) => r.channel)
        .join(', ')}]`;
      if (documentsNoop) {
        // Block correctly documents the no-op + its fix; consistent, not a reliance.
        result.warns.push(`${msg} — documented-and-avoided no-op (from "${raw}")`);
      } else {
        result.fails.push(`${msg} — block claims a silently-ignored channel (from "${raw}")`);
      }
    } else if (noop.length && good.length && !documentsNoop) {
      result.warns.push(
        `"${entry.component}:${entry.channel}" also matches a no-op row but no no-op note in entry (from "${raw}")`
      );
    }
  }

  // (3) + (4) structural / hex smells in the subtree(s) — all WARN per spec.
  // (Known structural-neutral blocks get a softer hex note, but it is still a warn.)
  const structuralNeutral = ALLOW_HEX.has(name);
  for (const key of ['subtree', '$rowTemplate']) {
    if (!block[key] || typeof block[key] !== 'object') continue;
    walk(block[key], (node) => {
      // columns ban — build splits with flex containers, never the columns component
      if (node.type === 'columns') {
        result.warns.push(`"${key}" contains a "columns" component — build splits with flex containers`);
      }
      // flex-without-display: flexDirection:"row"/"column" is inert unless display:"flex"
      const isContainer = node.type === 'container' || node.type === 'card';
      const fd = node.flexDirection;
      if (isContainer && (fd === 'row' || fd === 'column')) {
        const disp = node.display || (node.desktop && node.desktop.display);
        if (disp !== 'flex') {
          result.warns.push(
            `"${key}" container ${node.componentName || node.propertyName || '(unnamed)'} has flexDirection:"${fd}" without display:"flex" (flex props inert)`
          );
        }
      }
      // hex hunt: any literal colour in a skeleton belongs in the overlay, not the block
      for (const k of Object.keys(node)) {
        const v = node[k];
        if (typeof v === 'string' && HEX_RE.test(v)) {
          let msg = `"${key}" node ${node.componentName || node.type || '?'} prop "${k}" carries a hex (${v.match(HEX_RE)[0]})`;
          msg += structuralNeutral ? ' [structural-neutral; overlay overrides]' : ' — colour belongs in the design-system overlay';
          result.warns.push(msg);
        }
      }
    });
  }

  return result;
}

// ---- main ------------------------------------------------------------------

function main() {
  let matrix;
  try {
    matrix = readJson(MATRIX_PATH);
  } catch (e) {
    console.error(`FATAL: cannot read capability matrix at ${MATRIX_PATH}: ${e.message}`);
    process.exit(2);
  }
  if (!Array.isArray(matrix.rows)) {
    console.error(`FATAL: matrix has no "rows" array (${MATRIX_PATH})`);
    process.exit(2);
  }

  let files;
  try {
    files = fs
      .readdirSync(BLOCKS_DIR)
      .filter((f) => f.endsWith('.block.json'))
      .sort()
      .map((f) => path.join(BLOCKS_DIR, f));
  } catch (e) {
    console.error(`FATAL: cannot read blocks dir ${BLOCKS_DIR}: ${e.message}`);
    process.exit(2);
  }
  if (!files.length) {
    console.error(`FATAL: no *.block.json files in ${BLOCKS_DIR}`);
    process.exit(2);
  }

  const results = files.map((f) => validateBlock(f, matrix));

  // per-block PASS/FAIL table
  const nameW = Math.max(...results.map((r) => r.name.length), 5);
  console.log('');
  console.log(`validate-blocks  (${results.length} blocks against ${path.basename(MATRIX_PATH)})`);
  console.log('-'.repeat(nameW + 28));
  console.log(`${'BLOCK'.padEnd(nameW)}  RESULT  FAILS  WARNS`);
  console.log('-'.repeat(nameW + 28));
  for (const r of results) {
    const verdict = r.fails.length ? 'FAIL' : 'PASS';
    console.log(`${r.name.padEnd(nameW)}  ${verdict.padEnd(6)}  ${String(r.fails.length).padEnd(5)}  ${r.warns.length}`);
  }
  console.log('-'.repeat(nameW + 28));

  // detail
  for (const r of results) {
    if (r.fails.length || r.warns.length) {
      console.log(`\n[${r.name}]`);
      r.fails.forEach((m) => console.log(`  FAIL  ${m}`));
      r.warns.forEach((m) => console.log(`  warn  ${m}`));
    }
  }

  const totalFails = results.reduce((n, r) => n + r.fails.length, 0);
  const totalWarns = results.reduce((n, r) => n + r.warns.length, 0);
  console.log(`\n${totalFails} hard failure(s), ${totalWarns} warning(s) across ${results.length} block(s).`);

  process.exit(totalFails ? 1 : 0);
}

main();
