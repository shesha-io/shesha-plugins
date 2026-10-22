"""Rule `scripts` (H10): safe optional chaining in render-time Shesha scripts.

Symptom on 0.46: thousands of executeScriptSync errors, and components that should be hidden show, because 0.46 treats a
throwing visibility expression as VISIBLE and logs an error on every render (a path such as `data.order.status` throws
before the record has loaded).
Writes: optional chaining on every hop of render-time settings only:
  data.a.b / formData.a.b / form.data.a.b   ->  data?.a?.b ...   (root + >=2 member accesses)
  x?.a.b  (any root already marked nullable) ->  x?.a?.b
Never rewrites an assignment target (x.a.b = ..., x.a.b += ..., ++x.a.b): optional chaining is invalid there.
Every rewritten script is syntax-gated. Marker: none (idempotent by construction: a rewritten chain no longer matches).
Options: none.
"""
import re

from core import gate
from core.tree import walk
from packs.v0_46.common import flush

ROOTS = ('form._data', 'form.data', 'formData', 'data')
ROOTED = re.compile(r'(?<![\w$.])(?:form\.(?:_data|data)|formData|data)(?:\??\.[A-Za-z_$][\w$]*){2,}')
NULLABLE = re.compile(r'(?<![\w$.])[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\?\.[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)+')
ASSIGN_AFTER = re.compile(r'\s*(?:[-+*/%&|^]|\*\*|<<|>>>?|&&|\|\||\?\?)?=(?!=)')
INCDEC_BEFORE = re.compile(r'(?:\+\+|--)\s*$')
RENDER_KEYS = {'style', 'queryParams', 'customVisibility', 'customEnabled'}
CHILD_KEYS = {'components', 'columns', 'tabs', 'steps', 'items', 'content'}


def _fix_chain(chain):
    root = next((r for r in ROOTS if chain.startswith(r) and not chain[len(r):len(r) + 1].isalnum()), None)
    if root:
        head, rest = root, chain[len(root):]
    else:
        # nullable root: keep everything up to and including the first '?.' as written
        i = chain.index('?.') + 2
        j = re.match(r'[A-Za-z_$][\w$]*', chain[i:]).end() + i
        head, rest = chain[:j], chain[j:]
    return head + re.sub(r'\??\.', '?.', rest)


def safe_chain(code):
    """(new code, number of chains rewritten)"""
    out, n = code, 0
    for rx in (ROOTED, NULLABLE):
        res, pos = [], 0
        for m in rx.finditer(out):
            s, e = m.span()
            if ASSIGN_AFTER.match(out, e) or INCDEC_BEFORE.search(out[:s]) or out[e:e + 1] == '(' and False:
                continue
            fixed = _fix_chain(m.group(0))
            if fixed != m.group(0):
                res.append(out[pos:s])
                res.append(fixed)
                pos = e
                n += 1
        res.append(out[pos:])
        out = ''.join(res)
    return out, n


def render_scripts(component):
    """yield (holder, key) for every render-time script string on a component, at ANY depth of its own settings
    (0.46's style migration copies JS settings into desktop/tablet/mobile.{background,font}.color etc.).
    Child component containers are skipped: the caller's walk visits those components itself."""
    def visit(holder, top):
        for k, v in list(holder.items()):
            if top and k in CHILD_KEYS:
                continue
            if isinstance(v, dict):
                if isinstance(v.get('_code'), str):
                    yield v, '_code'
                else:
                    yield from visit(v, False)
            elif isinstance(v, str) and k in RENDER_KEYS:
                yield holder, k
    yield from visit(component, True)


def apply(ctx, markup):
    changed, notes = [], []
    for c, _, _ in walk(markup):
        for holder, key in render_scripts(c):
            old = holder[key]
            new, n = safe_chain(old)
            if n:
                changed.append((c.get('componentName'), key, old, new))
                holder[key] = new
                notes.append(f'{c.get("componentName")}.{key}: {n} safe chain(s)')
    if changed:
        gate.require_clean([x[3] for x in changed], [x[2] for x in changed], what='safe-chain')
    flush(ctx, notes)
    return len(changed)
