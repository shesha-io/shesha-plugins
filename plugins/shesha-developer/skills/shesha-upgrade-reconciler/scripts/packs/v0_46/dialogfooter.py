"""Rule `dialogfooter` (H35, targeted): custom dialog footer buttons ignore their `editMode` / visibility scripts.

Symptom on 0.46: a footer Save that 0.43 disabled until a condition held is always enabled.
Cause: 0.46 renders custom footer buttons with the raw button-group renderer, which reads only a static `visible` /
`disabled` and permissions; their `editMode` / visibility SCRIPTS are never evaluated. Fixed in 0.46.1 per its release
notes (not verified).

Writes - configuration only. Only dialogs (Show Dialog actions with `footerButtons: 'custom'`) whose button items carry a
code-valued `editMode` / `visible` / `hidden` / `disabled` qualify.
  * The dialog form is opened by exactly ONE Show Dialog action in the whole configuration: the buttons are rendered
    INSIDE the dialog form, as an ordinary `buttonGroup` in a right-aligned row appended to the form's root container (the
    normal evaluation pipeline applies), and the host's dialog gets `footerButtons: 'none'`, its original items kept in
    `_reconcilerFooterButtons046`. Items (labels, actions, scripts) are copied unchanged.
  * The dialog form is shared (opened by several dialogs, or not resolvable): the buttons cannot move into the form.
    The first `Execute Script` of a button with a code `editMode` is prefixed with that condition, so a click that
    0.43 would have blocked shows a warning and stops before any write (the button still LOOKS enabled).
Both halves run through this one rule; every transform edits a single form:
  - on the DIALOG form: adds the footer row (the buttons come from the host's dialog in the session's form snapshot);
  - on the HOST form: clears the footer ONLY once the dialog form in the fetched snapshot already holds the footer row
    (otherwise the buttons would be lost); the first run therefore adds the row and reports the host as pending, and a
    second run clears the host. Include both forms in `--only`, or run the rule over the whole fleet twice.
Markers: the `-ftr046` / `-ftrbtn046` id suffixes, `_reconcilerFooterButtons046`, /*reconciler:046-footer-guard*/.
`retire` removes the footer row (dialog form), restores `footerButtons: 'custom'` + the items (host) and removes the
guard block (shared dialogs).
Options: footerGuardMessage (the warning shown when a guarded click is blocked; default below).
Run with `apply --rules dialogfooter --only host,dialog,...`.
"""
import collections
import copy
import hashlib
import json
import re

from core.api import modname
from core.project import require
from core.tree import walk_dicts
from packs.v0_46.common import flush

ROW_SUFFIX, GROUP_SUFFIX = '-ftr046', '-ftrbtn046'
DYN_KEYS = ('editMode', 'visible', 'hidden', 'disabled')
STRIP = ('hidden', 'visible', 'customVisibility', 'editMode', 'readOnly', 'components')
GUARD = '/*reconciler:046-footer-guard*/'
DEFAULT_GUARD_MESSAGE = 'Complete the required details before continuing.'
# the guard block: marker line ... up to and including the closing brace after the `throw new Error(...)` line (any message)
_GUARD_BLOCK = re.compile(r'/\*reconciler:046-footer-guard\*/\n.*?throw new Error\([^\n]*\);\n\}\n', re.S)


def _dyn(item):
    return any(isinstance(item.get(k), dict) and item[k].get('_mode') == 'code' and (item[k].get('_code') or '').strip() for k in DYN_KEYS)


def form_name(fid):
    return fid.get('name') if isinstance(fid, dict) else (fid if isinstance(fid, str) else None)


def find_dialogs(markup, only_form=None):
    """Show Dialog action arguments with a custom footer that has at least one dynamic item."""
    out = []
    for o in walk_dicts(markup):
        a = o.get('actionArguments')
        if o.get('actionName') == 'Show Dialog' and isinstance(a, dict) and a.get('footerButtons') == 'custom' \
                and any(_dyn(b) for b in a.get('buttons') or []):
            if only_form is None or form_name(a.get('formId')) == only_form:
                out.append(a)
    return out


def _id(seed, suffix):
    return hashlib.sha1(seed.encode()).hexdigest()[:22] + suffix


def _find(markup, pred):
    return [o for o in walk_dicts(markup) if pred(o)]


