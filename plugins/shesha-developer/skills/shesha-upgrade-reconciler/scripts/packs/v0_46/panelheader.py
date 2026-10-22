"""Rule `panels` (H30, opt-in): collapsiblePanel header spacing back to the pre-upgrade look.

Symptom on 0.46: panel headers are 52-56px tall with 8px padding all round.
Cause: the 0.46 collapsiblePanel migration (collapsiblePanelComponent.tsx) writes default headerStyles into every device
block, including stylingBoxJson padding 8/8/8/8. How the pre-upgrade site spaced its headers is a project choice, so the
rule only runs when the option is set.
Writes: a header padding that is still exactly the migration default (8/8/8/8) is replaced by the configured padding;
an author's own header padding is kept.
Marker: none (idempotent: the configured padding is no longer the default).
Options: panelHeaderPadding ({paddingTop, paddingRight, paddingBottom, paddingLeft}, strings or numbers; unset = no-op).
"""
from core.project import require
from core.tree import walk
from packs.v0_46.common import flush

DEFAULT = {'paddingTop': '8', 'paddingRight': '8', 'paddingBottom': '8', 'paddingLeft': '8'}


def _wanted(ctx):
    raw = ctx.opt('panelHeaderPadding')
    if not raw:
        return None
    require(isinstance(raw, dict) and raw and set(raw) <= set(DEFAULT),
            f'option panelHeaderPadding must be an object with keys from {sorted(DEFAULT)}')
    want = {k: str(v) for k, v in raw.items()}
    return None if all(want.get(k, DEFAULT[k]) == DEFAULT[k] for k in DEFAULT) else want


def apply_component(c, notes, want):
    if c.get('type') != 'collapsiblePanel':
        return 0
    n = 0
    for dev in ('desktop', 'tablet', 'mobile'):
        hs = (c.get(dev) or {}).get('headerStyles') if isinstance(c.get(dev), dict) else None
        sb = hs.get('stylingBoxJson') if isinstance(hs, dict) else None
        if not isinstance(sb, dict):
            continue
        if all(str(sb.get(k)) == v for k, v in DEFAULT.items()):
            sb.update(want)
            n += 1
    if n:
        notes.append(f'{c.get("componentName")}: panel header padding 8 -> '
                     f'{want.get("paddingTop", "8")}/{want.get("paddingRight", "8")}/{want.get("paddingBottom", "8")}/{want.get("paddingLeft", "8")}')
    return n


def apply(ctx, markup):
    want = _wanted(ctx)
    if not want:
        return 0
    notes = []
    n = sum(apply_component(c, notes, want) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
