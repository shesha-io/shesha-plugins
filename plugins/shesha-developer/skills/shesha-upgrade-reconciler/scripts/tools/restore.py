"""Restore configuration from the mandatory backups. Restoring is itself a WRITE: it follows the same rules as any push - dry run by
default, the host must be the one the user confirmed (never the reference), a deployed site needs the in-session authorisation, the
current row is backed up (and verified) BEFORE it is overwritten, and the result is read back and logged to the ledger.

  shrec.py restore --list [--target local|deployed]
  shrec.py restore --run <run id> --target local|deployed --form <Module/name>   [--source before|snapshot] [--push]    one form
  shrec.py restore --run <run id> --target local|deployed --rule <rule>          [--source before|snapshot] [--push]    every item that rule pushed
  shrec.py restore --run <run id> --target local|deployed --all                  [--source before|snapshot] [--push]    the whole run
  shrec.py restore --target local|deployed --all                                 the newest run of that target

`--run R` alone is the whole run (same as --all). Backups live in <work>/backups/<role>/<run id>/ : snapshot/ (every form about to be
touched, taken at the start of the run), before/ (the row immediately before each write), after/ (what was sent), manifest.json.
--source before (default) restores the state an item had immediately before the run's FIRST write to it; --source snapshot restores the
state at the start of the run (forms only). A backup made on one role/host is refused on another.

What is restored, by backup kind:
  form      markup and modelType (what UpdateMarkup writes), through core.push.push.
  entity    the backed-up scalar fields that differ now, through core.push.push_entity (the row id comes from the backup).
  workflow  the BPMN schema, through core.push.push_workflow_schema.
  absent    the form was CREATED by the run. Deleting a created form is never automatic: the tool reports it and prints the form id so
            it can be deleted by hand in the designer once the user agrees.
Without --push it only reports what would change. After a --push, clear the browser form caches and close stale designer tabs, then
re-run the rule's dry run to see what it would change again. Every restore logs a `restore` ledger event (item, source backup, result).
"""
import argparse
import glob
import json
import os
import re

from core import ledger, project
from core.project import require

STAMP = r'(?:\d{9}|absent)'


def stem_of(module, name):
    return re.sub(r'[^\w.-]', '_', f'{module}__{name.strip()}')


def list_runs(role):
    for r in ([role] if role else ['local', 'deployed']):
        for d in sorted(glob.glob(os.path.join(project.work_path('backups', r, mkdir=False), '*'))):
            man = project.read_json(os.path.join(d, 'manifest.json'), {}) or {}
            n_before = len(glob.glob(os.path.join(d, 'before', '*.json')))
            print(f'{r:9} run {os.path.basename(d)}  forms in snapshot {len(man.get("forms", [])):4}  written (before-backups) {n_before:4}  '
                  f'rule {man.get("rule")}  host {man.get("host")}')


def load(path):
    d = project.read_json(path)
    require(isinstance(d, dict) and 'row' in d, f'{path}: not a backup file')
    return d


def kind_of(w):
    """'absent' | 'entity' | 'workflow' | 'form' for a backup wrapper"""
    if w.get('absent'):
        return 'absent'
    return w.get('kind') if w.get('kind') in ('entity', 'workflow') else 'form'


def item_key(w):
    k = kind_of(w)
    if k == 'entity':
        return f"entity:{w.get('module')}:{w.get('name')}:{w.get('id')}"
    if k == 'workflow':
        return f"workflow:{w.get('name')}:{w.get('id')}"
    return f"form:{w.get('module')}/{w.get('name')}"


def collect_items(rundir):
    """{key: {'kind', 'key', 'before': wrapper (earliest write), 'before_path', 'snapshot': wrapper | None}} from a run directory."""
    items = {}
    for p in sorted(glob.glob(os.path.join(rundir, 'before', '*.json'))):
        w = load(p)
        key = item_key(w)
        cur = items.get(key)
        if cur is None or w.get('timestamp', '') < cur['before'].get('timestamp', ''):
            items[key] = {'kind': kind_of(w), 'key': key, 'before': w, 'before_path': p, 'snapshot': None}
    for key, it in items.items():
        if it['kind'] == 'form':
            sp = os.path.join(rundir, 'snapshot', stem_of(it['before'].get('module'), it['before'].get('name')) + '.json')
            if os.path.exists(sp):
                it['snapshot'] = load(sp)
                it['snapshot_path'] = sp
    return items


def pushed_pairs(run, rule):
    """{(module, form)} the ledger shows as pushed by `rule` in this run (a rule may be one of several in a combined label)."""
    out = set()
    for e in ledger.read(run):
        if e.get('event') in ('form', 'retire') and e.get('result') in ('pushed', 'written-unverified'):
            if e.get('rule') == rule or rule in (e.get('rules') or {}) or rule in str(e.get('rule')).split(','):
                out.add((e.get('module'), e.get('form')))
    return out


def select(items, run, form=None, rule=None):
    """Items to restore. Pure function over collect_items() output and the ledger (for --rule)."""
    if form:
        mod, _, name = form.partition('/')
        require(name, '--form is <Module>/<name>')
        hit = [it for it in items.values() if it['kind'] in ('form', 'absent') and it['before'].get('module') == mod
               and (it['before'].get('name') or '').strip() == name.strip()]
        require(hit, f'run {run} has no backup for {form}')
        return hit
    if rule:
        pairs = pushed_pairs(run, rule)
        require(pairs, f'run {run} pushed nothing for rule {rule}')
        return [it for it in items.values() if (it['before'].get('module'), (it['before'].get('name') or '').strip()) in
                {(m, (f or '').strip()) for m, f in pairs}]
    return list(items.values())


