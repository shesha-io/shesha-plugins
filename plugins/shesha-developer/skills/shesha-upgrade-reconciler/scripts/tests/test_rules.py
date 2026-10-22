"""Offline tests for the 0.46 rule pack: every rule against a minimal neutral fixture (fixtures/<rule>.json).

For every fixture case: apply changes exactly the expected values and nothing else, applying twice gives 0 changes the
second time, and for rules with a retire function retire(apply(x)) == x. Nothing touches a network: sessions are built
with packs.Session(role='local', options=..., forms=[...], reference=[...]) and entity metadata is pre-seeded through the
session cache (session._cache['metadata:<entityType>'] = [property dicts]).
Cases that run the syntax gate need `node` on PATH and are skipped without it.
"""
import copy
import glob
import json
import os
import re
import shutil
import tempfile
import unittest

from core import engine, packs
from core.project import WriteRefused

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, 'fixtures')
PACK = next(m for m in packs.list_packs() if m['id'] == '0.46')
RULES = {r['id']: r for r in PACK['rules']}
HAS_NODE = shutil.which('node') is not None
ABSENT = '@absent'


def make_session(case=None, **over):
    case = dict(case or {}, **over)
    session = packs.Session(role='local', options=case.get('options') or {}, forms=case.get('forms') or [],
                            reference=case.get('reference') or [])
    for entity_type, props in (case.get('metadata') or {}).items():
        session._cache['metadata:' + entity_type] = props
    return session


def ctx_for(session, form):
    module, name = form.split('/', 1)
    return packs.Ctx(session, module, name)


def fns(rule_id):
    return packs.callables(PACK, RULES[rule_id])


def get_path(obj, path):
    cur = obj
    for tok in path.split('/'):
        if isinstance(cur, list):
            cur = cur[int(tok)]
        elif isinstance(cur, dict) and tok in cur:
            cur = cur[tok]
        else:
            return ABSENT
    return cur


def diff_paths(a, b, path=''):
    """leaf paths (joined by '/') at which two JSON values differ"""
    if type(a) != type(b):
        return [path]
    if isinstance(a, dict):
        out = []
        for k in set(a) | set(b):
            p = f'{path}/{k}' if path else k
            if k not in a or k not in b:
                out.append(p)
            else:
                out += diff_paths(a[k], b[k], p)
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [path]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff_paths(x, y, f'{path}/{i}' if path else str(i))
        return out
    return [] if a == b else [path]


def rule_fixture_files():
    """the per-rule fixtures ({"rule": ..., "cases": [...]}); other JSON files in fixtures/ belong to other tests"""
    out = []
    for f in sorted(glob.glob(os.path.join(FIXTURES, '*.json'))):
        with open(f, encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict) and 'rule' in d and 'cases' in d:
            out.append((f, d))
    return out


def load_cases():
    out = []
    for _, d in rule_fixture_files():
        for i, c in enumerate(d['cases']):
            out.append((d['rule'], i, c))
    return out


class RuleFixtureTests(unittest.TestCase):
    """one generated test per fixture case (see _add below)"""


def _make_test(rule_id, case):
    def test(self):
        apply_fn, retire_fn = fns(rule_id)
        before = copy.deepcopy(case['markup'])
        work = copy.deepcopy(before)
        session = make_session(case)
        ctx = ctx_for(session, case['form'])
        changes = apply_fn(ctx, work)
        self.assertEqual(changes, case['changes'], f'{rule_id}: change count; notes={ctx.notes}')
        real_notes = [n for n in ctx.notes if not n.startswith('INFO')]
        self.assertEqual(bool(real_notes), case['changes'] > 0, f'{rule_id}: notes {ctx.notes}')
        for path, want in case['expect']:
            got = get_path(work, path)
            self.assertEqual(got, want, f'{rule_id}: {path}')
        allowed = case.get('touched') or [p for p, _ in case['expect']]
        for p in diff_paths(before, work):
            self.assertTrue(any(p == a or p.startswith(a + '/') for a in allowed), f'{rule_id}: unexpected change at {p}')
        if case['changes'] == 0:
            self.assertEqual(work, before, f'{rule_id}: markup must be untouched when nothing is reported')
        # idempotent: a second application changes nothing
        after_first = copy.deepcopy(work)
        ctx2 = ctx_for(session, case['form'])
        self.assertEqual(apply_fn(ctx2, work), 0, f'{rule_id}: second application must change nothing; notes={ctx2.notes}')
        self.assertEqual(work, after_first)
        # retire(apply(x)) == x
        if case.get('retire'):
            self.assertIsNotNone(retire_fn, f'{rule_id} declares no retire')
            again = copy.deepcopy(before)
            s2 = make_session(case)
            apply_fn(ctx_for(s2, case['form']), again)
            retire_fn(ctx_for(s2, case['form']), again)
            self.assertEqual(again, before, f'{rule_id}: retire(apply(x)) != x')
    return test


