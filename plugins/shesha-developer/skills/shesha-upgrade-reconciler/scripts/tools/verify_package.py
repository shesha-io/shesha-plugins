"""Verify an exported configuration package before it is committed. Read-only.

  shrec.py verify-package <package.shaconfig> [--compare-role local|deployed|reference] [--module M] [--target-version 0.46.0]
                          [--expect Form=substring ...] [--forbid substring ...] [--forms-file <list>]

Reports: form count per module; every form that still mentions a pre-upgrade schema name for the target version (below: the built-in
0.43-era names for a 0.46 target; keyed on the target MINOR version, which is --target-version, else the version of --compare-role,
else the local role's version; with no known version the check is skipped and says so); --expect / --forbid check a substring inside a
named form (e.g. --expect my-form=someText --forbid forbiddenText for a hot fix that must not regress; --module narrows the form
lookup); --forms-file asserts that every listed form (one `Module/Form` or `Form` per line, or a JSON list) is IN the package;
--compare-role reads each packaged form back from that role and asserts the package holds exactly what the server holds (JSON-equal),
so a stale export cannot ship. Exit code 1 on any failed check.
"""
import argparse
import json
import os
import zipfile

from core import versions

# per target minor version: (names that mark a pre-upgrade schema or type, names that are allowed although they match)
LEGACY_BY_MINOR = {
    '0.46': (('Frwk_', 'Core_ShaRole', 'Shesha.Domain.ConfigurationItems.Module', 'Shesha.Framework.ConfigurableComponent'),
             ('Frwk_Discriminator',)),
}


def legacy_names(version):
    """(legacy names, allowed names) for the target version's minor, or None when nothing is known for it."""
    return LEGACY_BY_MINOR.get(versions.minor(version) or '')


def read_package(path):
    z = zipfile.ZipFile(path)
    forms = {}
    for nm in z.namelist():
        if not nm.replace('\\', '/').lower().endswith('.json'):
            continue
        try:
            d = json.loads(z.read(nm).decode('utf-8-sig'))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        n = d.get('Name') or d.get('name')
        mk = d.get('Markup') or d.get('markup')
        if n and mk:
            forms[((d.get('ModuleName') or d.get('moduleName') or '').strip(), n.strip())] = mk
    return forms


def target_version(args):
    if args.target_version:
        return args.target_version
    from core.metadata import role_version
    return (role_version(args.compare_role) if args.compare_role else None) or role_version('local')


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec verify-package', description=__doc__.split('\n')[0])
    ap.add_argument('package')
    ap.add_argument('--compare-role', choices=['local', 'deployed', 'reference'])
    ap.add_argument('--module')
    ap.add_argument('--target-version')
    ap.add_argument('--expect', action='append', default=[], metavar='Form=substring')
    ap.add_argument('--forbid', action='append', default=[], metavar='substring')
    ap.add_argument('--forms-file')
    a = ap.parse_args(argv)
    forms = read_package(a.package)
    bad = 0

    def text(k):
        return forms[k] if isinstance(forms[k], str) else json.dumps(forms[k], ensure_ascii=False)
    per = {}
    for m, _ in forms:
        per[m] = per.get(m, 0) + 1
    print('forms in package:', len(forms), '| by module:', per)
    tv = target_version(a)
    names = legacy_names(tv)
    if names:
        legacy, allowed = names

        def stripped(k):
            t = text(k)
            for ok in allowed:
                t = t.replace(ok, '')
            return t
        hits = [k[1] for k in forms if any(t in stripped(k) for t in legacy)]
        print(f'forms mentioning pre-upgrade schema names for {versions.minor(tv)} (check each is intended):', hits[:20])
    else:
        print(f'legacy-name check skipped: no names known for target version {tv or "(unknown: pass --target-version)"}')

    def find(form):
        return [k for k in forms if k[1] == form and (not a.module or k[0] == a.module)]
    for spec in a.expect:
        f, _, sub = spec.partition('=')
        ks = find(f)
        ok = bool(ks) and all(sub in text(k) for k in ks)
        bad += not ok
        print(('OK   ' if ok else 'FAIL ') + f'expect {f} contains {sub[:60]!r}')
    for sub in a.forbid:
        hits = [k[1] for k in forms if sub in text(k)]
        bad += bool(hits)
        print(('OK   ' if not hits else 'FAIL ') + f'forbid {sub[:60]!r}' + (f' found in {hits[:6]}' if hits else ''))
    if a.forms_file:
        with open(a.forms_file, encoding='utf-8-sig') as fh:
            raw = fh.read()
        try:
            d = json.loads(raw)
            want = d if isinstance(d, list) else list(d)
        except ValueError:
            want = [x.strip() for x in raw.splitlines() if x.strip() and not x.startswith('#')]
        absent = [n for n in want if not any(k[1] == n.split('/', 1)[-1].strip() and (('/' not in n) or k[0] == n.split('/', 1)[0].strip()) for k in forms)]
        bad += bool(absent)
        print(('OK   ' if not absent else 'FAIL ') + f'every listed form is in the package ({len(want)} listed)' + (f'; missing {absent}' if absent else ''))
    if a.compare_role:
        from core.api import FORMS, Api, modname
        api = Api(a.compare_role)
        idx = {((modname(i) or '').strip(), (i.get('name') or '').strip()): i['id'] for i in api.get_all(FORMS + '/GetAll')}
        diff = []
        for k in forms:
            if k not in idx:
                diff.append((k[1], 'not on the role'))
                continue
            live = api.get(FORMS + '/Get', id=idx[k])['result']['markup']
            pk = forms[k]
            if (json.loads(live) if isinstance(live, str) else live) != (json.loads(pk) if isinstance(pk, str) else pk):
                diff.append((k[1], 'differs from the server'))
        bad += bool(diff)
        print(('OK   ' if not diff else 'FAIL ') + f'package == {a.compare_role} for all {len(forms)} forms' + (f'; {diff[:10]}' if diff else ''))
    return 1 if bad else 0