def created_form_id(run, w):
    """id of a form created by the run (from the ledger), or None"""
    for e in reversed(ledger.read(run)):
        if e.get('event') == 'form' and e.get('result') in ('pushed', 'written-unverified') and e.get('module') == w.get('module') \
                and (e.get('form') or '').strip() == (w.get('name') or '').strip() and e.get('form_id'):
            return e['form_id']
    return None


def entity_changes(backup_row, current_row):
    """The backed-up scalar fields that differ from the current row: {field: backed-up value}. Pure function."""
    out = {}
    for k, v in (backup_row or {}).items():
        if k == 'id' or isinstance(v, (dict, list)) or k.startswith('last'):
            continue
        if k in current_row and current_row[k] != v:
            out[k] = v
    return out


def plan_text(it):
    k = it['kind']
    b = it['before']
    if k == 'absent':
        return f"created form {b.get('module')}/{b.get('name')}: deleting it is manual"
    return f"{k} {b.get('module')}/{b.get('name')}"


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec restore', description=__doc__.split('\n')[0])
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--run')
    ap.add_argument('--target', '--env', dest='target', choices=['local', 'deployed'])
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--form', help='<Module>/<name>')
    g.add_argument('--rule')
    g.add_argument('--all', action='store_true')
    ap.add_argument('--source', default='before', choices=['before', 'snapshot'])
    ap.add_argument('--push', action='store_true')
    a = ap.parse_args(argv)
    if a.list:
        list_runs(a.target)
        return 0
    require(a.target, '--target local|deployed is required')
    role = a.target
    run = a.run
    if not run:
        runs = sorted(glob.glob(os.path.join(project.work_path('backups', role, mkdir=False), '*')))
        require(runs and (a.all or a.form or a.rule), 'pass --run <id> (see --list), or --all for the newest run')
        run = os.path.basename(runs[-1])
    require(a.form or a.rule or a.all or a.run, 'choose --form, --rule, --all or --run')
    rundir = os.path.join(project.work_path('backups', role, mkdir=False), run)
    require(os.path.isdir(rundir), f'no such run: {rundir}')
    os.environ['SHREC_TARGET'] = role
    os.environ.setdefault('SHREC_RULE', 'restore')
    items = collect_items(rundir)
    require(items, 'this run wrote nothing (no before-backups): nothing to restore')
    todo = select(items, run, a.form, a.rule)
    from core import push as pushmod
    from core.api import Api
    host = Api(role).base
    for it in todo:
        w = it['before']
        require(w.get('role') == role and w.get('host') == host,
                f"[{it['key']}] backup was taken on {w.get('role')} {w.get('host')}, not on {role} {host}: refusing")
    forms = [it for it in todo if it['kind'] == 'form']
    if a.push and forms:
        print('snapshot dir:', pushmod.begin_run([(it['before']['module'], it['before']['name']) for it in forms], rule='restore', role=role))
    n_changed, failed = 0, []
    for it in todo:
        w, k = it['before'], it['kind']
        label = plan_text(it)
        result = 'failed'
        try:
            if k == 'absent':
                fid = created_form_id(run, w)
                print(f'[{w.get("module")}/{w.get("name")}] CREATED by run {run} (form id {fid or "unknown: look it up in the designer"}): '
                      'restoring means deleting it - do that by hand once the user agrees; this tool never deletes')
                result = 'manual-delete-needed'
            elif k == 'form':
                use = it['snapshot'] if a.source == 'snapshot' and it['snapshot'] else w
                row = use['row']
                want = json.loads(row['markup']) if isinstance(row['markup'], str) else row['markup']

                def transform(markup, _w=want, _u=use):
                    if markup == _w:
                        return []
                    markup.clear()
                    markup.update(_w)
                    return [f'restored from run {run} ({a.source}, taken {_u["timestamp"]})']
                notes = pushmod.push(w['module'], w['name'], transform, dry_run=not a.push, role=role, rule='restore',
                                     model_type=row.get('modelType'))
                n_changed += bool(notes)
                result = ('restored' if a.push else 'would-restore') if notes else 'already-equal'
            elif k == 'entity':
                module, _, cls = w['module'].partition('/')
                back_row = w['row']

                def transform(row, _b=back_row):
                    ch = entity_changes(_b, row)
                    return ch, [f'restored from run {run}: {", ".join(sorted(ch))}'] if ch else []
                notes = pushmod.push_entity(module, cls, w['id'], w['name'], transform, dry_run=not a.push, role=role, rule='restore')
                n_changed += bool(notes)
                result = ('restored' if a.push else 'would-restore') if notes else 'already-equal'
            elif k == 'workflow':
                changed = pushmod.push_workflow_schema(w['id'], w['name'], w['row'].get('workflowSchema'), dry_run=not a.push, role=role, rule='restore')
                n_changed += bool(changed)
                result = ('restored' if a.push else 'would-restore') if changed else 'already-equal'
        except Exception as e:
            failed.append((it['key'], f'{type(e).__name__}: {str(e)[:200]}'))
            print(f'[{it["key"]}] FAILED: {failed[-1][1]}')
        ledger.event('restore', env=role, host=host, module=w.get('module'), form=w.get('name'), item_kind=k, source=it['before_path'],
                     result=result, mode='push' if a.push else 'dry-run', run_restored=run)
        print(f'  -> {label}: {result}')
    print(('DRY RUN - ' if not a.push else '') + f'{n_changed} of {len(todo)} items differ from the backup'
          + ('' if a.push else ' (add --push to restore them)') + (f' | failed {len(failed)}' if failed else ''))
    ledger.event('summary', env=role, host=host, script='shrec restore', dry=not a.push, rules=['restore'], forms_changed=n_changed,
                 of=len(todo), failed=[f for f, _ in failed])
    return 1 if failed else 0
