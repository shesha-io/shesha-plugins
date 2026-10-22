"""SCRIPT-SCOPE PROBE: measure what a form script really sees at run time instead of guessing (LOCAL role only, always removed afterwards).

  shrec.py probe-scope <Module>/<form> --component <componentName|id> --prop <script property> [--contains <text>] [--field <name>]
                       [--page </dynamic/Module/page?id=..>] [--loads 2] [--click "<button text>"] [--wait 12000] [--push]
  shrec.py probe-scope <Module>/<form> --remove [--push]        remove every probe marker from the form (the guaranteed clean-up)

Why: on 0.46 a script inside a sub-form runs against the HOST page form (H49): `data` is {}, `form` is the host form, getFieldValue('x') is
undefined although the textarea shows text. Every guess (form.getFieldValue, data.x, pageContext.x) can be wrong; one dump settles it.
Probe first, then change.

What it does (dry run by default: it only shows what it would do; add --push to write):
 1. Prepends ONE dump line, marked /*reconciler:probe-scope*/ ... /*reconciler:probe-end*/, to ONE string property of ONE component of the
    form, through core.push.push (so the host guards, the per-write backup, the read-back and the ledger all apply; the ledger shows the
    note 'TEMPORARY probe added ...', and `shrec.py report` warns while it is still there).
 2. Loads the page N times (default 2; the first load after a push can mislead, H53) in a fresh browser and prints every console line
    starting SHPROBE: `data` (keys + value), `form` (keys, formMode, shaForm._formData keys + value, whether getFieldValue /
    formInstance.getFieldValue / getFormData exist, and with --field the value those handles and the DOM textarea/input hold for that
    component name), `pageContext` (own keys and prototype names) and `contexts` (keys). A script that only runs on a click needs
    --click "Save": the click is made in the read-only browser, so the writes it would send are BLOCKED, only the dump is printed.
 3. ALWAYS removes the probe afterwards (try/finally, also on Ctrl-C or a browser error), re-reads the form and confirms zero markers remain.
    If the removal fails it says so loudly with the exact command: `shrec.py probe-scope <form> --remove --push`.

Writes only through core.push to the LOCAL role: it refuses SHREC_TARGET=deployed and never touches a deployed site or the reference. The
local api must be the write target the user confirmed. It refuses to add a second marker to a form that already holds one (run --remove
--push first), so a form never carries more than one probe. The component and the property are anchors: if they are not found exactly
once the probe is refused (use --contains to pick one of several script properties of that name). The target must be a FUNCTION-BODY
script property (Execute Script, an htmlRender renderer, onAfterDataLoad, a `visible`/`enabled` code, ...): the dump is a statement block
placed before the original code. Console lines are cut at $SHREC_CONSOLE_MAX characters (default 2000).
"""
import argparse
import os
import re
import sys

from core import push as pushmod
from core.api import Api
from core.project import WriteRefused, require

TAG = '/*reconciler:probe-scope*/'
END = '/*reconciler:probe-end*/'
RULE = 'probe-scope'
_BLOCK_RX = re.compile(re.escape(TAG) + r'.*?' + re.escape(END) + r'\n?', re.S)


