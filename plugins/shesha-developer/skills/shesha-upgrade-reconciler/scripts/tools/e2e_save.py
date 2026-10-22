"""Functional check on the LOCAL role: open a details page, click Edit, click Save WITHOUT changing anything, and report the write
calls with their HTTP status, any UI error, and whether the form returned to view mode. Saving unchanged values is the safest real
test of the save path.

  shrec.py e2e-save <module>/<form> <record id> [<module>/<form> <record id> ...] [--push]   (dry run without --push: it SAVES records)

Button texts come from project.json "e2e" {"editText": "Edit", "saveText": "Save"} (defaults shown). Route:
/dynamic/<module>/<form>?id=<record id>. This is a write against the local database, so the local api must be the write target
the user confirmed (`shrec.py confirm-target --api <url>`); the browser may write to the local api only. Value-changing checks must
restore the exact original through the API afterwards. The outcome is logged as a `verify` ledger event of kind e2e.
"""
import json

from core import project
from core.browse import session, settle
from core.push import assert_writable
from tools._common import log_event

SELECT_FORM = '[data-sha-form-name]'
UI_JS = ("() => [...document.querySelectorAll('.ant-message-notice, .ant-notification-notice, .ant-form-item-explain-error')]"
         ".map(e=>e.innerText.trim().slice(0,140))")


def button_texts():
    cfg = project.config().get('e2e') or {}
    return cfg.get('editText') or 'Edit', cfg.get('saveText') or 'Save'


def pairs(argv):
    if len(argv) < 2 or len(argv) % 2:
        raise project.ConfigError('usage: e2e-save <module>/<form> <record id> [<module>/<form> <record id> ...]')
    out = []
    for target, rid in zip(argv[::2], argv[1::2]):
        if '/' not in target:
            raise project.ConfigError(f'{target!r}: give the form as <module>/<form>')
        module, form = target.split('/', 1)
        out.append((module, form, rid))
    return out


def main(argv):
    push = '--push' in argv
    todo = pairs([a for a in argv if a != '--push'])
    api = project.env_config('local')['api']
    if not push:     # it SAVES real records (Edit -> Save unchanged) on the local role: an explicit opt-in, like every write
        for module, form, rid in todo:
            print(f'DRY RUN - would open {module}/{form}?id={rid} on {api}, click {button_texts()[0]!r} then {button_texts()[1]!r} '
                  'without changes and record the write calls; add --push to run it')
        return 0
    assert_writable('local', api)
    edit_text, save_text = button_texts()
    failed = 0
    for module, form, rid in todo:
        log, calls = {}, []
        label = f'{module}/{form}'
        try:
            with session('local', log, viewport=(1568, 950), allow_local_writes=True) as pg:
                pg.on('response', lambda r: (r.request.method in ('PUT', 'POST') and api + '/api/' in r.url
                                             and not any(x in r.url for x in ('CheckPermissions', 'SyncClientApi')))
                      and calls.append(f'{r.status} {r.request.method} {r.url.split("/api/")[1][:90]}'))
                pg.goto(f'/dynamic/{module}/{form}?id={rid}', timeout=300000)
                pg.wait_for_selector(SELECT_FORM, timeout=300000)
                settle(pg, 8000)
                pg.get_by_text(edit_text, exact=True).first.click(timeout=60000)
                settle(pg, 5000)
                pg.get_by_role('button', name=save_text).first.click(timeout=60000)
                settle(pg, 8000)
                ui = pg.evaluate(UI_JS)
                back = pg.evaluate("(t) => [...document.querySelectorAll('button, a')].some(b=>(b.innerText||'').trim()===t)", edit_text)
                print(json.dumps({'form': label, 'calls': calls, 'uiMessages': ui, 'backToView': back}))
                ok = bool(back and calls and all(c.startswith('200') for c in calls))
                failed += 0 if ok else 1
                log_event('verify', env='local', host=api, kind='e2e', result='ok' if ok else 'fail',
                          detail=f'{label}: {edit_text} -> {save_text} unchanged: {len(calls)} write call(s), back to view {back}')
        except Exception as e:
            failed += 1
            print(json.dumps({'form': label, 'error': str(e)[:200], 'calls': calls}))
    return 1 if failed else 0
