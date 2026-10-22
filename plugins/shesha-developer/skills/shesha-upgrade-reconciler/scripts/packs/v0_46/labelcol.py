"""Rule `labelcol` (H14, opt-in): subForm label / wrapper column spans.

Symptom on 0.46: wrapped labels in hosted subforms, or labels that disappear (a subForm stored with `labelCol: 0` hides
the labels of the fields it hosts). The migrated default of a 0.43 subForm is labelCol 8 / wrapperCol 16; which split
reads best is a project choice, so the rule only runs when the option is set. The 0.46.1 release notes claim a subForm
labelCol/wrapperCol migration fix (not verified).
Writes: a subForm stored with labelCol 8 and wrapperCol 16 (or unset) gets the configured spans.
Marker: none (idempotent).  Options: subformLabelCol ([labelCol, wrapperCol], e.g. [10, 14]; unset = no-op).
"""
from core.project import require
from core.tree import walk
from packs.v0_46.common import flush


def _spans(ctx):
    raw = ctx.opt('subformLabelCol')
    if raw is None:
        return None
    require(isinstance(raw, (list, tuple)) and len(raw) == 2 and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in raw)
            and sum(raw) <= 24, 'option subformLabelCol must be [labelCol, wrapperCol], two positive integers summing to at most 24')
    return raw[0], raw[1]


def apply(ctx, markup):
    spans = _spans(ctx)
    if not spans:
        return 0
    lab, wrap = spans
    n, notes = 0, []
    for c, _, _ in walk(markup):
        if c.get('type') == 'subForm' and c.get('labelCol') == 8 and c.get('wrapperCol') in (16, None) \
                and (c.get('labelCol'), c.get('wrapperCol')) != (lab, wrap):
            c['labelCol'], c['wrapperCol'] = lab, wrap
            n += 1
            notes.append(f'{c.get("componentName")}: labelCol 8/16 -> {lab}/{wrap}')
    flush(ctx, notes)
    return n


# retire: none. The rule rewrites a stored span pair that carries no marker, so an exact undo is not possible, and the
# framework fix in 0.46.1 is a load-time migration of the same pair: nothing needs to be unwound.