def add_footer_to_form(form_markup, items, seed, row_template):
    """Append a right-aligned row with a buttonGroup holding `items` as the last child of the form's root container."""
    row_id = _id(seed, ROW_SUFFIX)
    if _find(form_markup, lambda o: o.get('id') == row_id):
        return []           # already applied
    comps = form_markup.get('components')
    require(isinstance(comps, list) and comps, 'anchor: form has no root components')
    root = comps[0] if len(comps) == 1 and comps[0].get('type') == 'container' else None
    holder = root['components'] if root else comps
    parent_id = root['id'] if root else None
    row = {k: copy.deepcopy(v) for k, v in row_template.items() if k not in STRIP}
    row.update({'id': row_id, 'parentId': parent_id, 'propertyName': 'dialogFooterRow046', 'componentName': 'dialogFooterRow046',
                'label': 'Dialog footer (reconciler 046)', 'components': []})
    group = {'id': _id(seed, GROUP_SUFFIX), 'type': 'buttonGroup', 'componentName': 'dialogFooterButtons046',
             'propertyName': 'dialogFooterButtons046', 'label': 'Dialog actions', 'hideLabel': True, 'isInline': True,
             'editMode': 'inherited', 'version': 15, 'parentId': row_id, 'items': copy.deepcopy(items)}
    row['components'].append(group)
    holder.append(row)
    return [f'footer buttons {[i.get("label") for i in items]} rendered inside the form (row {row_id})']


def clear_footer(dialog_args):
    if dialog_args.get('footerButtons') == 'none' and not dialog_args.get('buttons'):
        return []
    require(dialog_args.get('footerButtons') == 'custom', 'anchor: footerButtons is not custom')
    dialog_args['_reconcilerFooterButtons046'] = copy.deepcopy(dialog_args.get('buttons') or [])
    dialog_args['footerButtons'] = 'none'
    dialog_args['buttons'] = []
    return ['dialog footerButtons custom -> none (original items kept in _reconcilerFooterButtons046)']


def row_template_from(form_markup):
    """A clean right-aligned flex row from the same form when available, else a minimal v9 container."""
    for c in _find(form_markup, lambda o: o.get('type') == 'container' and str(o.get('justifyContent')) in ('end', 'flex-end')
                   and (o.get('desktop') or {}).get('display') == 'flex'):
        return c
    return {'type': 'container', 'version': 9, 'labelAlign': 'right', 'isDynamic': False, 'direction': 'horizontal',
            'display': 'flex', 'justifyContent': 'end', 'flexWrap': 'nowrap'}


def _js_string(text):
    """a single-quoted JS string literal holding `text` on one line"""
    return "'" + ' '.join(text.split()).replace('\\', '\\\\').replace("'", "\\'") + "'"


def guard_item(item, message=DEFAULT_GUARD_MESSAGE):
    """Prefix the first Execute Script of a dynamic footer button with its editMode condition. Returns a note or None."""
    em = item.get('editMode')
    if not (isinstance(em, dict) and em.get('_mode') == 'code' and (em.get('_code') or '').strip()):
        return None
    ac = item.get('actionConfiguration')
    if not (isinstance(ac, dict) and ac.get('actionOwner') == 'shesha.common' and ac.get('actionName') == 'Execute Script'):
        return None
    args = ac.setdefault('actionArguments', {})
    expr = args.get('expression') or ''
    if GUARD in expr:
        return None
    cond = em['_code']
    args['expression'] = (f"{GUARD}\nlet __footerMode;\n"
                          f"try {{ __footerMode = (() => {{\n{cond}\n}})(); }} catch (__e) {{ __footerMode = 'editable'; }}  // fail open\n"
                          "if (__footerMode === false || __footerMode === 'readOnly' || __footerMode === 'readonly' || __footerMode === 'disabled') {\n"
                          f"    message.warning({_js_string(message)});\n"
                          f"    throw new Error({_js_string('Action blocked: ' + message)});\n}}\n" + expr)
    return f'{item.get("label")}: enable condition enforced in its action (footer button, shared dialog form)'


def guard_dialogs(markup, shared_forms, message=DEFAULT_GUARD_MESSAGE):
    """Apply guard_item to dynamic custom-footer buttons of dialogs that open one of `shared_forms`."""
    notes = []
    for a in find_dialogs(markup):
        if form_name(a.get('formId')) not in shared_forms:
            continue
        for b in a.get('buttons') or []:
            n = guard_item(b, message)
            if n:
                notes.append(n)
    return notes


# ------------------------------------------------------------------ the cross-form plan (one per run, from the form snapshot)
def _parsed(session):
    out = {}
    for row in session.forms():
        mk = row.get('markup')
        try:
            out[(modname(row).strip(), (row.get('name') or '').strip())] = json.loads(mk) if isinstance(mk, str) else (mk or {})
        except ValueError:
            continue
    return out


