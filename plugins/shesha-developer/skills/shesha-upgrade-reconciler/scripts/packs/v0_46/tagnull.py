"""Rule `tagnull` (H33): a refListStatus with no value renders an empty grey chip on 0.46 (the 0.43 site rendered nothing).

Writes: every always-visible refListStatus gets the visibility condition `data?.<path> != null` (optional chaining on
every hop). Components that already carry a visibility condition, or are hidden, are left alone.
Marker: /*reconciler:046-tag-null*/ in the visible code.  Options: none.
"""
from core.tree import walk
from packs.v0_46.common import flush

MARK = '/*reconciler:046-tag-null*/'


def apply_component(c, notes):
    if c.get('type') != 'refListStatus':
        return 0
    pn = c.get('propertyName')
    if not isinstance(pn, str) or not pn or pn.startswith('_'):
        return 0
    v, h = c.get('visible'), c.get('hidden')
    if isinstance(v, dict) and v.get('_mode') == 'code':
        return 0
    if v is False or h is True or (isinstance(h, dict) and h.get('_mode') == 'code'):
        return 0
    if isinstance(v, dict) and v.get('_mode') == 'value' and v.get('_value') is False:
        return 0
    path = 'data?.' + '?.'.join(pn.split('.'))
    c['visible'] = {'_mode': 'code', '_code': f'{MARK}\nreturn {path} != null;', '_value': True}
    c.pop('hidden', None)
    notes.append(f'{c.get("componentName")}: visible only with a value ({pn})')
    return 1


def apply(ctx, markup):
    notes = []
    n = sum(apply_component(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
