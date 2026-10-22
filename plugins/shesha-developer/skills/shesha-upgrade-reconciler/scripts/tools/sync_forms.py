"""Copy the already-reconciled forms of one role onto the target for every form the pre-upgrade line did NOT change.

Typical use in the merge-reconcile flow: the deployed site holds the team's later fixes (designer edits, hot fixes) and the local stack
was started from an older copy. For every form that the pre-upgrade line did not touch, the deployed copy is newer and wins; the forms
that line changed are three-way merged by merge3 instead and are excluded here.

  shrec.py sync-forms --from deployed|reference|local [--to local|deployed] [--module A,B] [--exclude-file <work>/merge/branch_changed.json] [--push]

The source is only READ (GET). The target is written through core.push.push (backup of the whole row, modelType carried, read-back
verified); --to deployed follows the same go-ahead rules as any deployed write (core/push.py). Dry run unless --push: it lists the forms
that differ. Forms that exist on the source but not on the target are reported, never created. A source role below 0.45 is versioned
and only its Live rows are copied (same rule as `snapshot`). One failing form never aborts the loop: failures are collected, listed at
the end, and the exit code is 1 when any form failed.
"""
import argparse
import json
import os

from core import ledger, project
from core.api import FORMS, modname
from core.project import require


def plan_names(source_items, target_index, modules, exclude):
    """(candidates [(module, name)], excluded count, missing [name]) - pure function over the source rows and the target (module, name) set."""
    cand, skipped, missing = [], 0, []
    for i in sorted(source_items, key=lambda x: (x.get('name') or '')):
        mod, n = (modname(i) or '').strip(), (i.get('name') or '').strip()
        if modules and mod not in modules:
            continue
        if n in exclude:
            skipped += 1
            continue
        if (mod, n) not in target_index:
            missing.append(n)
            continue
        cand.append((mod, n))
    return cand, skipped, missing


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec sync-forms', description=__doc__.split('\n')[0])
    ap.add_argument('--from', dest='src', default='deployed', choices=list(project.ROLES))
    ap.add_argument('--to', default=os.environ.get('SHREC_TARGET', 'local'), choices=['local', 'deployed'])
    ap.add_argument('--module', help='comma list of modules (default: the project modules)')
    ap.add_argument('--exclude-file', help='JSON list (or object keyed by form name) of forms to leave alone')
    ap.add_argument('--push', action='store_true')
    a = ap.parse_args(argv)
    require(a.src != a.to, 'source and target are the same role')
    os.environ['SHREC_TARGET'] = a.to
    modules = [m.strip() for m in a.module.split(',') if m.strip()] if a.module else list(project.modules())
    exclude = set()
    if a.exclude_file:
        d = project.read_json(a.exclude_file, {})
        exclude = {n.strip() for n in (d if isinstance(d, list) else d.keys())}
    from core import push as pushmod
    from core.api import fetch_forms
    from tools.snapshot import fetch_rows
    sapi, sitems, _ = fetch_rows(a.src)
    _, titems = fetch_forms(a.to)
    tidx = {((modname(i) or '').strip(), (i.get('name') or '').strip()) for i in titems}
    cand, skipped, missing = plan_names(sitems, tidx, modules, exclude)
    by_name = {((modname(i) or '').strip(), (i.get('name') or '').strip()): i for i in sitems}
    if a.push:   # whole-run snapshot of every form that could be written, + manifest, BEFORE the first write
        print('snapshot dir:', pushmod.begin_run(cand, rule='sync_forms', role=a.to))
    same, differ, failed = 0, [], []
    for mod, n in cand:
        try:
            i = by_name[(mod, n)]
            mk = i.get('markup') or sapi.get(FORMS + '/Get', id=i['id'])['result']['markup']
            mk = json.loads(mk) if isinstance(mk, str) else mk

            def transform(markup, _mk=mk, _src=a.src):
                if markup == _mk:
                    return []
                markup.clear()
                markup.update(_mk)
                return [f'{_src} copy replaces the target markup']
            notes = pushmod.push(mod, n, transform, dry_run=not a.push, role=a.to, rule='sync_forms')
            if notes:
                differ.append(n)
            else:
                same += 1
        except Exception as e:                      # one failing form must not abort the loop
            failed.append((f'{mod}/{n}', f'{type(e).__name__}: {str(e)[:200]}'))
            print(f'[{n}] FAILED: {failed[-1][1]}')
    print(('DRY RUN - ' if not a.push else '') + f'identical {same} | differ {len(differ)} | excluded {skipped} | '
          f'on the source but not on the target: {missing} | failed {len(failed)}')
    for f, why in failed:
        print(f'  failed {f}: {why}')
    ledger.event('summary', env=a.to, script='shrec sync-forms', dry=not a.push, rules=['sync_forms'], forms_changed=len(differ),
                 of=len(cand), failed=[f for f, _ in failed])
    return 1 if failed else 0