def build_plan(session):
    """{'dialogs': {(module, name): [{host, title, seed, items}]}, 'shared': {(module, name) of a host: {dialog names}}}"""
    forms = _parsed(session)
    uses = collections.Counter()
    for m in forms.values():
        for o in walk_dicts(m):
            if o.get('actionName') == 'Show Dialog' and isinstance(o.get('actionArguments'), dict):
                uses[form_name(o['actionArguments'].get('formId'))] += 1
    dialogs, shared = collections.defaultdict(list), collections.defaultdict(set)
    for (mod, name), m in forms.items():
        for args in find_dialogs(m):
            fid = args.get('formId')
            dname = form_name(fid)
            dmod = fid.get('module') if isinstance(fid, dict) else None
            if not dmod:
                hits = [k for k in forms if k[1] == dname]
                dmod = hits[0][0] if len(hits) == 1 else None
            if uses[dname] != 1 or not dmod:
                shared[(mod, name)].add(dname)
                continue
            got = find_dialogs(m, dname)
            require(len(got) == 1, f'anchor: {len(got)} dynamic custom-footer dialogs for {dname} in {name}')
            dialogs[(dmod, dname)].append({'host': (mod, name), 'title': args.get('modalTitle'), 'seed': f'{name}:{args.get("modalTitle")}',
                                           'dialog': dname, 'items': copy.deepcopy(got[0]['buttons'])})
    return {'dialogs': dict(dialogs), 'shared': dict(shared), 'forms': forms}


def _plan(ctx):
    return ctx.cache('dialogfooter.plan', lambda: build_plan(ctx.session))


def apply(ctx, markup):
    plan = _plan(ctx)
    key = (ctx.module.strip(), ctx.name)
    n = 0
    # dialog form: add the footer row for each host dialog that opens it
    for entry in plan['dialogs'].get(key, []):
        notes = add_footer_to_form(markup, entry['items'], entry['seed'], row_template_from(markup))
        if notes:
            n += 1
            flush(ctx, notes)
    # host form: clear the footer of each unique dialog whose form already holds the footer row; guard the shared ones
    for (dmod, dname), entries in plan['dialogs'].items():
        for entry in entries:
            if entry['host'] != key:
                continue
            got = find_dialogs(markup, dname)
            if not got:
                continue            # already moved
            require(len(got) == 1, f'anchor: {len(got)} dynamic custom-footer dialogs for {dname} in {ctx.name}')
            row_id = _id(entry['seed'], ROW_SUFFIX)
            if not _find(plan['forms'].get((dmod, dname), {}), lambda o: o.get('id') == row_id):
                ctx.info(f'dialog form {dmod}/{dname} has no footer row yet: footer of {entry["title"]!r} kept; run the rule on the '
                         'dialog form first (its row is added now), then run it again to clear this host')
                continue
            notes = clear_footer(got[0])
            if notes:
                n += 1
                flush(ctx, notes)
    shared = plan['shared'].get(key)
    if shared:
        message = ctx.opt('footerGuardMessage', DEFAULT_GUARD_MESSAGE)
        require(isinstance(message, str) and message.strip(), 'option footerGuardMessage must be a non-empty string')
        notes = guard_dialogs(markup, shared, message)
        n += len(notes)
        flush(ctx, notes)
    return n


# ------------------------------------------------------------------ retire
def retire(ctx, markup):
    n = 0
    # 1. the footer rows this rule added (dialog forms)
    def holder_lists(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from holder_lists(v)
        elif isinstance(o, list):
            yield o
            for v in o:
                yield from holder_lists(v)
    for lst in list(holder_lists(markup)):
        for c in list(lst):
            if isinstance(c, dict) and str(c.get('id', '')).endswith(ROW_SUFFIX) and c.get('componentName') == 'dialogFooterRow046':
                lst.remove(c)
                n += 1
                ctx.note(f'dialog footer row {c["id"]} removed')
    # 2. host dialogs: restore the original custom footer; 3. shared dialogs: remove the guard block
    for o in walk_dicts(markup):
        if '_reconcilerFooterButtons046' in o and o.get('footerButtons') == 'none':
            o['buttons'] = o.pop('_reconcilerFooterButtons046')
            o['footerButtons'] = 'custom'
            n += 1
            ctx.note('dialog footerButtons restored to custom (original items put back)')
        expr = o.get('expression')
        m = _GUARD_BLOCK.match(expr) if isinstance(expr, str) else None
        if m:
            rest = expr[m.end():]
            if rest:
                o['expression'] = rest
            else:
                del o['expression']
            n += 1
            ctx.note('footer guard block removed from a button action')
    return n