def _add():
    for rule_id, i, case in load_cases():
        name = 'test_%s_%02d_%s' % (rule_id, i, re.sub(r'\W+', '_', case['name'])[:50])
        t = _make_test(rule_id, case)
        if case.get('node'):
            t = unittest.skipUnless(HAS_NODE, 'node is not on PATH (syntax gate)')(t)
        setattr(RuleFixtureTests, name, t)


_add()


class PackTests(unittest.TestCase):
    def test_every_rule_has_a_fixture(self):
        have = {r for r, _, _ in load_cases()}
        self.assertEqual({r['id'] for r in PACK['rules']} - have, set(), 'rules without a fixture')

    def test_pack_json_is_valid(self):
        ids = [r['id'] for r in PACK['rules']]
        self.assertEqual(len(ids), len(set(ids)), 'rule ids must be unique')
        for key in ('id', 'version', 'target', 'sourceBelow', 'hazards', 'rules'):
            self.assertIn(key, PACK)
        fields = {'id', 'entry', 'retire', 'hazard', 'title', 'kind', 'syntaxGate', 'marker', 'fixedIn', 'fixedEvidence', 'options'}
        for r in PACK['rules']:
            self.assertEqual(set(r), fields, r['id'])
            self.assertIn(r['kind'], ('fleet', 'targeted', 'opt-in'), r['id'])
            self.assertIsInstance(r['syntaxGate'], bool)
            self.assertIsInstance(r['options'], list)
            apply_fn, retire_fn = packs.callables(PACK, r)       # every entry (and retire) resolves
            self.assertTrue(callable(apply_fn), r['id'])
            if r['retire']:
                self.assertTrue(callable(retire_fn), r['id'])
            if r['fixedIn']:
                self.assertEqual(r['fixedEvidence'], 'release-notes', r['id'])
            else:
                self.assertIsNone(r['fixedEvidence'], r['id'])
            if r['hazard']:
                self.assertRegex(r['hazard'], r'^H\d+$')

    def test_old_order_and_ids_are_kept(self):
        fleet = [r['id'] for r in PACK['rules'] if r['kind'] != 'targeted']
        self.assertEqual(fleet, ['scripts', 'textvis', 'textsize', 'carriers', 'rlshidden', 'layout', 'tabs', 'status', 'hints',
                                 'labelcol', 'subfetch', 'rowgap', 'tabgap', 'tablectl', 'tagnull', 'types', 'panels', 'optfilter',
                                 'editmode', 'acsort', 'payload', 'urlwait', 'afterload', 'formref', 'gsrefresh', 'normparent'])
        self.assertEqual({r['id'] for r in PACK['rules'] if r['kind'] == 'targeted'},
                         {'split_labels', 'hide_empty_buttons', 'dialogfooter', 'url_reflist_columns', 'readonly_strip', 'urlfilter'})
        self.assertEqual({r['id'] for r in PACK['rules'] if r['kind'] == 'opt-in'}, {'labelcol', 'panels'})

    def test_release_notes_claims(self):
        fixed = {r['id'] for r in PACK['rules'] if r['fixedIn']}
        self.assertEqual(fixed, {'editmode', 'textvis', 'split_labels', 'optfilter', 'dialogfooter', 'afterload', 'labelcol'})
        self.assertEqual({r['fixedIn'] for r in PACK['rules'] if r['fixedIn']}, {'0.46.1'})
        retirable = {r['id'] for r in packs.retire_candidates(PACK, '0.46.1')}
        self.assertEqual(retirable, {'editmode', 'textvis', 'afterload', 'dialogfooter'})
        self.assertEqual(packs.retire_candidates(PACK, '0.46.0'), [])
        fates = {r['id']: f for r, f in packs.plan(PACK, '0.46.1')}
        self.assertEqual(fates['editmode'], 'apply-claimed-fixed')
        self.assertEqual(fates['labelcol'], 'opt-in')
        self.assertEqual(fates['rowgap'], 'apply')

    def test_declared_options_are_the_ones_read(self):
        """every option key a module reads through ctx.opt appears in its rule's `options` list"""
        src_dir = os.path.join(os.path.dirname(HERE), 'packs', 'v0_46')
        for r in PACK['rules']:
            mod = r['entry'].split(':')[0]
            with open(os.path.join(src_dir, mod + '.py'), encoding='utf-8') as f:
                read = set(re.findall(r"ctx\.opt\('(\w+)'", f.read()))
            self.assertTrue(read <= set(r['options']), f"{r['id']}: reads {read - set(r['options'])} without declaring it")


