"""Rule `layout` (H22 / H16 / H21): per-component APPEARANCE fixes for 0.46 layout drift.

No hidden stylesheet components: every value written is one the component's own Appearance panel shows.
Where a value must be stored depends on the stored component version: a component saved below the version whose
migration moved styles into desktop/tablet/mobile gets its previous styles COPIED into those blocks at load (the copy
replaces `desktop`), so for those the value goes into the top-level `stylingBox` / `dimensions` the migration copies.

1. container  Dimensions > Min height '0px'  (0.46 default 32px, container/data.ts, lands on the wrapper: hidden and
   empty containers keep a 32px gap; the pre-upgrade site had none). Skipped where the author stored a min height, and
   where the REFERENCE form stored a real one (ctx.reference_components(): {component id: component}).
2. columns    Margin left -(gutterX/2), LEFT ONLY. 0.46 cancels antd's row margin (columns.tsx) so fields are inset by
   gutterX/2. A right margin as well would overflow the 0.46 overflow:auto containers and tab bodies (horizontal
   scrollbars), so only the left inset is restored.
3. form field Margin bottom '-3'. The framework adds padding-bottom 3px to every label column (shaComponentStyles.ts, not
   configurable), so rows are 35px where 0.43 had 32. The 5px row gap is antd's `.ant-form-item-row` margin, which
   collapses with the field's own margin, so a positive value cannot shrink it. A negative margin collapses with it:
   5 + (-3) = 2, and 35 + 2 = the 37px pitch. Skipped where the author stored a bottom margin.
Marker: none (idempotent).  Options: none.
"""
import json

from core.project import ConfigError, require
from core.tree import walk
from packs.v0_46.common import flush

FIELDS = {'textField', 'dropdown', 'checkbox', 'dateField', 'numberField', 'textArea', 'autocomplete', 'entityReference',
          'address', 'radio', 'switch', 'timePicker', 'checkboxGroup', 'refListStatus', 'currency', 'password'}
DEVICES = ('desktop', 'tablet', 'mobile')
PARTIAL = {'dimensions': {'minHeight': '0px'}}


def _blocks(c):
    return [c[d] for d in DEVICES if isinstance(c.get(d), dict)]


def _top_box(c):
    raw = c.get('stylingBox')
    box = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    require(isinstance(box, dict), f'{c.get("componentName")}: stylingBox is not an object')
    return box


def _uses_json(c):
    """True when the stored model already carries device stylingBoxJson (migrated); else write the top-level string."""
    return any(isinstance(b.get('stylingBoxJson'), dict) for b in _blocks(c))


def container_min_height(c, notes, ref_min=None, ref_had_desktop=None):
    """A container that stores no device blocks is still below the style step: the load-time migration builds its
    desktop/tablet/mobile blocks FROM ITS TOP-LEVEL PROPS, but only when no device block exists
    (migrateStyles: prevStyles = prev[screen] ? prev[screen] : prev). Creating a partial `desktop` block therefore
    makes the migration ignore every top-level style (height, padding, ...) and collapses boxes.
    So: write the top-level `dimensions.minHeight` for those, and repair a partial block an earlier run created.
    NOTE: existing EMPTY blocks ({}) are also used by the migration (an empty object is truthy), so for those the
    value must go INTO the blocks - emptying them and writing the top level would bring the 32px floor back."""
    if c.get('type') != 'container':
        return 0
    n = 0
    # The repair is only right when the block did not exist before the upgrade (an earlier run created it). When the
    # reference stored a desktop block, it is the filled EMPTY block below: removing it would bring the 32px floor
    # back and the rule would flip on every run.
    if (c.get('desktop') == PARTIAL and not isinstance(c.get('tablet'), dict) and not isinstance(c.get('mobile'), dict)
            and ref_had_desktop is not True):
        del c['desktop']
        n += 1   # repair: undo the partial block, keep the intent at top level below
        c.setdefault('dimensions', {})['minHeight'] = '0px'
        notes.append(f'{c.get("componentName")}: partial desktop block removed, min height 0px at top level')
        return n
    if ref_min not in (None, '', '0px', '0'):
        return 0
    blocks = _blocks(c)
    if not blocks:
        dims = c.get('dimensions') if isinstance(c.get('dimensions'), dict) else {}
        if dims.get('minHeight') in (None, '', '32px'):
            c['dimensions'] = {**dims, 'minHeight': '0px'}
            n += 1
    for b in blocks:
        dims = b.setdefault('dimensions', {})
        if dims.get('minHeight') in (None, '', '32px'):
            dims['minHeight'] = '0px'
            n += 1
    if n:
        notes.append(f'{c.get("componentName")}: min height 0px')
    return n


def columns_left_margin(c, notes):
    if c.get('type') != 'columns':
        return 0
    g = c.get('gutterX')
    if not isinstance(g, (int, float)) or g <= 0:
        return 0
    want = str(-(int(g) // 2))
    name = c.get('componentName') or c['id']

    def setbox(box, where):
        cur = box.get('marginLeft')
        if str(cur) == want:
            return False
        if cur not in (None, '', '0', 0):
            notes.append(f'INFO {name}: {where} marginLeft {cur!r} kept')
            return False
        box['marginLeft'] = want
        return True
    n = 0
    if _uses_json(c):
        for b in _blocks(c):
            if isinstance(b.get('stylingBoxJson'), dict) and setbox(b['stylingBoxJson'], 'stylingBoxJson'):
                n += 1
    else:
        box = _top_box(c)
        if setbox(box, 'stylingBox'):
            c['stylingBox'] = json.dumps(box)
            n += 1
    if n:
        notes.append(f'{name}: margin left {want}px (gutter {g})')
    return n


def field_margin_bottom(c, notes):
    if c.get('type') not in FIELDS:
        return 0
    name = c.get('componentName') or c['id']

    def setbox(box):
        cur = box.get('marginBottom')
        if str(cur) == '-3' or cur not in (None, '', '2'):
            return False
        box['marginBottom'] = '-3'
        return True
    n = 0
    if _uses_json(c):
        for b in _blocks(c):
            if isinstance(b.get('stylingBoxJson'), dict) and setbox(b['stylingBoxJson']):
                n += 1
    else:
        box = _top_box(c)
        if setbox(box):
            c['stylingBox'] = json.dumps(box)
            n += 1
    if n:
        notes.append(f'{name}: margin bottom -3')
    return n


def _reference_min_heights(ctx):
    """{component id: (min height the reference stored - device dimensions first, then top level; whether the reference
    stored a desktop block)}"""
    def build():
        try:
            comps = ctx.reference_components()
        except ConfigError:
            comps = {}   # no project / no reference snapshot: every container is treated as having no stored reference height
        return {cid: (((c.get('desktop') or {}).get('dimensions') or {}).get('minHeight') or c.get('minHeight'),
                      isinstance(c.get('desktop'), dict))
                for cid, c in comps.items()}
    return ctx.cache('layout.reference_min_heights', build)


def apply(ctx, markup):
    ref = _reference_min_heights(ctx)
    notes, n = [], 0
    for c, _, _ in walk(markup):
        ref_min, ref_had_desktop = ref.get(c['id'], (None, None))
        n += (container_min_height(c, notes, ref_min, ref_had_desktop) + columns_left_margin(c, notes)
              + field_margin_bottom(c, notes))
    flush(ctx, notes)
    return n
