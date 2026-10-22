"""Static, read-only detectors for markup traps that survive a Shesha upgrade. Run BEFORE and AFTER every merge-reconcile.

  shrec.py detect --markup <file.json | dir> [--checks a,b] [--context dir] [--hosted n,n] [--rows n,n] [--nested n,n]
  shrec.py detect --role local|deployed|reference [--only form,form] [--module A,B|all] [--checks a,b]
  shrec.py detect --selftest

One line per finding: `form | component | check | severity | evidence`, then a summary. Exit code 1 when there is any finding, 0 when clean.
Reads files or does GET requests only; it never writes and never edits markup. --markup takes a raw markup file, a stored row
({"markup": "<json>"}), a push backup wrapper ({"row": {...}}) or a directory of them. With --role the modules reported on are the
project's (project.json "modules"), or --module A,B / all; every form of the role still feeds the embedded-form index.

severity: trap   = the mechanism is proven on 0.46 (hazards H47, H49-H52): fix it
          review = a heuristic: look at it, it may be fine

Hazards covered by the built-in checks (check id: hazard):
  parent-id               H47 trap    a component's parentId names no container that holds it (the 0.46 designer re-nests it on the next save).
                                      A component with no parentId is not reported. When the active rule pack ships a parentId rule `shrec.py plan`
                                      lists it; otherwise correct the parentId by hand.
  url-endpoint-query      H50         datatableContext/dataContext with sourceType Url whose endpoint (string or code) carries filter=, sorting=
                                      or properties=: 0.46 DROPS the query text and rebuilds those from the context settings. trap when it is a generic
                                      list endpoint (Crud/GetAll, Entities/GetAll) carrying filter= and the context has NO permanentFilter (every row
                                      shows: data leak); review otherwise (a permanentFilter beside it, sorting/properties only, a custom endpoint).
  subform-script-scope    H49 review  a sub-form NESTED two deep (or named with --hosted/--nested) has an event script (Execute Script expression,
                                      on<Event> handler) reading data.<own field> (`id` excluded, aliases like `var d = data` followed) or any script
                                      calling form.getFieldValue/setFieldsValue/getFormData: there `data`/`form` are the HOST page form (silently empty
                                      read / write to the host).
  hidden-row-field        H52         in a datalist row form: a bound input with hidden:true, or a bound input nested in a zero-height holder container:
                                      neither is mounted, the row's data keeps only id + <sortField>. trap when a row script reads data.<field>,
                                      review when nothing reads it.
  required-mustache-subform H51 review a required:true {{data.*}} / {{pageContext.*}} mustache in a permanentFilter of a form embedded TWO deep
                                      (sub-form of a sub-form): it did not resolve in that nesting (no request, empty list). {{page.state.<id>}} did.

Sibling detectors (check `scan-hazards`, severity review, finding id `scan-H<n>`): when the shesha-developer-0-46 plugin is found, its
scan-hazards.mjs markup detectors H1 and H3-H18 are run over the same forms (Node 18+ needed). Looked up in $SHREC_SCAN_HAZARDS, then
<this skill>/../../../shesha-developer-0-46/skills/shesha-form-edit/scripts/ (repository checkout), then
<this skill>/../../../../shesha-developer-0-46/<version>/skills/shesha-form-edit/scripts/ (plugin cache). When it is absent one line
says so and the run continues. A finding is a hypothesis: confirm it in the browser before rewriting a working form.

Embedded / row / nested forms are learned from the forms given (subForm/datalist/list/childTable `formId`). Give the HOSTING forms too (or a
--context dir, only read to learn who embeds whom), or name them with --hosted / --rows / --nested; without them the host-dependent checks have
nothing to look at and the run says so.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHECKS = ('parent-id', 'url-endpoint-query', 'subform-script-scope', 'hidden-row-field', 'required-mustache-subform')
SCAN = 'scan-hazards'
ALL_CHECKS = CHECKS + (SCAN,)
HOST_CHECKS = ('subform-script-scope', 'hidden-row-field', 'required-mustache-subform')
EMBED_TYPES = {'subForm', 'datalist', 'list', 'childTable'}   # components that render another form INSIDE the page
ROW_TYPES = {'datalist', 'list'}                              # ... as a per-item row
FORM_KEYS = ('formId', 'itemFormId')
# types that never hold a bound input value
NOT_INPUT = {'container', 'htmlRender', 'text', 'columns', 'sizableColumns', 'tabs', 'collapsiblePanel', 'card', 'buttonGroup', 'button', 'datatableContext',
             'dataContext', 'subForm', 'datalist', 'list', 'datatable', 'sectionSeparator', 'alert', 'image', 'wizard', 'childTable', 'kanban',
             'toolbar', 'chevron', 'attachmentsEditor', 'dynamicView', 'iframe', 'link', 'divider', 'title', 'statistic'}
URL_QUERY_RE = re.compile(r'(?<![A-Za-z0-9_])(filter|sorting|properties)=')
GENERIC_LIST_RE = re.compile(r'/(?:Crud|Entities)/GetAll\b', re.I)
DATA_ALIAS_RE = re.compile(r'\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*\(?\s*data\b')
DATA_DESTRUCT_RE = re.compile(r'\b(?:var|let|const)\s*\{([^}]*)\}\s*=\s*\(?\s*data\b')


def data_reads(txt):
    """names of the `data` properties a script reads: data.x, data?.x, data['x'], through an alias (`var d = data || {}; d.x`) or by destructuring."""
    names, reads = {'data'}, set()
    names.update(m.group(1) for m in DATA_ALIAS_RE.finditer(txt))
    for m in DATA_DESTRUCT_RE.finditer(txt):
        reads.update(re.split(r'\s*[:=]', p.strip())[0] for p in m.group(1).split(',') if p.strip())
    for n in names:
        q = re.escape(n)
        reads.update(m.group(1) for m in re.finditer(r'(?<![\w$.])' + q + r'\s*(?:\?\.|\.)\s*([A-Za-z_$][\w$]*)', txt))
        reads.update(m.group(1) for m in re.finditer(r'(?<![\w$.])' + q + r'\s*\??\.?\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]', txt))
    return reads
FORM_CALL_RE = re.compile(r'(?<![\w$.])form\s*(?:\?\.|\.)\s*(getFieldValue|getFieldsValue|setFieldsValue|setFieldValue|getFormData|setFormData)\b\s*\(?\s*([\'"][^\'"]*[\'"])?')
HOST_MUSTACHE_RE = re.compile(r'\{\{\s*((?:data|pageContext)\s*\.[^}]*?)\s*\}\}')
BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)
LINE_COMMENT_RE = re.compile(r'(?m)^[ \t]*//.*$')


# ------------------------------------------------------------------ loading
def _unwrap(d):
    """raw markup / stored row / push backup wrapper -> (markup dict | None, module | None, name | None)"""
    module = name = None
    for _ in range(3):
        if not isinstance(d, dict):
            return None, module, name
        m = d.get('module')
        module = module or (m.get('name') if isinstance(m, dict) else m if isinstance(m, str) else None)
        name = name or (d.get('name') if isinstance(d.get('name'), str) else None)
        if isinstance(d.get('row'), dict) and 'markup' in d['row']:
            d = d['row']
            continue
        if 'markup' in d:
            mk = d['markup']
            if isinstance(mk, str):
                try:
                    mk = json.loads(mk)
                except ValueError:
                    return None, module, name
            return (mk if isinstance(mk, dict) and 'components' in mk else None), module, name
        break
    return (d if isinstance(d, dict) and isinstance(d.get('components'), list) else None), module, name


def _name_from_path(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    mod = None
    if '__' in stem:
        mod, stem = stem.split('__', 1)
    stem = re.sub(r'\.\d{6,}$', '', stem)        # push backup stamp
    return mod, stem


def load_path(path):
    """-> {display id: {'module', 'name', 'markup'}} for a file or a directory (recursive). Non-form json files are skipped."""
    files = [path] if os.path.isfile(path) else sorted(glob.glob(os.path.join(path, '**', '*.json'), recursive=True))
    base = os.path.dirname(path) if os.path.isfile(path) else path
    out = {}
    for f in files:
        try:
            with open(f, encoding='utf-8-sig') as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            continue
        mk, module, name = _unwrap(raw)
        if mk is None:
            continue
        pm, pn = _name_from_path(f)
        parent = os.path.basename(os.path.dirname(f))
        out[os.path.relpath(f, base).replace('\\', '/')[:-5]] = {'module': module or pm or (parent if '.' in parent else None), 'name': name or pn, 'markup': mk}
    return out


def load_role(role):
    """GET-only: every form of one role {display id: {'module', 'name', 'markup'}}. Needs the project configuration and credentials."""
    from core.api import fetch_forms, modname
    _, items = fetch_forms(role)
    out = {}
    for i in items:
        mk = i.get('markup') or '{}'
        try:
            mk = json.loads(mk) if isinstance(mk, str) else mk
        except ValueError:
            continue
        if not isinstance(mk, dict) or 'components' not in mk:
            continue
        mod = (modname(i) or '').strip()
        out[f'{mod}/{i["name"].strip()}'] = {'module': mod, 'name': i['name'].strip(), 'markup': mk}
    return out


# ------------------------------------------------------------------ parentId analysis (H47)
# Every component's parentId must name the container that really holds it in the markup tree. 0.43 renders by NESTING and ignores
# `parentId`; the 0.46 designer rebuilds the tree from `parentId` the moment someone opens and saves the form. What counts as "the holder":
#   - the markup root holds its children as parentId 'root';
#   - any `components` list belongs to the nearest enclosing dict that has an `id`: a component, a tab pane (`tabs[]`), a column
#     (`columns[]`), a wizard step or a panel part (`header` / `content` / `customHeader`);
#   - collapsiblePanel / columns children are stored with the part's id (dominant 0.46 shape) AND, in forms never re-saved by the 0.46
#     designer, with the owning component's id: both are accepted, only an id that names neither is stale;
#   - a component that appears in two lists (the legacy duplicate list kept on `columns` / `collapsiblePanel`) is fine when its parentId
#     matches ANY of its places;
#   - a component with NO parentId is left alone, and keys starting with '_' (stashes) are not part of the tree.
ROOT = 'root'
PANEL_PARENT_TYPES = {'collapsiblePanel', 'columns'}


def _scan(o, holder, host_comp, out, is_root=False):
    """holder: id string / ROOT / None (unknown: skip); host_comp: nearest enclosing component dict (has `type` and `id`) or None."""
    if isinstance(o, dict):
        is_comp = 'type' in o and isinstance(o.get('id'), str)
        if is_root:
            h = ROOT
        elif isinstance(o.get('id'), str):
            h = o['id']
        else:
            h = None
        if is_comp:
            host_comp = o
        pane_like = (not is_comp) and h not in (None, ROOT)
        for k, v in o.items():
            if k.startswith('_') or not isinstance(v, (dict, list)):
                continue
            if k == 'components' and isinstance(v, list) and h is not None:
                accept = {h}
                if pane_like and host_comp is not None and host_comp.get('type') in PANEL_PARENT_TYPES:
                    accept.add(host_comp['id'])
                siblings = [c for c in v if isinstance(c, dict) and 'type' in c and isinstance(c.get('id'), str)]
                for c in siblings:
                    out.append({'comp': c, 'holder': h, 'accept': accept, 'pane_like': pane_like})
            _scan(v, h, host_comp, out)
    elif isinstance(o, list):
        for v in o:
            _scan(v, holder, host_comp, out)


def placements(markup):
    out = []
    if isinstance(markup, dict):
        _scan(markup, ROOT, None, out, is_root=True)
    return out


def analyse_parent_ids(markup):
    """[{'comp', 'current', 'holder', 'accepted'}] for every component whose parentId names nothing that holds it."""
    ps = placements(markup)
    accepted, canon = {}, {}
    for p in ps:
        cid = p['comp']['id']
        accepted.setdefault(cid, set()).update(p['accept'])
        if cid not in canon or (p['pane_like'] and not canon[cid]['pane_like']):
            canon[cid] = p
    out, seen = [], set()
    for p in ps:
        c = p['comp']
        if id(c) in seen:
            continue
        seen.add(id(c))
        pid = c.get('parentId')
        if pid is None or pid in accepted[c['id']]:
            continue
        out.append({'comp': c, 'current': pid, 'holder': canon[c['id']]['holder'], 'accepted': sorted(accepted[c['id']])})
    return out


# ------------------------------------------------------------------ tree helpers
def components(o, anc=()):
    """yield (component, ancestors tuple) for every dict with `type` and `id`; keys starting with '_' (stashes) are not part of the form."""
    if isinstance(o, dict):
        if 'type' in o and isinstance(o.get('id'), str):
            yield o, anc
            anc = anc + (o,)
        for k, v in o.items():
            if not k.startswith('_') and isinstance(v, (dict, list)):
                yield from components(v, anc)
    elif isinstance(o, list):
        for v in o:
            yield from components(v, anc)


def strings(o, comp=None, key=None, parent=None):
    """yield (nearest component, key, string, dict holding the key) for every string value of the markup."""
    if isinstance(o, dict):
        if 'type' in o and isinstance(o.get('id'), str):
            comp = o
        for k, v in o.items():
            if k.startswith('_'):
                continue
            if isinstance(v, str):
                yield comp, k, v, o
            elif isinstance(v, (dict, list)):
                yield from strings(v, comp, k, o)
    elif isinstance(o, list):
        for v in o:
            if isinstance(v, str):
                yield comp, key, v, parent
            else:
                yield from strings(v, comp, key, parent)


def cname(c):
    return c.get('componentName') or c.get('propertyName') or c.get('type') or '?'


def hosting_index(forms):
    """({(module|None, name)} embedded as sub-form or row, {(module|None, name)} used as a datalist/list row) from every form given."""
    hosted, rows = set(), set()
    for f in forms.values():
        for c, _ in components(f['markup']):
            if c.get('type') not in EMBED_TYPES:
                continue
            for k in FORM_KEYS:
                ref = c.get(k)
                if isinstance(ref, dict) and isinstance(ref.get('name'), str):
                    key = (ref.get('module') if isinstance(ref.get('module'), str) else None, ref['name'].strip())
                    hosted.add(key)
                    if c['type'] in ROW_TYPES:
                        rows.add(key)
    return hosted, rows


def _in(index, module, name, extra):
    if name in extra:
        return True
    return any(n == name and (m is None or module is None or m == module) for m, n in index)


def embed_depth(forms):
    """{form name: how many forms deep it is embedded}: 0 = a page, 1 = sub-form of a page, 2 = sub-form of a sub-form (longest chain wins)."""
    hosts = {}
    for f in forms.values():
        for c, _ in components(f['markup']):
            if c.get('type') in EMBED_TYPES:
                for k in FORM_KEYS:
                    ref = c.get(k)
                    if isinstance(ref, dict) and isinstance(ref.get('name'), str) and ref['name'].strip() != f['name']:
                        hosts.setdefault(ref['name'].strip(), set()).add(f['name'])
    memo = {}

    def depth(n, stack=()):
        if n in memo:
            return memo[n]
        if n in stack:
            return 0
        d = 1 + max((depth(h, stack + (n,)) for h in hosts[n]), default=-1) if n in hosts else 0
        memo[n] = d
        return d
    return {n: depth(n) for n in {f['name'] for f in forms.values()} | set(hosts)}


def _clip(s, n=200):
    s = re.sub(r'\s+', ' ', str(s)).strip()
    return s if len(s) <= n else s[:n - 3] + '...'


def _short(i):
    return str(i)[:8] + '..'


def _zero(v):
    return str(v).strip().lower() in ('0', '0px', '0.0', '0em', '0rem')


def _zero_height(c):
    """a container collapsed to height 0 (device dimensions, top-level dimensions or style code)"""
    blocks = [c] + [c[d] for d in ('desktop', 'tablet', 'mobile') if isinstance(c.get(d), dict)]
    for b in blocks:
        dims = b.get('dimensions') if isinstance(b.get('dimensions'), dict) else {}
        if any(_zero(dims.get(k)) for k in ('height', 'maxHeight')):
            return True
        st = b.get('style')
        if isinstance(st, str) and re.search(r'["\']?\b(?:max-?[hH]eight|height)["\']?\s*[:=]\s*["\']?0(?:px)?["\']?\s*[,;}\s]', st + ' '):
            return True
    return False


def _bound_input(c):
    return bool(c.get('propertyName')) and c.get('type') not in NOT_INPUT


def _code(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict) and isinstance(v.get('_code'), str):
        return v['_code']
    return ''


# ------------------------------------------------------------------ checks: each returns [(component, evidence, severity)]
def check_parent_id(ctx):
    out = []
    for s in analyse_parent_ids(ctx['markup']):
        c = s['comp']
        out.append((c, f'parentId {_short(s["current"])} names no container that holds it; it sits in {_short(s["holder"])} '
                       f'(the 0.46 designer would re-nest it on save; `shrec.py plan` lists a rule for it when the pack ships one)', 'trap'))
    return out


def check_url_endpoint_query(ctx):
    out = []
    for c, _ in components(ctx['markup']):
        if c.get('type') not in ('datatableContext', 'dataContext') or c.get('sourceType') != 'Url':
            continue
        ep = _code(c.get('endpoint'))
        keys = sorted({m.group(1) for m in URL_QUERY_RE.finditer(ep)})
        if not keys:
            continue
        # proven on the generic list endpoints (Crud/GetAll, Entities/GetAll): filter text dropped and NO other filter = every row of the entity (data leak).
        # With a permanentFilter beside it the query text is dead but harmless; on a custom endpoint it is unproven: look at it.
        has_pf = bool(c.get('permanentFilter'))
        leak = 'filter' in keys and not has_pf and bool(GENERIC_LIST_RE.search(ep))
        why = ('and NO permanentFilter: the list shows every row of the entity (data leak)' if leak else
               'a permanentFilter exists beside it, so check the query text is not the only thing narrowing the list' if has_pf else
               'custom endpoint: confirm on the wire (capture the request) that the query text still reaches the server')
        out.append((c, f'sourceType Url endpoint carries {", ".join(k + "=" for k in keys)}; 0.46 keeps only entityType from it and rebuilds '
                       f'filter/sorting/properties from the context settings - {why}. Use permanentFilter + standardSorting; endpoint: {_clip(ep, 120)}',
                    'trap' if leak else 'review'))
    return out


def _script_text(s):
    return LINE_COMMENT_RE.sub('', BLOCK_COMMENT_RE.sub('', s))


def _is_event_script(key, s):
    """a script that runs on a user action: an Execute Script expression (not a {{mustache}} filter value) or an on<Event> handler;
    render-time scripts (visible, style, htmlRender) are not: in a list row `data` is the row there"""
    if key == 'expression':
        return not s.lstrip().startswith('{{')
    return bool(re.match(r'^on[A-Z]\w*$', key or ''))


def check_subform_script_scope(ctx):
    """Verified (H49) on a sub-form NESTED two deep (a form nested two deep): `data` = {} and `form` = the page form.
    A sub-form one level under a page loads its own record and its scripts work, so only nested forms (or the ones named with --hosted/--nested) are looked at.
    A list-row form is skipped for data.* (there `data` is the row) but not for form.*."""
    if not ctx['script_scope']:
        return []
    own = set()   # `id` is left out: nearly every form binds it and scripts read data.id with a URL fallback
    for c, _ in components(ctx['markup']):
        if c.get('propertyName'):
            own.add(str(c['propertyName']).split('.')[0])
    own.discard('id')
    out, seen = [], set()
    for c, key, s, _holder in strings(ctx['markup']):
        if c is None or len(s) < 6 or not re.search(r'\b(data|form)\b', s):
            continue
        txt = _script_text(s)
        ev = []
        if _is_event_script(key, s) and not ctx['row']:
            hits = sorted(data_reads(txt) & own)
            if hits:
                ev.append('reads data.' + ', data.'.join(hits) + ' (own field of this form)')
        for m in FORM_CALL_RE.finditer(txt):
            fn, arg = m.group(1), (m.group(2) or '').strip('\'"')
            if fn in ('getFieldValue', 'setFieldValue') and arg and arg not in own:
                continue
            shown = ('"' + arg + '"') if arg else '...'
            ev.append(f'calls form.{fn}({shown})')
        if ev and (id(c), key) not in seen:
            seen.add((id(c), key))
            out.append((c, f'{key}: ' + '; '.join(dict.fromkeys(ev)) + ' - in an embedded form `data`/`form` are the HOST page form on 0.46 '
                           f'(empty read / silent write to the host); probe the scope, or read the DOM node by component name', 'review'))
    return out


def check_hidden_row_field(ctx):
    if not ctx['row']:
        return []
    # a row script (htmlRender, visible code ...) reading data.<field> is what makes a missing value visible: trap; otherwise the field is just unused: review
    read = set()
    for _c, _k, s, _h in strings(ctx['markup']):
        if 'data' in s:
            read.update(data_reads(_script_text(s)))
    out = []
    for c, anc in components(ctx['markup']):
        if not _bound_input(c):
            continue
        prop = str(c.get('propertyName')).split('.')[0]
        sev = 'trap' if prop in read else 'review'
        used = f'a row script reads data.{prop}' if prop in read else f'no script of the row reads data.{prop}, so it may be dead'
        if c.get('hidden') is True or c.get('visible') is False:
            out.append((c, f'{c.get("type")} bound to "{c.get("propertyName")}" is hidden:true in a list row form ({used}) - hidden fields are not mounted, '
                           f'the row data keeps only id + <sortField>. Keep it visible as a DIRECT child of the row root and collapse it '
                           f'(height 0 + overflow hidden)', sev))
            continue
        holder = next((a for a in reversed(anc) if a.get('type') == 'container' and _zero_height(a)), None)
        if holder is not None:
            out.append((c, f'{c.get("type")} bound to "{c.get("propertyName")}" is nested in the zero-height container {cname(holder)} in a list row form '
                           f'({used}) - nesting stops it being mounted for the row data; make it a direct child of the row root and collapse the field itself', sev))
    return out


def _mustaches(o):
    """(expression, required) for every mustache evaluate item inside a permanentFilter value"""
    if isinstance(o, dict):
        e = o.get('expression')
        if isinstance(e, str) and '{{' in e:
            yield e, o.get('required') is True
        for v in o.values():
            yield from _mustaches(v)
    elif isinstance(o, list):
        for v in o:
            yield from _mustaches(v)


def check_required_mustache_subform(ctx):
    if not ctx['nested']:
        return []
    out = []
    for c, _ in components(ctx['markup']):
        pf = c.get('permanentFilter')
        if not isinstance(pf, (dict, list)):
            continue
        for expr, required in _mustaches(pf):
            m = HOST_MUSTACHE_RE.search(expr)
            if m and required:
                out.append((c, f'permanentFilter has a required {{{{{m.group(1)}}}}} in an embedded form: it resolved to nothing in a nested sub-form '
                               f'(no request, "No data" list) on 0.46; {{{{page.state.<id>}}}} resolved (the pattern shared list sub-forms use). Verify on the wire', 'review'))
    return out


CHECK_FUNCS = {'parent-id': check_parent_id, 'url-endpoint-query': check_url_endpoint_query, 'subform-script-scope': check_subform_script_scope,
               'hidden-row-field': check_hidden_row_field, 'required-mustache-subform': check_required_mustache_subform}


# ------------------------------------------------------------------ run
def run(forms, checks=CHECKS, only=None, hosted_names=(), row_names=(), nested_names=(), context=None):
    """forms {id: {'module','name','markup'}} -> (findings, notes). `context` forms only teach who embeds whom."""
    everything = {**(context or {}), **forms}
    hosted, rows = hosting_index(everything)
    depth = embed_depth(everything)
    hosted_names, row_names, nested_names = set(hosted_names), set(row_names), set(nested_names)
    findings, n_hosted = [], 0
    for fid in sorted(forms):
        f = forms[fid]
        if only and f['name'] not in only and fid not in only:
            continue
        is_row = _in(rows, f['module'], f['name'], row_names)
        ctx = {'markup': f['markup'], 'module': f['module'], 'name': f['name'], 'row': is_row,
               'hosted': is_row or f['name'] in nested_names or _in(hosted, f['module'], f['name'], hosted_names | row_names),
               'nested': f['name'] in nested_names or depth.get(f['name'], 0) >= 2}
        ctx['script_scope'] = ctx['nested'] or f['name'] in hosted_names
        n_hosted += 1 if ctx['hosted'] else 0
        for chk in checks:
            for comp, ev, sev in CHECK_FUNCS[chk](ctx):
                findings.append({'form': fid, 'component': cname(comp), 'check': chk, 'severity': sev, 'evidence': ev})
    notes = []
    if any(c in checks for c in HOST_CHECKS) and not n_hosted:
        notes.append('note: none of the forms checked is known to be embedded as a sub-form or list row, so the host-dependent checks (' +
                     ', '.join(c for c in checks if c in HOST_CHECKS) + ') had nothing to look at; pass the hosting forms too, --context <dir>, '
                     'or name the forms with --hosted / --rows')
    return findings, notes


def report(findings, notes, n_forms, out=None):
    out = out or sys.stdout
    for f in findings:
        print(f'{f["form"]} | {f["component"]} | {f["check"]} | {f["severity"]} | {_clip(f["evidence"], 400)}', file=out)
    for n in notes:
        print(n, file=out)
    by = {}
    for f in findings:
        k = (f['check'], f['severity'])
        by[k] = by.get(k, 0) + 1
    print(f'summary: {len(findings)} finding(s) in {len({f["form"] for f in findings})} of {n_forms} form(s)'
          + (' - ' + ', '.join(f'{c}[{s}]={n}' for (c, s), n in sorted(by.items())) if by else ' - clean'), file=out)

# ------------------------------------------------------------------ sibling markup detectors (scan-hazards.mjs)
SCAN_IDS = re.compile(r'^H(1|[3-9]|1[0-8])$')
SCAN_REL = os.path.join('shesha-developer-0-46', 'skills', 'shesha-form-edit', 'scripts', 'scan-hazards.mjs')
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_scan_hazards():
    """Path of the sibling plugin's scan-hazards.mjs, or None. $SHREC_SCAN_HAZARDS wins; then the checkout layout, then the plugin cache."""
    env = os.environ.get('SHREC_SCAN_HAZARDS')
    if env:
        return env if os.path.isfile(env) else None
    cand = os.path.join(SKILL_DIR, '..', '..', '..', SCAN_REL)
    if os.path.isfile(cand):
        return os.path.normpath(cand)
    pat = os.path.join(SKILL_DIR, '..', '..', '..', '..', 'shesha-developer-0-46', '*', 'skills', 'shesha-form-edit', 'scripts', 'scan-hazards.mjs')
    hits = glob.glob(pat)
    if hits:
        def ver(p):      # <cache>/shesha-developer-0-46/<version>/skills/shesha-form-edit/scripts/scan-hazards.mjs
            d = p
            for _ in range(4):
                d = os.path.dirname(d)
            return os.path.basename(d)
        try:
            from core import versions
            hits.sort(key=lambda p: versions.key(ver(p)) or (0,))
        except Exception:
            hits.sort()
        return os.path.normpath(hits[-1])
    return None