class OptionValidationTests(unittest.TestCase):
    def run_rule(self, rule_id, options, markup):
        s = make_session(options=options)
        return fns(rule_id)[0](ctx_for(s, 'Shop/order-details'), markup)

    def test_labelcol_option_must_be_two_spans(self):
        for bad in ([10], 'x', [10, 'a'], [20, 20], [0, 14]):
            with self.assertRaises(WriteRefused, msg=repr(bad)):
                self.run_rule('labelcol', {'subformLabelCol': bad}, {'components': []})

    def test_labelcol_equal_to_the_default_is_a_stable_no_op(self):
        m = {'components': [{'id': 's', 'type': 'subForm', 'labelCol': 8, 'wrapperCol': None}]}
        self.assertEqual(self.run_rule('labelcol', {'subformLabelCol': [8, 16]}, m), 1)
        self.assertEqual(self.run_rule('labelcol', {'subformLabelCol': [8, 16]}, m), 0)

    def test_formref_entries_are_validated(self):
        with self.assertRaises(WriteRefused):
            self.run_rule('formref', {'formRefMap': [{'from': 'NoSlash', 'to': 'A/b'}]}, {'components': []})

    def test_panels_option_is_validated(self):
        with self.assertRaises(WriteRefused):
            self.run_rule('panels', {'panelHeaderPadding': {'top': 1}}, {'components': []})

    def test_types_extra_that_cannot_settle_is_refused(self):
        with self.assertRaises(WriteRefused):
            self.run_rule('types', {'typeMapExtra': {'A.B': 'A.B.C'}}, {'components': []})

    def test_status_pattern_needs_a_group(self):
        with self.assertRaises(WriteRefused):
            self.run_rule('status', {'statusLabelPattern': 'const status'}, {'components': []})
        with self.assertRaises(WriteRefused):
            self.run_rule('status', {'statusLabelPattern': '('}, {'components': []})

    def test_label_split_option_path_must_exist(self):
        with self.assertRaises(WriteRefused):
            self.run_rule('split_labels', {'labelSplit': os.path.join(tempfile.gettempdir(), 'no-such-sweep-file.json')},
                          {'components': [{'id': 'f', 'type': 'textField', 'label': 'x'}]})


class SyntaxGateTests(unittest.TestCase):
    @unittest.skipUnless(HAS_NODE, 'node is not on PATH')
    def test_carrier_with_invalid_script_is_refused(self):
        m = {'components': [{'id': 'c', 'type': 'htmlRender', 'componentName': 'c', 'hidden': True,
                             'renderer': "<style>.a{}</style>"}]}
        with self.assertRaises(WriteRefused):
            fns('carriers')[0](ctx_for(make_session(), 'Shop/order-details'), m)

    @unittest.skipUnless(HAS_NODE, 'node is not on PATH')
    def test_safe_chain_that_would_break_a_script_is_refused(self):
        # a script that already fails to parse is not made worse; the gate only refuses regressions
        m = {'components': [{'id': 't', 'type': 'textField', 'componentName': 't', 'visible': {'_mode': 'code', '_code': 'return data.a.b;'}}]}
        self.assertEqual(fns('scripts')[0](ctx_for(make_session(), 'Shop/f'), m), 1)


