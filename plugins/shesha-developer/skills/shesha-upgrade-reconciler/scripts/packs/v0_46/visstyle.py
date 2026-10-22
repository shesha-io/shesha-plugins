"""Rule `textvis` (H19, TEMPORARY WORKAROUND): conditional `text` components ignore hidden / visible on 0.46.

Symptom on 0.46: texts that should be conditional (hints, notes, "this field is required") always show.
Cause: `text` neither renders through ConfigurableFormItem (configurableFormItemLive.tsx) nor checks model.hidden in its
Factory, so visible {_mode:'value',_value:false}, a visible code returning false and hidden:true all leave it on screen.
(collapsiblePanel honours visible and is excluded.)
Writes: keeps the visibility setting untouched and ALSO drives `display:none` from the same expression through the
component's evaluated `style` (root and each device block that stores a style; genericText.tsx applies model.styleCss).
The original style is preserved inside the wrapper; `retire` unwraps it. Syntax-gated.
Marker: /*reconciler:046-visibility-style*/.  Options: none.
Remove once the framework enforces visibility for texts (fixed in 0.46.1 per its release notes, not verified).
"""
import re

from core import gate
from core.tree import walk
from packs.v0_46.common import flush

MARK = '/*reconciler:046-visibility-style*/'
TYPES = {'text'}   # collapsiblePanel honours visible; KeyInformationBar untested


def visibility_code(c):
    """JS function body returning the component's VISIBLE boolean, or None if it has no visibility condition."""
    v, h = c.get('visible'), c.get('hidden')
    if isinstance(v, dict) and v.get('_mode') == 'code' and (v.get('_code') or '').strip():
        return v['_code']
    if isinstance(v, dict) and v.get('_mode') == 'value' and v.get('_value') is False:
        return 'return false;'
    if v is False:
        return 'return false;'
    if isinstance(h, dict) and h.get('_mode') == 'code' and (h.get('_code') or '').strip():
        return 'return !(() => {\n' + h['_code'] + '\n})();'
    if (isinstance(h, dict) and h.get('_mode') == 'value' and h.get('_value') is True) or h is True:
        return 'return false;'
    return None


def wrap(base_style, vis_code):
    base = base_style if isinstance(base_style, str) and base_style.strip() else 'return {};'
    return (MARK + '\n'
            'const __vis = (() => {\n' + vis_code + '\n})();\n'
            'const __base = (() => {\n' + base + '\n})() || {};\n'
            "return __vis === false ? Object.assign({}, __base, { display: 'none' }) : __base;")


def unwrap(style):
    m = re.search(r"const __base = \(\(\) => \{\n(.*)\n\}\)\(\) \|\| \{\};\nreturn __vis", style, re.S)
    if not m:
        return style
    inner = m.group(1)
    return None if inner == 'return {};' else inner


def _holders(c):
    return [c] + [c[d] for d in ('desktop', 'tablet', 'mobile') if isinstance(c.get(d), dict) and 'style' in c[d]]


def apply_component(c, notes):
    """Mutates component c. Returns the number of style holders changed."""
    if c.get('type') not in TYPES:
        return 0
    vc = visibility_code(c)
    if vc is None:
        return 0
    n = 0
    for h in _holders(c):
        cur = h.get('style')
        if isinstance(cur, str) and cur.startswith(MARK):
            # refresh if the visibility expression changed since it was wrapped
            new = wrap(unwrap(cur), vc)
            if new == cur:
                continue
        else:
            new = wrap(cur, vc)
        h['style'] = new
        n += 1
    if n:
        notes.append(f'{c.get("componentName")}: visibility enforced via style ({n} holder(s))')
    return n


def _styles(c):
    return [h['style'] for h in [c] + [c[d] for d in ('desktop', 'tablet', 'mobile') if isinstance(c.get(d), dict)]
            if isinstance(h.get('style'), str) and MARK in h['style']]


def apply(ctx, markup):
    notes, n = [], 0
    for c, _, _ in walk(markup):
        n += apply_component(c, notes) or 0
    if n:
        gate.require_clean([s for c, _, _ in walk(markup) for s in _styles(c)], what='visibility-style wrap')
    flush(ctx, notes)
    return n


def retire(ctx, markup):
    """Undo apply: restore each wrapped style (an originally absent style key is removed from the component root, and
    set to null in a device block, which is where apply found it)."""
    n = 0
    for c, _, _ in walk(markup):
        if c.get('type') not in TYPES:
            continue
        for h in [c] + [c[d] for d in ('desktop', 'tablet', 'mobile') if isinstance(c.get(d), dict)]:
            cur = h.get('style')
            if isinstance(cur, str) and cur.startswith(MARK):
                orig = unwrap(cur)
                if orig is None and h is c:
                    del h['style']
                else:
                    h['style'] = orig
                n += 1
                ctx.note(f'{c.get("componentName")}: visibility-style wrapper removed')
    return n
