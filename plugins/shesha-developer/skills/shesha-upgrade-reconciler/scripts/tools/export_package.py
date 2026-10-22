"""Export form configurations as a configuration package through the Shesha API - exactly what the Configuration Studio Export dialog
calls (ConfigurationStudio/ExportPackage). NEVER hand-build a .shaconfig. The package is saved under the server-generated name and,
with --apply, copied into the backend's package folder and registered in the Application .csproj (None Remove + EmbeddedResource).

  shrec.py export-package --target local|deployed (--forms Module/Form,... | --forms-file F | --only a,b [--module M] | --all-module M)
                          [--extra Module/Form,...] [--target-branch <ref>] [--package-dir <dir>] [--csproj <file>] [--apply] --reviewer-approved

Why a SUBSET: packages import on every backend start by ascending file name, skipping by md5, and a LATER-named package overwrites the
forms of an earlier one. A subset package that holds only the forms you changed is the smallest blast radius; an all-forms package
silently reverts every form it carries that someone else changed after your last read. Every PR that changes forms ships a freshly
exported package with ALL the forms it changed, named later than every package already on the target branch, exported AFTER the
reconcile so it overwrites earlier packages last.

Name check: the server-generated name must sort AFTER the newest package on the TARGET BRANCH (`git ls-tree` of --target-branch, or the
option `targetBranch`) and after the newest in the working tree. Without a target branch the export is refused (--skip-branch-check
only after the user agreed: the working tree alone can miss packages that arrived on the branch).

Paths: --package-dir / --csproj, or the project options `packageDir` / `packageCsproj`; repo-relative (joined onto the project root) or
absolute. There is no default. The csproj entries use the package folder relative to the csproj.

Needs --reviewer-approved (alias --approved): exporting a package is the reviewer's gate. Pass it only after the user said to export,
in this session. The export itself does not change the server (ExportPackage is a read-only query, sent through core.api.Api.post_query).
Dry run (no --apply) writes only <work>/exports/<name>. Logs an `export` ledger event with the forms list.
"""
import argparse
import contextlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from core import project
from core.api import Api, FORMS, modname
from core.project import require
from tools._common import log_event

EXPORT_PATHS = ('/api/services/app/ConfigurationStudio/ExportPackage', '/api/services/Shesha/ConfigurationStudio/ExportPackage')


@contextlib.contextmanager
def capture_headers(timeout=900):
    """Record the response headers of the request Api.post_query sends (Api returns only the body, the file name is in a header)."""
    cap = {}
    orig = urllib.request.urlopen

    def spy(*a, **kw):
        kw['timeout'] = max(kw.get('timeout') or 0, timeout)
        r = orig(*a, **kw)
        cap['headers'] = r.headers
        return r
    urllib.request.urlopen = spy
    try:
        yield cap
    finally:
        urllib.request.urlopen = orig


def filename_from(headers):
    cd = (headers or {}).get('Content-Disposition') or ''
    m = re.search(r'filename=([^;]+)', cd)
    require(m, 'no filename in the export response')
    name = m.group(1).strip().strip('"').strip("'")
    # the name comes from a server response header and is joined onto local paths below: accept a plain file name only
    require(name and name not in ('.', '..') and '/' not in name and '\\' not in name and os.path.basename(name) == name
            and os.path.splitdrive(name)[0] == '', f'refusing the export: the server sent a file name that is not a plain name ({name!r})')
    return name


def newest_on_branch(repo, ref, pdir):
    """Newest *.shaconfig name in <pdir> on a git ref (None when none, or when the ref has no such folder)."""
    r = subprocess.run(['git', '-C', repo, 'ls-tree', '--name-only', ref, pdir.strip('/').replace('\\', '/') + '/'], capture_output=True)
    require(r.returncode == 0, f'git could not read {ref}: {r.stderr.decode("utf-8", "replace")[:160]}')
    names = sorted(l.split('/')[-1] for l in r.stdout.decode().splitlines() if l.endswith('.shaconfig'))
    return names[-1] if names else None


def csproj_prefix(pdir, csproj):
    rel = os.path.relpath(pdir, os.path.dirname(csproj)).replace('/', '\\')
    return rel if rel != '.' else ''