def payload(field=None):
    """The one-line dump (no newline, no backslash). Every read is wrapped so one failing handle never hides the others."""
    L = [
        "try{var __g=function(f){try{var v=f();if(v===undefined)return 'undefined';var s=JSON.stringify(v);return s===undefined?String(v):s.slice(0,700)}catch(e){return 'err '+e}};",
        "var __k=function(o){try{return Object.keys(o||{}).slice(0,60)}catch(e){return 'err '+e}};",
        "var __p=function(o){try{return Object.getOwnPropertyNames(Object.getPrototypeOf(o)).slice(0,60)}catch(e){return 'err '+e}};",
        "console.error('SHPROBE data keys '+__g(function(){return __k(data)}));",
        "console.error('SHPROBE data '+__g(function(){return data}));",
        "console.error('SHPROBE form keys '+__g(function(){return __k(form)}));",
        "console.error('SHPROBE form.formMode '+__g(function(){return form.formMode}));",
        "console.error('SHPROBE form.shaForm._formData keys '+__g(function(){return __k(form.shaForm._formData)}));",
        "console.error('SHPROBE form.shaForm._formData '+__g(function(){return form.shaForm._formData}));",
        "console.error('SHPROBE handles '+__g(function(){return {formGetFieldValue:typeof form.getFieldValue,formInstanceGetFieldValue:typeof (form.formInstance||{}).getFieldValue,formGetFormData:typeof form.getFormData,formSetFieldsValue:typeof form.setFieldsValue}}));",
        "console.error('SHPROBE pageContext keys '+__g(function(){return __k(pageContext)}));",
        "console.error('SHPROBE pageContext proto '+__g(function(){return __p(pageContext)}));",
        "console.error('SHPROBE contexts keys '+__g(function(){return __k(contexts)}));",
    ]
    if field:
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', field) is not None, '--field must be a component/property name (letters, digits, _ . -)')
        f = "'" + field + "'"
        L += [
            f"console.error('SHPROBE field {field} via form.getFieldValue: '+__g(function(){{return form.getFieldValue({f})}}));",
            f"console.error('SHPROBE field {field} via form.formInstance.getFieldValue: '+__g(function(){{return form.formInstance.getFieldValue({f})}}));",
            f"console.error('SHPROBE field {field} via data: '+__g(function(){{return data[{f}]}}));",
            f"console.error('SHPROBE field {field} via the DOM node: '+__g(function(){{var n=document.querySelector('[data-sha-c-name=\"'+{f}+'\"] textarea, [data-sha-c-name=\"'+{f}+'\"] input');return n?n.value:'(no DOM node)'}}));",
        ]
    L.append("}catch(e){console.error('SHPROBE err '+e)}")
    return ''.join(L)


def _strings(o):
    """yield (container, key, value) for every string in the markup tree"""
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if isinstance(v, str):
                yield o, k, v
            else:
                yield from _strings(v)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            if isinstance(v, str):
                yield o, i, v
            else:
                yield from _strings(v)


def count_markers(markup):
    return sum(v.count(TAG) for _, _, v in _strings(markup))


def _own_strings(o, prop):
    """(container, key, value) of string properties named `prop` that belong to this component (its child components are not searched)"""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == 'components':
                continue
            if isinstance(v, str):
                if k == prop:
                    yield o, k, v
            else:
                yield from _own_strings(v, prop)
    elif isinstance(o, list):
        for v in o:
            yield from _own_strings(v, prop)


def locate(markup, component, prop, contains=None):
    from core.tree import walk
    comps = [c for c, _, _ in walk(markup) if c.get('componentName') == component or c.get('id') == component]
    require(len(comps) == 1, f'anchor: component {component!r} matched {len(comps)} times (need exactly 1; use the componentName or the id)')
    hits = [h for h in _own_strings(comps[0], prop) if not contains or contains in h[2]]
    require(len(hits) == 1, f'anchor: {len(hits)} string properties named {prop!r} in {component!r}'
                            + (f' containing {contains!r}' if contains else '') + ' (need exactly 1; use --contains to pick one)')
    return hits[0]


def make_add(component, prop, contains=None, field=None):
    line = TAG + payload(field) + END + '\n'

    def add(markup):
        require(count_markers(markup) == 0, 'this form already holds a probe marker: run `shrec.py probe-scope <form> --remove --push` first (one probe per form)')
        parent, key, val = locate(markup, component, prop, contains)
        parent[key] = line + val
        require(_BLOCK_RX.sub('', parent[key]) == val, 'probe self-check failed: removing the probe would not restore the script exactly')
        return [f'TEMPORARY probe added: {component}.{prop} (script-scope dump {TAG}) - must be removed']
    return add


def remove(markup):
    n = 0
    for parent, key, val in list(_strings(markup)):
        if TAG in val:
            new, c = _BLOCK_RX.subn('', val)
            require(TAG not in new, 'a probe marker without its end marker was found: edit it out by hand (do not guess)')
            parent[key] = new
            n += c
    return [f'probe removed: {n} marker block(s)'] if n else []


def _markers_now(module, form):
    """independent fresh read of the form on the local backend: number of probe markers it holds"""
    row = pushmod.find(Api('local'), module, form)
    return row['markup'].count(TAG)


