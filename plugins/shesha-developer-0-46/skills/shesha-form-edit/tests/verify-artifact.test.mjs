/*
 * Tests for scripts/verify-artifact.mjs.
 *
 * The two headline cases are lifted straight from real build retrospectives,
 * so they are regression tests for failures that actually shipped:
 *
 *   "dangling form reference"  — a datalist pointing at a row-template form
 *                                that was never created. The agent reported
 *                                "53 components, everything checks out".
 *   "output never written"     — the agent burned 50 tool calls and produced
 *                                no file, then reported completion.
 *
 * The rest guard the property that makes this gate worth trusting: it must
 * never report a pass for something it did not actually look at.
 *
 * Run: node --test tests/
 * (no dependencies; the backend is a stub http server on an ephemeral port)
 */

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(HERE, '..', 'scripts', 'verify-artifact.mjs');

let tmp;
let server;
let backend;

/** Forms the stub backend knows about. Anything else resolves to result:null. */
const EXISTING_FORMS = new Set(['Vet/animal-patient-detail', 'Shesha/entity-card']);

before(async () => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-artifact-'));

  server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const key = `${url.searchParams.get('Module')}/${url.searchParams.get('Name')}`;
    res.setHeader('content-type', 'application/json');
    // Shesha returns an ABP envelope; a missing form is result:null, not a 404.
    res.end(
      JSON.stringify(
        EXISTING_FORMS.has(key)
          ? { result: { configuration: { id: '11111111-1111-4111-8111-111111111111', name: key } }, success: true }
          : { result: null, success: true }
      )
    );
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  backend = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise((r) => server.close(r));
  fs.rmSync(tmp, { recursive: true, force: true });
});

// ------------------------------------------------------------------- helpers

const uuid = (n) => `${String(n).padStart(8, '0')}-1111-4111-8111-111111111111`;

const comp = (i, over = {}) => ({
  id: uuid(i),
  parentId: 'root',
  type: 'textField',
  propertyName: `field${i}`,
  ...over,
});

function fixture(name, body) {
  const file = path.join(tmp, name);
  fs.writeFileSync(file, typeof body === 'string' ? body : JSON.stringify(body, null, 2));
  return file;
}

/**
 * Must be async: the stub backend is served by THIS process, so a synchronous
 * spawn would block the event loop and the child's request would never be
 * answered (it just times out 15s later, looking like an unreachable backend).
 */
function run(file, ...args) {
  return new Promise((resolve) => {
    execFile(process.execPath, [SCRIPT, file, '--json', ...args], { encoding: 'utf8' }, (err, stdout, stderr) => {
      let parsed = null;
      try {
        parsed = JSON.parse(stdout);
      } catch {
        /* non-JSON output only happens on arg errors */
      }
      resolve({ code: err ? err.code : 0, json: parsed, stdout, stderr });
    });
  });
}

const fam = (json, name) => json.families.find((f) => f.name === name);
const allText = (entries) => entries.map((e) => `${e.where} ${e.message ?? e.reason}`).join('\n');

// ----------------------------------------------------- the retrospective cases

describe('regressions from real build retrospectives', async () => {
  test('a datalist pointing at a form that does not exist is a hard failure', async () => {
    const file = fixture('dangling.json', {
      components: [
        comp(1, {
          type: 'datalist',
          propertyName: 'patients',
          formId: { name: 'animal-patient-card', module: 'Vet' },
        }),
      ],
    });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(json.verdict, 'fail');
    assert.equal(code, 1);

    const refs = fam(json, 'references');
    assert.equal(refs.failures.length, 1);
    assert.match(allText(refs.failures), /Vet\/animal-patient-card.*does not exist/s);
  });

  test('an output file the agent never wrote is an error, not a pass', async () => {
    const { code, json } = await run(path.join(tmp, 'never-written.json'), '--backend', backend);
    assert.equal(json.verdict, 'error');
    assert.equal(code, 2);
    assert.match(allText(fam(json, 'file').failures), /never wrote it/);
  });

  test('a form whose references all resolve passes with non-zero coverage', async () => {
    const file = fixture('valid.json', {
      components: [
        comp(1),
        comp(2, {
          type: 'datalist',
          propertyName: 'patients',
          formId: { name: 'animal-patient-detail', module: 'Vet' },
        }),
      ],
    });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(json.verdict, 'pass');
    assert.equal(code, 0);
    // A pass is only meaningful if it actually checked something.
    assert.ok(fam(json, 'structure').checked > 0);
    assert.equal(fam(json, 'references').checked, 1);
  });
});

// -------------------------------------------------- the no-false-green property

