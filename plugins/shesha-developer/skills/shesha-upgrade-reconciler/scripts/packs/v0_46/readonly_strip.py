"""Rule `readonly_strip` (H42, targeted): the 0.46 dynamic CRUD rejects READ-ONLY (calculated) properties in a create/update payload.

Symptom on 0.46: a save fails with "Your request is not valid! Property 'total' is readonly." where 0.43 ignored the
value. Forms that display a calculated value, or host a subform whose entity is updated in cascade, post it.
Writes: the form's `onPrepareSubmitData` deletes every property the entity metadata marks `readonly` - on the form's
model and, for entity references updated in cascade (`cascadeUpdate`), under that reference - before `return data;`.
Deleting an absent key is a no-op; read-only values were never stored by 0.43 either. Only forms that submit through the
default dynamic CRUD endpoints qualify. The block is regenerated in place between its markers, so it is idempotent.
Metadata (Metadata/Get) is fetched lazily through ctx.api() and cached per entity type; offline tests pre-seed
`session._cache['metadata:<entityType>']` (see metadata.py). The nested entity type is resolved from the property's short
type name by trying `<module>.Domain.<Type>`, `<module>.Domain.<Type>s.<Type>`, each pattern of the option, then the bare name.
Marker: /*reconciler:046-readonly-strip*/ ... /*end:046-readonly-strip*/.  No retire: the block removes only values the
backend rejects anyway.
Options: entityNamespacePatterns (extra type-name patterns tried after the two built-in ones, with {module} and {type}
placeholders, e.g. "{module}.Domain.Sales.{type}"; optional).
Run with `apply --rules readonly_strip --only form,...`.
"""
import json
import re

from core.project import require
from core.tree import camel, walk_dicts
from packs.v0_46 import metadata
from packs.v0_46.common import flush

MARK = '/*reconciler:046-readonly-strip*/'
END = '/*end:046-readonly-strip*/'


def _patterns(ctx):
    extra = ctx.opt('entityNamespacePatterns') or []
    require(isinstance(extra, list) and all(isinstance(x, str) and '{type}' in x for x in extra),
            'option entityNamespacePatterns must be a list of patterns containing {type} (and optionally {module})')
    return ['{module}.Domain.{type}', '{module}.Domain.{type}s.{type}'] + extra


def resolve(ctx, short, module):
    for pat in _patterns(ctx) + ['{type}']:
        cand = pat.format(module=module, type=short)
        if metadata.properties(ctx, cand):
            return cand
    return None


def strip_block(ctx, model):
    props = metadata.properties(ctx, model)
    if not props:
        return None
    top = sorted(camel(p['path']) for p in props if p.get('readonly'))
    nested = {}
    for p in props:
        if p.get('dataType') == 'entity' and p.get('cascadeUpdate') and p.get('entityType'):
            et = resolve(ctx, p['entityType'], p.get('entityModule') or '')
            sub = metadata.properties(ctx, et) if et else None
            ro = sorted(camel(x['path']) for x in (sub or []) if x.get('readonly'))
            if ro:
                nested[camel(p['path'])] = ro
    if not top and not nested:
        return None
    lines = [MARK, '// 0.46 CRUD rejects read-only (calculated) properties that 0.43 ignored - strip them before submit (H42).']
    if top:
        lines.append('for (const __k of ' + json.dumps(top) + ') { if (data && __k in data) delete data[__k]; }')
    for ref, ro in nested.items():
        lines.append(f'if (data && data.{ref} && typeof data.{ref} === "object") {{ for (const __k of {json.dumps(ro)}) {{ delete data.{ref}[__k]; }} }}')
    lines.append(END)
    return '\n'.join(lines)


def apply(ctx, markup):
    fs = markup.get('formSettings') or {}
    model = fs.get('modelType')
    if not isinstance(model, str) or not model:
        return 0
    # only forms that submit through the default dynamic CRUD endpoints (a custom endpoint may accept these values)
    if fs.get('dataSubmitterType') not in (None, 'gql'):
        return 0
    gql = (fs.get('dataSubmittersSettings') or {}).get('gql') or {}
    if gql.get('endpointType') not in (None, 'default'):
        return 0
    block = strip_block(ctx, model)
    if not block:
        return 0
    markup.setdefault('formSettings', fs)
    code = fs.get('onPrepareSubmitData') or ''
    if MARK in code:
        old = code[code.index(MARK):code.index(END) + len(END)]
        if old == block:
            return 0
        fs['onPrepareSubmitData'] = code.replace(old, block)
        ctx.note('read-only strip refreshed')
        return 1
    if code.strip():
        rets = [m.start() for m in re.finditer(r'return\s+data\s*;\s*$', code.rstrip(), re.M)]
        if not rets:
            ctx.info('onPrepareSubmitData has an unknown shape (no trailing `return data;`): read-only strip not added, review by hand')
            return 0
        i = rets[-1]
        fs['onPrepareSubmitData'] = code[:i] + block + '\n' + code[i:]
    else:
        fs['onPrepareSubmitData'] = block + '\nreturn data;'
    ctx.note(f'onPrepareSubmitData strips read-only properties of {model.split(".")[-1]} (H42)')
    return 1