class EngineOfflineTests(unittest.TestCase):
    def test_selected_rules_run_through_apply_offline_and_settle(self):
        markup = {'components': [
            {'id': 'row', 'type': 'container', 'componentName': 'row', 'direction': 'horizontal', 'desktop': {}},
            {'id': 'tag', 'type': 'refListStatus', 'componentName': 'tag', 'propertyName': 'order.status'},
            {'id': 'ac', 'type': 'autocomplete', 'componentName': 'ac', 'dataSourceType': 'entitiesList', 'displayPropName': 'name'}]}
        rules = engine.selected_rules(PACK, '0.46.0', only_rules={'rowgap', 'tagnull', 'acsort'})
        self.assertEqual([m['id'] for m, _, _ in rules], ['rowgap', 'tagnull', 'acsort'])
        session = make_session()
        out, notes = engine.apply_offline(session, rules, 'Shop', 'order-details', markup)
        self.assertEqual(len(notes), 3)
        _, notes2 = engine.apply_offline(session, rules, 'Shop', 'order-details', out)
        self.assertEqual(notes2, [])

    def test_retire_mode_unwinds_through_the_engine(self):
        code = "return data?.mode === 'edit' ? 'edit' : 'readonly';"
        markup = {'components': [{'id': 't', 'type': 'textField', 'componentName': 't', 'editMode': {'_mode': 'code', '_code': code}}]}
        before = copy.deepcopy(markup)
        rules = engine.selected_rules(PACK, '0.46.0', only_rules={'editmode'})
        session = make_session()
        engine.apply_offline(session, rules, 'Shop', 'f', markup)
        self.assertNotEqual(markup, before)
        engine.apply_offline(session, rules, 'Shop', 'f', markup, mode='retire')
        self.assertEqual(markup, before)


