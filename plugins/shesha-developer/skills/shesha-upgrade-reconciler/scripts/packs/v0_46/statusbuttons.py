"""Rule `status` (H10): 0.43 behaviour that relied on a THROWING setting expression.

Symptom on 0.46: blank 37px status buttons, a lost gap under section separators.
1. Status buttons (ONLY when option `statusLabelPattern` is set; there is no default, the label idiom is the project's):
   a label whose code matches the pattern (for example `const status = data?.X?.status; switch (status) ...`) with no
   visibility condition. On 0.43 the label threw when X was absent and the button did not render (no space taken). 0.46
   swallows the error (executeScriptSync returns undefined) and renders an empty button. Restored with an explicit
   condition `data?.X?.<prop> != null`.
2. sectionSeparator lost its bottom spacing on 0.46 (0.43 left about 10px under the rule, 0.46 2px): wrapperStyle
   marginBottom 8px when none is stored (sectionSeprator/index.tsx applies wrapperStyle to the separator's container).
3. A container holding only such a status button takes the button's condition (a hidden component keeps its wrapper
   size on 0.46, containers do not render at all when hidden). Part 2 is unconditional; parts 1 and 3 need the option.
Markers: /*reconciler:046-status-button*/, /*reconciler:046-separator-gap*/.
Options: statusLabelPattern (regex string, required for the status-button part, no default): matches the label code of a
status button; group 1 is the object the status is read from, an optional named group `prop` is the property (default
`status`).
"""
import re

from core.project import require
from core.tree import walk
from packs.v0_46.common import flush


def _pattern(ctx):
    """the compiled statusLabelPattern, or None when the option is unset (the status-button part is then a no-op)"""
    raw = ctx.opt('statusLabelPattern')
    if raw is None:
        return None
    require(isinstance(raw, str) and raw, 'option statusLabelPattern must be a non-empty regex string')
    try:
        rx = re.compile(raw)
    except re.error as e:
        require(False, f'option statusLabelPattern is not a valid regex: {e}')
    require(rx.groups >= 1, 'option statusLabelPattern needs a capture group 1 (the object the status is read from)')
    return rx


def status_button(c, notes, rx):
    if rx is None or c.get('type') != 'button':
        return 0
    lab = c.get('label')
    code = lab.get('_code') if isinstance(lab, dict) and lab.get('_mode') == 'code' else None
    m = rx.search(code or '')
    if not m:
        return 0
    v, h = c.get('visible'), c.get('hidden')
    if (isinstance(v, dict) and v.get('_mode') == 'code') or (isinstance(h, dict) and h.get('_mode') == 'code'):
        return 0
    if v is False or h is True:
        return 0
    prop = (m.groupdict().get('prop') if rx.groupindex.get('prop') else None) or 'status'
    c['visible'] = {'_mode': 'code', '_code': f'/*reconciler:046-status-button*/\nreturn data?.{m.group(1)}?.{prop} != null;', '_value': False}
    c.pop('hidden', None)
    notes.append(f'{c.get("componentName")}: visible only when {m.group(1)}.{prop} exists (0.43 hid it by throwing)')
    return 1


def separator_spacing(c, notes):
    if c.get('type') != 'sectionSeparator':
        return 0
    n = 0
    sb = (c.get('desktop') or {}).get('stylingBoxJson')
    if isinstance(sb, dict) and sb.get('marginBottom') == '8' and set(sb) <= {'_type', 'marginBottom'}:
        del c['desktop']['stylingBoxJson']      # an earlier approach: the separator ignores stylingBoxJson margins
        n += 1
    if not (c.get('wrapperStyle') or '').strip():
        c['wrapperStyle'] = "/*reconciler:046-separator-gap*/\nreturn { marginBottom: '8px' };"
        n += 1
    if n:
        notes.append(f'{c.get("componentName")}: separator bottom gap via wrapperStyle')
    return n


def lone_button_container(c, notes):
    if c.get('type') != 'container':
        return 0
    kids = c.get('components') or []
    if len(kids) != 1 or kids[0].get('type') != 'button':
        return 0
    v = kids[0].get('visible')
    if not (isinstance(v, dict) and '/*reconciler:046-status-button*/' in (v.get('_code') or '')):
        return 0
    cv = c.get('visible')
    if isinstance(cv, dict) and cv.get('_code') == v['_code']:
        return 0
    if (isinstance(cv, dict) and cv.get('_mode') == 'code') or isinstance(c.get('hidden'), dict):
        return 0
    c['visible'] = dict(v)
    c.pop('hidden', None)
    notes.append(f'{c.get("componentName")}: container takes its only status button\'s condition')
    return 1


def apply(ctx, markup):
    rx = _pattern(ctx)
    notes, n = [], 0
    for _ in range(2):   # a lone-button container qualifies once its button has been fixed in the same pass
        n += sum(status_button(c, notes, rx) + separator_spacing(c, notes) + lone_button_container(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
