"""Shesha version handling: parse, compare, range checks, and detection from a repository's package pins.

A running 0.46 backend exposes no framework-version endpoint (the session login-info DTO carries no application block),
so the version of a LOCAL stack is read from the repository: the frontend `@shesha-io/reactjs` pin in package.json
(framework releases are tagged with it), falling back to the backend `Shesha.*` NuGet pins in *.props / *.csproj
(their own patch numbering; MSBuild properties resolved). Deployed and reference versions are declared in
project.json ("environments": {"<role>": {"version": "0.46.1"}}) as the framework (frontend package) version.
"""
import glob
import json
import os
import re

_V = re.compile(r'(\d+)\.(\d+)(?:\.(\d+))?(?:[.-]([0-9A-Za-z.-]+))?')


def parse(v):
    """'0.46.1' -> (0, 46, 1, ''); a pre-release suffix sorts before the release. None when unparseable."""
    m = _V.search(str(v or ''))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), m.group(4) or ''


def key(v):
    p = parse(v)
    if p is None:
        return None
    return p[0], p[1], p[2], 0 if p[3] else 1, p[3]


def cmp(a, b):
    ka, kb = key(a), key(b)
    if ka is None or kb is None:
        raise ValueError(f'cannot compare versions {a!r} and {b!r}')
    return (ka > kb) - (ka < kb)


def satisfies(v, spec):
    """spec: space-separated clauses like '>=0.46.0 <0.47.0' (operators >= > <= < ==)."""
    if not spec:
        return True
    for clause in spec.split():
        m = re.match(r'(>=|<=|==|>|<)(.+)', clause)
        if not m:
            raise ValueError(f'bad version clause {clause!r}')
        op, rhs = m.groups()
        c = cmp(v, rhs)
        if not {'>=': c >= 0, '>': c > 0, '<=': c <= 0, '<': c < 0, '==': c == 0}[op]:
            return False
    return True


def minor(v):
    p = parse(v)
    return f'{p[0]}.{p[1]}' if p else None


def _skip(path):
    return any(os.sep + d + os.sep in path for d in ('node_modules', 'bin', 'obj', '.git'))


def detect_repo(root):
    """{'framework', 'frontend', 'backend', 'sources'} from the repository's package pins.

    `framework` is the version rule packs compare against: the `@shesha-io/reactjs` version, because framework releases
    are tagged with it and the render fixes ship there. Backend `Shesha.*` NuGet packages follow their own patch
    numbering (e.g. backend 0.46.4 alongside frontend 0.46.0), so the backend version is reported but used only when
    no frontend pin exists. MSBuild properties such as `$(SheshaVersion)` are resolved from *.props / *.csproj."""
    out = {'framework': None, 'backend': None, 'frontend': None, 'sources': []}
    pat = re.compile(r'<Package(?:Reference|Version)\s+Include="Shesha\.(?:Core|Framework|Application|Web\.Core)"\s+Version="([^"]+)"', re.I)
    files = [f for f in glob.glob(os.path.join(root, '**', '*.props'), recursive=True) +
             glob.glob(os.path.join(root, '**', '*.csproj'), recursive=True) if not _skip(f)]
    texts = {}
    for f in files:
        try:
            texts[f] = open(f, encoding='utf-8-sig', errors='replace').read()
        except OSError:
            continue
    props = {}
    for f, text in texts.items():
        for name, value in re.findall(r'<(\w+)>\s*([^<]+?)\s*</\1>', text):
            props.setdefault(name, (value, f))
    for f, text in texts.items():
        m = pat.search(text)
        if not m:
            continue
        raw, src = m.group(1), f
        ref = re.fullmatch(r'\$\((\w+)\)', raw.strip())
        if ref and ref.group(1) in props:
            raw, src = props[ref.group(1)]
        raw = raw.strip().strip('[]()').split(',')[0].strip()
        if parse(raw):
            out['backend'] = raw
            out['sources'].append(os.path.relpath(src, root).replace(os.sep, '/'))
            break
    for f in glob.glob(os.path.join(root, '**', 'package.json'), recursive=True):
        if os.sep + 'node_modules' + os.sep in f:
            continue
        try:
            deps = json.load(open(f, encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        for block in ('dependencies', 'devDependencies'):
            v = (deps.get(block) or {}).get('@shesha-io/reactjs')
            if v and parse(v):
                out['frontend'] = re.sub(r'^[~^=v]+', '', v)
                out['sources'].append(os.path.relpath(f, root).replace(os.sep, '/'))
                break
        if out['frontend']:
            break
    out['framework'] = out['frontend'] or out['backend']
    return out
