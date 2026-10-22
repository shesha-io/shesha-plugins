#!/usr/bin/env node
// summarize.js — distill a raw Shesha entity-metadata or form-config JSON
// into a compact .summary.md companion file. The skill reads summaries by
// default and only opens the raw blob when a detail is missing.
//
// Usage:
//   node summarize.js <input.json> [--out <output.md>] [--type form|metadata]
//
// Type auto-detection (when --type is omitted):
//   - root or root.result has `properties` array → metadata
//   - root or root.result has `markup` string OR `components` array → form
//
// Stdin: pass `-` as input to read JSON from stdin.

const fs = require('fs');
const path = require('path');

function readInput(p) {
  const raw = (p === '-') ? fs.readFileSync(0, 'utf8') : fs.readFileSync(p, 'utf8');
  // Strip UTF-8 BOM if present (PowerShell often writes one)
  return raw.charCodeAt(0) === 0xFEFF ? raw.slice(1) : raw;
}

function unwrap(json) {
  // Unwrap ABP envelope { result: ... }
  let payload = json.result ?? json;
  // Unwrap stringified-markup envelope { markup: "{...}" }
  if (typeof payload.markup === 'string') {
    try { payload = JSON.parse(payload.markup); } catch (_) { /* keep */ }
  }
  return payload;
}

function detectType(payload) {
  if (Array.isArray(payload.properties)) return 'metadata';
  if (payload.components || payload.formSettings) return 'form';
  return null;
}

// ---------- metadata summary ----------

function summarizeMetadata(meta) {
  const lines = [];
  const name = meta.entityFullName ?? meta.containerName ?? meta.modelType ?? '(unknown entity)';
  lines.push(`# Entity: ${name}`);
  lines.push('');
  lines.push(`Generated: ${new Date().toISOString()}`);
  if (meta.properties) lines.push(`Property count: ${meta.properties.length}`);
  lines.push('');
  lines.push('## Properties');
  lines.push('');
  for (const p of (meta.properties ?? [])) {
    const propPath = p.path ?? p.name ?? '(unnamed)';
    const dataType = p.dataType ?? p.type ?? '?';
    const required = p.required ? ' **required**' : '';
    const tags = [];
    if (p.referenceListName) {
      const mod = p.referenceListModule ?? p.module ?? '?';
      tags.push(`refList: ${mod}/${p.referenceListName}`);
    }
    if (p.entityType) tags.push(`entity: ${p.entityType}`);
    if (p.dataFormat) tags.push(`format: ${p.dataFormat}`);
    if (p.readOnly) tags.push('readOnly');
    const tagStr = tags.length ? ` _(${tags.join('; ')})_` : '';
    lines.push(`- \`${propPath}\` : ${dataType}${tagStr}${required}`);
  }
  return lines.join('\n') + '\n';
}

// ---------- form summary ----------

function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  visit(node);
  if (Array.isArray(node.components)) node.components.forEach(c => walk(c, visit));
  if (node.content && Array.isArray(node.content.components)) node.content.components.forEach(c => walk(c, visit));
  if (node.header && Array.isArray(node.header.components)) node.header.components.forEach(c => walk(c, visit));
  if (Array.isArray(node.tabs)) node.tabs.forEach(t => (t.components ?? []).forEach(c => walk(c, visit)));
  if (Array.isArray(node.columns)) node.columns.forEach(col => (col.components ?? []).forEach(c => walk(c, visit)));
  if (Array.isArray(node.items)) node.items.forEach(i => walk(i, visit));
}

const SCRIPT_KEYS = [
  'onChangeCustom', 'onClickCustom', 'customVisibility', 'customEnabled',
  'onSubmit', 'onBeforeDataLoad', 'onAfterDataLoad', 'getOptions',
  'customSubmit', 'validator',
];

const STRUCTURAL_TYPES = new Set(['container', 'card', 'columns', 'tabs', 'dataContext']);

