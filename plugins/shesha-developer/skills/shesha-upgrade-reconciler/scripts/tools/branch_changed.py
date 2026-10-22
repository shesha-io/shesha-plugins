"""Which forms did the pre-upgrade line change since the upgrade branch was cut? (`shrec.py branch-changed`; read-only: git + zip, no API, no writes)

The pre-upgrade line ships its form changes as raw configuration packages (*.shaconfig, zip files of JSON items) in the backend's
package folder. The packages that are on the SOURCE ref but NOT on the TARGET (upgrade) ref are the new work. For every form in those
packages this finds its previous raw export (the newest package that was already on the target ref and holds the form) and, with
--extract, writes both raw markups so `merge3` can three-way merge them onto the upgraded forms:

    <work>/merge/base/<module>/<form>.json     previous raw export  (what the earlier reconcile already saw)
    <work>/merge/theirs/<module>/<form>.json   newest raw export in the new packages
    <work>/merge/branch_changed.json           {form: {module, packages, previous, new_form, changed}}

`changed` is False when the new package re-exports the form unchanged (nothing to do). `new_form` is True when no earlier export exists.

  shrec.py branch-changed --source-ref <ref> --target-ref <ref> [--extract] [--repo <path>] [--package-dir <dir>] [--out <file>]
  shrec.py branch-changed --package <file.shaconfig> --target-ref <ref> [--extract]
        (no source branch: ONE package is "theirs"; the base of each form is its newest export among the packages on the target ref)

The package folder is the project option `packageDir` (repo-relative; --package-dir overrides it); there is no default. The repository is
the project root unless --repo is given. Refs may be omitted when the options `sourceRef` / `targetRef` are set. Compares refs, not the
working tree, so it works before or after a merge as long as both refs exist. A bare branch name means its origin/ remote-tracking ref.

`sprint-changed` is the old name of this command and still works (it runs this module); the output file used to be called
sprint_changed.json, and merge3 still reads an existing one when branch_changed.json is absent (sync-forms --exclude-file takes either path).
"""
import io
import json
import os
import re
import subprocess
import zipfile

from core import project


def opt(a, n, d=None):
    return a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d


def safe(s):
    return re.sub(r'[^\w.-]', '_', s.strip())


def forms_of(data):
    """{(module, name): markup (parsed)} of the form items in the bytes of one .shaconfig package."""
    z = zipfile.ZipFile(io.BytesIO(data))
    out = {}
    for nm in z.namelist():
        if not nm.lower().endswith('.json'):
            continue
        try:
            d = json.loads(z.read(nm).decode('utf-8-sig'))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        n = d.get('Name') or d.get('name')
        m = d.get('Markup') or d.get('markup')
        mod = d.get('ModuleName') or d.get('moduleName') or ''
        if n and m:
            try:
                out[(mod, n.strip())] = json.loads(m) if isinstance(m, str) else m
            except Exception:
                pass
    return out


class Repo:
    def __init__(self, repo, pdir):
        self.repo, self.pdir, self._c = repo, pdir.strip('/').replace('\\', '/'), {}

    def git(self, *a):
        r = subprocess.run(['git', '-C', self.repo, *a], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError('git ' + ' '.join(a) + ': ' + r.stderr.decode('utf-8', 'replace')[:200])
        return r.stdout

    def packages(self, ref):
        out = self.git('ls-tree', '--name-only', ref, self.pdir + '/').decode()
        return sorted(l.split('/')[-1] for l in out.splitlines() if l.endswith('.shaconfig'))

    def forms(self, ref, pk):
        k = (ref, pk)
        if k not in self._c:
            self._c[k] = forms_of(self.git('show', f'{ref}:{self.pdir}/{pk}'))
        return self._c[k]


def as_ref(r):
    """a bare branch name means its remote-tracking ref"""
    return r if '/' in r and r.split('/')[0] in ('origin', 'refs', 'upstream') else 'origin/' + r


def main(argv):
    a = argv
    pkg_file = opt(a, '--package')
    source = opt(a, '--source-ref') or project.option('sourceRef')
    target = opt(a, '--target-ref') or project.option('targetRef')
    pdir = opt(a, '--package-dir') or project.option('packageDir')
    if (not source and not pkg_file) or not target:
        print(__doc__)
        return 2
    if not pdir:
        raise project.ConfigError('no package folder: set the option "packageDir" (repo-relative folder holding the *.shaconfig packages) in project.json or pass --package-dir')
    target = as_ref(target)
    repo = Repo(opt(a, '--repo', project.root()), pdir)
    on_target = repo.packages(target)
    if pkg_file:
        pk_name = os.path.basename(pkg_file)
        source = None
        new, old, on_source = [pk_name], list(on_target), []
        with open(pkg_file, 'rb') as fh:
            single = forms_of(fh.read())
        get_new = lambda pk: single
        print(f'single package {pk_name} vs target {target}: {len(on_target)} packages')
    else:
        source = as_ref(source)
        on_source = repo.packages(source)
        new = [p for p in on_source if p not in on_target]
        old = [p for p in on_source if p in on_target]
        get_new = lambda pk: repo.forms(source, pk)
        print(f'source {source}: {len(on_source)} packages | target {target}: {len(on_target)} | NEW on the source: {len(new)}')
        for p in new:
            print('   new package', p)
    out_path = opt(a, '--out') or os.path.join(project.work_path('merge', mkdir=False), 'branch_changed.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if not new:
        print('no new packages: no changes to bring over')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return 0
    res = {}
    for pk in new:
        for (mod, n), mk in get_new(pk).items():
            r = res.setdefault(n, {'module': mod, 'packages': [], 'previous': None, '_theirs': None})
            r['packages'].append(pk)
            r['_theirs'] = mk                  # packages are name-sorted = time-sorted: the last one wins
            if r['module'] != mod:
                print(f'   WARNING {n} appears in two modules ({r["module"]}, {mod}); handle the second by hand')
    for n, r in res.items():
        r['_base'] = None
        for pk in reversed(old):
            f = repo.forms(target if pkg_file else source, pk).get((r['module'], n))
            if f is not None:
                r['previous'] = pk
                r['_base'] = f
                break
        r['new_form'] = r['_base'] is None
        r['changed'] = r['_base'] is None or r['_base'] != r['_theirs']
    merge_root = project.work_path('merge', mkdir=False)
    if '--extract' in a:
        for n, r in res.items():
            for side, key in (('theirs', '_theirs'), ('base', '_base')):
                if r[key] is None:
                    continue
                d = os.path.join(merge_root, side, safe(r['module'] or '_nomodule'))
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, safe(n) + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(r[key], f, ensure_ascii=False, indent=1)
    slim = {n: {k: v for k, v in r.items() if not k.startswith('_')} for n, r in res.items()}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(slim, f, indent=1)
    real = [n for n, r in slim.items() if r['changed']]
    print(f'{len(slim)} forms in the new packages | really changed: {len(real)} | new forms: {sum(1 for r in slim.values() if r["new_form"])} | '
          f're-exported unchanged: {len(slim) - len(real)}')
    for n, r in sorted(slim.items()):
        print(f"  {'CHANGED' if r['changed'] else 'same   '} {r['module'] or '?':26} {n:52} {'NEW FORM' if r['new_form'] else 'previous ' + (r['previous'] or '')[7:18]}")
    print('written:', out_path, ('(raw exports under ' + merge_root + ')') if '--extract' in a else '(add --extract to write the raw exports)')
    print('newest package on either ref (the package you export later must be named LATER than this):',
          max(on_source + on_target) if (on_source or on_target) else None)
    return 0
