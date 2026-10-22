"""Rule `urlwait` (H40): a URL-sourced table context fetches when it mounts, possibly before the record has loaded.

Symptom on 0.46: URL-sourced tables stay empty; one request goes out with an EMPTY id (400 "The value '' is invalid") and
there is no retry.
Cause: a datatableContext / dataContext with `sourceType: 'Url'` and an endpoint such as `.../Get?id={{data.id}}` mounts
before the record has loaded; 0.46 does not fetch again once `{{data.id}}` resolves. 0.43 showed the rows.
Writes: the context's `visible` becomes a code setting that is true only once every id-like value its endpoint needs
exists, so it mounts (and fetches) with real ids. Only static-visibility contexts whose mustache parameters are all
id-like (`data.id`, `data.xxxId`) are gated; filter parameters (which may legitimately be empty) are left alone.
Marker: /*reconciler:046-url-wait*/.  Options: none.
"""
import re

from core.tree import walk
from packs.v0_46.common import flush

MARK = '/*reconciler:046-url-wait*/'
IDLIKE = re.compile(r'^data\.(id|[A-Za-z0-9_]*Id)$')


def apply_component(c, notes):
    if c.get('type') not in ('datatableContext', 'dataContext') or c.get('sourceType') != 'Url':
        return 0
    ep = c.get('endpoint')
    ep = ep.get('url') if isinstance(ep, dict) else ep
    params = re.findall(r'\{\{\s*([^}]+?)\s*\}\}', str(ep or ''))
    if not params or not all(IDLIKE.match(p) for p in params):
        return 0
    v, h = c.get('visible'), c.get('hidden')
    if isinstance(v, dict) and MARK in (v.get('_code') or ''):
        return 0
    if (isinstance(v, dict) and (v.get('_code') or '').strip()) or (isinstance(h, dict) and (h.get('_code') or '').strip()):
        return 0
    if v is False or h is True:
        return 0
    cond = ' && '.join('!!' + p.replace('data.', 'data?.') for p in dict.fromkeys(params))
    c['visible'] = {'_mode': 'code', '_code': f'{MARK}\n// mount (and fetch) only once the record ids are loaded\nreturn {cond};', '_value': True}
    c.pop('hidden', None)
    notes.append(f'{c.get("componentName")}: fetches only once {", ".join(dict.fromkeys(params))} is loaded (H40)')
    return 1


def apply(ctx, markup):
    notes = []
    n = sum(apply_component(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