function summarizeForm(form, name) {
  const counts = {};
  const propertyBindings = [];
  const scriptRefs = [];
  let depth = 0;

  function visit(n) {
    if (!n.type) return;
    counts[n.type] = (counts[n.type] ?? 0) + 1;
    if (n.propertyName && !STRUCTURAL_TYPES.has(n.type)) {
      propertyBindings.push(`${n.propertyName} : ${n.type}`);
    }
    for (const k of SCRIPT_KEYS) {
      const v = n[k];
      if (typeof v === 'string' && v.trim().length > 20) {
        const ref = n.propertyName ?? n.componentName ?? (n.id || '').slice(0, 8);
        scriptRefs.push(`${ref}.${k} (${v.length} chars)`);
      }
    }
  }

  (form.components ?? []).forEach(c => walk(c, visit));

  const fs2 = form.formSettings ?? {};
  const lines = [];
  lines.push(`# Form: ${name}`);
  lines.push('');
  lines.push(`Generated: ${new Date().toISOString()}`);
  if (fs2.modelType) lines.push(`Bound entity: \`${fs2.modelType}\``);
  if (fs2.access != null) lines.push(`Access: ${fs2.access}${fs2.access === 5 ? ' (anonymous)' : ''}`);
  if (fs2.layout) lines.push(`Layout: ${fs2.layout}`);
  if (fs2.dataLoaderType) lines.push(`dataLoader: ${fs2.dataLoaderType}`);
  if (fs2.dataSubmitterType) lines.push(`dataSubmitter: ${fs2.dataSubmitterType}`);
  lines.push('');

  lines.push('## Component counts');
  lines.push('');
  Object.entries(counts).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
    lines.push(`- ${t}: ${c}`);
  });
  lines.push('');

  if (propertyBindings.length) {
    lines.push(`## Bound properties (${propertyBindings.length})`);
    lines.push('');
    propertyBindings.slice(0, 60).forEach(p => lines.push(`- ${p}`));
    if (propertyBindings.length > 60) lines.push(`- ...and ${propertyBindings.length - 60} more`);
    lines.push('');
  }

  // Form-level scripts
  const formLevelScripts = [];
  for (const k of SCRIPT_KEYS) {
    const v = fs2[k];
    if (typeof v === 'string' && v.trim().length > 20) {
      formLevelScripts.push(`formSettings.${k} (${v.length} chars)`);
    }
  }

  if (formLevelScripts.length || scriptRefs.length) {
    lines.push(`## Embedded scripts (${formLevelScripts.length + scriptRefs.length})`);
    lines.push('');
    formLevelScripts.forEach(s => lines.push(`- ${s}`));
    scriptRefs.slice(0, 30).forEach(s => lines.push(`- ${s}`));
    if (scriptRefs.length > 30) lines.push(`- ...and ${scriptRefs.length - 30} more`);
    lines.push('');
  }

  return lines.join('\n');
}

// ---------- main ----------

function parseArgs(argv) {
  const args = { input: null, out: null, type: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out') args.out = argv[++i];
    else if (a === '--type') args.type = argv[++i];
    else if (a === '-h' || a === '--help') args.help = true;
    else if (!args.input) args.input = a;
  }
  return args;
}

function defaultOutPath(inputPath) {
  if (inputPath === '-') return '/dev/stdout';
  const dir = path.dirname(inputPath);
  const base = path.basename(inputPath, path.extname(inputPath)).replace(/\.raw$/i, '');
  return path.join(dir, base + '.summary.md');
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.input) {
    console.error('Usage: node summarize.js <input.json|-> [--out <output.md>] [--type form|metadata]');
    process.exit(args.help ? 0 : 2);
  }

  const raw = readInput(args.input);
  let json;
  try { json = JSON.parse(raw); }
  catch (e) {
    console.error(`Failed to parse JSON: ${e.message}`);
    process.exit(3);
  }

  const payload = unwrap(json);
  const type = args.type || detectType(payload);
  if (!type) {
    console.error('Could not auto-detect type. Pass --type form|metadata.');
    process.exit(4);
  }

  const baseName = args.input === '-'
    ? 'stdin'
    : path.basename(args.input, path.extname(args.input)).replace(/\.raw$/i, '');

  const md = (type === 'metadata') ? summarizeMetadata(payload) : summarizeForm(payload, baseName);
  const out = args.out ?? defaultOutPath(args.input);

  if (out === '/dev/stdout') {
    process.stdout.write(md);
  } else {
    fs.writeFileSync(out, md);
    const tokens = Math.ceil(md.length / 4);
    console.log(`Wrote ${out} (${md.length} chars, ~${tokens} tokens)`);
  }
}

main();