describe('never reports a pass for what it did not inspect', async () => {
  test('references are partial, not pass, when no backend is supplied', async () => {
    const file = fixture('unresolved.json', {
      components: [comp(1, { type: 'datalist', formId: { name: 'animal-patient-detail', module: 'Vet' } })],
    });

    const { code, json } = await run(file);
    assert.equal(json.verdict, 'partial');
    assert.equal(code, 3);
    assert.match(allText(fam(json, 'references').uninspectable), /never resolved/);
  });

  test('a code-mode formId is named as uninspectable rather than skipped silently', async () => {
    const file = fixture('codemode.json', {
      components: [comp(1, { type: 'datalist', formId: { _mode: 'code', _code: 'return x;' } })],
    });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(json.verdict, 'partial');
    assert.equal(code, 3);
    assert.match(allText(fam(json, 'references').uninspectable), /code-mode/);
  });

  test('a backend that cannot be reached is uninspectable, never a pass', async () => {
    const file = fixture('unreachable.json', {
      components: [comp(1, { type: 'datalist', formId: { name: 'whatever', module: 'Vet' } })],
    });

    // Port 1 is reserved and refuses connections.
    const { code, json } = await run(file, '--backend', 'http://127.0.0.1:1');
    assert.equal(json.verdict, 'partial');
    assert.equal(code, 3);
    assert.equal(fam(json, 'references').failures.length, 0);
    assert.match(allText(fam(json, 'references').uninspectable), /failed/);
  });

  test('a form with no components fails rather than reporting an empty pass', async () => {
    const file = fixture('hollow.json', { components: [], formSettings: {} });
    const { code, json } = await run(file, '--backend', backend);
    assert.equal(json.verdict, 'fail');
    assert.equal(code, 1);
    assert.match(allText(fam(json, 'structure').failures), /not a usable form/);
  });
});

// ------------------------------------------------------------ structure checks

describe('structure', async () => {
  test('missing parentId fails — it crashes the renderer with no useful error', async () => {
    const c = comp(1);
    delete c.parentId;
    const file = fixture('noparent.json', { components: [c] });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(code, 1);
    assert.match(allText(fam(json, 'structure').failures), /missing "parentId"/);
  });

  test('duplicate ids fail and name both sites', async () => {
    const file = fixture('dupe.json', { components: [comp(1), { ...comp(2), id: uuid(1) }] });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(code, 1);
    assert.match(allText(fam(json, 'structure').failures), /duplicate "id"/);
  });

  test('an unstamped {{TOKEN}} id fails in a build output but is expected under --seed', async () => {
    const file = fixture('unstamped.json', { components: [comp(1, { id: '{{GEN_KEY}}' })] });

    const build = await run(file, '--backend', backend);
    assert.equal(build.code, 1);
    assert.match(allText(fam(build.json, 'structure').failures), /stampTree did not run/);

    const seed = await run(file, '--backend', backend, '--seed');
    assert.equal(seed.json.verdict, 'partial');
    assert.equal(seed.code, 3);
    assert.equal(fam(seed.json, 'structure').failures.length, 0);
  });

  test('nanoid ids are accepted as legitimate, only reported as unjudged coverage', async () => {
    // Real Shesha forms are full of these; asserting UUID-only would flag ~110
    // findings against canonical seeds that render perfectly well.
    const file = fixture('nanoid.json', {
      components: [comp(1, { id: '8jJ1tFFwhdXB8tGQn7xbB2cwTvcPLe' })],
    });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(json.verdict, 'partial');
    assert.equal(code, 3);
    assert.equal(fam(json, 'structure').failures.length, 0);
    assert.match(allText(fam(json, 'structure').uninspectable), /not UUIDs/);
  });
});

// --------------------------------------------------------------- file handling

describe('artifact unwrapping', async () => {
  test('an ABP envelope with double-stringified markup is unwrapped', async () => {
    const markup = JSON.stringify({ components: [comp(1)], formSettings: {} });
    const file = fixture('envelope.json', { result: { id: 'x', markup }, success: true });

    const { code, json } = await run(file, '--backend', backend);
    assert.equal(json.verdict, 'pass');
    assert.equal(code, 0);
    assert.equal(fam(json, 'structure').walked, 1);
  });

  test('an empty file is an error', async () => {
    const { code, json } = await run(fixture('empty.json', ''));
    assert.equal(json.verdict, 'error');
    assert.equal(code, 2);
    assert.match(allText(fam(json, 'file').failures), /empty/);
  });

  test('a non-JSON file is an error naming the parse problem', async () => {
    const { code, json } = await run(fixture('garbage.json', 'this is not json {{'));
    assert.equal(json.verdict, 'error');
    assert.equal(code, 2);
    assert.match(allText(fam(json, 'file').failures), /not valid JSON/);
  });

  test('a BOM-prefixed file still parses (PowerShell writes these constantly)', async () => {
    const file = fixture('bom.json', '﻿' + JSON.stringify({ components: [comp(1)] }));
    const { code } = await run(file, '--backend', backend);
    assert.equal(code, 0);
  });
});
