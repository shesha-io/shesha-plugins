"""Rule `url_reflist_columns` (H36, targeted): a `[default]` column on a URL-sourced table shows a reference-list value as a number.

Symptom on 0.46: a datatable column of a table whose `datatableContext.sourceType` is 'Url' shows the RAW value of a
reference-list property ('12', '20') instead of the item name.
Cause: 0.43 resolved the list from the context's entity type; 0.46's default display gets no property metadata for URL
data. Columns bound to a dropdown display with the reference list render names.
Writes (configuration only): for each `[default]` data column whose property is a reference list in the context entity's
metadata, a read-only dropdown display bound to that list is stored (stored values unchanged). The display template is
copied from a working reference-list dropdown display in the same form when present, else the option
`refListDisplayTemplate`, else the bundled minimal one (`bundled_template()`).
Metadata (Metadata/Get) is fetched lazily through ctx.api() and cached per entity type; offline tests pre-seed
`session._cache['metadata:<entityType>']` (see metadata.py). A type the backend does not know is skipped (INFO).
Marker: the `-rl046` suffix of the display settings id.  No retire: a display binding is a plain, valid configuration.
Options: refListDisplayTemplate (a displayComponent dict {"type": "dropdown", "settings": {...}}; optional).
Run with `apply --rules url_reflist_columns --only form,...`.
"""
import copy
import hashlib

from core.project import require
from packs.v0_46 import metadata
from packs.v0_46.common import flush


def bundled_template():
    return {'type': 'dropdown',
            'settings': {'id': 'bundled-dropdown', 'type': 'dropdown', 'propertyName': 'editor', 'hidden': False, 'isDynamic': False,
                         'version': 7, 'dataSourceType': 'referenceList', 'useRawValues': False,
                         'referenceListId': {'name': '', 'module': ''}, 'valueFormat': 'simple',
                         'desktop': {}, 'tablet': {}, 'mobile': {}, 'validate': {}, 'hideLabel': True}}


def _reflist(p):
    if not p:
        return None
    r = p.get('referenceListId')
    if isinstance(r, dict) and r.get('name'):
        return {'name': r['name'], 'module': r.get('module')}
    if p.get('referenceListName'):
        return {'name': p['referenceListName'], 'module': p.get('referenceListModule')}
    return None


def _templates(m):
    out = []

    def walk(o):
        if isinstance(o, dict):
            d = o.get('displayComponent')
            if isinstance(d, dict) and d.get('type') == 'dropdown' and ((d.get('settings') or {}).get('dataSourceType') == 'referenceList'):
                out.append(d)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(m)
    return out


def plan_columns(ctx, m):
    """[(column dict, reflist)] for '[default]' columns on Url-sourced tables whose entity property is a reference list."""
    out = []

    def walk(o, tctx=None):
        if isinstance(o, dict):
            if o.get('type') == 'datatableContext':
                tctx = o
            if o.get('type') == 'datatable' and tctx is not None and tctx.get('sourceType') == 'Url' and tctx.get('entityType'):
                et = tctx['entityType']
                et = et.get('fullClassName') if isinstance(et, dict) else et
                plist = metadata.properties(ctx, et)
                if plist is None:
                    ctx.info(f'no metadata for entity type {et}: its [default] columns are not checked')
                    plist = []
                props = {(p.get('path') or '').lower(): p for p in plist}
                for c in o.get('items', []):
                    d = (c.get('displayComponent') or {}).get('type')
                    rl = _reflist(props.get((c.get('propertyName') or '').lower()))
                    if c.get('columnType') == 'data' and d in ('[default]', None) and rl:
                        out.append((c, rl))
            for v in o.values():
                walk(v, tctx)
        elif isinstance(o, list):
            for v in o:
                walk(v, tctx)
    walk(m)
    return out


def apply(ctx, markup):
    cols = plan_columns(ctx, markup)
    if not cols:
        return 0
    custom = ctx.opt('refListDisplayTemplate')
    if custom is not None:
        require(isinstance(custom, dict) and custom.get('type') == 'dropdown' and isinstance(custom.get('settings'), dict),
                'option refListDisplayTemplate must be {"type": "dropdown", "settings": {...}}')
    tpl = next(iter(_templates(markup)), None) or custom or bundled_template()
    notes = []
    for c, rl in cols:
        d = copy.deepcopy(tpl)
        d['settings']['id'] = hashlib.sha1(f'{ctx.name}:{c.get("id")}'.encode()).hexdigest()[:22] + '-rl046'
        d['settings']['referenceListId'] = rl
        c['displayComponent'] = d
        notes.append(f'{c.get("caption")} ({c.get("propertyName")}): dropdown display bound to {rl["module"]}/{rl["name"]}')
    flush(ctx, notes)
    return len(cols)
