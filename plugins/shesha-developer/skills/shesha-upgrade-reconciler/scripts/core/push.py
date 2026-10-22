"""The ONLY write path of the reconciler (forms through FormConfiguration/UpdateMarkup on the in-place form API of
Shesha 0.45+/0.46; entities through dynamic CRUD; workflow schemas through UpdateSchema).

Write target = $SHREC_TARGET: 'local' (default) or 'deployed'. The 'reference' role is NEVER writable.

Host guards (assert_writable, before every request that writes; never contacts the network):
- every host recorded for the reference role is refused, whatever else is true;
- the host must be EXACTLY the write target the user confirmed this session (`shrec.py confirm-target --api <url>`);
- local: localhost / 127.0.0.1 only;
- deployed: https, equal to the configured deployed api, an authorisation younger than the TTL
  (`shrec.py authorise-deployed`), and $SHREC_DEPLOY_CONFIRM set to exactly that host in the shell.

Mandatory backups (nothing is written without them):
- whole-run snapshot: begin_run(forms) saves the full row of every form about to be touched, with a manifest;
- per-write backup: the current row is saved to <work>/backups/<role>/<run>/before/ and re-read from disk first;
- read-back: markup and modelType must equal what was sent (UpdateMarkup overwrites modelType with the request value,
  so the existing value is always carried forward).
Dry run is the default: a preview file and a ledger line, nothing written to the backend and nothing under after/.

Transforms are callables (markup_dict) -> list[str] of change notes; they assert their anchors (raise WriteRefused)
and return [] when already applied. A transform may carry `.rules = {rule: [notes]}` for the report.
"""
import json
import os
import re
import sys
import time
import urllib.request

from core import ledger
from core.api import Api, FORMS, modname
from core.project import (env_config, netloc, reference_hosts, write_target, require, WriteRefused, is_localhost,
                          deployed_authorised, work_path, read_json)

_UNSET = object()


class WrittenUnverified(RuntimeError):
    """The write request was sent, but the outcome could not be confirmed (no response, an error status, or a read-back
    mismatch). The backend may hold the new value: the form counts as TOUCHED (export list, restore --rule) and must not
    be retried blindly; check it, then restore it from its before/ backup or re-run the rule."""
WRITABLE = ('local', 'deployed')


def _script():
    return os.path.basename(os.environ.get('SHREC_SCRIPT') or (sys.argv[0] if sys.argv and sys.argv[0] else 'push'))


def target():
    t = os.environ.get('SHREC_TARGET', 'local')
    require(t in WRITABLE, f'SHREC_TARGET must be local or deployed (got {t}); the reference role is never written')
    return t


def assert_writable(role, base):
    """Raise WriteRefused unless writing to `base` as `role` is allowed."""
    require(role != 'reference', 'REFUSED: the reference environment is read-only; the reconciler never writes to it')
    require(netloc(base) not in reference_hosts(), f'REFUSED: {base} is recorded as a reference host; it is never written')
    require(role in WRITABLE, f'role {role} is not writable')
    wt = write_target()
    require(bool(wt) and wt.get('api') == base and wt.get('role') == role,
            f'{base} is not the write target the user confirmed: ask the user, then `shrec.py confirm-target --api {base}`')
    if role == 'local':
        require(is_localhost(base), f'refusing non-local write to {base} as the local role')
        return
    cfg = env_config('deployed')
    require(base.startswith('https://') and base == cfg['api'], f'refusing: {base} is not the configured deployed api')
    require(deployed_authorised(base), 'deployed writes are not authorised (or the authorisation expired): only after the user '
                                       'says so in this session (`shrec.py authorise-deployed --api <url>`)')
    require(os.environ.get('SHREC_DEPLOY_CONFIRM', '').rstrip('/') == base,
            'set SHREC_DEPLOY_CONFIRM to the exact deployed API host in this shell to write there')


class Writer(Api):
    def __init__(self, role=None):
        super().__init__(role or target())

    def put(self, path, body):
        return self._send('PUT', path, body)

    def post(self, path, body):
        return self._send('POST', path, body)

    def _send(self, method, path, body):
        assert_writable(self.role, self.base)
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(),
                                     {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token}, method=method)
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read().decode('utf-8', 'replace')


_IDX = {}


