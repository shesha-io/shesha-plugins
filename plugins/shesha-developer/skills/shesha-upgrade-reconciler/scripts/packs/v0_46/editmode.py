"""Rule `editmode` (H15): an `editMode` script returning anything other than 'editable' | 'readOnly' | 'disabled' |
'inherited' renders the component DISABLED on 0.46.

Symptom on 0.46: fields stay disabled after Edit is pressed; a read-only button stays clickable.
Cause: 0.43 read `true` / 'edit' as editable and `false` / 'readonly' as read-only; 0.46 accepts only the four values
above. Buttons: 0.46 maps 'readOnly' to {disabled:false, readOnly:true} and a button only honours `disabled`, so a
read-only button became clickable (0.43 rendered it disabled).
Writes: a script that can return a non-canonical value is wrapped so its result is mapped back to the 0.43 meaning;
canonical values pass through untouched. Scripts whose every `return` is a canonical literal (or a ternary of them) are
left alone. For buttons (button components, button-group items) 'readOnly' / false map to 'disabled', and a static
'readOnly' editMode becomes 'disabled'. Applies to every dict carrying an editMode: components, button-group items and
tab items.
Marker: /*reconciler:046-editmode*/ (`retire` unwraps the script; a static button 'readOnly' -> 'disabled' change has no
marker and is not reverted).
Options: none.  Fixed in 0.46.1 per its release notes (not verified).
"""
import re

from packs.v0_46.common import edit_mode_dicts, flush

MARK = '/*reconciler:046-editmode*/'
VALID = ('editable', 'readOnly', 'disabled', 'inherited')
LIT = r"""(?:'(?:%s)'|"(?:%s)")""" % ('|'.join(VALID), '|'.join(VALID))
CANON_EXPR = re.compile(r'^\s*(?:%s|[^?;]+\?\s*%s\s*:\s*%s)\s*;?\s*$' % (LIT, LIT, LIT), re.S)
RO_LINE = "if (__em === false || __em === 'readonly' || __em === 'read-only' || __em === 'ReadOnly') return 'readOnly';"
RO_LINE_BUTTON = ("if (__em === false || __em === 'readonly' || __em === 'read-only' || __em === 'ReadOnly' || __em === 'readOnly') "
                  "return 'disabled';")
_HEAD = MARK + '\nconst __em = (() => {\n'
_TAIL = "\n})();\nif (__em === true || __em === 'edit' || __em === 'Edit') return 'editable';\n"


def _strip(code):
    return re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', code, flags=re.S))


def needs_wrap(code):
    body = _strip(code)
    rets = re.findall(r'\breturn\b([^;\n]*)', body)
    if not rets:
        return False
    return any(not CANON_EXPR.match(r) for r in rets)


def wrap(code, button=False):
    return (f"{_HEAD}{code}{_TAIL}"
            f"{RO_LINE_BUTTON if button else RO_LINE}\n"
            "return __em;")


def unwrap(code):
    """the original script of a wrapped editMode, or None when `code` is not a wrapper"""
    if not code.startswith(_HEAD) or _TAIL not in code:
        return None
    return code[len(_HEAD):code.rindex(_TAIL)]


def is_button(c):
    return c.get('type') == 'button' or (c.get('itemType') == 'item' and ('buttonType' in c or 'actionConfiguration' in c))


def apply_dict(c, notes):
    """c: any dict carrying an `editMode` (components, button-group items and tab items)."""
    em, button = c.get('editMode'), is_button(c)
    name = c.get('componentName') or c.get('label') or c.get('title') or c.get('id')
    if button and em == 'readOnly':
        c['editMode'] = 'disabled'
        notes.append(f'{name}: read-only button -> disabled (H15)')
        return 1
    if not (isinstance(em, dict) and em.get('_mode') == 'code' and isinstance(em.get('_code'), str) and em['_code'].strip()):
        return 0
    code = em['_code']
    if MARK in code:   # already wrapped; a button wrapped before the button mapping existed gets its read-only line upgraded
        if button and RO_LINE in code:
            em['_code'] = code.replace(RO_LINE, RO_LINE_BUTTON)
            notes.append(f'{name}: wrapped button editMode upgraded (read-only -> disabled) (H15)')
            return 1
        return 0
    if not (needs_wrap(code) or (button and re.search(r"""['"]readOnly['"]""", _strip(code)))):
        return 0
    em['_code'] = wrap(code, button)
    notes.append(f'{name}: editMode result mapped to 0.46 values{" (button: read-only -> disabled)" if button else ""} (H15)')
    return 1


def apply(ctx, markup):
    notes, n = [], 0
    for d in edit_mode_dicts(markup):
        n += apply_dict(d, notes)
    flush(ctx, notes)
    return n


def retire(ctx, markup):
    n = 0
    for d in edit_mode_dicts(markup):
        em = d.get('editMode')
        if isinstance(em, dict) and isinstance(em.get('_code'), str):
            orig = unwrap(em['_code'])
            if orig is not None:
                em['_code'] = orig
                n += 1
                ctx.note(f'{d.get("componentName") or d.get("label") or d.get("title") or d.get("id")}: editMode wrapper removed (H15)')
    return n
