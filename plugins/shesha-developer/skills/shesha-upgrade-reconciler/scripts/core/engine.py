"""Applies a selected rule list to forms: online (through core.push, guarded and ledgered) or offline (a markup dict,
for self-tests and parity runs)."""
import collections
import json
import time

from core import ledger, packs, project
from core.api import fetch_forms, modname
from core.project import require

COUNT = collections.Counter()


def selected_rules(pack, target_version, only_rules=None, enable=(), disable=(), include_claimed=True):
    """[(meta, apply, retire)] in application order: pack rules by plan(), then project rules."""
    out = []
    for meta, fate in packs.plan(pack, target_version, enable, disable):
        if only_rules and meta['id'] not in only_rules:
            continue
        if fate == 'apply' or (fate == 'apply-claimed-fixed' and include_claimed) or (only_rules and fate in ('opt-in', 'targeted')):
            a, r = packs.callables(pack, meta)
            out.append((meta, a, r))
    for meta, a, r in packs.load_project_rules():
        if meta['id'] in disable or (only_rules and meta['id'] not in only_rules):
            continue
        kind = meta.get('kind') or 'fleet'
        if not only_rules and (kind != 'fleet' and not (kind == 'opt-in' and meta['id'] in enable)):
            continue                     # targeted / opt-in / unknown kinds run only when named (opt-in: or enabled)
        out.append((meta, a, r))
    unknown = set(only_rules or ()) - {m['id'] for m, _, _ in out}
    require(not unknown, f'unknown, opt-in-only or not applicable rule(s): {sorted(unknown)} (see `shrec.py plan`)')
    return out


def make_transform(session, rules, module, name, mode='apply'):
    """A push transform running every rule's apply (or retire) on one form; .rules = {rule: [notes]} for the ledger."""
    def t(markup):
        ctx = packs.Ctx(session, module, name)
        t.rules = {}
        for meta, apply_fn, retire_fn in rules:
            fn = apply_fn if mode == 'apply' else retire_fn
            if fn is None:
                continue
            before = len(ctx.notes)
            k = fn(ctx, markup)
            if k:
                COUNT[meta['id']] += k
            if len(ctx.notes) > before:
                t.rules[meta['id']] = ctx.notes[before:]
        return ctx.notes if any(not x.startswith('INFO') for x in ctx.notes) else []
    t.rules = {}
    return t


def apply_offline(session, rules, module, name, markup, mode='apply'):
    """Run the rules on a markup dict in memory; returns (markup, notes). Never touches a backend."""
    t = make_transform(session, rules, module, name, mode)
    notes = t(markup)
    return markup, notes


def run(pack, rules, role, only_forms=None, dry=True, mode='apply', rule_label=None):
    """Fleet run over the project's modules on the given role. Returns (changed {form: n}, failed [(form, reason)])."""
    from core import push as pushmod
    a, items = fetch_forms(role, project.modules())
    names = sorted({(modname(i).strip(), (i.get('name') or '').strip()) for i in items
                    if not only_forms or i['name'].strip() in only_forms or f"{modname(i)}/{i['name']}" in only_forms})
    tv = (project.environments().get(role) or {}).get('version')
    rv = (project.environments().get('reference') or {}).get('version')
    ledger.set_context(pack=f"{pack['id']}@{pack.get('version', '?')}" if pack else None, versions={'from': rv, 'to': tv})
    session = packs.Session(role=role, options=project.config().get('options') or {}, versions_pair={'from': rv, 'to': tv})
    label = rule_label or ','.join(m['id'] for m, _, _ in rules)
    if not dry:
        print('snapshot dir:', pushmod.begin_run(names, rule=label, role=role))
    changed, failed = {}, []
    for module, name in names:
        for attempt in range(3):
            try:
                notes = pushmod.push(module, name, make_transform(session, rules, module, name, mode), dry_run=dry, role=role,
                                     rule=label, event='form' if mode == 'apply' else 'retire')
                if notes:
                    changed[f'{module}/{name}'] = len(notes)
                break
            except pushmod.WrittenUnverified as e:   # the write may have landed: never retry blindly
                failed.append((f'{module}/{name}', 'WRITTEN-UNVERIFIED (check the form; restore --form from before/): ' + str(e)[:160]))
                break
            except AssertionError as e:
                failed.append((f'{module}/{name}', str(e)[:200]))
                break
            except Exception as e:      # transient network errors: retry twice
                if attempt == 2:
                    failed.append((f'{module}/{name}', f'{type(e).__name__}: {e}'[:200]))
                else:
                    time.sleep(5)
    ledger.event('summary', env=role, script=f'shrec {mode}', dry=dry, rules=[m['id'] for m, _, _ in rules],
                 forms_changed=len(changed), of=len(names), failed=[f for f, _ in failed], by_rule=dict(COUNT))
    return changed, failed, len(names)


def load_markup(row):
    mk = row.get('markup')
    return json.loads(mk) if isinstance(mk, str) else (mk or {})
