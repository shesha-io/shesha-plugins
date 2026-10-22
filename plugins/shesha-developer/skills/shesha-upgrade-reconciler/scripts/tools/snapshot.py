"""Read-only form snapshots: <work>/snapshots/<role>/<module>/<form>.json plus <work>/snapshots/<role>-index.json.

  shrec.py snapshot [reference] [local] [deployed] [--modules A,B]      default roles: reference and local; default modules: all

Every row is stored as the API returned it, with `markup` parsed to a dict. The merge flow uses the local / deployed snapshot as
the "ours" side and rules read the reference snapshot (core.packs Ctx.reference_components).

Versioned configuration items: a role whose version is below 0.45 keeps one row per form version, so only the Live rows
(versionStatus == 3) are kept for it, and the server-side filter asks for them too. From 0.45 on there is one row per form and
nothing is filtered. This is keyed on the role's version (project.json environments.<role>.version, or the version detected in
the repository for the local role), never on a role name. When the version is unknown and a form appears more than once with
different versionStatus values, the Live rows are kept and a warning is printed.
"""
import argparse
import collections
import json
import os
import re

from core import project, versions
from core.api import Api, FORMS, modname
from core.metadata import role_version

LIVE = 3


def versioned(version):
    """True when the version predates in-place configuration items (below 0.45.0). Unknown -> None."""
    if not version or versions.parse(version) is None:
        return None
    return versions.cmp(version, '0.45.0') < 0


def keep_live_rows(items, version):
    """(rows kept, warning or None). Pure function."""
    v = versioned(version)
    if v:
        return [i for i in items if i.get('versionStatus') == LIVE], None
    if v is None:
        counts = collections.Counter((modname(i).strip(), (i.get('name') or '').strip()) for i in items)
        if any(n > 1 for n in counts.values()) and any('versionStatus' in i for i in items):
            return [i for i in items if i.get('versionStatus') == LIVE], \
                'version unknown and some forms have several rows: kept the Live rows only'
    return list(items), None


def safe(s):
    return re.sub(r'[^\w.-]', '_', s)


def fetch_rows(role, modules=None):
    """(api, rows, total_on_server) for one role, with the version-keyed Live filter applied."""
    a = Api(role)
    version = role_version(role)
    params = {}
    if versioned(version):
        params['Filter'] = json.dumps({'==': [{'var': 'versionStatus'}, LIVE]})
    items = a.get_all(FORMS + '/GetAll', **params)
    total = len(items)
    items, warn = keep_live_rows(items, version)
    if warn:
        print(f'{role}: {warn}')
    if modules:
        wanted = set(modules)
        items = [i for i in items if (modname(i).strip() or '_nomodule') in wanted]
    return a, items, total


def write_snapshot(role, a, items, out_root=None):
    out_root = out_root or project.work_path('snapshots', mkdir=False)
    index = []
    for it in items:
        mn = modname(it).strip() or '_nomodule'
        d = os.path.join(out_root, role, safe(mn))
        os.makedirs(d, exist_ok=True)
        fn = safe((it.get('name') or '').strip()) + '.json'
        mk = it.get('markup')
        if not mk and it.get('id'):
            try:
                mk = a.get(FORMS + '/Get', id=it['id'])['result'].get('markup')
            except Exception:
                mk = None
        try:
            mk = json.loads(mk) if isinstance(mk, str) and mk else mk
        except ValueError:
            pass
        row = {k: v for k, v in it.items() if k != 'markup'} | {'markup': mk}
        with open(os.path.join(d, fn), 'w', encoding='utf-8', newline='\n') as f:
            json.dump(row, f, indent=1, ensure_ascii=False)
        index.append({'module': mn, 'name': it.get('name'), 'id': it.get('id'), 'version': it.get('versionNo'),
                      'file': f'{role}/{os.path.basename(d)}/{fn}', 'hasMarkup': bool(mk)})
    with open(os.path.join(out_root, f'{role}-index.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(index, f, indent=1)
    return index


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec snapshot', description=__doc__.split('\n')[0])
    ap.add_argument('roles', nargs='*', metavar='role', help='reference | local | deployed')
    ap.add_argument('--modules', help='comma list of module names (default all)')
    a = ap.parse_args(argv)
    bad = [r for r in a.roles if r not in project.ROLES]
    if bad:
        ap.error(f'unknown role(s) {bad}: use {", ".join(project.ROLES)}')
    roles = a.roles or ['reference', 'local']
    modules = [m.strip() for m in a.modules.split(',') if m.strip()] if a.modules else None
    for role in roles:
        api, items, total = fetch_rows(role, modules)
        index = write_snapshot(role, api, items)
        print(role, 'server total', total, 'kept', len(index), collections.Counter(i['module'] for i in index).most_common(8))
    return 0
