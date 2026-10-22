"""Rule `payload` (H39): `delete data.<prop>` in a 0.46 action script has no effect.

Symptom on 0.46: a save that posts `{...data}` after deleting helper fields is rejected by the dynamic CRUD ("Property
'x' not found for '<Entity>'"), so the form saves nothing.
Cause: `data` is a proxy that ignores deletes, so the helper fields are sent anyway. 0.43 honoured the deletes.
Writes: `data` is copied into a local object before the first `delete data.`, deletes go to the copy, and the copy is
spread where the script spread `data` afterwards. Reads of `data.<x>` are unchanged. Only scripts that both delete from
`data` and spread it afterwards are touched (code-mode settings and action `expression` strings).
Marker: /*reconciler:046-payload-copy*/ and the local name __payload046.  Options: none.
"""
import re

from packs.v0_46.common import flush

MARK = '/*reconciler:046-payload-copy*/'
VAR = '__payload046'


def rewrite(code):
    if MARK in code:
        return None
    m = re.search(r'\bdelete\s+data\.', code)
    if not m:
        return None
    head, tail = code[:m.start()], code[m.start():]
    if not re.search(r'\.\.\.\s*data\b(?!\s*\.)', tail):
        return None
    line_start = head.rfind('\n') + 1
    indent = re.match(r'[ \t]*', head[line_start:]).group(0)
    tail = re.sub(r'\bdelete\s+data\.', f'delete {VAR}.', tail)
    tail = re.sub(r'\.\.\.(\s*)data\b(?!\s*\.)', rf'...\1{VAR}', tail)
    return head[:line_start] + f'{indent}{MARK}\n{indent}const {VAR} = {{ ...data }};\n' + head[line_start:] + tail


def apply_all(markup, notes):
    n = 0

    def walk(o, ctxname=None):
        nonlocal n
        if isinstance(o, dict):
            ctxname = o.get('label') or o.get('componentName') or ctxname
            for k, v in list(o.items()):
                if isinstance(v, dict) and v.get('_mode') == 'code' and isinstance(v.get('_code'), str):
                    r = rewrite(v['_code'])
                    if r:
                        v['_code'] = r
                        n += 1
                        notes.append(f'{ctxname}.{k}: payload copied before deleting helper fields (H39)')
                elif k == 'expression' and isinstance(v, str):
                    r = rewrite(v)
                    if r:
                        o[k] = r
                        n += 1
                        notes.append(f'{ctxname} script: payload copied before deleting helper fields (H39)')
            for v in o.values():
                walk(v, ctxname)
        elif isinstance(o, list):
            for v in o:
                walk(v, ctxname)
    walk(markup)
    return n


def apply(ctx, markup):
    notes = []
    n = apply_all(markup, notes)
    flush(ctx, notes)
    return n
