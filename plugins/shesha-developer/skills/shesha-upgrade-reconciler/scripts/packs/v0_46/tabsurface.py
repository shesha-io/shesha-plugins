"""Rules `tabs` (H9, H7) and `tabgap` (H24): undo the 0.46 tabs 'surface' and restore the gap under the tab bar.

Symptom on 0.46: grey inactive tabs, a black active label, a bordered and padded tab body, and no gap between the tab
bar and the first field.
Cause: the v4+ tabs migration persists a surface into the tabs desktop/tablet/mobile blocks: card.background
rgba(0,0,0,0.02), font.color '' (an empty-but-defined colour overrides colorPrimary, tabs/styles.ts
--ant-tabs-item-selected-color), font.weight 500, a 1px #f0f0f0 border with radius 8 and 16px padding. Theme defaults
cannot win (desktop > theme, formComponentModelPreparer.tsx), so this is a per-form rule. 0.46 also sets
`.ant-tabs-nav{margin:0}` (antd's default was a 16px bottom margin) and applies the component's padding to
`.ant-tabs-body-holder`, i.e. BELOW the bar.
Writes (`apply`, rule `tabs`): only values equal to the migration defaults are reset (transparent card, primary colour
400, zero borders with hideBorder, zero padding); tabs saved below v4 are seeded (`seed_low_version`) with the same
desktop surface that restores the 0.43 framework tab look (primary-colour label, transparent card, no borders), marked
`_reconciler046`.
Writes (`apply_gap`, rule `tabgap`): top-positioned tabs with a stored top padding of 0/unset get paddingTop 16; an
author's own padding is kept.
Marker: `_reconciler046` in a seeded desktop block; none otherwise.  Options: none.
"""
import copy
import json

from core.tree import walk
from packs.v0_46.common import flush

GREY = {'rgba(0,0,0,0.02)', 'rgba(0, 0, 0, 0.02)'}
ZERO = {'width': '0px', 'style': 'none', 'color': '#f0f0f0'}
# tabs body border lines come from border.border.all/sides and IGNORE hideBorder (tabs/styles.ts borderLinesStyles)
REFERENCE_SURFACE = {'card': {'background': {'type': 'color', 'color': 'transparent'}},
                     'font': {'color': 'var(--primary-color)', 'weight': '400'},
                     'border': {'hideBorder': True, 'borderType': 'all',
                                'border': {'all': ZERO, 'top': ZERO, 'right': ZERO, 'bottom': ZERO, 'left': ZERO}},
                     'stylingBoxJson': {'_type': 'styleBox', 'paddingTop': '0', 'paddingRight': '0', 'paddingBottom': '0', 'paddingLeft': '0'}}


def seed_low_version(c, notes):
    """v<4 tabs are migrated at render time and receive the 0.46 surface defaults; give them explicit desktop values that
    restore the 0.43 framework tab look (primary-colour label, transparent card, no borders) for the migration to merge under."""
    if c.get('type') != 'tabs' or (c.get('version') or 0) >= 4:
        return 0
    d = c.setdefault('desktop', {})
    before = repr(d)
    for k, v in REFERENCE_SURFACE.items():
        cur = d.get(k)
        # border: the seed wins (the migration's border lines must be zeroed); everything else, incl. stylingBoxJson,
        # keeps stored values so later rules (tab_gap paddingTop 16) are not overwritten on the next run.
        d[k] = {**(cur if isinstance(cur, dict) else {}), **copy.deepcopy(v)} if k == 'border' else {**copy.deepcopy(v), **(cur if isinstance(cur, dict) else {})}
    sbm = c.get('stylingBox')
    if isinstance(sbm, str) and 'marginBottom' in sbm:
        try:
            d['stylingBoxJson']['marginBottom'] = str(json.loads(sbm).get('marginBottom'))
        except Exception:
            pass
    d['_reconciler046'] = True
    if repr(d) == before:
        return 0
    notes.append(f'{c.get("componentName")}: v{c.get("version")} tabs seeded with the 0.43 framework tab look (primary-colour label, transparent card, no borders)')
    return 1


def reset_surface(c, notes):
    if c.get('type') != 'tabs':
        return 0
    n = 0
    for dev in ('desktop', 'tablet', 'mobile'):
        d = c.get(dev)
        if not isinstance(d, dict):
            continue
        bg = ((d.get('card') or {}).get('background') or {})
        if bg.get('color') in GREY:
            bg['color'] = 'transparent'
            n += 1
        f = d.setdefault('font', {}) if dev == 'desktop' else d.get('font')
        if isinstance(f, dict):
            # tabs defaults (tabs/utils.ts) merge color '' back in; '' is "defined" and replaces colorPrimary,
            # so write the primary colour explicitly (0.46 defines --primary-color on the active tab).
            if f.get('color') in ('', None) and dev == 'desktop':
                f['color'] = 'var(--primary-color)'
                n += 1
            elif f.get('color') == '':
                del f['color']
                n += 1
            if str(f.get('weight')) == '500':
                f['weight'] = '400'
                n += 1
        b = d.get('border')
        if isinstance(b, dict) and ((b.get('border') or {}).get('all') or {}).get('color') == '#f0f0f0':
            sides = b.setdefault('border', {})
            if any(str((sides.get(k) or {}).get('width')) not in ('0px', '0') for k in ('all', 'top', 'right', 'bottom', 'left')) or not b.get('hideBorder'):
                b['hideBorder'] = True
                for k in ('all', 'top', 'right', 'bottom', 'left'):
                    sides[k] = dict(ZERO)
                n += 1
        sb = d.get('stylingBoxJson')
        if isinstance(sb, dict) and all(str(sb.get(k)) == '16' for k in ('paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft')):
            for k in ('paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft'):
                sb[k] = '0'
            n += 1
    if n:
        notes.append(f'{c.get("componentName")}: tabs 0.46 surface reset ({n})')
    return n


def tab_gap(c, notes):
    """Gap between the tab bar and the first field: paddingTop 16 on top-positioned tabs whose stored top padding is 0/unset."""
    if c.get('type') != 'tabs' or c.get('tabPosition') not in (None, '', 'top'):
        return 0
    n = 0
    for dev in ('desktop', 'tablet', 'mobile'):
        d = c.get(dev)
        if not isinstance(d, dict):
            continue
        sb = d.get('stylingBoxJson')
        if sb is None:
            sb = d['stylingBoxJson'] = {'_type': 'styleBox'}
        if not isinstance(sb, dict):
            continue
        if str(sb.get('paddingTop', '')) in ('', '0', 'None'):
            sb['paddingTop'] = '16'
            n += 1
    if n:
        notes.append(f'{c.get("componentName")}: 16px gap under the tab bar')
    return n


def apply(ctx, markup):
    notes = []
    n = sum(seed_low_version(c, notes) + reset_surface(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n


def apply_gap(ctx, markup):
    notes = []
    n = sum(tab_gap(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
