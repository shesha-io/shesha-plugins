"""Rule `subfetch` (H28): a value the host form shows from a subform-loaded object disappears after the subform loads.

Symptom on 0.46: a host-form status tag shows, then goes blank when the subform finishes loading.
Cause: a subForm loading through the API (dataSource 'api') with an explicit `properties` list writes what it loads
back into the host's field (its propertyName), REPLACING the host's copy. Any `<propertyName>.<x>` the HOST form shows
but the subform does not fetch disappears once the subform's Crud/Get returns without it.
Writes: every such top-level field the host shows is appended to the subform's `properties` list.
Marker: none (idempotent: the field is then in the list).  Options: none.
"""
import re

from core.tree import walk
from packs.v0_46.common import flush


def apply(ctx, markup):
    n, notes = 0, []
    for c, _, _ in walk(markup):
        if c.get('type') != 'subForm' or c.get('dataSource') != 'api' or not isinstance(c.get('properties'), str) or not c.get('propertyName'):
            continue
        pn = c['propertyName']
        have = {x.strip().split('{')[0].strip() for x in re.split(r'[\r\n,]+', c['properties']) if x.strip()}
        bound = sorted({x['propertyName'][len(pn) + 1:].split('.')[0] for x, _, _ in walk(markup)
                        if isinstance(x.get('propertyName'), str) and x['propertyName'].startswith(pn + '.')} - have)
        if not bound:
            continue
        sep = '\r\n' if '\r\n' in c['properties'] else '\n'
        c['properties'] = c['properties'].rstrip() + sep + sep.join(bound)
        n += len(bound)
        notes.append(f'{c.get("componentName")}: fetch {bound} (shown by the host from {pn})')
    flush(ctx, notes)
    return n
