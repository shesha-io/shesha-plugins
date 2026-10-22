"""Regression tests for the write-safety guarantees (offline: a temp project and a fake backend)."""
import json
import os
import shutil
import tempfile
import time
import unittest

from core import project, ledger, push, packs, engine


class TempProject(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, '.shesha-reconcile'))
        self.envs = {'reference': {'api': 'https://ref.example.com', 'portal': 'https://ref-portal.example.com', 'version': '0.43.38'},
                     'local': {'api': 'http://localhost:21021', 'portal': 'http://localhost:3000', 'version': '0.46.0'},
                     'deployed': {'api': 'https://dep.example.com', 'portal': 'https://dep-portal.example.com', 'version': '0.46.0'}}
        self.write_project()
        self._env = {k: os.environ.get(k) for k in ('SHREC_PROJECT', 'SHREC_TARGET', 'SHREC_DEPLOY_CONFIRM', 'SHREC_RUN')}
        os.environ['SHREC_PROJECT'] = self.root
        os.environ['SHREC_RUN'] = 'test-run'
        ledger._RUN.clear()
        push._RUNS.clear()
        push._IDX.clear()

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        ledger._RUN.clear()
        push._RUNS.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def write_project(self, **extra):
        project.write_json(os.path.join(self.root, '.shesha-reconcile', 'project.json'),
                           dict({'name': 't', 'modules': ['Demo.Module'], 'environments': self.envs}, **extra))

    def confirm(self, role, api):
        st = project.state()
        st['write_target'] = {'role': role, 'api': api, 'at': 'now'}
        if role == 'deployed':
            st['deployed_authorisation'] = {'api': api, 'at': 'now', 'epoch': time.time()}
        project.save_state(st)


class TestHostIdentity(TempProject):
    def test_host_key_folds_spellings(self):
        k = project.host_key
        self.assertEqual(k('https://Dep.Example.com'), k('https://dep.example.com:443'))
        self.assertEqual(k('https://dep.example.com.'), k('https://dep.example.com'))
        self.assertEqual(k('http://localhost:21021'), k('http://127.0.0.1:21021'))
        self.assertEqual(k('https://user:pw@dep.example.com'), k('https://dep.example.com'))
        self.assertNotEqual(k('http://localhost:21021'), k('http://localhost:21022'))

    def test_is_localhost_rejects_userinfo_and_lookalikes(self):
        for url in ('http://localhost:pw@evil.example.com', 'http://localhost.evil.example.com', 'http://127.0.0.1.evil.example.com'):
            self.assertFalse(project.is_localhost(url), url)
        self.assertTrue(project.is_localhost('http://127.0.0.1:21021'))

    def test_reference_written_under_another_spelling_is_refused(self):
        self.envs['reference']['api'] = 'https://dep.example.com'
        self.envs['deployed']['api'] = 'https://dep.example.com:443'
        self.write_project()
        self.confirm('deployed', 'https://dep.example.com:443')
        os.environ['SHREC_DEPLOY_CONFIRM'] = 'https://dep.example.com:443'
        with self.assertRaises(project.WriteRefused):
            push.assert_writable('deployed', 'https://dep.example.com:443')

    def test_local_alias_of_reference_is_refused(self):
        self.envs['reference']['api'] = 'http://localhost:21021'
        self.envs['local']['api'] = 'http://127.0.0.1:21021'
        self.write_project()
        self.confirm('local', 'http://127.0.0.1:21021')
        with self.assertRaises(project.WriteRefused):
            push.assert_writable('local', 'http://127.0.0.1:21021')

    def test_userinfo_url_in_project_is_a_config_error(self):
        self.envs['deployed']['api'] = 'https://u:p@dep.example.com'
        self.write_project()
        with self.assertRaises(project.ConfigError):
            project.env_config('deployed')


class TestReadPost(unittest.TestCase):
    def test_anchored(self):
        from core import browse
        self.assertFalse(browse.is_read_post('https://r.example.com/api/dynamic/M/Country/Crud/Create'))
        self.assertFalse(browse.is_read_post('https://r.example.com/api/x/Delete?x=/GetAll'))
        self.assertFalse(browse.is_read_post('https://r.example.com/api/services/x/Person/GetAllAndDelete'))
        self.assertTrue(browse.is_read_post('https://r.example.com/api/dynamic/M/Country/Crud/GetAll'))
        self.assertTrue(browse.is_read_post('https://r.example.com/api/TokenAuth/Authenticate'))


class TestLedger(TempProject):
    def test_identity_fields_are_protected(self):
        with self.assertRaises(ValueError):
            ledger.event('form', run='other')
        e = ledger.event('verify', kind='browser', result='ok')
        self.assertEqual((e['event'], e['kind']), ('verify', 'browser'))