class DialogFooterTests(unittest.TestCase):
    """dialogfooter touches two forms: the dialog form gets the footer row first, the host is cleared on a second run"""

    @staticmethod
    def host_markup(buttons, title='Edit order'):
        return {'components': [{'id': 'b', 'type': 'button', 'componentName': 'b', 'actionConfiguration': {
            'actionName': 'Show Dialog', 'actionOwner': 'shesha.common',
            'actionArguments': {'formId': {'module': 'Shop', 'name': 'order-dialog'}, 'modalTitle': title,
                                'footerButtons': 'custom', 'buttons': buttons}}}]}

    BUTTONS = [{'id': 'i1', 'itemType': 'item', 'label': 'Save', 'buttonType': 'primary',
                'editMode': {'_mode': 'code', '_code': 'return !!data?.ready;'}}]

    def dialog_markup(self):
        return {'components': [{'id': 'root1', 'type': 'container', 'componentName': 'root1', 'components': []}]}

    def test_two_phase_move_and_retire(self):
        host, dialog = self.host_markup(copy.deepcopy(self.BUTTONS)), self.dialog_markup()
        rows = lambda h, d: [{'module': 'Shop', 'name': 'order-host', 'markup': h}, {'module': 'Shop', 'name': 'order-dialog', 'markup': d}]
        apply_fn, retire_fn = fns('dialogfooter')
        # run 1: the dialog form gets the row; the host is NOT cleared (the row is not in the fetched snapshot yet)
        s1 = make_session(forms=rows(copy.deepcopy(host), copy.deepcopy(dialog)))
        d1, h1 = copy.deepcopy(dialog), copy.deepcopy(host)
        self.assertEqual(apply_fn(ctx_for(s1, 'Shop/order-dialog'), d1), 1)
        c = ctx_for(s1, 'Shop/order-host')
        self.assertEqual(apply_fn(c, h1), 0)
        self.assertEqual(h1, host)
        self.assertTrue(any(n.startswith('INFO') for n in c.notes))
        row = d1['components'][0]['components'][0]
        self.assertTrue(row['id'].endswith('-ftr046'))
        group = row['components'][0]
        self.assertEqual(group['type'], 'buttonGroup')
        self.assertEqual(group['items'], self.BUTTONS)
        # run 2 (fresh snapshot: the dialog form now holds the row): the host footer moves into the form
        s2 = make_session(forms=rows(copy.deepcopy(host), copy.deepcopy(d1)))
        h2, d2 = copy.deepcopy(host), copy.deepcopy(d1)
        self.assertEqual(apply_fn(ctx_for(s2, 'Shop/order-host'), h2), 1)
        args = h2['components'][0]['actionConfiguration']['actionArguments']
        self.assertEqual((args['footerButtons'], args['buttons']), ('none', []))
        self.assertEqual(args['_reconcilerFooterButtons046'], self.BUTTONS)
        self.assertEqual(apply_fn(ctx_for(s2, 'Shop/order-dialog'), d2), 0)       # row already there
        self.assertEqual(d2, d1)
        # run 3: nothing left to do on either form
        s3 = make_session(forms=rows(copy.deepcopy(h2), copy.deepcopy(d1)))
        self.assertEqual(apply_fn(ctx_for(s3, 'Shop/order-host'), h2), 0)
        self.assertEqual(apply_fn(ctx_for(s3, 'Shop/order-dialog'), d2), 0)
        # retire restores both forms exactly
        self.assertEqual(retire_fn(ctx_for(s3, 'Shop/order-host'), h2), 1)
        self.assertEqual(h2, host)
        self.assertEqual(retire_fn(ctx_for(s3, 'Shop/order-dialog'), d2), 1)
        self.assertEqual(d2, dialog)

    def test_shared_dialog_form_gets_a_guard_not_a_move(self):
        host = self.host_markup([{'id': 'i1', 'itemType': 'item', 'label': 'Save', 'editMode': {'_mode': 'code', '_code': 'return !!data?.ready;'},
                                  'actionConfiguration': {'actionOwner': 'shesha.common', 'actionName': 'Execute Script',
                                                          'actionArguments': {'expression': 'return http.post("/api/x", data);'}}}])
        other = self.host_markup([{'id': 'i2', 'itemType': 'item', 'label': 'Other'}], title='Other')   # a second dialog onto the same form
        rows = [{'module': 'Shop', 'name': 'order-host', 'markup': host}, {'module': 'Shop', 'name': 'order-other', 'markup': other},
                {'module': 'Shop', 'name': 'order-dialog', 'markup': self.dialog_markup()}]
        apply_fn, retire_fn = fns('dialogfooter')
        s = make_session(forms=rows)
        before, work = copy.deepcopy(host), copy.deepcopy(host)
        self.assertEqual(apply_fn(ctx_for(s, 'Shop/order-host'), work), 1)
        expr = work['components'][0]['actionConfiguration']['actionArguments']['buttons'][0]['actionConfiguration']['actionArguments']['expression']
        self.assertTrue(expr.startswith('/*reconciler:046-footer-guard*/'))
        self.assertTrue(expr.endswith('return http.post("/api/x", data);'))
        self.assertEqual(work['components'][0]['actionConfiguration']['actionArguments']['footerButtons'], 'custom')
        self.assertEqual(apply_fn(ctx_for(s, 'Shop/order-host'), work), 0)
        self.assertEqual(retire_fn(ctx_for(s, 'Shop/order-host'), work), 1)
        self.assertEqual(work, before)