def run_sibling(forms, only=None, script=None):
    """(findings, notes): scan-hazards.mjs over the given forms, mapped to the detect finding shape. Never raises."""
    script = script or find_scan_hazards()
    if not script:
        return [], ['note: scan-hazards.mjs of the sibling plugin (shesha-developer-0-46) not found: its markup detectors H1, H3-H18 were skipped '
                    '(set SHREC_SCAN_HAZARDS to its path to run them)']
    node = shutil.which('node')
    if not node:
        return [], ['note: node is not on PATH: the sibling scan-hazards detectors (H1, H3-H18) were skipped']
    picked = {fid: f for fid, f in forms.items() if not only or f['name'] in only or fid in only}
    if not picked:
        return [], []
    findings = []
    with tempfile.TemporaryDirectory(prefix='shrec-scan-') as d:
        names = {}
        for n, (fid, f) in enumerate(sorted(picked.items())):
            fn = f'f{n:05d}.json'
            names[fn] = fid
            with open(os.path.join(d, fn), 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(f['markup'], fh, ensure_ascii=False)
        try:
            r = subprocess.run([node, script, d, '--json'], capture_output=True, text=True, encoding='utf-8', timeout=600)
        except (OSError, subprocess.SubprocessError) as e:
            return [], [f'note: scan-hazards.mjs could not run ({type(e).__name__}); its detectors were skipped']
        if r.returncode not in (0, 1):
            return [], [f'note: scan-hazards.mjs could not run (exit {r.returncode}: {(r.stderr or "").strip()[:160]}); its detectors were skipped']
        try:
            results = json.loads(r.stdout or '[]')
        except ValueError:
            return [], ['note: scan-hazards.mjs printed no JSON; its detectors were skipped']
        for res in results:
            fid = names.get(os.path.basename(res.get('file') or ''))
            for x in res.get('findings') or []:
                if fid and SCAN_IDS.match(str(x.get('id'))):
                    findings.append({'form': fid, 'component': x.get('component') or '?', 'check': f'scan-{x["id"]}', 'severity': 'review',
                                     'evidence': f'{x.get("message")} ({x.get("ptr")})'})
    return findings, [f'note: sibling scan-hazards.mjs covered H1 and H3-H18 on {len(picked)} form(s)']


# ------------------------------------------------------------------ self test
def _comp(t, name, **kw):
    return {'id': name + '-id', 'type': t, 'componentName': name, 'propertyName': kw.pop('propertyName', name), **kw}


def selftest(quiet=False):
    import copy
    ok = []

    def expect(label, cond):
        ok.append((label, bool(cond)))

    # parent-id: row holds main + rail; the rail still names the OLD tab pane
    rail = _comp('container', 'sideRail', parentId='oldPane-id')
    row = _comp('container', 'row', parentId='root', components=[_comp('container', 'main', parentId='row-id'), rail])
    pane = {'id': 'newPane-id', 'components': [row]}
    tabs = _comp('tabs', 'tabs1', parentId='root', tabs=[pane])
    stale = {'components': [tabs], 'formSettings': {}}
    rail['parentId'] = 'oldPane-id'
    row['parentId'] = 'newPane-id'
    f, _ = run({'stale': {'module': 'M', 'name': 'stale', 'markup': stale}}, ('parent-id',))
    expect('parent-id flags the stale rail only', [x['component'] for x in f] == ['sideRail'] and f[0]['severity'] == 'trap')
    fixed = copy.deepcopy(stale)
    fixed['components'][0]['tabs'][0]['components'][0]['components'][1]['parentId'] = 'row-id'
    f, _ = run({'fixed': {'module': 'M', 'name': 'fixed', 'markup': fixed}}, ('parent-id',))
    expect('parent-id is clean once the parentId names the holder', not f)
    expect('parent-id analysis reports the holder of the stale component', analyse_parent_ids(stale)[0]['holder'] == 'row-id')
    # legit shapes stay clean: panel children with the panel id or the content id, legacy duplicate list, component without parentId
    kid1, kid2 = _comp('textField', 'a', parentId='panel-id'), _comp('textField', 'b', parentId='content-id')
    panel = _comp('collapsiblePanel', 'panel', parentId='root', content={'id': 'content-id', 'components': [kid1, kid2]}, components=[copy.deepcopy(kid2)])
    nopid = _comp('container', 'helper')
    ctxc = _comp('datatableContext', 'ctx', parentId='root', components=[nopid])
    clean = {'components': [panel, ctxc]}
    f, _ = run({'c': {'module': 'M', 'name': 'c', 'markup': clean}}, ('parent-id',))
    expect('parent-id accepts panel/content ids, legacy duplicates, missing parentId', not f)
    bad_root = {'components': [_comp('container', 'r', parentId='somewhere')]}
    f, _ = run({'r': {'module': 'M', 'name': 'r', 'markup': bad_root}}, ('parent-id',))
    expect('parent-id: a root child must say root', len(f) == 1)

    # url-endpoint-query
    code = {'_mode': 'code', '_code': "return '/api/dynamic/Shop/Order/Crud/GetAll' + '?properties=' + encodeURIComponent('id') + '&filter=' + x;"}
    good = _comp('datatableContext', 'ok', parentId='root', sourceType='Url', endpoint='/api/dynamic/Shop/Order/Crud/GetAll', permanentFilter={'and': []})
    bad1 = _comp('datatableContext', 'bad1', parentId='root', sourceType='Url', endpoint=code)
    bad2 = _comp('dataContext', 'bad2', parentId='root', sourceType='Url', endpoint='/api/services/app/Entities/GetAll?entityType=X&sorting=a desc')
    bad3 = _comp('datatableContext', 'bad3', parentId='root', sourceType='Url', endpoint='/api/services/app/Entities/GetAll?entityType=X&filter={{data.f}}',
                 permanentFilter={'and': [{'==': [{'var': 'a'}, 1]}]})
    ent = _comp('datatableContext', 'ent', parentId='root', sourceType='Entity', endpoint='/x?filter=1')
    f, _ = run({'u': {'module': 'M', 'name': 'u', 'markup': {'components': [good, bad1, bad2, bad3, ent]}}}, ('url-endpoint-query',))
    sev = {x['component']: x['severity'] for x in f}
    expect('url-endpoint-query: filter text on a generic list endpoint with no permanentFilter is a trap; sorting-only or with a permanentFilter is a review; '
           'a clean Url or an Entity context is silent', sev == {'bad1': 'trap', 'bad2': 'review', 'bad3': 'review'})

    # host-dependent checks: an entries form embeds an entry row form as a datalist row and is itself a sub-form of the host
    save = ("var text = (data && data.newEntry ? String(data.newEntry) : '').trim();\n// data.newEntry in a code comment is ignored\n"
            "await http.post('/x', {t: text}); form.setFieldsValue({ newEntry: null });")
    save_ok = "var box = document.querySelector('[data-sha-c-name=\"newEntry\"] textarea'); const text = String(box ? box.value : '').trim(); var o = (data && data.id);"
    btn = lambda s: _comp('buttonGroup', 'actions', parentId='root', items=[{'id': 'i1', 'actionConfiguration': {'actionName': 'Execute Script', 'actionArguments': {'expression': s}}}])
    memo = _comp('textArea', 'newEntry', parentId='root')
    pf = {'and': [{'==': [{'var': 'parentRecordId'}, {'evaluate': [{'expression': '{{data.id}}', 'required': True, 'type': 'mustache'}]}]}]}
    pf_ok = {'and': [{'==': [{'var': 'parentRecordId'}, {'evaluate': [{'expression': '{{page.state.parentFormId}}', 'required': True, 'type': 'mustache'}]}]}]}
    lst = _comp('datalist', 'list', parentId='root', formId={'module': 'M', 'name': 'row'})
    entries = {'components': [memo, btn(save), _comp('datatableContext', 'dtc', parentId='root', permanentFilter=pf, components=[lst])]}
    entries_ok = {'components': [memo, btn(save_ok), _comp('datatableContext', 'dtc', parentId='root', permanentFilter=pf_ok, components=[lst])]}
    # page > host > entries > row: `entries` is nested two deep, `row` is a list row
    host = {'components': [_comp('subForm', 'sub', parentId='root', formId={'module': 'M', 'name': 'entries'})]}
    page = {'components': [_comp('subForm', 'sub', parentId='root', formId={'module': 'M', 'name': 'host'})]}
    html = _comp('htmlRender', 'html', renderer='return "<b>" + data.bodyText + data.createdBy + "</b>";')
    hidden = _comp('textField', 'bodyHidden', parentId='root', propertyName='bodyText', hidden=True)
    unused = _comp('textField', 'unusedHidden', parentId='root', propertyName='unusedField', hidden=True)
    row_bad = {'components': [_comp('container', 'rowRoot', parentId='root', components=[hidden, unused, html])]}
    holder = _comp('container', 'holder', parentId='rowRoot-id', desktop={'dimensions': {'height': '0px'}},
                   components=[_comp('textField', 'inner', parentId='holder-id', propertyName='createdBy')])
    row_nest = {'components': [_comp('container', 'rowRoot', parentId='root', components=[holder, html])]}
    collapsed = _comp('textField', 'bodyText', parentId='rowRoot-id', propertyName='bodyText', desktop={'dimensions': {'height': '0px'}},
                      style='return {"height":"0px","overflow":"hidden"};')
    row_ok = {'components': [_comp('container', 'rowRoot', parentId='root', components=[collapsed, html])]}

    def hostrun(c, r, checks):
        return run({'page': {'module': 'M', 'name': 'page', 'markup': page}, 'host': {'module': 'M', 'name': 'host', 'markup': host},
                    'entries': {'module': 'M', 'name': 'entries', 'markup': c}, 'row': {'module': 'M', 'name': 'row', 'markup': r}}, checks)[0]
    f = hostrun(entries, row_bad, ('subform-script-scope',))
    expect('subform-script-scope flags data.<own field> and form.setFieldsValue in the Save script (review)',
           len(f) == 1 and f[0]['severity'] == 'review' and 'data.newEntry' in f[0]['evidence'] and 'setFieldsValue' in f[0]['evidence'])
    expect('subform-script-scope is silent on the DOM-node version (data.id is not an own field, code comments ignored)',
           not hostrun(entries_ok, row_ok, ('subform-script-scope',)))
    expect('subform-script-scope is silent when the form is not embedded', not run({'c': {'module': 'M', 'name': 'entries', 'markup': entries}}, ('subform-script-scope',))[0])
    f = hostrun(entries, row_bad, ('hidden-row-field',))
    expect('hidden-row-field flags hidden:true bound fields of the row form: trap when a row script reads it, review when nothing does',
           {x['component']: x['severity'] for x in f} == {'bodyHidden': 'trap', 'unusedHidden': 'review'})
    f = hostrun(entries, row_nest, ('hidden-row-field',))
    expect('hidden-row-field flags a bound field nested in a zero-height holder', [x['component'] for x in f] == ['inner'])
    expect('hidden-row-field accepts the collapsed direct child', not hostrun(entries, row_ok, ('hidden-row-field',)))
    f = hostrun(entries, row_ok, ('required-mustache-subform',))
    expect('required-mustache-subform flags {{data.id}} (review)', len(f) == 1 and f[0]['component'] == 'dtc' and f[0]['severity'] == 'review')
    expect('required-mustache-subform accepts {{page.state.parentFormId}}', not hostrun(entries_ok, row_ok, ('required-mustache-subform',)))
    two = run({'host': {'module': 'M', 'name': 'host', 'markup': host}, 'entries': {'module': 'M', 'name': 'entries', 'markup': entries}},
              ('required-mustache-subform',))[0]
    expect('required-mustache-subform is silent for a sub-form only one level deep (the page is not among the forms)', not two)
    expect('required-mustache-subform honours --nested',
           len(run({'entries': {'module': 'M', 'name': 'entries', 'markup': entries}}, ('required-mustache-subform',), nested_names=['entries'])[0]) == 1)
    f, notes = run({'entries': {'module': 'M', 'name': 'entries', 'markup': entries}}, ('hidden-row-field',))
    expect('a run with no hosting form says so', not f and notes)
    # CLI contract
    import io
    buf = io.StringIO()
    report([{'form': 'a', 'component': 'b', 'check': 'parent-id', 'severity': 'trap', 'evidence': 'e'}], [], 1, buf)
    expect('report prints one line per finding plus a summary', buf.getvalue().count('\n') == 2 and 'a | b | parent-id | trap | e' in buf.getvalue())

    bad = [l for l, c in ok if not c]
    if not quiet:
        for l, c in ok:
            print(('PASS ' if c else 'FAIL ') + l)
        print(f'selftest: {len(ok) - len(bad)}/{len(ok)} passed')
    selftest.failed = bad
    return not bad

def main(argv=None):
    ap = argparse.ArgumentParser(prog='shrec detect', description='Static read-only markup detectors (exit 1 when there are findings).')
    ap.add_argument('--markup', help='a markup / row / backup .json file, or a directory of them')
    ap.add_argument('--role', choices=('reference', 'local', 'deployed'), help='read the forms of that role (GET only)')
    ap.add_argument('--only', help='comma list of form names to report on (all forms still feed the embedded-form index)')
    ap.add_argument('--module', help="with --role: module(s) to report on, comma list or 'all' (default: the project modules)")
    ap.add_argument('--checks', help='comma list of: ' + ', '.join(ALL_CHECKS))
    ap.add_argument('--hosted', help='comma list of form names to treat as embedded sub-forms')
    ap.add_argument('--rows', help='comma list of form names to treat as datalist/list row forms')
    ap.add_argument('--nested', help='comma list of form names to treat as a sub-form of a sub-form (H51 only looks at those)')
    ap.add_argument('--context', help='directory read only to learn which forms embed which (not reported on)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args(argv)
    if a.selftest:
        return 0 if selftest() else 1
    if bool(a.markup) == bool(a.role):
        ap.error('give exactly one of --markup or --role (or --selftest)')
    checks = tuple(c.strip() for c in a.checks.split(',') if c.strip()) if a.checks else ALL_CHECKS
    unknown = [c for c in checks if c not in ALL_CHECKS]
    if unknown:
        ap.error(f'unknown check {unknown}; choose from {list(ALL_CHECKS)}')
    split = lambda s: [x.strip() for x in s.split(',') if x.strip()] if s else []
    if a.markup:
        if not os.path.exists(a.markup):
            ap.error(f'{a.markup} does not exist')
        forms = load_path(a.markup)
        context = load_path(a.context) if a.context else None
    else:
        from core import project
        allf = load_role(a.role)
        mods = split(a.module) or list(project.modules())
        forms = {k: v for k, v in allf.items() if 'all' in mods or v['module'] in mods}
        context = {k: v for k, v in allf.items() if k not in forms}
    if not forms:
        print('no form markup found in the input', file=sys.stderr)
        return 2
    only = set(split(a.only))
    findings, notes = run(forms, tuple(c for c in checks if c in CHECKS), only=only or None, hosted_names=split(a.hosted),
                          row_names=split(a.rows), nested_names=split(a.nested), context=context)
    if SCAN in checks:
        f2, n2 = run_sibling(forms, only or None)
        findings += f2
        notes += n2
    # the same matching as run(): a form counts when its name OR its display id is selected
    report(findings, notes, len(forms) if not only else len([k for k, f in forms.items() if f['name'] in only or k in only]))
    return 1 if findings else 0


if __name__ == '__main__':
    if __package__ in (None, ''):          # `python tools/detect.py ...` outside shrec.py
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
