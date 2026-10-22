"""Rule `afterload` (H44): a page-level form's `formSettings.onAfterDataLoad` gets only the id as `data` on 0.46.

Symptom on 0.46: after-load handlers that read record fields from `data` get undefined, throw part-way and skip the rest
of the handler (page state / global state never set, totals show 0).
Cause: 0.46 passes as `data` only the initial values (the id from the URL); the loaded record is `form.data`. 0.43 passed
the loaded record. Sub-form after-load scripts behave the same on both versions. Fixed in 0.46.1 per its release notes
(not verified).
Writes: the original handler runs with `data` bound to `form.data` exactly when `data` holds nothing but the id and
`form.data` holds more (the 0.46 symptom); otherwise it runs unchanged. Only handlers that read record fields through
`data` are wrapped; handlers that write into `data` are reported (INFO) and left alone. Syntax-gated: a wrapper that does
not parse is skipped.
Marker: /*reconciler:046-afterload-data*/ (`retire` restores the original handler).  Options: none.
"""
import re

from core import gate

MARK = '/*reconciler:046-afterload-data*/'
READ = re.compile(r'(?<![\w$.?])data\s*\??\.\s*([A-Za-z_$][\w$]*)')
WRITE = re.compile(r'(?<![\w$.?])data\s*(\.\s*[A-Za-z_$][\w$]*|\[[^\]]+\])\s*(=(?!=)|\+=|-=)|(?<![\w$.?])delete\s+data\b')
_BODY_HEAD = 'return (async (data) => {\n'
_BODY_TAIL = '\n})(__d046);'


def _strip_comments(code):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', code, flags=re.S)


def wrap(code):
    return (f'{MARK}\n// 0.46 passes only the initial values (the id) as `data` to onAfterDataLoad; the loaded record is\n'
            f'// form.data (0.43 passed the loaded record). When `data` holds nothing but the id and form.data holds more,\n'
            f'// run the handler with `data` = the loaded record; otherwise it runs unchanged (H44).\n'
            f'const __d046 = (typeof form !== "undefined" && form && form.data && typeof form.data === "object"\n'
            f'    && Object.keys(data || {{}}).filter(k => k !== "id").length === 0\n'
            f'    && Object.keys(form.data).filter(k => k !== "id").length > 0) ? form.data : data;\n'
            f'{_BODY_HEAD}{code}{_BODY_TAIL}')


def unwrap(code):
    """the original handler of a wrapped onAfterDataLoad, or None"""
    if not code.startswith(MARK) or _BODY_HEAD not in code or not code.endswith(_BODY_TAIL):
        return None
    return code[code.index(_BODY_HEAD) + len(_BODY_HEAD):-len(_BODY_TAIL)]


def apply(ctx, markup):
    fs = markup.get('formSettings') or {}
    code = fs.get('onAfterDataLoad')
    if not isinstance(code, str) or not code.strip() or MARK in code:
        return 0
    bare = _strip_comments(code)
    reads = {m.group(1) for m in READ.finditer(bare)} - {'id'}
    if not reads:
        return 0
    if WRITE.search(bare):
        ctx.info('onAfterDataLoad writes into `data` - not wrapped, review by hand (H44)')
        return 0
    new = wrap(code)
    if gate.syntax_errors([new]):
        return 0
    fs['onAfterDataLoad'] = new
    ctx.note(f'onAfterDataLoad reads the loaded record (form.data) - {", ".join(sorted(reads))[:120]} (H44)')
    return 1


def retire(ctx, markup):
    fs = markup.get('formSettings') or {}
    code = fs.get('onAfterDataLoad')
    if not isinstance(code, str):
        return 0
    orig = unwrap(code)
    if orig is None:
        return 0
    fs['onAfterDataLoad'] = orig
    ctx.note('onAfterDataLoad wrapper removed (H44)')
    return 1
