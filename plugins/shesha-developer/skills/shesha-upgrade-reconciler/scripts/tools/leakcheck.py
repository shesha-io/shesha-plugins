"""Scan a tree of text files for terms that must not appear in it (client names, hostnames, record ids ...). The deny list is supplied by
the caller: it lives in a private project, never in this skill.

  shrec.py leakcheck --deny-file <path> [--root <dir>] [--guid]

--deny-file  one term per line; blank lines and lines starting with # are ignored; matching is case-insensitive substring.
--root       directory to scan (default: the current directory). .git and node_modules are skipped, and so are binary files.
--guid       also report every GUID literal (8-4-4-4-12 hex digits).
Prints one line per hit as  path:line:term  (term is `GUID` for a GUID literal) and exits 1 on any hit, 0 when clean, 2 on a usage error.
"""
import argparse
import os
import re

SKIP_DIRS = {'.git', 'node_modules', '__pycache__'}
GUID = re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')


def load_terms(path):
    with open(path, encoding='utf-8-sig') as f:
        return [t.strip() for t in f.read().splitlines() if t.strip() and not t.lstrip().startswith('#')]


def is_binary(path, probe=4096):
    try:
        with open(path, 'rb') as f:
            return b'\0' in f.read(probe)
    except OSError:
        return True


def files_under(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(files):
            yield os.path.join(d, f)


def scan(root, terms, guid=False, deny_file=None):
    """[(path, line number, term)] for every hit under root. The deny file itself is skipped."""
    lowered = [(t, t.lower()) for t in terms]
    skip = os.path.abspath(deny_file) if deny_file else None
    hits = []
    for p in files_under(root):
        if skip and os.path.abspath(p) == skip:
            continue
        if is_binary(p):
            continue
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                for n, line in enumerate(f, 1):
                    low = line.lower()
                    for t, tl in lowered:
                        if tl in low:
                            hits.append((p, n, t))
                    if guid and GUID.search(line):
                        hits.append((p, n, 'GUID'))
        except OSError:
            continue
    return hits


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec leakcheck', description=__doc__.split('\n')[0])
    ap.add_argument('--deny-file', required=True)
    ap.add_argument('--root', default='.')
    ap.add_argument('--guid', action='store_true')
    a = ap.parse_args(argv)
    if not os.path.isfile(a.deny_file) or not os.path.isdir(a.root):
        print('leakcheck: --deny-file must be a file and --root a directory')
        return 2
    terms = load_terms(a.deny_file)
    hits = scan(a.root, terms, a.guid, a.deny_file)
    for p, n, t in hits:
        print(f'{os.path.relpath(p, a.root)}:{n}:{t}')
    print(f'leakcheck: {len(hits)} hit(s) for {len(terms)} term(s)' + (' + GUIDs' if a.guid else '') + f' under {os.path.abspath(a.root)}')
    return 1 if hits else 0
