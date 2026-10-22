"""Rule `types` (H32): 0.43 framework entity type names -> their 0.46 names.

Symptom on 0.46: lookups come back blank; Metadata/Get answers 404 and Entities/GetAll 500 for the old type names.
Cause: 0.46 renamed framework entity types (the map below is framework knowledge).
Writes: every string setting containing an old type name has it replaced by the new one, anywhere in the markup.
Marker: none (idempotent: the new names do not contain the old ones).
Options: typeMapExtra ({"Old.Full.TypeName": "New.Full.TypeName"}) adds project entries to the built-in map.
"""
from core.project import require
from packs.v0_46.common import flush

TYPE_MAP = {'Shesha.Domain.ConfigurationItems.Module': 'Shesha.Domain.Module',
            'Shesha.Framework.ConfigurableComponent': 'Shesha.Domain.FormConfiguration'}


def _map(ctx):
    extra = ctx.opt('typeMapExtra') or {}
    require(isinstance(extra, dict) and all(isinstance(k, str) and k and isinstance(v, str) for k, v in extra.items()),
            'option typeMapExtra must be an object {"Old.Type": "New.Type"}')
    for k, v in extra.items():
        require(k not in v, f'typeMapExtra entry {k!r}: the new name contains the old one, the rule could never settle')
    return {**TYPE_MAP, **extra}


def apply(ctx, markup):
    tmap = _map(ctx)
    n, notes = 0, []

    def rec(o):
        nonlocal n
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and any(a in v for a in tmap):
                    nv = v
                    for a, b in tmap.items():
                        nv = nv.replace(a, b)
                    o[k] = nv
                    n += 1
                    notes.append(f'{o.get("componentName") or "?"}.{k}: 0.46 entity type {nv[:50]}')
                else:
                    rec(v)
        elif isinstance(o, list):
            for x in o:
                rec(x)
    rec(markup)
    flush(ctx, notes)
    return n