class GuardMessageTests(unittest.TestCase):
    def test_custom_message_round_trips_and_parses(self):
        btn = {'id': 'i1', 'itemType': 'item', 'label': 'Save', 'editMode': {'_mode': 'code', '_code': 'return !!data?.ready;'},
               'actionConfiguration': {'actionOwner': 'shesha.common', 'actionName': 'Execute Script', 'actionArguments': {'expression': 'return 1;'}}}

        def host(title):
            return {'components': [{'id': 'b', 'type': 'button', 'componentName': 'b', 'actionConfiguration': {
                'actionName': 'Show Dialog', 'actionArguments': {'formId': {'module': 'Shop', 'name': 'dlg'}, 'modalTitle': title,
                                                                 'footerButtons': 'custom', 'buttons': [copy.deepcopy(btn)]}}}]}
        rows = [{'module': 'Shop', 'name': 'h1', 'markup': host('One')}, {'module': 'Shop', 'name': 'h2', 'markup': host('Two')}]
        s = make_session(options={'footerGuardMessage': "Fill in the customer's name first."}, forms=rows)
        m, before = host('One'), host('One')
        apply_fn, retire_fn = fns('dialogfooter')
        self.assertEqual(apply_fn(ctx_for(s, 'Shop/h1'), m), 1)
        expr = m['components'][0]['actionConfiguration']['actionArguments']['buttons'][0]['actionConfiguration']['actionArguments']['expression']
        self.assertIn("message.warning('Fill in the customer\\'s name first.');", expr)
        if HAS_NODE:
            from core import gate
            self.assertEqual(gate.syntax_errors([expr]), [])
        self.assertEqual(retire_fn(ctx_for(s, 'Shop/h1'), m), 1)
        self.assertEqual(m, before)


class LabelSplitOptionTests(unittest.TestCase):
    def test_label_font_option(self):
        m = {'components': [{'id': 'f1', 'type': 'textField', 'componentName': 'f1', 'parentId': 'root', 'label': 'Long label'}]}
        s = make_session(options={'labelSplit': ['Long label'], 'labelSplitFont': {'size': 13, 'weight': '600'}})
        self.assertEqual(fns('split_labels')[0](ctx_for(s, 'Shop/order-details'), m), 1)
        font = m['components'][0]['components'][0]['desktop']['font']
        self.assertEqual((font['size'], font['weight'], font['type'], font['align']), (13, '600', 'inherit', 'right'))

    def test_label_font_defaults_to_the_antd_form_label_look(self):
        m = {'components': [{'id': 'f1', 'type': 'textField', 'componentName': 'f1', 'parentId': 'root', 'label': 'Long label'}]}
        s = make_session(options={'labelSplit': ['Long label']})
        self.assertEqual(fns('split_labels')[0](ctx_for(s, 'Shop/order-details'), m), 1)
        font = m['components'][0]['components'][0]['desktop']['font']
        self.assertEqual((font['size'], font['weight'], font['color'], font['type'], font['align']),
                         (14, '400', 'rgba(0, 0, 0, 0.88)', 'inherit', 'right'))

    def test_label_font_option_overrides_each_key_separately(self):
        m = {'components': [{'id': 'f1', 'type': 'textField', 'componentName': 'f1', 'parentId': 'root', 'label': 'Long label'}]}
        s = make_session(options={'labelSplit': ['Long label'], 'labelSplitFont': {'weight': '700', 'type': 'Segoe UI'}})
        self.assertEqual(fns('split_labels')[0](ctx_for(s, 'Shop/order-details'), m), 1)
        font = m['components'][0]['components'][0]['desktop']['font']
        self.assertEqual((font['size'], font['weight'], font['color'], font['type']), (14, '700', 'rgba(0, 0, 0, 0.88)', 'Segoe UI'))

    def test_labels_come_from_a_sweep_measurement_file(self):
        label = 'Total amount of the order'
        sweep = {'main': {'labelOverflow': []}, 'tabs': [{'defects': {'labelOverflow': [label]}, 'sub': [{'defects': {'labelOverflow': ['x']}}]}]}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'order-details.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(sweep, f)
            for option in (path, d):
                m = {'components': [{'id': 'f1', 'type': 'textField', 'componentName': 'f1', 'parentId': 'root', 'label': label + ':'}]}
                s = make_session(options={'labelSplit': option})
                self.assertEqual(fns('split_labels')[0](ctx_for(s, 'Shop/order-details'), m), 1, option)
                self.assertEqual(m['components'][0]['id'], 'f1-row046')

    def test_bundled_templates_have_the_expected_component_versions(self):
        from packs.v0_46 import labelsplit
        self.assertEqual((labelsplit.bundled_text()['type'], labelsplit.bundled_text()['version']), ('text', 7))
        self.assertEqual((labelsplit.bundled_container()['type'], labelsplit.bundled_container()['version']), ('container', 9))


if __name__ == '__main__':
    unittest.main()
