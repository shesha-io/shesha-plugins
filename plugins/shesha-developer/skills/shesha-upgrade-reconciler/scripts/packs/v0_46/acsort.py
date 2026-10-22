"""Rule `acsort` (H38): an entity autocomplete with no stored `sorting` lists options in database order on 0.46.

Symptom on 0.46: options (for example a list of categories) are not alphabetical.
Cause: 0.43 sent `sorting=<displayPropName>` by default; 0.46 sends none.
Writes: the 0.43 default is stored explicitly: an ascending sort on the display property, in the 0.46 `sorting` format
([{id, propertyName, sorting: 'asc', itemType: 'item'}]). Only for dataSourceType 'entitiesList' autocompletes whose
display property is a real column (not '_displayName' or a dotted path); any stored sorting is left alone.
Marker: the `-s046` suffix of the sorting item id.  Options: none.
"""
import hashlib

from core.tree import walk
from packs.v0_46.common import flush


def apply_component(c, notes):
    if c.get('type') != 'autocomplete' or c.get('dataSourceType') != 'entitiesList':
        return 0
    if c.get('sorting'):
        return 0
    prop = c.get('displayPropName')
    if not isinstance(prop, str) or not prop or prop.startswith('_') or '.' in prop:
        return 0
    c['sorting'] = [{'id': hashlib.sha1(f'{c.get("id")}:sort046'.encode()).hexdigest()[:22] + '-s046', 'propertyName': prop,
                     'sorting': 'asc', 'itemType': 'item'}]
    notes.append(f'{c.get("componentName") or c.get("propertyName")}: options sorted by {prop} (0.43 default)')
    return 1


def apply(ctx, markup):
    notes = []
    n = sum(apply_component(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