def _index(a, refresh=False):
    if refresh or a.role not in _IDX:
        idx = {}
        for i in a.get_all(FORMS + '/GetAll'):
            idx.setdefault((modname(i).strip(), (i.get('name') or '').strip()), []).append(i['id'])
        _IDX[a.role] = idx
    return _IDX[a.role]


def find(a, module, name):
    """Fresh read of one form. The name->id index is cached per process and role; the row is re-read by id every time."""
    ids = _index(a).get((module, name.strip()), [])
    require(len(ids) == 1, f'{module}/{name}: {len(ids)} matches')
    row = a.get(FORMS + '/Get', id=ids[0])['result']
    require(bool(row) and row.get('id') == ids[0] and 'markup' in row, f'{module}/{name}: unexpected Get payload')
    return row


# ---------------------------------------------------------------- backups
_RUNS = {}


def fname(module, name, stamp=None):
    base = re.sub(r'[^\w.-]', '_', f'{module}__{name.strip()}')
    return base + (f'.{stamp}' if stamp else '') + '.json'


def _stamp():
    return time.strftime('%H%M%S') + f'{int(time.time() * 1000) % 1000:03d}'


def write_json_verified(path, obj):
    """write JSON and re-read it from disk; refuses when the file does not hold exactly what was written"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    with open(path, encoding='utf-8') as f:
        back = json.load(f)
    require(back == json.loads(json.dumps(obj)), f'BACKUP NOT VERIFIED ({path}): refusing to write')


def backup_wrapper(role, base, module, name, row, **extra):
    return dict({'role': role, 'host': base, 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'), 'module': module,
                 'name': name.strip(), 'id': row.get('id') if row else None, 'modelType': (row or {}).get('modelType'),
                 'row': row}, **extra)


def run_dir(role):
    if role not in _RUNS:
        d = work_path('backups', role, ledger.run_id())
        os.makedirs(d, exist_ok=True)
        _RUNS[role] = {'dir': d, 'forms': {}}
    return _RUNS[role]


def _save_manifest(role, w, rule):
    r = run_dir(role)
    path = os.path.join(r['dir'], 'manifest.json')
    old = read_json(path, {}) or {}
    forms = {f"{f.get('module')}/{f.get('name')}": f for f in old.get('forms') or []}
    for k, f in r['forms'].items():
        forms.setdefault(k, f)                       # the first snapshot of a form wins
    rules = old.get('rules') or ([old['rule']] if old.get('rule') else [])
    if rule and rule not in rules:
        rules.append(rule)
    man = {'run': ledger.run_id(), 'batch': ledger.batch_id(), 'role': role, 'host': w.base,
           'created': old.get('created') or time.strftime('%Y-%m-%dT%H:%M:%S'), 'updated': time.strftime('%Y-%m-%dT%H:%M:%S'),
           'rules': rules, 'forms': list(forms.values())}
    write_json_verified(path, man)


def _snapshot_one(role, w, module, name, rule):
    r = run_dir(role)
    key = f'{module}/{name.strip()}'
    if key in r['forms']:
        return r['forms'][key]
    p = os.path.join(r['dir'], 'snapshot', fname(module, name))
    if os.path.exists(p):           # an earlier process of the same run already saved the pre-run state: never overwrite it
        old = read_json(p, {}) or {}
        row = old.get('row') or {}
        r['forms'][key] = {'module': module, 'name': name.strip(), 'id': row.get('id'), 'modelType': row.get('modelType'),
                           'snapshot': p, 'markup_sha256': ledger.sha256(row.get('markup'))}
        return r['forms'][key]
    row = find(w, module, name)
    write_json_verified(p, backup_wrapper(role, w.base, module, name, row))
    r['forms'][key] = {'module': module, 'name': name.strip(), 'id': row['id'], 'modelType': row.get('modelType'),
                       'snapshot': p, 'markup_sha256': ledger.sha256(row.get('markup'))}
    return r['forms'][key]


def _run_start(role, host, rule, **kw):
    if not _RUNS.get(role, {}).get('started'):
        run_dir(role)['started'] = True
        ledger.event('run-start', env=role, host=host, script=rule or _script(), mode='push',
                     reference_hosts=sorted(reference_hosts()), **kw)


def begin_run(forms, rule=None, role=None):
    """Whole-run snapshot of every (module, name) about to be touched + manifest.json, BEFORE the first write.
    Refuses when this run may not write at all, or when a snapshot cannot be written and verified."""
    role = role or target()
    w = Writer(role)
    assert_writable(role, w.base)
    for module, name in forms:
        _snapshot_one(role, w, module, name, rule)
    _save_manifest(role, w, rule)
    _run_start(role, w.base, rule, snapshot_dir=run_dir(role)['dir'], forms=len(forms))
    return run_dir(role)['dir']


def _fail(done, e, sent):
    """Ledger a failure: 'written-unverified' once the write request was sent (it may have landed), else 'failed'."""
    reason = f'{type(e).__name__}: {str(e)[:300]}'
    if sent:
        done('written-unverified', reason=reason)
        raise WrittenUnverified(reason) from e
    done('failed', reason=reason)
    raise e


# ---------------------------------------------------------------- push one form
def push(module, name, transform, dry_run=False, role=None, rule=None, model_type=_UNSET, event='form'):
    """Apply `transform` to one form and write it (or preview it on a dry run). event='retire' records an unwind."""
    role = role or target()
    w = Writer(role)
    host = w.base
    require(netloc(host) not in reference_hosts() and role != 'reference', 'REFUSED: the reference environment is read-only')
    rule = rule or os.environ.get('SHREC_RULE') or _script()
    if not dry_run:
        assert_writable(role, host)                      # host guard BEFORE anything is read for a write
        _run_start(role, host, rule)
    rec = {'module': module, 'form': name.strip(), 'rule': rule, 'mode': 'dry-run' if dry_run else 'push'}

    def done(result, **kw):
        ledger.event(event, env=role, host=host, result=result, **rec, **kw)

    row = find(w, module, name)
    rec['form_id'] = row['id']
    rec['before_sha256'] = ledger.sha256(row['markup'])
    markup = json.loads(row['markup'])
    try:
        notes = transform(markup)
    except AssertionError as e:
        done('skipped-anchor', reason=str(e)[:300])
        raise
    except Exception as e:
        _fail(done, e, locals().get('sent'))
    if not notes:
        print(f'[{name}] no change (already applied)')
        done('no-change', reason='already applied')
        return []
    rec.update(notes=notes, rules=getattr(transform, 'rules', None))
    new_markup = json.dumps(markup, ensure_ascii=False)
    rec['after_sha256'] = ledger.sha256(new_markup)
    mtype = row.get('modelType') if model_type is _UNSET else model_type
    print(f'[{name}] {len(notes)} change(s):')
    for n in notes:
        print('   -', n)
    if dry_run:
        pv = os.path.join(run_dir(role)['dir'], 'preview', fname(module, name))
        os.makedirs(os.path.dirname(pv), exist_ok=True)
        with open(pv, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(markup, f, ensure_ascii=False, indent=1)
        print(f'[{name}] DRY RUN - not pushed')
        done('dry-run')
        return notes
    backup = ''
    try:
        _snapshot_one(role, w, module, name, rule)
        backup = os.path.join(run_dir(role)['dir'], 'before', fname(module, name, _stamp()))
        write_json_verified(backup, backup_wrapper(role, host, module, name, row))
        rec['backup'] = backup
        sent = True
        status, body = w.put(FORMS + '/UpdateMarkup', {'id': row['id'], 'markup': new_markup, 'modelType': mtype})
        require(status == 200, (status, body[:300]))
        back = find(w, module, name)
        require(back['markup'] == new_markup, 'READ-BACK MISMATCH')
        require(back.get('modelType') == mtype, ('modelType changed', back.get('modelType')))
        write_json_verified(os.path.join(run_dir(role)['dir'], 'after', fname(module, name)), markup)
        _save_manifest(role, w, rule)
    except Exception as e:
        _fail(done, e, locals().get('sent'))
    print(f'[{name}] pushed + read-back verified on {role} (id {row["id"]}, modelType {mtype})')
    done('pushed')
    return notes


# ---------------------------------------------------------------- create a form that is missing on the target
def create_form(module, name, markup, model_type, form_label=None, description='', source=None, dry_run=False, role=None, rule=None):
    """Create a form that is MISSING on the target. Refuses when it exists (that is push()'s job); never deletes.
    The backup is an 'absent' record, so restore knows the form was created."""
    role = role or target()
    w = Writer(role)
    host = w.base
    rule = rule or os.environ.get('SHREC_RULE') or _script()
    rec = {'module': module, 'form': name.strip(), 'rule': rule, 'mode': 'dry-run' if dry_run else 'push',
           'notes': ['created (missing on the target)']}

    def done(result, **kw):
        ledger.event('form', env=role, host=host, result=result, **rec, **kw)

    n = len(_index(w, refresh=True).get((module, name.strip()), []))
    require(n == 0, f'{module}/{name}: {n} match(es) on {role}: create_form never overwrites or duplicates; use push()')
    new_markup = json.dumps(markup, ensure_ascii=False)
    if dry_run:
        print(f'[{name}] DRY RUN - would create on {role} (modelType {model_type}, {len(new_markup)} chars)')
        done('dry-run')
        return None
    assert_writable(role, host)
    _run_start(role, host, rule)
    try:
        backup = os.path.join(run_dir(role)['dir'], 'before', fname(module, name, 'absent'))
        write_json_verified(backup, backup_wrapper(role, host, module, name, None, absent=True, source=source))
        rec['backup'] = backup
        mods = w.get_all('/api/services/app/Module/GetAll')
        mid = [m['id'] for m in mods if m.get('name') == module]
        require(len(mid) == 1, f'module {module}: {len(mid)} matches')
        sent = True
        status, body = w.post(FORMS + '/Create', {'moduleId': mid[0], 'name': name.strip(), 'label': form_label or name.strip(),
                                                  'description': description or '', 'markup': new_markup, 'modelType': model_type})
        require(status == 200 and json.loads(body).get('success') is not False, (status, body[:300]))
        _index(w, refresh=True)
        back = find(w, module, name)
        if back['markup'] != new_markup or back.get('modelType') != model_type:   # Create may ignore markup/modelType
            status, body = w.put(FORMS + '/UpdateMarkup', {'id': back['id'], 'markup': new_markup, 'modelType': model_type})
            require(status == 200, (status, body[:300]))
            back = find(w, module, name)
        require(back['markup'] == new_markup, 'READ-BACK MISMATCH')
        require(back.get('modelType') == model_type, ('modelType', back.get('modelType')))
        rec['form_id'] = back['id']
        rec['after_sha256'] = ledger.sha256(new_markup)
        write_json_verified(os.path.join(run_dir(role)['dir'], 'after', fname(module, name)), markup)
    except Exception as e:
        _fail(done, e, locals().get('sent'))
    print(f'[{name}] created + read-back verified on {role} (id {back["id"]}, modelType {model_type})')
    done('pushed')
    return back['id']


# ---------------------------------------------------------------- one entity row through dynamic CRUD
def push_entity(module, cls, item_id, item_label, transform, dry_run=False, role=None, rule=None):
    """Update one entity row through /api/dynamic/{module}/{cls}/Crud/Update. `transform(row) -> (changes, notes)` where
    `changes` holds ONLY the fields to change ({} when already applied). Afterwards every changed field must read back
    as sent and every other scalar field must be unchanged."""
    role = role or target()
    w = Writer(role)
    host = w.base
    rule = rule or os.environ.get('SHREC_RULE') or _script()
    base = f'/api/dynamic/{module}/{cls}/Crud'
    rec = {'module': f'{module}/{cls}', 'form': item_label, 'rule': rule, 'mode': 'dry-run' if dry_run else 'push',
           'form_id': item_id, 'kind': 'entity'}

    def done(result, **kw):
        ledger.event('form', env=role, host=host, result=result, **rec, **kw)

    row = w.get(base + '/Get', id=item_id)['result']
    require(bool(row) and row.get('id') == item_id, f'{cls} {item_id}: unexpected Get payload')
    try:
        changes, notes = transform(row)
    except AssertionError as e:
        done('skipped-anchor', reason=str(e)[:300])
        raise
    if not changes:
        print(f'[{item_label}] no change (already applied)')
        done('no-change', reason='already applied')
        return []
    require('id' not in changes, 'transform must not change the id')
    rec['notes'] = notes
    if dry_run:
        print(f'[{item_label}] DRY RUN - {len(notes)} change(s):')
        for n in notes:
            print('   -', n)
        done('dry-run')
        return notes
    assert_writable(role, host)
    _run_start(role, host, rule)

    def scalars(r):
        return {k: v for k, v in r.items() if not isinstance(v, (dict, list)) and not k.startswith('last') and k not in changes}
    try:
        backup = os.path.join(run_dir(role)['dir'], 'before', fname(f'{module}.{cls}', f'{item_label}.{item_id}', _stamp()))
        write_json_verified(backup, backup_wrapper(role, host, f'{module}/{cls}', item_label, row, kind='entity'))
        rec['backup'] = backup
        sent = True
        status, body = w.put(base + '/Update', dict(changes, id=item_id))
        require(status == 200 and json.loads(body).get('success') is not False, (status, body[:300]))
        back = w.get(base + '/Get', id=item_id)['result']
        for k, v in changes.items():
            require(back.get(k) == v, f'READ-BACK MISMATCH ({k})')
        require(scalars(back) == scalars(row), 'other fields changed on the entity row')
        write_json_verified(os.path.join(run_dir(role)['dir'], 'after', fname(f'{module}.{cls}', f'{item_label}.{item_id}')), back)
    except Exception as e:
        _fail(done, e, locals().get('sent'))
    print(f'[{item_label}] pushed + read back on {role} ({cls} {item_id})')
    done('pushed')
    return notes


# ---------------------------------------------------------------- workflow definition schema (Shesha.Workflow)
WF_GET = '/api/services/SheshaWorkflow/WorkflowDefinition/Get'
WF_UPDATE = '/api/services/SheshaWorkflow/WorkflowDefinition/UpdateSchema'


def push_workflow_schema(item_id, name, schema, dry_run=False, role=None, rule=None):
    """Replace a workflow definition's BPMN schema the way the designer saves it (PUT UpdateSchema {id, workflowSchema});
    the full Get row is backed up first and the schema is read back by id afterwards."""
    role = role or target()
    w = Writer(role)
    host = w.base
    rule = rule or os.environ.get('SHREC_RULE') or _script()
    rec = {'module': 'workflow', 'form': name, 'rule': rule, 'mode': 'dry-run' if dry_run else 'push', 'form_id': item_id,
           'kind': 'workflow'}

    def done(result, **kw):
        ledger.event('form', env=role, host=host, result=result, **rec, **kw)

    row = w.get(WF_GET, id=item_id)['result']
    require(bool(row) and row.get('id') == item_id and 'workflowSchema' in row, f'workflow {item_id}: unexpected Get payload')
    if row['workflowSchema'] == schema:
        print(f'[{name}] no change (schema already applied)')
        done('no-change', reason='already applied')
        return False
    rec['notes'] = [f'workflow schema replaced ({len(row["workflowSchema"] or "")} -> {len(schema)} chars)']
    if dry_run:
        print(f'[{name}] DRY RUN - would replace the schema on {role}')
        done('dry-run')
        return True
    assert_writable(role, host)
    _run_start(role, host, rule)
    try:
        backup = os.path.join(run_dir(role)['dir'], 'before', fname('workflow', name, _stamp()))
        write_json_verified(backup, backup_wrapper(role, host, 'workflow', name, row, kind='workflow'))
        rec['backup'] = backup
        sent = True
        status, body = w.put(WF_UPDATE, {'id': item_id, 'workflowSchema': schema})
        require(status == 200 and json.loads(body).get('success') is not False, (status, body[:300]))
        back = w.get(WF_GET, id=item_id)['result']
        require(back.get('workflowSchema') == schema, 'READ-BACK MISMATCH (workflowSchema)')
        write_json_verified(os.path.join(run_dir(role)['dir'], 'after', fname('workflow', name)), {'id': item_id, 'row': back})
    except Exception as e:
        _fail(done, e, locals().get('sent'))
    print(f'[{name}] schema pushed + read back on {role} (id {item_id})')
    done('pushed')
    return True


__all__ = ['WriteRefused', 'assert_writable', 'begin_run', 'push', 'create_form', 'push_entity', 'push_workflow_schema',
           'find', 'run_dir', 'target', 'Writer']