class TestDefectsWithFreeTextWhere(TempProject):
    def test_set_and_report_tolerate_imported_text(self):
        import io
        import contextlib
        import shrec
        with open(project.defects_path(), 'w', encoding='utf-8') as f:
            f.write(json.dumps({'id': 'D-1', 'title': 't', 'where': 'every list page', 'status': 'open'}) + '\n')
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            shrec.cmd_defect(['set', 'D-1', '--component', 'grid1'])
        self.assertEqual(shrec._defects()['D-1']['where'], {'text': 'every list page', 'component': 'grid1'})
        from tools import report
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.main(['--all']) or 0, 0)


class TestProjectRuleKinds(TempProject):
    def test_only_fleet_project_rules_run_by_default(self):
        d = os.path.join(self.root, '.shesha-reconcile', 'rules')
        os.makedirs(d)
        for rid, kind in (('pfleet', 'fleet'), ('ptarget', 'targeted'), ('pweird', 'something'), ('popt', 'opt-in')):
            with open(os.path.join(d, rid + '.py'), 'w') as f:
                f.write(f'RULE = {{"id": "{rid}", "kind": "{kind}"}}\ndef apply(ctx, markup):\n    return 0\n')
        pack = packs.pack_for('0.46.0', '0.43.38')
        ids = [m['id'] for m, _, _ in engine.selected_rules(pack, '0.46.0')]
        self.assertIn('pfleet', ids)
        for rid in ('ptarget', 'pweird', 'popt'):
            self.assertNotIn(rid, ids)
        self.assertIn('ptarget', [m['id'] for m, _, _ in engine.selected_rules(pack, '0.46.0', ['ptarget'])])
        self.assertIn('popt', [m['id'] for m, _, _ in engine.selected_rules(pack, '0.46.0', enable={'popt'})])

    def test_patch_upgrade_inside_the_line_keeps_the_pack(self):
        self.assertIsNotNone(packs.pack_for('0.46.1', '0.46.0'))
        self.assertIsNone(packs.pack_for('0.46.0', '0.46.1'))      # a downgrade


class FakeWriter:
    """Minimal backend: one form; `mode` decides how the write behaves."""
    rows = {}
    mode = 'ok'

    def __init__(self, role=None):
        self.role = role or 'local'
        self.base = project.env_config(self.role)['api']

    def get_all(self, path, **kw):
        return [{'id': 'f1', 'name': 'a-form', 'module': 'Demo.Module'}]

    def get(self, path, **params):
        return {'result': dict(self.rows['f1'])}

    def put(self, path, body):
        push.assert_writable(self.role, self.base)
        if FakeWriter.mode == 'timeout-after-apply':
            self.rows['f1']['markup'] = body['markup']
            raise TimeoutError('no response')
        if FakeWriter.mode == 'mutate':
            self.rows['f1']['markup'] = body['markup'] + ' '
            return 200, '{}'
        self.rows['f1']['markup'] = body['markup']
        return 200, '{}'


class TestPushOutcomes(TempProject):
    def setUp(self):
        super().setUp()
        self._writer = push.Writer
        push.Writer = FakeWriter
        FakeWriter.rows = {'f1': {'id': 'f1', 'markup': json.dumps({'components': []}), 'modelType': 'Demo.Thing'}}
        self.confirm('local', 'http://localhost:21021')

    def tearDown(self):
        push.Writer = self._writer
        FakeWriter.mode = 'ok'
        super().tearDown()

    @staticmethod
    def transform(m):
        m.setdefault('components', []).append({'id': 'x', 'type': 'text'})
        return ['added x'] if len(m['components']) == 1 else []

    def results(self):
        return [e.get('result') for e in ledger.read() if e.get('event') == 'form']

    def test_sent_but_unconfirmed_write_is_ledgered_and_not_silent(self):
        FakeWriter.mode = 'timeout-after-apply'
        with self.assertRaises(push.WrittenUnverified):
            push.push('Demo.Module', 'a-form', self.transform, role='local')
        self.assertEqual(self.results()[-1], 'written-unverified')

    def test_read_back_mismatch_is_written_unverified(self):
        FakeWriter.mode = 'mutate'
        with self.assertRaises(push.WrittenUnverified):
            push.push('Demo.Module', 'a-form', self.transform, role='local')
        self.assertEqual(self.results()[-1], 'written-unverified')

    def test_dry_run_sends_nothing(self):
        before = FakeWriter.rows['f1']['markup']
        push.push('Demo.Module', 'a-form', self.transform, dry_run=True, role='local')
        self.assertEqual(FakeWriter.rows['f1']['markup'], before)
        self.assertEqual(self.results()[-1], 'dry-run')

    def test_run_snapshot_keeps_the_first_copy(self):
        push.push('Demo.Module', 'a-form', self.transform, role='local')        # pilot: snapshot = pre-run state
        snap = os.path.join(push.run_dir('local')['dir'], 'snapshot', push.fname('Demo.Module', 'a-form'))
        first = project.read_json(snap)['row']['markup']
        push._RUNS.clear()                                                        # a second process, same SHREC_RUN
        push.begin_run([('Demo.Module', 'a-form')], rule='fleet', role='local')
        self.assertEqual(project.read_json(snap)['row']['markup'], first)


if __name__ == '__main__':
    unittest.main()
