"""Rule `optfilter` (H34): an optional filter item that does not resolve is sent as `null`, so the table loads nothing.

Symptom on 0.46: a table shows no rows; Entities/GetAll answers 400 ("The binary operator AndAlso is not defined for the
types 'System.Boolean' and 'System.Object'").
Cause: on 0.46 an `and`/`or` filter item whose `evaluate` is optional (`required: false`) and does not resolve is left in
the array as `undefined`; JSON turns it into `null`. 0.43 dropped the item.
Writes: the optional item is dropped when a REQUIRED sibling compares the same variable (the common "required value +
optional fallback on the same field" shape; identical to 0.43 whenever the fallback is unresolved or equal). Any optional
item without such a sibling is reported (REVIEW), not changed.
Marker: none. No retire: the dropped item is not stored anywhere, so the change cannot be undone from the markup (and the
0.46.1 release notes claim the framework now drops unresolved optional items itself, so nothing needs to be undone).
Options: none.
"""
from core.tree import walk
from packs.v0_46.common import flush


def _eval(n):
    """(var, required) for {"==": [{"var": v}, {"evaluate": [{... "required": r}]}]}, else None."""
    if not isinstance(n, dict) or list(n) != ['==']:
        return None
    args = n['==']
    if not (isinstance(args, list) and len(args) == 2 and isinstance(args[0], dict) and 'var' in args[0]):
        return None
    ev = args[1].get('evaluate') if isinstance(args[1], dict) else None
    if not (isinstance(ev, list) and len(ev) == 1 and isinstance(ev[0], dict) and 'expression' in ev[0]):
        return None
    return args[0]['var'], ev[0].get('required') is True


def _has_optional(n):
    if isinstance(n, dict):
        ev = n.get('evaluate')
        if isinstance(ev, list) and ev and isinstance(ev[0], dict) and ev[0].get('required') is not True:
            return True
        return any(_has_optional(v) for v in n.values())
    if isinstance(n, list):
        return any(_has_optional(v) for v in n)
    return False


def fix_filter(f, where, notes):
    changed = 0
    if isinstance(f, dict):
        for op in ('and', 'or'):
            items = f.get(op)
            if not (isinstance(items, list) and len(items) > 1):
                continue
            required_vars = {e[0] for e in map(_eval, items) if e and e[1]}
            keep = []
            for it in items:
                e = _eval(it)
                if e and not e[1] and e[0] in required_vars:
                    changed += 1
                    notes.append(f'{where}: dropped optional fallback on `{e[0]}`')
                    continue
                if _has_optional(it) and not (e and e[1]):
                    notes.append(f'INFO REVIEW {where}: optional filter item kept: {str(it)[:120]}')
                keep.append(it)
            f[op] = keep
        for k, v in f.items():
            if k != '_value':
                changed += fix_filter(v, where, notes)
    elif isinstance(f, list):
        for v in f:
            changed += fix_filter(v, where, notes)
    return changed


def apply_component(c, notes):
    pf = c.get('permanentFilter')
    if not isinstance(pf, dict):
        return 0
    return fix_filter(pf, f'{c.get("componentName") or c.get("propertyName") or c.get("id")}.permanentFilter', notes)


def apply(ctx, markup):
    notes = []
    n = sum(apply_component(c, notes) for c, _, _ in walk(markup))
    flush(ctx, notes)
    return n