def browse(page, loads, wait, click, viewport=(1700, 1000)):
    from core.browse import session, settle
    out = []
    for k in range(1, loads + 1):
        log = {}
        with session('local', log, viewport=viewport) as pg:      # read-only browser: writes the click would send are blocked
            pg.goto(page)
            settle(pg, wait)
            if click:
                try:
                    pg.get_by_role('button', name=click).first.click(timeout=20000)
                    settle(pg, 3000)
                except Exception as e:
                    print(f'  (could not click {click!r}: {str(e)[:120]})')
        lines = [c.split('SHPROBE', 1)[1].strip() for c in log['console'] if 'SHPROBE' in c]
        out.append(lines)
        print(f'\n--- load {k}/{loads}: {len(lines)} probe line(s)')
        for ln in lines:
            print('  SHPROBE', ln)
        if not lines:
            print('  (no SHPROBE output: the script did not run during this load; use --click "<button text>" for a click handler, or check the property name)')
        if log.get('blocked'):
            print('  writes blocked by the read-only browser:', log['blocked'][:3])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog='shrec probe-scope', description='Script-scope probe (local only). See the module docstring.')
    ap.add_argument('form', help='<Module>/<form name>')
    ap.add_argument('--component', help='componentName (or id) of the component that owns the script')
    ap.add_argument('--prop', help='name of the string property that holds the script, e.g. expression, renderer, onAfterDataLoad')
    ap.add_argument('--contains', help='pick the script property that contains this text (when several share the name)')
    ap.add_argument('--field', help='also report what the handles and the DOM hold for this component name (sub-form scope check, H49)')
    ap.add_argument('--page', help='page to load (default /dynamic/<Module>/<form>)')
    ap.add_argument('--loads', type=int, default=2)
    ap.add_argument('--click', help='visible text of a button to click in the read-only browser (writes stay blocked)')
    ap.add_argument('--wait', type=int, default=12000)
    ap.add_argument('--remove', action='store_true', help='only remove probe markers from the form')
    ap.add_argument('--push', action='store_true', help='really write (default: dry run)')
    a = ap.parse_args(argv)
    require(os.environ.get('SHREC_TARGET', 'local') in ('', 'local'), 'REFUSED: the probe runs on the LOCAL backend only (unset SHREC_TARGET or set it to local)')
    require('/' in a.form, 'form must be <Module>/<form name>')
    module, form = a.form.split('/', 1)
    if a.remove:
        notes = pushmod.push(module, form, remove, dry_run=not a.push, role='local', rule=RULE)
        if a.push:
            print(f'markers left in {a.form}: {_markers_now(module, form)}')
        elif notes:
            print('DRY RUN: add --push to remove them')
        return 0
    require(a.component and a.prop, '--component and --prop are required (the anchor of the injection); use --remove to clean up')
    add = make_add(a.component, a.prop, a.contains, a.field)
    if not a.push:
        print('DRY RUN (nothing written): the probe would be added, the page loaded and the probe removed again. Add --push to do it.')
        pushmod.push(module, form, add, dry_run=True, role='local', rule=RULE)
        return 0
    require(_markers_now(module, form) == 0, f'{a.form} already holds a probe marker: run `shrec.py probe-scope {a.form} --remove --push` first')
    state = {'ran': False}

    def add_tracked(markup):
        notes = add(markup)
        state['ran'] = bool(notes)
        return notes
    failure, code = None, 0
    try:
        pushmod.push(module, form, add_tracked, role='local', rule=RULE)
        browse(a.page or f'/dynamic/{module}/{form}', a.loads, a.wait, a.click)
    except BaseException as e:      # incl. KeyboardInterrupt: the clean-up below still runs
        failure = e
    finally:
        if state['ran']:
            try:
                pushmod.push(module, form, remove, role='local', rule=RULE)
                left = _markers_now(module, form)
                print(f'PROBE REMOVED: markers left in {a.form}: {left}' + ('' if left == 0 else '  <-- NOT CLEAN'))
                require(left == 0, 'probe marker still present after the removal')
            except BaseException as e2:
                print(f'!!! PROBE NOT REMOVED from {a.form} ({type(e2).__name__}: {str(e2)[:200]}). Run NOW: shrec.py probe-scope {a.form} --remove --push',
                      file=sys.stderr)
                code = 3
    if failure is not None and code == 0:
        raise failure
    if failure is not None:
        print(f'(the probe run itself failed first: {type(failure).__name__}: {str(failure)[:200]})', file=sys.stderr)
    return code
