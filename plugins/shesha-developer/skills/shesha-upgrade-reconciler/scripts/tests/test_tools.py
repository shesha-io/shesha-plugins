"""Offline unit tests for scripts/tools/* and core/browse.py + core/metadata.py. No network, no browser, no backend.

Run:  python -m unittest tests.test_tools        (from the scripts/ directory)   or   python shrec.py selftest -q
Every test that needs a project builds a throw-away one in a temp directory (SHREC_PROJECT / SHREC_WORK) with neutral values.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import ledger, packs, project          # noqa: E402

PROJECT = {
    'name': 'demo', 'modules': ['Demo.Module'],
    'environments': {
        'reference': {'api': 'https://ref.example.com', 'portal': 'https://ref-portal.example.com', 'version': '0.43.38'},
        'local': {'api': 'http://localhost:21021', 'portal': 'http://localhost:3000', 'version': '0.46.1'},
        'deployed': {'api': 'https://dep.example.com', 'portal': 'https://dep-portal.example.com', 'version': '0.46.1'},
    },
    'options': {'entityNamespaces': ['{module}.Domain'], 'probeStyleClasses': ['my-carrier']},
}
HOST = 'http://localhost:21021'


def write_lines(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')


class TempProject(unittest.TestCase):
    """A throw-away project (SHREC_PROJECT) with its own work directory (SHREC_WORK)."""
    options = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='shrec-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, project.DIRNAME)
        os.makedirs(self.home)
        cfg = json.loads(json.dumps(PROJECT))
        if self.options is not None:
            cfg['options'] = self.options
        with open(os.path.join(self.home, 'project.json'), 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        self.work = os.path.join(self.tmp, 'work')
        p = mock.patch.dict(os.environ, {'SHREC_PROJECT': self.tmp, 'SHREC_WORK': self.work})
        p.start()
        self.addCleanup(p.stop)

    def ledger(self, rows):
        write_lines(project.ledger_path(), rows)


def ev(name, ts, **kw):
    e = {'event': name, 'ts': ts, 'run': kw.pop('run', 'R1'), 'batch': kw.pop('batch', 'B1'), 'env': kw.pop('env', 'local'),
         'host': kw.pop('host', HOST)}
    e.update(kw)
    return e


def pushed(ts, form, rule='status-buttons', notes=None, module='Demo.Module', **kw):
    return ev('form', ts, module=module, form=form, rule=rule, result='pushed', mode='push', form_id='id-' + form,
              notes=notes or [f'{form}: changed by {rule}'], **kw)


# ---------------------------------------------------------------- leakcheck
class LeakcheckTests(unittest.TestCase):
    def setUp(self):
        from tools import leakcheck
        self.m = leakcheck
        self.tmp = tempfile.mkdtemp(prefix='shrec-leak-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def put(self, rel, data, mode='w'):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, mode + ('b' if isinstance(data, bytes) else ''), **({} if isinstance(data, bytes) else {'encoding': 'utf-8'})) as f:
            f.write(data)
        return p

    def test_terms_guid_binary_and_skips(self):
        root = os.path.join(self.tmp, 'tree')
        os.makedirs(root)
        self.put('tree/a.txt', 'line one\nthis mentions SecretCorp here\n')
        guid = '-'.join(['3f2504e0', '4f89', '11d3', '9a0c', '0305e82c3301'])      # built at run time: no GUID literal in the source
        self.put('tree/sub/b.json', json.dumps({'id': guid}) + '\n')
        self.put('tree/bin.dat', b'\x00\x01 secretcorp \x00')
        self.put('tree/.git/config', 'secretcorp\n')
        self.put('tree/node_modules/x.js', 'secretcorp\n')
        deny = self.put('deny.txt', '# comment\n\nsecretcorp\n')
        hits = self.m.scan(root, self.m.load_terms(deny), guid=True, deny_file=deny)
        got = sorted((os.path.relpath(p, root).replace('\\', '/'), n, t) for p, n, t in hits)
        self.assertEqual(got, [('a.txt', 2, 'secretcorp'), ('sub/b.json', 1, 'GUID')])
        no_guid = self.m.scan(root, ['secretcorp'], guid=False)
        self.assertEqual([t for _, _, t in no_guid], ['secretcorp'])

    def test_cli_exit_codes_and_output(self):
        root = os.path.join(self.tmp, 'tree')
        os.makedirs(root)
        self.put('tree/a.txt', 'Acme appears\n')
        deny = os.path.join(root, 'deny.txt')                    # the deny file inside the scanned tree is never reported
        with open(deny, 'w', encoding='utf-8') as f:
            f.write('acme\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.m.main(['--deny-file', deny, '--root', root])
        self.assertEqual(code, 1)
        self.assertIn('a.txt:1:acme', out.getvalue().replace('\\', '/'))
        self.assertNotIn('deny.txt:', out.getvalue())
        os.remove(os.path.join(root, 'a.txt'))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.m.main(['--deny-file', deny, '--root', root]), 0)
            self.assertEqual(self.m.main(['--deny-file', os.path.join(root, 'missing.txt'), '--root', root]), 2)


# ---------------------------------------------------------------- report
class ReportTests(TempProject):
    def setUp(self):
        super().setUp()
        from tools import report
        self.r = report

    def build(self, rows, defects=None, all_events=None):
        self.ledger(rows)
        return self.r.build(rows, all_events or rows, defects={} if defects is None else defects, now='2026-01-01 00:00')

    def test_dry_run_headline(self):
        text = self.build([ev('form', '2026-01-01T10:00:00', module='M', form='f', rule='r', result='dry-run', mode='dry-run', notes=['x'])])
        self.assertIn('STATUS: DRY RUN - nothing written', text)
        self.assertIn('NOTHING WAS WRITTEN', text)

    def test_unverified_until_a_browser_check_follows_the_last_push(self):
        rows = [pushed('2026-01-01T10:00:00', 'a'), pushed('2026-01-01T10:05:00', 'b')]
        self.assertIn('UNVERIFIED IN BROWSER', self.build(rows))
        stale = rows + [ev('verify', '2026-01-01T10:01:00', kind='browser', result='ok', detail='looked fine')]
        text = self.build(stale)
        self.assertIn('UNVERIFIED IN BROWSER', text)
        self.assertIn('BEFORE the last push', text)
        fresh = rows + [ev('verify', '2026-01-01T10:10:00', kind='browser', result='ok', detail='looked fine')]
        text = self.build(fresh)
        self.assertIn('browser-verified', text)
        self.assertNotIn('UNVERIFIED IN BROWSER', text)
        failed = rows + [ev('verify', '2026-01-01T10:10:00', kind='browser', result='fail', detail='tab is blank')]
        text = self.build(failed)
        self.assertIn('UNVERIFIED IN BROWSER', text)
        self.assertIn('tab is blank', text)

    def test_leftover_probe_is_flagged_and_kept_out_of_the_export_list(self):
        rows = [pushed('2026-01-01T10:00:00', 'real-form'),
                pushed('2026-01-01T10:01:00', 'probed-form', rule='probe-scope',
                       notes=['TEMPORARY probe added: btn.expression (script-scope dump) - must be removed']),
                ev('verify', '2026-01-01T10:30:00', kind='browser', result='ok', detail='ok')]
        text = self.build(rows)
        self.assertIn('UNVERIFIED IN BROWSER', text)                 # a browser ok does not cover a probe left in a form
        self.assertIn('probe was left behind', text)
        self.assertIn('probe-scope Demo.Module/probed-form --remove --push', text)
        export = self.r.export_rows(rows)
        self.assertEqual([x['form'] for x in export], ['real-form'])  # the probe-only form is not a change to export
        self.assertIn('TEMPORARY / diagnostic', text)
        removed = rows[:2] + [pushed('2026-01-01T10:20:00', 'probed-form', rule='probe-scope', notes=['probe removed: 1 marker block(s)'])]
        self.assertEqual([x['form'] for x in self.r.export_rows(removed)], ['real-form'])
        self.assertEqual(self.r.leftovers(self.r.pushed_events(removed)), {})

    def test_export_list_starts_after_the_last_export_event(self):
        rows = [pushed('2026-01-01T09:00:00', 'one'), pushed('2026-01-01T09:05:00', 'two'),
                ev('export', '2026-01-01T09:10:00', package='20260101_a.shaconfig', forms=['Demo.Module/one', 'Demo.Module/two']),
                pushed('2026-01-01T09:20:00', 'three'), pushed('2026-01-01T09:25:00', 'two', notes=['two: changed again'])]
        since = self.r.last_export_ts(rows)
        self.assertEqual(since, '2026-01-01T09:10:00')
        self.assertEqual([x['form'] for x in self.r.export_rows(rows, since)], ['three', 'two'])
        self.assertEqual([x['form'] for x in self.r.export_rows(rows)], ['one', 'three', 'two'])
        text = self.build(rows)
        self.assertIn('Demo.Module/three', text)
        self.assertIn('--reviewer-approved', text)
        self.assertNotIn('Demo.Module/one,', text)
        self.assertEqual(self.r.export_list_text(self.r.export_rows(rows, since)), 'Demo.Module/three\nDemo.Module/two\n')

    def test_restored_forms_and_other_configs_are_not_exported(self):
        rows = [pushed('2026-01-01T09:00:00', 'a'), pushed('2026-01-01T09:30:00', 'a', rule='restore', notes=['restored from run R1 (before, taken x)']),
                ev('form', '2026-01-01T09:40:00', module='Demo.Module/Thing', form='row 1', rule='r', result='pushed', mode='push', kind='entity',
                   form_id='e1', notes=['entity field changed'])]
        self.assertEqual(self.r.export_rows(rows), [])
        text = self.build(rows)
        self.assertIn('Other configs touched (not forms):', text)
        self.assertIn('entity: Demo.Module/Thing / row 1', text)

    def test_retire_candidates_use_the_pack_and_the_target_version(self):
        pack = {'id': 'x', 'version': '1', 'rules': [{'id': 'r-fixed', 'retire': 'm:retire', 'fixedIn': '0.46.1', 'fixedEvidence': 'verified'},
                                                        {'id': 'r-later', 'retire': 'm:retire', 'fixedIn': '0.46.5'},
                                                        {'id': 'r-never', 'retire': None, 'fixedIn': None}]}
        rows = [pushed('2026-01-01T09:00:00', 'a', rule='r-fixed'), pushed('2026-01-01T09:00:01', 'a', rule='r-later'),
                pushed('2026-01-01T09:00:02', 'b', rule='r-never')]
        with mock.patch.object(packs, 'pack_for', return_value=pack):
            cands, why = self.r.retire_candidates(rows)
            self.assertEqual([c['id'] for c, _ in cands], ['r-fixed'])
            self.assertIn('0.46.1', why)
            text = self.build(rows)
            self.assertIn('## 6. RETIRE CANDIDATES', text)
            self.assertIn('| r-fixed | 0.46.1 | verified | 1 |', text)
            self.assertNotIn('| r-later |', text)
            # a rule that was already retired after its last application is no longer a candidate
            done = rows + [ev('retire', '2026-01-01T09:30:00', module='Demo.Module', form='a', rule='r-fixed', result='pushed', notes=['unwound'])]
            self.assertEqual(self.r.retire_candidates(done)[0], [])
        with mock.patch.object(packs, 'pack_for', return_value=None):
            self.assertEqual(self.r.retire_candidates(rows)[0], [])

    def test_retire_candidates_below_the_fixed_version(self):
        cfg = json.loads(json.dumps(PROJECT))
        cfg['environments']['local']['version'] = '0.46.0'
        project.write_json(os.path.join(self.home, 'project.json'), cfg)
        pack = {'id': 'x', 'rules': [{'id': 'r-fixed', 'retire': 'm:retire', 'fixedIn': '0.46.1'}]}
        with mock.patch.object(packs, 'pack_for', return_value=pack):
            cands, _ = self.r.retire_candidates([pushed('2026-01-01T09:00:00', 'a', rule='r-fixed')])
        self.assertEqual(cands, [])

    def test_definition_of_done_table_accepts_the_old_kind_name(self):
        rows = [pushed('2026-01-01T09:00:00', 'a')] + [ev('verify', '2026-01-01T09:30:0%d' % i, kind=k, result='ok', detail=f'{k} checked')
                                                      for i, k in enumerate(self.r.DOD_REQUIRED)]
        rows.append(ev('verify', '2026-01-01T09:31:00', kind='owner', result='ok', detail='tried it in a clean browser'))
        text = self.build(rows)
        self.assertIn('All six required items are recorded ok after the last push', text)
        self.assertIn('(`reviewer`)', text)
        self.assertIn('tried it in a clean browser', text)
        self.assertNotIn('Iron rule', text)
        missing = self.build([pushed('2026-01-01T09:00:00', 'a'), ev('verify', '2026-01-01T09:01:00', kind='placement', result='ok', detail='d')])
        self.assertIn('Iron rule', missing)
        self.assertIn('request-audit', missing)
        self.assertEqual(self.r.norm_kind('owner'), 'reviewer')
        self.assertEqual(self.r.norm_kind('write'), 'write-path')

    def test_defects_fold_by_status_and_hazard_with_rule_links(self):
        path = os.path.join(self.home, 'defects.jsonl')
        write_lines(path, [{'id': 'D-1', 'title': 'blank tag', 'status': 'open', 'hazard': 'H33', 'rule': 'status-buttons',
                            'where': {'module': 'Demo.Module', 'form': 'a', 'component': 'tag1'}},
                           {'id': 'D-2', 'title': 'wrapped label', 'status': 'open', 'hazard': 'H20'},
                           {'id': 'D-1', 'status': 'fixed', 'evidence': 'verified on local'}])
        folded = self.r.fold_defects()
        self.assertEqual(folded['D-1']['status'], 'fixed')            # later lines win field by field
        self.assertEqual(folded['D-1']['title'], 'blank tag')
        self.assertEqual(folded['D-1']['hazard'], 'H33')
        text = self.build([pushed('2026-01-01T09:00:00', 'a')], defects=folded)
        self.assertIn('Status: open 1 | fixed 1', text)
        self.assertIn('| D-1 | fixed | H33 | Demo.Module/a/tag1 | blank tag | [status-buttons](#status-buttons) |', text)
        self.assertIn('| H20 | 1 | 1 |', text)
        self.assertIn('#### status-buttons', text)

    def test_sections_by_rule_and_batch_and_revert_commands(self):
        rows = [pushed('2026-01-01T09:00:00', 'a', batch='batch-1'), pushed('2026-01-01T09:01:00', 'b', rule='other-rule', batch='batch-2')]
        text = self.build(rows)
        for needle in ('## 1. Where changes were written', '### Updated, by rule', '### By batch', '| batch-1 | 1 | status-buttons |',
                       'shrec.py restore --run R1 --target local --all', '## 4. What to export', '## 5. Defects', '## 8. Next steps'):
            self.assertIn(needle, text)

    def test_main_writes_markdown_html_and_export_list(self):
        self.ledger([pushed('2026-01-01T09:00:00', 'a'), pushed('2026-01-01T09:01:00', 'b')])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.r.main(['--all', '--html'])
        self.assertEqual(code, 0)
        reports = os.path.join(self.work, 'reports')
        names = sorted(os.listdir(reports))
        self.assertEqual([os.path.splitext(n)[1] for n in names if not n.endswith('-export-list.txt')], ['.html', '.md'])
        lst = [n for n in names if n.endswith('-export-list.txt')][0]
        with open(os.path.join(reports, lst), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'Demo.Module/a\nDemo.Module/b\n')

    def test_html_is_self_contained_with_light_and_dark_css(self):
        text = self.build([pushed('2026-01-01T09:00:00', 'a')])
        page = self.r.md_to_html(text)
        self.assertTrue(page.startswith('<!doctype html>'))
        self.assertIn('prefers-color-scheme:dark', page)
        self.assertIn('<style>', page)
        self.assertIn('class="banner warn"', page)
        self.assertNotIn('<link', page)
        self.assertNotIn('<script', page)
        self.assertNotIn('src=', page)
        self.assertIn('<table>', page)
        self.assertIn('<h2 id="1-where-changes-were-written">', page)


# ---------------------------------------------------------------- detect
class DetectTests(unittest.TestCase):
    def setUp(self):
        from tools import detect
        self.d = detect

    def test_selftest_passes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            ok = self.d.selftest(quiet=True)
        self.assertTrue(ok, getattr(self.d.selftest, 'failed', None))

    def test_docstring_lists_exactly_the_covered_hazards(self):
        doc = self.d.__doc__
        for h in ('H47', 'H49', 'H50', 'H51', 'H52', 'H1 and H3-H18'):
            self.assertIn(h, doc)
        for h in ('H48', 'H53'):
            self.assertNotIn(h, doc)

    def test_sibling_missing_prints_one_note_and_continues(self):
        with mock.patch.dict(os.environ, {'SHREC_SCAN_HAZARDS': os.path.join(tempfile.gettempdir(), 'no-such-scan.mjs')}):
            findings, notes = self.d.run_sibling({'f': {'module': 'M', 'name': 'f', 'markup': {'components': []}}})
        self.assertEqual(findings, [])
        self.assertEqual(len(notes), 1)
        self.assertIn('not found', notes[0])

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_sibling_output_is_mapped_to_the_finding_line_format(self):
        tmp = tempfile.mkdtemp(prefix='shrec-scan-test-')
        self.addCleanup(shutil.rmtree, tmp, True)
        script = os.path.join(tmp, 'scan.mjs')
        with open(script, 'w', encoding='utf-8') as f:
            f.write("import fs from 'node:fs'; import path from 'node:path';\n"
                    "const d = process.argv[2]; const out = fs.readdirSync(d).map((n) => ({file: path.join(d, n), findings: ["
                    "{id: 'H10', ptr: '/components/0', component: 'btn', message: 'unguarded chain'},"
                    "{id: 'H2', ptr: '/x', component: 'x', message: 'not a markup detector in scope'},"
                    "{id: 'syntax', ptr: '/y', component: 'y', message: 'syntax'}]}));\n"
                    "console.log(JSON.stringify(out)); process.exit(1);\n")
        forms = {'M/f': {'module': 'M', 'name': 'f', 'markup': {'components': []}}, 'M/g': {'module': 'M', 'name': 'g', 'markup': {'components': []}}}
        findings, notes = self.d.run_sibling(forms, only={'g'}, script=script)
        self.assertEqual(findings, [{'form': 'M/g', 'component': 'btn', 'check': 'scan-H10', 'severity': 'review',
                                     'evidence': 'unguarded chain (/components/0)'}])
        self.assertTrue(any('covered H1 and H3-H18' in n for n in notes))
        buf = io.StringIO()
        self.d.report(findings, notes, 1, buf)
        self.assertIn('M/g | btn | scan-H10 | review | unguarded chain (/components/0)', buf.getvalue())

    def test_cli_on_a_markup_file(self):
        tmp = tempfile.mkdtemp(prefix='shrec-detect-')
        self.addCleanup(shutil.rmtree, tmp, True)
        p = os.path.join(tmp, 'f.json')
        mk = {'formSettings': {'modelType': 'X'}, 'components': [{'id': 'c1', 'type': 'datatableContext', 'componentName': 'ctx', 'parentId': 'root',
                                                                  'sourceType': 'Url', 'endpoint': '/api/dynamic/M/E/Crud/GetAll?filter=x'}]}
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(mk, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.d.main(['--markup', p, '--checks', 'url-endpoint-query'])
        self.assertEqual(code, 1)
        self.assertIn('f | ctx | url-endpoint-query | trap |', out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.d.main(['--markup', p, '--checks', 'parent-id']), 0)
        self.assertIn('clean', out.getvalue())


# ---------------------------------------------------------------- restore planning
class RestoreTests(TempProject):
    RUN = '20260101-090000'

    def setUp(self):
        super().setUp()
        from tools import restore
        from core import push
        self.m, self.push = restore, push
        self.rundir = os.path.join(self.work, 'backups', 'local', self.RUN)

    def backup(self, sub, fname, **kw):
        w = {'role': 'local', 'host': HOST, 'timestamp': kw.pop('timestamp', '2026-01-01T09:00:00'), 'module': 'Demo.Module', 'name': 'a',
             'id': 'id-a', 'modelType': 'Demo.Domain.A', 'row': {'id': 'id-a', 'markup': '{"components": []}', 'modelType': 'Demo.Domain.A'}}
        w.update(kw)
        p = os.path.join(self.rundir, sub, fname)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(w, f)
        return p

    def populate(self):
        self.backup('snapshot', self.push.fname('Demo.Module', 'a'))
        self.backup('before', self.push.fname('Demo.Module', 'a', '090001001'), timestamp='2026-01-01T09:00:01')
        self.backup('before', self.push.fname('Demo.Module', 'a', '090500001'), timestamp='2026-01-01T09:05:00',
                    row={'id': 'id-a', 'markup': '{"components": [1]}', 'modelType': 'Demo.Domain.A'})
        self.backup('before', self.push.fname('Demo.Module', 'b', '090002001'), name='b', id='id-b')
        self.backup('before', self.push.fname('Demo.Module', 'created', 'absent'), name='created', id=None, row=None, absent=True)
        self.backup('before', self.push.fname('Demo.Module.Thing', 'row 1.e1', '090003001'), module='Demo.Module/Thing', name='row 1', id='e1',
                    kind='entity', row={'id': 'e1', 'title': 'old', 'count': 3, 'lastModificationTime': 'x', 'child': {'id': 'c'}})
        self.backup('before', self.push.fname('workflow', 'wf', '090004001'), module='workflow', name='wf', id='w1', kind='workflow',
                    row={'id': 'w1', 'workflowSchema': '<old/>'})
        self.ledger([pushed('2026-01-01T09:00:01', 'a', run=self.RUN, rule='rule-one'),
                     pushed('2026-01-01T09:00:02', 'b', run=self.RUN, rule='rule-one,rule-two'),
                     ev('form', '2026-01-01T09:00:03', run=self.RUN, module='Demo.Module', form='created', rule='rule-two', result='pushed',
                        mode='push', form_id='new-id-1', notes=['created (missing on the target)'])])

    def test_items_by_kind_and_the_earliest_before_backup_wins(self):
        self.populate()
        items = self.m.collect_items(self.rundir)
        kinds = {it['key']: it['kind'] for it in items.values()}
        self.assertEqual(kinds, {'form:Demo.Module/a': 'form', 'form:Demo.Module/b': 'form', 'form:Demo.Module/created': 'absent',
                                 'entity:Demo.Module/Thing:row 1:e1': 'entity', 'workflow:wf:w1': 'workflow'})
        a = items['form:Demo.Module/a']
        self.assertEqual(a['before']['timestamp'], '2026-01-01T09:00:01')         # not the later per-write backup
        self.assertIsNotNone(a['snapshot'])

    def test_selection_by_form_rule_and_run(self):
        self.populate()
        items = self.m.collect_items(self.rundir)
        self.assertEqual({it['key'] for it in self.m.select(items, self.RUN, form='Demo.Module/a')}, {'form:Demo.Module/a'})
        by_rule = {it['key'] for it in self.m.select(items, self.RUN, rule='rule-two')}
        self.assertEqual(by_rule, {'form:Demo.Module/b', 'form:Demo.Module/created'})
        self.assertEqual(len(self.m.select(items, self.RUN)), 5)
        with self.assertRaises(project.WriteRefused):
            self.m.select(items, self.RUN, form='Demo.Module/missing')
        with self.assertRaises(project.WriteRefused):
            self.m.select(items, self.RUN, rule='no-such-rule')

    def test_created_forms_are_reported_never_deleted(self):
        self.populate()
        items = self.m.collect_items(self.rundir)
        it = items['form:Demo.Module/created']
        self.assertEqual(self.m.kind_of(it['before']), 'absent')
        self.assertEqual(self.m.created_form_id(self.RUN, it['before']), 'new-id-1')
        self.assertIn('deleting it is manual', self.m.plan_text(it))
        import inspect
        src = inspect.getsource(self.m)
        self.assertNotIn('.delete(', src)
        self.assertNotIn("'DELETE'", src)

    def test_entity_changes_restore_only_differing_scalar_fields(self):
        backed = {'id': 'e1', 'title': 'old', 'count': 3, 'lastModificationTime': 'x', 'child': {'id': 'c'}, 'gone': 1}
        current = {'id': 'e1', 'title': 'new', 'count': 3, 'lastModificationTime': 'y', 'child': {'id': 'd'}}
        self.assertEqual(self.m.entity_changes(backed, current), {'title': 'old'})
        self.assertEqual(self.m.entity_changes(backed, backed), {})

    def test_host_mismatch_is_detectable_from_the_wrapper(self):
        self.populate()
        items = self.m.collect_items(self.rundir)
        self.assertTrue(all(it['before']['role'] == 'local' and it['before']['host'] == HOST for it in items.values()))

    def run_main(self, args, fail_form=None):
        """restore.main with the network and the write path replaced by recorders; returns (exit code, calls, output)"""
        calls = []

        class FakeApi:
            base = HOST

            def __init__(self, role):
                self.role = role

        def fake_push(module, name, transform, dry_run=False, role=None, rule=None, model_type=None, event='form'):
            if name == fail_form:
                raise RuntimeError('simulated failure')
            markup = {'components': [2]}                       # the current markup differs from every backup
            notes = transform(markup)
            calls.append(('form', module, name, dry_run, role, rule, model_type, markup))
            return notes

        def fake_entity(module, cls, item_id, label, transform, dry_run=False, role=None, rule=None):
            changes, notes = transform({'id': item_id, 'title': 'new', 'count': 3, 'child': {'id': 'x'}})
            calls.append(('entity', module, cls, item_id, dry_run, changes))
            return notes

        def fake_workflow(item_id, name, schema, dry_run=False, role=None, rule=None):
            calls.append(('workflow', item_id, name, schema, dry_run))
            return True

        def fake_begin(forms, rule=None, role=None):
            calls.append(('begin_run', sorted(forms), rule, role))
            return 'snapdir'
        out = io.StringIO()
        with mock.patch('core.api.Api', FakeApi), mock.patch.object(self.push, 'push', fake_push), \
                mock.patch.object(self.push, 'push_entity', fake_entity), mock.patch.object(self.push, 'push_workflow_schema', fake_workflow), \
                mock.patch.object(self.push, 'begin_run', fake_begin), contextlib.redirect_stdout(out):
            code = self.m.main(args)
        return code, calls, out.getvalue()

    def test_dry_run_plans_every_kind_and_writes_nothing(self):
        self.populate()
        code, calls, out = self.run_main(['--run', self.RUN, '--target', 'local', '--all'])
        self.assertEqual(code, 0)
        self.assertFalse(any(c[0] == 'begin_run' for c in calls))                 # a dry run takes no snapshot and writes nothing
        forms = {c[2]: c for c in calls if c[0] == 'form'}
        self.assertEqual(set(forms), {'a', 'b'})
        self.assertTrue(all(c[3] is True and c[4] == 'local' and c[5] == 'restore' for c in forms.values()))
        self.assertEqual(forms['a'][7], {'components': []})                       # restored to the EARLIEST before-backup, not the later one
        ent = [c for c in calls if c[0] == 'entity'][0]
        self.assertEqual((ent[1], ent[2], ent[3], ent[4], ent[5]), ('Demo.Module', 'Thing', 'e1', True, {'title': 'old'}))
        wf = [c for c in calls if c[0] == 'workflow'][0]
        self.assertEqual((wf[1], wf[3], wf[4]), ('w1', '<old/>', True))
        self.assertIn('manual-delete-needed', out)
        self.assertIn('new-id-1', out)                                            # the created form id is printed, nothing is deleted
        self.assertIn('DRY RUN', out)
        events = [e for e in ledger.read() if e['event'] == 'restore']
        self.assertEqual(len(events), 5)
        self.assertEqual({e['result'] for e in events}, {'would-restore', 'manual-delete-needed'})
        self.assertTrue(all(e['mode'] == 'dry-run' and e['source'].endswith('.json') for e in events))

    def test_push_takes_a_snapshot_and_one_failure_does_not_stop_the_rest(self):
        self.populate()
        code, calls, out = self.run_main(['--run', self.RUN, '--target', 'local', '--all', '--push'], fail_form='a')
        self.assertEqual(code, 1)
        begin = [c for c in calls if c[0] == 'begin_run'][0]
        self.assertEqual(begin[1], [('Demo.Module', 'a'), ('Demo.Module', 'b')])
        self.assertTrue(any(c[0] == 'form' and c[2] == 'b' and c[3] is False for c in calls))     # b is still restored
        self.assertTrue(any(c[0] == 'entity' for c in calls) and any(c[0] == 'workflow' for c in calls))
        self.assertIn('FAILED', out)
        results = {e['form']: e['result'] for e in ledger.read() if e['event'] == 'restore'}
        self.assertEqual(results['a'], 'failed')
        self.assertEqual(results['b'], 'restored')

    def test_a_backup_from_another_host_is_refused(self):
        self.populate()
        self.backup('before', self.push.fname('Demo.Module', 'c', '090009001'), name='c', host='https://other.example.com')
        with self.assertRaises(project.WriteRefused):
            self.run_main(['--run', self.RUN, '--target', 'local', '--all'])

    def test_list_runs(self):
        self.populate()
        write_lines(os.path.join(self.rundir, 'manifest.json'), [{'run': self.RUN, 'rule': 'rule-one', 'host': HOST, 'forms': [{}]}])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.list_runs('local')
        self.assertIn(self.RUN, out.getvalue())


# ---------------------------------------------------------------- snapshot (version keyed)
class SnapshotTests(unittest.TestCase):
    ROWS = [{'id': '1', 'name': 'f', 'module': {'name': 'M'}, 'versionStatus': 1},
            {'id': '2', 'name': 'f', 'module': {'name': 'M'}, 'versionStatus': 3},
            {'id': '3', 'name': 'g', 'module': {'name': 'M'}, 'versionStatus': 2},
            {'id': '4', 'name': 'g', 'module': {'name': 'M'}, 'versionStatus': 3}]

    def setUp(self):
        from tools import snapshot
        self.s = snapshot

    def test_versioned_roles_keep_live_rows_only(self):
        for v in ('0.43.38', '0.44.9'):
            kept, warn = self.s.keep_live_rows(self.ROWS, v)
            self.assertEqual([r['id'] for r in kept], ['2', '4'], v)
            self.assertIsNone(warn)

    def test_unversioned_roles_keep_everything(self):
        kept, warn = self.s.keep_live_rows(self.ROWS, '0.46.1')
        self.assertEqual(len(kept), 4)
        self.assertIsNone(warn)
        self.assertEqual(len(self.s.keep_live_rows(self.ROWS, '0.45.0')[0]), 4)

    def test_unknown_version_with_duplicates_keeps_live_and_warns(self):
        kept, warn = self.s.keep_live_rows(self.ROWS, None)
        self.assertEqual([r['id'] for r in kept], ['2', '4'])
        self.assertIn('version unknown', warn)
        single = [self.ROWS[1], self.ROWS[3]]
        self.assertEqual(self.s.keep_live_rows(single, None), (single, None))

    def test_versioned_is_keyed_on_the_version_not_a_name(self):
        self.assertTrue(self.s.versioned('0.43.38'))
        self.assertFalse(self.s.versioned('0.45.0'))
        self.assertFalse(self.s.versioned('0.46.1'))
        self.assertIsNone(self.s.versioned(None))
        self.assertIsNone(self.s.versioned('x'))

    def test_snapshot_files_and_index_layout(self):
        tmp = tempfile.mkdtemp(prefix='shrec-snap-')
        self.addCleanup(shutil.rmtree, tmp, True)
        items = [dict(self.ROWS[1], markup='{"components": []}')]
        idx = self.s.write_snapshot('reference', mock.Mock(), items, out_root=tmp)
        self.assertEqual(idx[0]['file'], 'reference/M/f.json')
        self.assertTrue(os.path.exists(os.path.join(tmp, 'reference', 'M', 'f.json')))
        self.assertTrue(os.path.exists(os.path.join(tmp, 'reference-index.json')))
        with open(os.path.join(tmp, 'reference', 'M', 'f.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['markup'], {'components': []})


# ---------------------------------------------------------------- core/browse + core/metadata
class BrowseTests(TempProject):
    def test_playwright_is_not_imported_by_the_modules(self):
        import importlib
        for name in [m for m in sys.modules if m.startswith('playwright')]:
            sys.modules.pop(name)
        importlib.reload(importlib.import_module('core.browse'))
        importlib.import_module('tools.capture')
        self.assertFalse(any(m.startswith('playwright') for m in sys.modules))

    def test_guard_decisions(self):
        from core import browse
        ref_hosts = {'ref.example.com', 'ref-portal.example.com'}
        g = lambda role, url, method, allow=False: browse.blocked_by_guard(role, url, method, ref_hosts, HOST, allow)[0]
        self.assertEqual(g('reference', 'https://ref.example.com/api/services/app/Thing/GetAll', 'GET'), 'allow')
        self.assertEqual(g('reference', 'https://ref.example.com/api/services/app/Metadata/Get', 'POST'), 'allow')
        self.assertEqual(g('reference', 'https://ref.example.com/api/dynamic/M/E/Crud/Update', 'PUT'), 'block')
        self.assertEqual(g('reference', 'https://ref.example.com/api/dynamic/M/E/Crud/Create', 'POST'), 'block')
        self.assertEqual(g('reference', HOST + '/api/dynamic/M/E/Crud/Update', 'PUT', True), 'block')    # no flag opens the reference role
        self.assertEqual(g('local', 'https://ref.example.com/api/dynamic/M/E/Crud/Update', 'PUT', True), 'block')   # nor a reference host
        self.assertEqual(g('local', HOST + '/api/dynamic/M/E/Crud/Update', 'PUT'), 'block')
        self.assertEqual(g('local', HOST + '/api/dynamic/M/E/Crud/Update', 'PUT', True), 'allow-local-write')
        self.assertEqual(g('local', HOST + '/api/dynamic/M/E/Crud/GetAll', 'GET', True), 'allow')
        self.assertEqual(g('local', 'https://dep.example.com/api/dynamic/M/E/Crud/Update', 'PUT', True), 'block')
        self.assertEqual(g('deployed', 'https://dep.example.com/api/dynamic/M/E/Crud/Update', 'PUT', True), 'block')
        self.assertEqual(g('deployed', 'https://dep.example.com/api/services/app/Thing/GetAll', 'POST'), 'allow')

    def test_configuration_item_mode_only_below_0_45(self):
        from core import browse
        self.assertTrue(browse.sets_config_item_mode('reference'))       # 0.43.38
        self.assertFalse(browse.sets_config_item_mode('local'))          # 0.46.1
        self.assertFalse(browse.sets_config_item_mode('deployed'))

    def test_probe_pattern_and_login_defaults(self):
        from core import browse
        self.assertEqual(browse.probe_pattern(), 'ant-tabs|my\\-carrier')
        self.assertEqual(browse.login_config()['submitText'], 'Sign In')
        with mock.patch.dict(os.environ, {'SHREC_CONSOLE_MAX': '50'}):
            self.assertEqual(browse.console_max(), 100)
        with mock.patch.dict(os.environ, {'SHREC_CONSOLE_MAX': '5000'}):
            self.assertEqual(browse.console_max(), 5000)
        self.assertEqual(browse.portal_base('local'), 'http://localhost:3000')


class MetadataTests(TempProject):
    class Api:
        def __init__(self, known):
            self.known, self.calls = known, []

        def get(self, path, **params):
            self.calls.append(params)
            props = self.known.get(params['entityType'])
            if props is None:
                raise RuntimeError('404')
            return {'result': {'properties': props}}

    def test_resolution_uses_the_entity_namespaces_option_and_caches(self):
        from core.metadata import Metadata
        api = self.Api({'Demo.Module.Domain.Widget': [{'path': 'Name'}, {'path': 'Total', 'readonly': True}],
                        'Demo.Module.Domain.Gadgets.Gadget': [{'path': 'Id'}]})
        m = Metadata(api)
        self.assertEqual(m.resolve('Widget', 'Demo.Module'), 'Demo.Module.Domain.Widget')
        self.assertEqual(m.resolve('Gadget', 'Demo.Module'), 'Demo.Module.Domain.Gadgets.Gadget')
        self.assertIsNone(m.resolve('Missing', 'Demo.Module'))
        n = len(api.calls)
        m.props('Demo.Module.Domain.Widget')
        self.assertEqual(len(api.calls), n)                              # cached
        self.assertEqual(m.paths('Demo.Module.Domain.Widget'), {'name', 'total'})
        self.assertIn('total', m.prop_map('Demo.Module.Domain.Widget'))
        self.assertIsNone(m.props('Nope'))

    def test_custom_namespaces_and_full_names(self):
        from core.metadata import Metadata, reference_list
        api = self.Api({'Acme.Core.Thing': [{'path': 'A'}]})
        self.assertEqual(Metadata(api, namespace_list=['Acme.Core']).resolve('Thing'), 'Acme.Core.Thing')
        self.assertEqual(Metadata(api, namespace_list=[]).resolve('Acme.Core.Thing'), 'Acme.Core.Thing')
        self.assertEqual(reference_list({'referenceListId': {'name': 'L', 'module': 'M'}}), {'name': 'L', 'module': 'M'})
        self.assertEqual(reference_list({'referenceListName': 'L2'}), {'name': 'L2', 'module': None})
        self.assertIsNone(reference_list({}))

    def test_container_is_sent_when_given(self):
        from core.metadata import Metadata
        api = self.Api({'T': [{'path': 'A'}]})
        Metadata(api, container='Mod').props('T')
        self.assertEqual(api.calls[-1], {'entityType': 'T', 'container': 'Mod'})

    def test_role_version(self):
        from core.metadata import role_version
        self.assertEqual(role_version('reference'), '0.43.38')
        self.assertEqual(role_version('local'), '0.46.1')


# ---------------------------------------------------------------- export-package flow (network replaced)
class ExportFlowTests(TempProject):
    options = {'packageDir': 'Pkgs', 'packageCsproj': 'src/App.csproj'}

    def setUp(self):
        super().setUp()
        import subprocess
        if not shutil.which('git'):
            self.skipTest('git is not installed')
        from tools import export_package
        self.m = export_package
        run = lambda *a: subprocess.run(['git', '-C', self.tmp, *a], capture_output=True, check=True)
        run('init', '-q')
        run('config', 'user.email', 'a@example.com')
        run('config', 'user.name', 'a')
        os.makedirs(os.path.join(self.tmp, 'Pkgs'))
        os.makedirs(os.path.join(self.tmp, 'src'))
        with open(os.path.join(self.tmp, 'Pkgs', '20260101_old.shaconfig'), 'wb') as f:
            f.write(b'PK')
        with open(os.path.join(self.tmp, 'src', 'App.csproj'), 'w', encoding='utf-8', newline='') as f:
            f.write('<Project>\n    <None Remove="..\\Pkgs\\20260101_old.shaconfig" />\n    <EmbeddedResource Include="..\\Pkgs\\20260101_old.shaconfig" />\n</Project>')
        run('add', 'Pkgs')
        run('commit', '-q', '-m', 'x')
        self.branch = run('rev-parse', '--abbrev-ref', 'HEAD').stdout.decode().strip()

    def export(self, name, extra=()):
        class FakeApi:
            base = HOST

            def __init__(self, role):
                pass

            def get_all(self, path, **kw):
                return [{'id': 'id-a', 'name': 'a', 'module': {'name': 'Demo.Module'}}, {'id': 'id-b', 'name': 'b', 'module': {'name': 'Demo.Module'}}]
        out = io.StringIO()
        with mock.patch.object(self.m, 'Api', FakeApi), \
                mock.patch.object(self.m, 'post_export', return_value=(b'PK\x03\x04data', {'Content-Disposition': f'attachment; filename={name}'})), \
                contextlib.redirect_stdout(out):
            code = self.m.main(['--target', 'local', '--forms', 'Demo.Module/a,Demo.Module/b', '--reviewer-approved', *extra])
        return code, out.getvalue()

    def test_name_must_sort_after_the_newest_package_on_the_target_branch(self):
        with self.assertRaises(project.WriteRefused):
            self.export('20251231_early.shaconfig', ['--target-branch', self.branch])
        with self.assertRaises(project.WriteRefused):                              # no target branch given: refused
            self.export('20260201_new.shaconfig')
        code, out = self.export('20260201_new.shaconfig', ['--target-branch', self.branch])      # dry run
        self.assertEqual(code, 0)
        self.assertIn('dry run', out)
        self.assertTrue(os.path.exists(os.path.join(self.work, 'exports', '20260201_new.shaconfig')))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'Pkgs', '20260201_new.shaconfig')))

    def test_a_package_only_on_the_branch_still_counts(self):
        import subprocess
        run = lambda *a: subprocess.run(['git', '-C', self.tmp, *a], capture_output=True, check=True)
        run('checkout', '-q', '-b', 'other')
        with open(os.path.join(self.tmp, 'Pkgs', '20260301_branch_only.shaconfig'), 'wb') as f:
            f.write(b'PK')
        run('add', 'Pkgs')
        run('commit', '-q', '-m', 'y')
        run('checkout', '-q', self.branch)                          # the working tree does not hold it, the other branch does
        with self.assertRaises(project.WriteRefused):
            self.export('20260201_new.shaconfig', ['--target-branch', 'other'])

    def test_apply_copies_registers_and_logs_an_export_event(self):
        code, out = self.export('20260201_new.shaconfig', ['--target-branch', self.branch, '--apply'])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'Pkgs', '20260201_new.shaconfig')))
        with open(os.path.join(self.tmp, 'src', 'App.csproj'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('<EmbeddedResource Include="..\\Pkgs\\20260201_new.shaconfig" />', text)
        events = [e for e in ledger.read() if e['event'] == 'export']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['forms'], ['Demo.Module/a', 'Demo.Module/b'])
        self.assertEqual(events[0]['package'], '20260201_new.shaconfig')
        self.assertTrue(events[0]['applied'])

    def test_missing_approval_prints_the_help_and_refuses(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.m.main(['--target', 'local', '--forms', 'Demo.Module/a']), 1)


# ---------------------------------------------------------------- the other tools (pure parts)
class ToolPartsTests(unittest.TestCase):
    def test_merge3_keeps_ours_and_takes_theirs_additions(self):
        from tools import merge3
        base = {'components': [{'id': 'a', 'type': 'x', 'v': 1, 'components': []}]}
        ours = {'components': [{'id': 'a', 'type': 'x', 'v': 2, 'components': []}]}
        theirs = {'components': [{'id': 'a', 'type': 'x', 'v': 1, 'w': 5, 'components': []}]}
        merged, conf, _, _ = merge3.merge_form(base, ours, theirs)
        self.assertEqual(merged['components'][0]['v'], 2)
        self.assertEqual(merged['components'][0]['w'], 5)
        both = {'components': [{'id': 'a', 'type': 'x', 'v': 3, 'components': []}]}
        merged, conf, _, _ = merge3.merge_form(base, ours, both)
        self.assertEqual(merged['components'][0]['v'], 2)
        self.assertTrue(any('ours kept' in c[1] for c in conf))

    def test_sync_forms_plan_skips_excluded_and_missing_forms(self):
        from tools import sync_forms
        rows = [{'name': 'a', 'module': {'name': 'M'}}, {'name': 'b', 'module': {'name': 'M'}}, {'name': 'c', 'module': {'name': 'M'}},
                {'name': 'd', 'module': {'name': 'Other'}}]
        cand, skipped, missing = sync_forms.plan_names(rows, {('M', 'a'), ('M', 'b'), ('Other', 'd')}, ['M'], {'b'})
        self.assertEqual((cand, skipped, missing), ([('M', 'a')], 1, ['c']))

    def test_sync_forms_collects_failures_and_exits_1_without_aborting(self):
        from core import push as pushmod
        from tools import sync_forms, snapshot
        tmp = tempfile.mkdtemp(prefix='shrec-sync-')
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, '.shesha-reconcile'))
        with open(os.path.join(tmp, '.shesha-reconcile', 'project.json'), 'w', encoding='utf-8') as f:
            json.dump(PROJECT, f)
        rows = [{'id': n, 'name': n, 'module': {'name': 'Demo.Module'}, 'markup': json.dumps({'components': [n]})} for n in ('a', 'b', 'c')]
        done = []

        def fake_push(module, name, transform, dry_run=False, role=None, rule=None, **kw):
            if name == 'b':
                raise RuntimeError('boom')
            notes = transform({'components': ['other']})
            done.append((name, dry_run, role, bool(notes)))
            return notes
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'SHREC_PROJECT': tmp, 'SHREC_WORK': os.path.join(tmp, 'work')}), \
                mock.patch.object(snapshot, 'fetch_rows', return_value=(mock.Mock(), rows, 3)), \
                mock.patch('core.api.fetch_forms', return_value=(mock.Mock(), rows)), \
                mock.patch.object(pushmod, 'push', fake_push), contextlib.redirect_stdout(out):
            code = sync_forms.main(['--from', 'deployed', '--to', 'local'])
        self.assertEqual(code, 1)
        self.assertEqual(done, [('a', True, 'local', True), ('c', True, 'local', True)])        # c ran after b failed; dry run
        self.assertIn('failed 1', out.getvalue())
        self.assertIn('failed Demo.Module/b', out.getvalue())

    def test_export_package_name_csproj_and_branch_helpers(self):
        from tools import export_package as ep
        self.assertEqual(ep.filename_from({'Content-Disposition': 'attachment; filename="20260101_pkg.shaconfig"; size=1'}), '20260101_pkg.shaconfig')
        for bad in ('../x.shaconfig', 'a/b.shaconfig', '..'):
            with self.assertRaises(project.WriteRefused):
                ep.filename_from({'Content-Disposition': f'attachment; filename={bad}'})
        with self.assertRaises(project.WriteRefused):
            ep.filename_from({})
        tmp = tempfile.mkdtemp(prefix='shrec-exp-')
        self.addCleanup(shutil.rmtree, tmp, True)
        pdir = os.path.join(tmp, 'src', 'Pkgs')
        os.makedirs(pdir)
        cs = os.path.join(tmp, 'src', 'App.csproj')
        with open(cs, 'w', encoding='utf-8', newline='') as f:
            f.write('<Project>\r\n  <ItemGroup>\r\n    <None Remove="Pkgs\\20260101_old.shaconfig" />\r\n'
                    '    <EmbeddedResource Include="Pkgs\\20260101_old.shaconfig" />\r\n  </ItemGroup>\r\n</Project>')
        self.assertEqual(ep.csproj_prefix(pdir, cs), 'Pkgs')
        self.assertTrue(ep.register_in_csproj(cs, pdir, '20260102_new.shaconfig', '20260101_old.shaconfig'))
        with open(cs, encoding='utf-8-sig', newline='') as fh:
            text = fh.read()
        self.assertIn('<None Remove="Pkgs\\20260102_new.shaconfig" />', text)
        self.assertIn('<EmbeddedResource Include="Pkgs\\20260102_new.shaconfig" />', text)
        self.assertFalse(ep.register_in_csproj(cs, pdir, '20260102_new.shaconfig', '20260101_old.shaconfig'))   # idempotent
        with self.assertRaises(project.WriteRefused):
            ep.register_in_csproj(cs, pdir, '20260103_x.shaconfig', '20250101_missing.shaconfig')
        self.assertIn('reviewer-approved', ep.__doc__)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ep.main(['--target', 'local']), 1)       # refuses without the approval flag

    def test_export_name_is_checked_against_the_target_branch(self):
        import subprocess
        from tools import export_package as ep
        if not shutil.which('git'):
            self.skipTest('git is not installed')
        tmp = tempfile.mkdtemp(prefix='shrec-git-')
        self.addCleanup(shutil.rmtree, tmp, True)
        run = lambda *a: subprocess.run(['git', '-C', tmp, *a], capture_output=True, check=True)
        run('init', '-q')
        run('config', 'user.email', 'a@example.com')
        run('config', 'user.name', 'a')
        os.makedirs(os.path.join(tmp, 'Pkgs'))
        for n in ('20260101_a.shaconfig', '20260105_b.shaconfig'):
            with open(os.path.join(tmp, 'Pkgs', n), 'wb') as fh:
                fh.write(b'PK')
        run('add', '.')
        run('commit', '-q', '-m', 'x')
        branch = run('rev-parse', '--abbrev-ref', 'HEAD').stdout.decode().strip()
        self.assertEqual(ep.newest_on_branch(tmp, branch, 'Pkgs'), '20260105_b.shaconfig')
        with self.assertRaises(project.WriteRefused):
            ep.newest_on_branch(tmp, 'no-such-ref', 'Pkgs')

    def test_verify_package_legacy_names_are_keyed_on_the_target_minor(self):
        from tools import verify_package as vp
        legacy, allowed = vp.legacy_names('0.46.1')
        self.assertIn('Frwk_', legacy)
        self.assertEqual(allowed, ('Frwk_Discriminator',))
        self.assertIsNone(vp.legacy_names('0.47.0'))
        self.assertIsNone(vp.legacy_names(None))

    def test_verify_package_reads_a_package_and_checks_expectations(self):
        import zipfile
        from tools import verify_package as vp
        tmp = tempfile.mkdtemp(prefix='shrec-pkg-')
        self.addCleanup(shutil.rmtree, tmp, True)
        pk = os.path.join(tmp, 'p.shaconfig')
        with zipfile.ZipFile(pk, 'w') as z:
            z.writestr('a.json', json.dumps({'Name': 'form-a', 'ModuleName': 'M', 'Markup': '{"x": "dbo.Frwk_Thing"}'}))
            z.writestr('b.json', json.dumps({'Name': 'form-b', 'ModuleName': 'M', 'Markup': '{"x": "fine"}'}))
        lst = os.path.join(tmp, 'l.txt')
        with open(lst, 'w', encoding='utf-8') as fh:
            fh.write('M/form-a\nform-b\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vp.main([pk, '--target-version', '0.46.0', '--expect', 'form-b=fine', '--forbid', 'zzz', '--forms-file', lst])
        self.assertEqual(code, 0)
        self.assertIn("['form-a']", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vp.main([pk, '--target-version', '0.46.0', '--forbid', 'fine']), 1)

    def test_migration_check_patterns_are_keyed_on_the_target_minor(self):
        from tools import migration_check as mc
        self.assertTrue(mc.suspect_pattern('0.46.2').search('update dbo.Frwk_Modules set x = 1'))
        self.assertTrue(mc.suspect_pattern('0.46.0').search('select * from Core_ShaRoles'))
        self.assertIsNone(mc.suspect_pattern('0.50.0'))
        tmp = tempfile.mkdtemp(prefix='shrec-mig-')
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, 'bin'))
        for rel, num in (('M1.cs', 1), (os.path.join('bin', 'M2.cs'), 2)):
            with open(os.path.join(tmp, rel), 'w', encoding='utf-8') as fh:
                fh.write('[Migration(2026010100000%d)]\nclass C {}' % num)
        self.assertEqual(sorted(mc.scan([tmp])), [20260101000001])

    def test_sqlq_is_read_only(self):
        from tools import sqlq
        self.assertEqual(sqlq.check_select('select 1;'), 'select 1')
        self.assertEqual(sqlq.check_select('WITH x AS (select 1 a) select a from x'), 'WITH x AS (select 1 a) select a from x')
        for bad in ('delete from t', 'select 1; drop table t', 'select * into t2 from t', 'exec sp_who', 'update t set a=1', 'insert t values (1)'):
            with self.assertRaises(ValueError, msg=bad):
                sqlq.check_select(bad)
        self.assertEqual(sqlq.check_select("select 'drop me' as a"), "select 'drop me' as a")      # a keyword inside a literal is fine
        with mock.patch.dict(os.environ, {'SHREC_SQL': ''}):
            with self.assertRaises(RuntimeError):
                sqlq.run('select 1')
        self.assertIn('SHREC_SQL', sqlq.__doc__)

    def test_capture_helpers(self):
        from tools import capture
        self.assertEqual(capture.page_url({'module': 'M.N', 'form': 'f', 'id': 'abc'}), '/dynamic/M.N/f?id=abc')
        self.assertEqual(capture.page_url({'module': 'M', 'form': 'f', 'id': '-'}), '/dynamic/M/f')
        self.assertEqual(capture.page_tag({'module': 'M', 'form': 'a b'}), 'M__a_b')
        for field in ('labelOverflow', 'scrollers', 'tags', 'refListStatus', 'htmlRenderEmpty', 'htmlRenders', 'empty32', 'panels',
                      'buttonsEmpty', 'statistics', 'placeholdersNoData', 'errors'):
            self.assertIn('o.' + field, capture.DEFECTS)

    def test_compare_helpers(self):
        from tools import compare
        self.assertEqual(compare.slug_of('/dynamic/M.N/form-x?id=1'), 'M.N__form-x')
        base = {'items': [['A', 10, 20, 100, 0, 30], ['B', 10, 20, 100, 40, 30]]}
        other = {'items': [['A', 12, 22, 100, 0, 30]]}
        rows = compare.geometry_rows(base, other)
        self.assertEqual(rows[0][3], (2, 2, 0, 0))
        self.assertIsNone(rows[1][2])

    def test_audit_requests_flags(self):
        from tools import audit_requests as ar
        e = {'path': '/api/dynamic/M/E/Crud/GetAll', 'params': {'properties': ['id'], 'maxResultCount': ['10']}, 'items': [{'id': '1'}], 'status': 200}
        flags = ar.analyse(e)
        self.assertTrue(any(f.startswith('NO FILTER') for f in flags))
        self.assertTrue(any(f.startswith('TRIMMED PROPERTIES') for f in flags))
        ok = {'path': '/api/dynamic/M/E/Crud/GetAll', 'params': {'filter': ['{"a":1}'], 'sorting': ['id'], 'properties': ['id name']}, 'items': [], 'status': 200}
        self.assertEqual(ar.analyse(ok), [])


if __name__ == '__main__':
    unittest.main()
