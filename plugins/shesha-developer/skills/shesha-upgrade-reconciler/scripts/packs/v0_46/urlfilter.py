"""Rule `urlfilter` (H43, targeted): a leftover required filter on a URL-sourced table keeps it from ever fetching.

Symptom on 0.46: a URL-sourced table shows "No Data" and never issues its request.
Cause: a URL context (`datatableContext` / `dataContext`, `sourceType: 'Url'`) that still carries a permanent filter
(a leftover from when it was entity-sourced) whose REQUIRED mustache value can never resolve on this form - for example
`{{data.order.id}}` on a form whose data IS the order - stays "not ready", so the request is never sent. 0.43 fetched the
URL without the filter.
Writes: that permanent filter is removed. Only filters whose every mustache expression starts with `data.<prop>`, where
<prop> is neither `id` nor a property of the form's model, are removed; anything else is reported (INFO) and left alone
(0.46 does send a resolvable filter to the URL endpoint). The model's properties come from Metadata/Get, fetched lazily
through ctx.api() and cached; offline tests pre-seed `session._cache['metadata:<modelType>']` (see metadata.py).
Marker: none (a removed filter is not re-found).  No retire: the dropped filter never resolved.
Options: none.  Run with `apply --rules urlfilter --only form,...`.
"""
import json
import re

from core.tree import camel, walk_dicts
from packs.v0_46 import metadata
from packs.v0_46.common import flush


def contexts(o):
    for d in walk_dicts(o):
        if d.get('type') in ('datatableContext', 'dataContext') and d.get('sourceType') == 'Url' and d.get('permanentFilter'):
            yield d


def apply(ctx, markup):
    model = (markup.get('formSettings') or {}).get('modelType')
    plist = metadata.properties(ctx, model) if isinstance(model, str) and model else None
    props = {camel(p['path']) for p in plist} if plist is not None else None
    n, notes = 0, []
    for c in list(contexts(markup)):
        exprs = re.findall(r'\{\{\s*([^}]+?)\s*\}\}', json.dumps(c['permanentFilter']))
        dead = [e for e in exprs if props is not None and re.match(r'^data\.([A-Za-z0-9_]+)', e)
                and re.match(r'^data\.([A-Za-z0-9_]+)', e).group(1) not in props | {'id'}]
        if exprs and len(dead) == len(exprs):
            c.pop('permanentFilter')
            n += 1
            notes.append(f'{c.get("componentName")}: leftover permanent filter on {", ".join(dead)} (never resolves on {model.split(".")[-1]}) removed - the URL source fetches again (H43)')
        else:
            notes.append(f'INFO {c.get("componentName")}: permanent filter {exprs} '
                         f'{"left alone: model unknown" if props is None else "left alone: resolvable"}')
    flush(ctx, notes)
    return n
