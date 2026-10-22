"""Rule `formref` (H45): subForms naming a framework form that 0.46 no longer ships.

Symptom on 0.46: the subForm renders an empty box ("form <Module>/<name> not found").
Cause: a form shipped by the 0.43 framework modules is absent on 0.46. Which project form replaces it is a project
decision (verify that the copy has the same components), so the replacement map is an option and the rule is a no-op
without it.
Writes: `formId` of a subForm naming a mapped form is pointed at its replacement (module and name replaced, other keys kept).
Marker: none (idempotent: the old name is gone).
Options: formRefMap (list of {"from": "Module/name", "to": "Module/name"}; empty = no-op).
"""
from core.project import require
from core.tree import walk
from packs.v0_46.common import flush


def _pairs(ctx):
    raw = ctx.opt('formRefMap') or []
    require(isinstance(raw, list), 'option formRefMap must be a list of {"from": "Module/name", "to": "Module/name"}')
    out = {}
    for e in raw:
        require(isinstance(e, dict) and isinstance(e.get('from'), str) and isinstance(e.get('to'), str)
                and '/' in e['from'] and '/' in e['to'], f'option formRefMap entry {e!r}: need "from" and "to" as "Module/name"')
        out[tuple(e['from'].split('/', 1))] = tuple(e['to'].split('/', 1))
    return out


def apply(ctx, markup):
    fmap = _pairs(ctx)
    if not fmap:
        return 0
    n, notes = 0, []
    for c, _, _ in walk(markup):
        f = c.get('formId')
        if isinstance(f, dict) and (f.get('module'), f.get('name')) in fmap:
            mod, name = fmap[(f['module'], f['name'])]
            notes.append(f'{c.get("componentName")}: form {f["module"]}/{f["name"]} (not shipped by 0.46) -> {mod}/{name} (H45)')
            c['formId'] = {**f, 'module': mod, 'name': name}
            n += 1
    flush(ctx, notes)
    return n
