"""Rule `rowgap` (H29): horizontal containers lose their gap on 0.46 (table toolbars: search, filter, refresh, columns, pager touch).

Cause: a container stored below the style step with PARTIAL device blocks (e.g. only `className`) is migrated from those
blocks (migrateStyles reads prev[screen] when it exists), and the v9 step copies `gap: prev.gap` (unset/null), so the
row renders with gap 0 where 0.43 spaced it.
Writes: `gap` = the option value in every device block that has no gap (top level when the container stores no device
blocks). Containers with their own gap are left alone. Rows are horizontal when stored so, or when they carry a class
0.46 forces into a flex row.
Marker: none (idempotent).  Options: rowGap (default '8px').
"""
from core.project import require
from core.tree import walk
from packs.v0_46.common import flush

ROW_CLASSES = {'index-table-controls-right'}   # 0.46 container defaults force display:flex/nowrap for these (container/data.ts)


def _class(c):
    return c.get('className') or next((c[d].get('className') for d in ('desktop', 'tablet', 'mobile') if isinstance(c.get(d), dict) and c[d].get('className')), None)


def _horizontal(c):
    """Rendered as a row: stored horizontal, or a class 0.46 forces into a flex row whatever the stored direction."""
    cls = _class(c)    # className may be stored as an object (code setting): only a plain string can name a row class
    return (c.get('direction') == 'horizontal' or (isinstance(cls, str) and cls in ROW_CLASSES)
            or any(isinstance(c.get(d), dict) and c[d].get('direction') == 'horizontal' for d in ('desktop', 'tablet', 'mobile')))


def apply_component(c, notes, gap='8px'):
    if c.get('type') != 'container' or not _horizontal(c):
        return 0
    if c.get('gap') not in (None, ''):
        return 0
    blocks = [c[d] for d in ('desktop', 'tablet', 'mobile') if isinstance(c.get(d), dict)]
    n = 0
    if blocks:
        for b in blocks:
            if b.get('gap') in (None, ''):
                b['gap'] = gap
                n += 1
    else:
        c['gap'] = gap
        n = 1
    if n:
        notes.append(f'{c.get("componentName")}: horizontal row gap {gap}')
    return n


def apply(ctx, markup):
    gap = ctx.opt('rowGap', '8px')
    require(isinstance(gap, str) and gap.strip(), 'option rowGap must be a CSS length string such as "8px"')
    notes = []
    n = sum(apply_component(c, notes, gap) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