def register_in_csproj(csproj, pdir, name, newest):
    with open(csproj, encoding='utf-8-sig', newline='') as fh:
        s = fh.read()
    nl = '\r\n' if '\r\n' in s else '\n'
    if name in s:
        return False
    require(newest, 'no earlier package to mirror in the csproj: add the two entries by hand')
    pre = csproj_prefix(pdir, csproj)
    pre = pre + '\\' if pre else ''
    none_line = f'    <None Remove="{pre}{newest}" />'
    emb = re.search(r'^[ \t]*<EmbeddedResource Include="' + re.escape(pre + newest) + r'" />', s, re.M)
    require(none_line in s and emb, 'anchor lines of the newest package not found in the csproj')
    s = s.replace(none_line, none_line + nl + f'    <None Remove="{pre}{name}" />', 1)
    s = s.replace(emb.group(0), emb.group(0) + nl + emb.group(0).replace(newest, name), 1)
    with open(csproj, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(s)
    return True


def post_export(api, ids):
    body = {'filter': json.dumps({'in': [{'var': 'id'}, ids]}), 'exportDependencies': False}
    last = None
    with capture_headers() as cap:
        for path in EXPORT_PATHS:
            try:
                data = api.post_query(path, body, binary=True)
                return data, cap.get('headers')
            except RuntimeError as e:           # the read-only client does not list this route: try the next spelling
                last = e
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                last = e
    raise RuntimeError(f'ExportPackage was not reachable on any known route ({last})')


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec export-package', description=__doc__.split('\n')[0])
    ap.add_argument('--target', '--role', dest='role', default=os.environ.get('SHREC_TARGET', 'local'), choices=['local', 'deployed'])
    ap.add_argument('--forms', help='comma list of Module/Form')
    ap.add_argument('--forms-file', help='file with one Module/Form per line (the export list written by `shrec report`)')
    ap.add_argument('--only', help='comma list of form names (with --module)')
    ap.add_argument('--module')
    ap.add_argument('--all-module')
    ap.add_argument('--extra', help='comma list of Module/Form added to the selection')
    ap.add_argument('--target-branch', help='git ref holding the packages already shipped (default: option targetBranch)')
    ap.add_argument('--skip-branch-check', action='store_true')
    ap.add_argument('--package-dir')
    ap.add_argument('--csproj')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--reviewer-approved', '--approved', '--owner-approved', dest='approved', action='store_true')
    a = ap.parse_args(argv)
    if not a.approved:
        print(__doc__)
        return 1
    pdir_opt = a.package_dir or project.option('packageDir')
    csproj_opt = a.csproj or project.option('packageCsproj')
    require(pdir_opt, 'no package folder: set the option "packageDir" in project.json or pass --package-dir')
    require(csproj_opt or not a.apply, 'no csproj: set the option "packageCsproj" in project.json or pass --csproj (needed with --apply)')
    root = project.root()
    pdir = os.path.join(root, pdir_opt)
    csproj = os.path.join(root, csproj_opt) if csproj_opt else None
    branch = a.target_branch or project.option('targetBranch')
    require(branch or a.skip_branch_check, 'no target branch: pass --target-branch <ref> (or set the option targetBranch); the name check must see '
                                           'the packages already on the branch, not only the working tree')
    api = Api(a.role)
    items = api.get_all(FORMS + '/GetAll')
    by = {((modname(i) or '').strip(), (i.get('name') or '').strip()): i['id'] for i in items}
    wanted = []
    if a.forms:
        wanted += [tuple(x.strip().split('/', 1)) for x in a.forms.split(',') if '/' in x]
    if a.forms_file:
        with open(a.forms_file, encoding='utf-8') as fh:
            wanted += [tuple(x.strip().split('/', 1)) for x in fh.read().splitlines() if '/' in x and not x.startswith('#')]
    if a.only:
        mod = a.module or (project.modules()[0] if len(project.modules()) == 1 else None)
        require(mod, '--only needs --module (the project has several modules)')
        wanted += [(mod, n.strip()) for n in a.only.split(',') if n.strip()]
    if a.all_module:
        wanted += [k for k in by if k[0] == a.all_module]
    if a.extra:
        wanted += [tuple(x.split('/', 1)) for x in a.extra.split(',') if '/' in x]
    require(wanted, 'name the forms: --forms Module/Form,... (a subset, preferred), --forms-file, --only a,b --module M, or --all-module M')
    wanted = list(dict.fromkeys(wanted))
    missing = [k for k in wanted if k not in by]
    require(not missing, f'not on {a.role}: {missing}')
    ids = [by[k] for k in wanted]
    data, headers = post_export(api, ids)
    name = filename_from(headers)
    require(name.endswith('.shaconfig') and data[:2] == b'PK', (name, data[:2]))
    existing = sorted(f for f in os.listdir(pdir) if f.endswith('.shaconfig')) if os.path.isdir(pdir) else []
    candidates = [x for x in (existing[-1] if existing else None, newest_on_branch(root, branch, pdir_opt) if branch else None) if x]
    newest = max(candidates) if candidates else None
    print(f'{len(ids)} forms -> {name} ({len(data)} bytes) | newest package in the working tree: {existing[-1] if existing else None}'
          f' | on {branch or "(no branch check)"}: {newest_on_branch(root, branch, pdir_opt) if branch else "skipped"}')
    require(not newest or name > newest, f'package name {name} is not later than {newest}: a later import must overwrite an earlier one - fix the clock/branch, do not rename')
    scratch = os.path.join(project.work_path('exports', mkdir=False), name)
    os.makedirs(os.path.dirname(scratch), exist_ok=True)
    with open(scratch, 'wb') as f:
        f.write(data)
    print('scratch copy:', scratch)
    written = None
    if a.apply:
        os.makedirs(pdir, exist_ok=True)
        written = os.path.join(pdir, name)
        with open(written, 'wb') as f:
            f.write(data)
        register_in_csproj(csproj, pdir, name, existing[-1] if existing else None)
        print('written to', written, 'and registered in', os.path.basename(csproj), '- verify with verify-package, then commit these two paths explicitly')
    else:
        print('dry run: nothing copied into the repo (add --apply)')
    log_event('export', env=a.role, host=api.base, package=name, forms=[f'{m}/{n}' for m, n in wanted], file=written or scratch, applied=bool(a.apply))
    return 0
