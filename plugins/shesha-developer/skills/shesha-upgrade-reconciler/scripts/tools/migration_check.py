"""Migrations authored against the previous framework schema can break the upgraded backend at boot. Run this at EVERY merge of the
pre-upgrade line, before the PR.

Mechanism (0.43 -> 0.46): the pre-upgrade line keeps authoring migrations against dbo.Frwk_ConfigurationItems / Frwk_Modules /
Frwk_StoredFiles / Frwk_ReferenceListItems / Frwk_PermissionDefinitions / Frwk_PermissionedObjects, Core_ShaRole* and the function
dbo.Frwk_GetRefListItem. 0.46 has frwk.* snake_case tables and revisioned configuration items (item row + revision row + type table, ids
shared; permissioned_objects needs md5='' and parent=''; reference_list_items needs color/description/icon/short_alias=''). A database that
has already applied a migration hides the problem: THE TARGET DATABASE'S dbo.VersionInfo IS THE TRUTH, not "it ran locally".

  shrec.py migration-check [--tree <dir>] [--target-version 0.46.0] (--applied-file versions.txt | reads dbo.VersionInfo via sqlq: SHREC_SQL)

Where to look: --tree (repo-relative or absolute), else the project option `migrationPaths` (a list of repo-relative folders), else the
whole repository: every *.cs file with `[Migration(<version>)]` (bin, obj, node_modules, .git and .vs are skipped).
Suspect patterns are keyed on the TARGET MINOR version (--target-version, else the local role's version): the built-in set is the 0.43
-> 0.46 one (Frwk_*, Core_ShaRole*, dbo.Frwk_GetRefListItem); for another target minor nothing is flagged and the run says so.
Lists every migration in the tree that is not in VersionInfo, and for each flags the suspect references. Fix a flagged migration in place
(it is unapplied on the target) by converting it to the new schema, and verify the converted SQL against the live schema, not from memory.
Read-only: a git-free file scan plus one SELECT. Exit code 1 when an unapplied migration is flagged.
"""
import argparse
import os
import re

from core import project, versions

MIG = re.compile(r'\[Migration\(\s*(\d+)\s*\)\]')
SKIP = {'bin', 'obj', 'node_modules', '.git', '.vs'}
SUSPECT_BY_MINOR = {
    '0.46': re.compile(r'(Frwk_[A-Za-z]+|Core_ShaRole\w*|dbo\.Frwk_\w+|\bFrwk_GetRefListItem\b)'),
}


def suspect_pattern(version):
    return SUSPECT_BY_MINOR.get(versions.minor(version) or '')


def scan(roots):
    out = {}
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP]
            for f in files:
                if not f.endswith('.cs'):
                    continue
                p = os.path.join(d, f)
                try:
                    with open(p, encoding='utf-8-sig', errors='replace') as fh:
                        t = fh.read()
                except OSError:
                    continue
                for v in MIG.findall(t):
                    out[int(v)] = (p, t)
    return out


def tree_roots(repo, tree=None):
    if tree:
        return [tree if os.path.isabs(tree) else os.path.join(repo, tree)]
    paths = project.option('migrationPaths') or []
    roots = [p if os.path.isabs(p) else os.path.join(repo, p) for p in paths]
    return roots or [repo]


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec migration-check', description=__doc__.split('\n')[0])
    ap.add_argument('--tree')
    ap.add_argument('--applied-file')
    ap.add_argument('--target-version')
    a = ap.parse_args(argv)
    repo = project.root()
    roots = tree_roots(repo, a.tree)
    tree = scan(roots)
    print(f'{len(tree)} migrations in {", ".join(os.path.relpath(r, repo) for r in roots)}')
    if a.applied_file:
        with open(a.applied_file, encoding='utf-8-sig') as fh:
            applied = {int(x) for x in re.findall(r'\d{10,}', fh.read())}
    else:
        from tools import sqlq
        _, rows = sqlq.run('select Version from dbo.VersionInfo')
        applied = {int(r[0]) for r in rows if r and r[0].isdigit()}
    print(f'{len(applied)} applied on the target database')
    tv = a.target_version
    if not tv:
        from core.metadata import role_version
        tv = role_version('local')
    pat = suspect_pattern(tv)
    if not pat:
        print(f'no suspect schema patterns are known for target version {tv or "(unknown: pass --target-version)"}: unapplied migrations are listed, none is flagged')
    unapplied = sorted(set(tree) - applied)
    print(f'{len(unapplied)} UNAPPLIED (will run for the first time on the target):')
    bad = 0
    for v in unapplied:
        p, t = tree[v]
        hits = sorted(set(pat.findall(t))) if pat else []
        flag = f'SUSPECT {versions.minor(tv)} SCHEMA REFERENCE -> convert: ' + ', '.join(hits[:6]) if hits else 'ok'
        bad += bool(hits)
        print(f'  {v}  {os.path.relpath(p, repo)}  {flag}')
    print(f'{bad} unapplied migration(s) reference the previous schema'
          + ('' if not bad else ': fix them before the PR (verify each against the live schema)'))
    return 1 if bad else 0
