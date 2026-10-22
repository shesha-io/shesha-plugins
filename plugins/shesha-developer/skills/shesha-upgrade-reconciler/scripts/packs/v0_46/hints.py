"""Rule `hints` (H22): a columns block holding one conditional text keeps its margins when the text is hidden.

Symptom on 0.46: an empty strip (the columns block's own margin and the cell padding) where a hint text was hidden.
Cause: the hidden text is gone but the always-visible columns block around it stays, and a hidden or empty block still
takes its box (see the `layout` rule).
Writes: a `visible: true` columns block whose only child is a `text` with a visibility CODE takes a copy of that
visibility code (and drops `hidden`), so the block disappears together with its text.
Marker: none (idempotent: the block's visible is then a code setting).  Options: none.
"""
import copy

from core.tree import walk
from packs.v0_46.common import flush


def apply(ctx, markup):
    n, notes = 0, []
    for c, _, _ in walk(markup):
        if c.get('type') != 'columns' or c.get('visible') is not True:
            continue
        kids = [k for col in c.get('columns') or [] for k in col.get('components') or []]
        if len(kids) != 1 or kids[0].get('type') != 'text':
            continue
        v = kids[0].get('visible')
        if not (isinstance(v, dict) and v.get('_mode') == 'code' and (v.get('_code') or '').strip()):
            continue
        c['visible'] = copy.deepcopy(v)
        c.pop('hidden', None)
        n += 1
        notes.append(f'{c.get("componentName")}: takes the visibility of its only text')
    flush(ctx, notes)
    return n
