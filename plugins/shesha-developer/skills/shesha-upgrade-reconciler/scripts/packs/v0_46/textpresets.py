"""Rule `textsize` (H8): restore the 0.43 sizes of `text` components that use legacy presets.

Symptom on 0.46: titles and texts are 12.5% smaller and the preset padding is gone.
Cause: the 0.46 text v5 migration converts `fontSize` presets with a 14px root (text/index.tsx remToPx) while 0.43 rendered
them in rem against the browser's 16px root; v7 ignores the legacy `padding` preset entirely (0.43 applied it on all
four sides). Example: text-xl = 1.25rem x 16 = 20px.
Writes: desktop.font.size = preset rem x 16 and the preset padding into desktop.stylingBoxJson. Only rewrites values that
are the migration's own output (font.size == rem*14 or absent; padding sides unset/0).
Marker: none (idempotent: the written values are no longer the migration's).  Options: none.
"""
from core.tree import walk
from packs.v0_46.common import flush

FONT = {'text-xxs': .6, 'text-xs': .75, 'text-sm': .875, 'text-base': 1, 'text-lg': 1.125, 'text-xl': 1.25, 'text-2xl': 1.5,
        'text-3xl': 1.875, 'text-4xl': 2.25, 'text-5xl': 3, 'text-6xl': 3.75, 'text-7xl': 4.5, 'text-8xl': 6, 'text-9xl': 8}
PAD = {'padding-xxs': .6, 'padding-xs': .75, 'padding-sm': .875, 'padding-base': 1, 'padding-lg': 1.125, 'padding-xl': 1.25,
       'padding-2xl': 1.5, 'padding-3xl': 1.875, 'padding-4xl': 2.25, 'padding-5xl': 3, 'padding-6xl': 3.75,
       'padding-7xl': 4.5, 'padding-8xl': 6}
SIDES = ('paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft')


def _num(v):
    try:
        return float(str(v).replace('px', ''))
    except Exception:
        return None


def apply_component(c, notes):
    if c.get('type') != 'text':
        return 0
    d = c.get('desktop')
    if not isinstance(d, dict):
        d = c['desktop'] = {}
    n = 0
    fs = c.get('fontSize')
    if isinstance(fs, str) and fs in FONT:
        want, migrated = FONT[fs] * 16, FONT[fs] * 14
        font = d.setdefault('font', {})
        cur = _num(font.get('size'))
        if cur is None or abs(cur - migrated) < 0.01 or abs(cur - want) < 0.01:
            if cur is None or abs(cur - want) >= 0.01:
                font['size'] = int(want) if want == int(want) else want
                n += 1
                notes.append(f'{c.get("componentName")}: font {cur} -> {font["size"]} ({fs} at 16px root)')
    pd = c.get('padding')
    if isinstance(pd, str) and pd in PAD:
        px = str(int(PAD[pd] * 16)) if PAD[pd] * 16 == int(PAD[pd] * 16) else str(PAD[pd] * 16)
        box = d.get('stylingBoxJson') if isinstance(d.get('stylingBoxJson'), dict) else {'_type': 'styleBox'}
        changed = False
        for s in SIDES:
            if _num(box.get(s)) in (None, 0.0) and box.get(s) != px:
                box[s] = px
                changed = True
        if changed:
            box['_type'] = 'styleBox'
            d['stylingBoxJson'] = box
            n += 1
            notes.append(f'{c.get("componentName")}: padding {pd} -> {px}px all sides')
    return n


def apply(ctx, markup):
    notes = []
    n = sum(apply_component(c, notes) or 0 for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
