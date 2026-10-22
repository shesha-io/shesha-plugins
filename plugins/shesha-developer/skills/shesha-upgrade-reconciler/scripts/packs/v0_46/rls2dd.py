"""Rule `rlshidden` (H13, TEMPORARY WORKAROUND): hidden refListStatus helpers inside hosted forms.

Symptom on 0.46: "Component with id ... is not found" thrown by a refListStatus rendered inside a subForm.
Cause: refListStatus/index.tsx calls the markup-context useComponentModel, which a subForm does not provide. Only forms
rendered inside another form (subForm / dataList / list item / dialog form: ctx.hosted_forms()) are affected.
Writes: a STATICALLY hidden refListStatus in a hosted form is replaced, keeping id / binding / visibility, by a hidden
textField (binding kept, nothing rendered). The original component is kept verbatim under `_reconcilerOriginal` so the
swap can be reversed when the framework fix ships. (A visible refListStatus is not touched: swap() can also build a
read-only reference-list dropdown shown as a solid tag, for callers that need it.)
Marker: the `_reconcilerOriginal` key.  Options: none.
"""
import copy

from core.project import require
from core.tree import walk
from packs.v0_46.common import flush

MARK_KEY = '_reconcilerOriginal'
KEEP = ('id', 'propertyName', 'componentName', 'label', 'labelAlign', 'hideLabel', 'parentId', 'visible', 'hidden',
        'description', 'desktop', 'tablet', 'mobile', 'enableStyleOnReadonly', 'permissions', 'visiblePermissions')


def is_static_hidden(c):
    v, h = c.get('visible'), c.get('hidden')
    return v is False or h is True or (isinstance(v, dict) and v.get('_mode') == 'value' and v.get('_value') is False) \
        or (isinstance(h, dict) and h.get('_mode') == 'value' and h.get('_value') is True)


def swap(c, dropdown_version=15, textfield_version=8):
    """Return the replacement dict for refListStatus c (does not mutate c)."""
    require(c.get('type') == 'refListStatus' and c.get('referenceListId'), f'{c.get("id")}: not a refListStatus with a reference list')
    base = {k: copy.deepcopy(c[k]) for k in KEEP if k in c}
    base[MARK_KEY] = copy.deepcopy(c)
    if is_static_hidden(c):
        base.update({'type': 'textField', 'version': textfield_version, 'editMode': 'readOnly'})
        return base
    base.update({'type': 'dropdown', 'version': dropdown_version, 'dataSourceType': 'referenceList',
                 'referenceListId': copy.deepcopy(c['referenceListId']), 'valueFormat': 'simple', 'editMode': 'readOnly',
                 'displayStyle': 'tags', 'tagVariant': 'solid' if c.get('solidBackground', True) else 'outlined',
                 'showItemName': True, 'enableMultiSelect': False})
    return base


def apply(ctx, markup):
    if ctx.form not in ctx.hosted_forms():
        return 0
    n, notes = 0, []
    for c, pl, i in list(walk(markup)):
        if c.get('type') == 'refListStatus' and is_static_hidden(c):
            pl[i] = swap(c)
            n += 1
            notes.append(f'{c.get("componentName")}: hidden refListStatus -> hidden textField')
    flush(ctx, notes)
    return n
