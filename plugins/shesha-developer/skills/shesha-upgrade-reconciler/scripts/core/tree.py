"""Markup tree helpers shared by every rule and tool (one walker instead of one per script)."""
import re

from core.project import require

DEVICES = ('desktop', 'tablet', 'mobile')


def is_component(o):
    return isinstance(o, dict) and 'type' in o and 'id' in o


def walk(o):
    """yield (component, parent_list, index) for every component dict in the markup tree (depth first, document order)."""
    if isinstance(o, list):
        for i, v in enumerate(o):
            if is_component(v):
                yield v, o, i
            yield from walk(v)
    elif isinstance(o, dict):
        for v in o.values():
            if isinstance(v, (list, dict)):
                yield from walk(v)


def walk_dicts(o):
    """yield every dict in the tree (components, tab items, button-group items, settings blocks)."""
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk_dicts(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_dicts(v)


def with_depth(o, d=0, parent=None):
    """yield (depth, component, parent_component)."""
    if isinstance(o, dict):
        if is_component(o):
            yield d, o, parent
            parent, d = o, d + 1
        for v in o.values():
            yield from with_depth(v, d, parent)
    elif isinstance(o, list):
        for v in o:
            yield from with_depth(v, d, parent)


def one(markup, cid, ctype=None, cname=None):
    """The single (component, parent_list, index) with this id; refuses unless exactly one matches (an anchor)."""
    hits = [(c, pl, i) for c, pl, i in walk(markup) if c['id'] == cid]
    require(len(hits) == 1, f'anchor {cid}: {len(hits)} hits')
    c = hits[0][0]
    if ctype:
        require(c['type'] == ctype, f'anchor {cid}: type {c["type"]} != {ctype}')
    if cname:
        require(c.get('componentName') == cname, f'anchor {cid}: name {c.get("componentName")} != {cname}')
    return hits[0]


def device_blocks(c):
    """the component itself plus each device block it has (settings may live at either level)."""
    return [c] + [c[d] for d in DEVICES if isinstance(c.get(d), dict)]


def code_of(setting):
    """the JS body of a {_mode:'code', _code} setting, or None"""
    if isinstance(setting, dict) and setting.get('_mode') == 'code' and (setting.get('_code') or '').strip():
        return setting['_code']
    return None


def statically_hidden(c):
    """hidden by a constant setting (visible false / hidden true), not by an expression"""
    v, h = c.get('visible'), c.get('hidden')
    if v is False or h is True:
        return True
    if isinstance(v, dict) and v.get('_mode') == 'value' and v.get('_value') is False:
        return True
    if isinstance(h, dict) and h.get('_mode') == 'value' and h.get('_value') is True:
        return True
    return False


def strip_comments(code):
    return re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', code or '', flags=re.S))


def camel(name):
    return name[:1].lower() + name[1:] if name else name


def form_refs(markup):
    """every {module, name} form reference a markup holds (subForm / dataList / list item / dialog forms)."""
    out = set()
    for c, _, _ in walk(markup):
        for key in ('formId', 'itemFormId', 'createFormId', 'formSelectionMode'):
            f = c.get(key)
            if isinstance(f, dict) and f.get('name'):
                out.add(f"{f.get('module')}/{f['name']}")
    return out
