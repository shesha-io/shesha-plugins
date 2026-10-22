"""Rule `carriers` (H3 / H6): htmlRender CSS carriers on 0.46, keeping the XSS sanitizer ON.

Symptom on 0.46: htmlRender components whose renderer starts with a <style> inject nothing and show the Empty placeholder
("Please, provide some content"); HTML built by htmlRenders (header bars, rows) shrinks to its content.
Cause: 0.46 sanitizes htmlRender output with DOMPurify by default (htmlRender/index.tsx) and DOMPurify drops a LEADING
<style> (the HTML parser hoists it into <head>); hidden components are not mounted; 0.46 also gives every htmlRender a
fit-content wrapper (getWrapperStyle), where 0.43 rendered a full-width block.
Writes: the carrier is made mounted (hidden false / visible true), contentType jsx when no static html is stored, and
the renderer is wrapped so its output is prefixed with '<span hidden></span>' (the <style> is then body content and is
kept); an empty output becomes the hidden span. The prefix also carries one rule restoring full width for htmlRenders
inside ITS OWN form ([data-sha-c-form-name="<module>/<name>"]), which is why the rule reads ctx.form.
Syntax-gated. Marker: /*reconciler:046-carrier*/ (and the opt-out /*reconciler:nonempty*/ already in a renderer).
Options: none.
"""
from core import gate
from core.tree import walk
from packs.v0_46.common import flush

MARK = '/*reconciler:046-carrier*/'


def is_carrier(c):
    return c.get('type') == 'htmlRender' and '<style' in (c.get('renderer') or '')


def _prefix(form):
    css = ''
    if form:
        css = ('<style>[data-sha-c-form-name="' + form + '"] [data-sha-c-type="htmlRender"]'
               '{width:100% !important;}</style>')
    return '<span hidden></span>' + css


def apply_component(c, notes, form=None):
    if not is_carrier(c):
        return 0
    n = 0
    if c.get('hidden') is True:
        c['hidden'] = False
        n += 1
    v = c.get('visible')
    if v is False or (isinstance(v, dict) and v.get('_mode') == 'value' and v.get('_value') is False):
        c['visible'] = True
        n += 1
    if c.get('contentType') == 'html' and not (c.get('html') or '').strip():
        c['contentType'] = 'jsx'
        n += 1
    r = c['renderer']
    if MARK not in r and '/*reconciler:nonempty*/' not in r:
        prefix = _prefix(form).replace('\\', '\\\\').replace("'", "\\'")
        c['renderer'] = (MARK + '\nconst __out = (() => {\n' + r + '\n})();\n'
                         "return '" + prefix + "' + ((typeof __out === 'string') ? __out : '');")
        n += 1
    if n:
        notes.append(f'{c.get("componentName")}: carrier mounted + style kept under the sanitizer')
    return n


def apply(ctx, markup):
    notes = []
    n = sum(apply_component(c, notes, form=ctx.form) or 0 for c, _, _ in walk(markup))
    if n:
        gate.require_clean([c['renderer'] for c, _, _ in walk(markup)
                            if c.get('type') == 'htmlRender' and MARK in (c.get('renderer') or '')], what='carrier renderer')
    flush(ctx, notes)
    return n
