"""Three-way merge of Shesha form markup, by component id: bring the NEW changes made on the pre-upgrade line onto the already
reconciled upgraded forms without losing either side.

  base   = the form's PREVIOUS raw export (what the earlier reconcile already saw)        <work>/merge/base/<module>/<form>.json
  theirs = the form's NEWEST raw export in the new packages of the pre-upgrade line      <work>/merge/theirs/<module>/<form>.json
           (both written by `shrec.py branch-changed --extract`, which also writes <work>/merge/branch_changed.json)
  ours   = the reconciled form: the target row itself (default), another role, or a snapshot directory

Rule per node: equal -> that; only one side changed -> that side; both changed -> recurse (dicts by key, component lists by id);
a scalar both sides changed keeps OURS and is REPORTED (use --theirs-wins <path fragment>|<fragment> to take theirs for those);
scripts changed by both are line-merged with `git merge-file` (clean merge or reported conflict); lists of plain strings are merged as
sets (additions added, removals removed). A component theirs deleted is deleted. `attr_pass` re-applies theirs' attribute changes by
component id wherever the component now sits (moved/restructured components keep the update) and `name_pass` does the same by
(type, componentName) for components whose id was regenerated.

  shrec.py merge3 delta --forms a,b [--module M] [--full]              component-level delta base -> theirs (the real intent)
  shrec.py merge3 merge (--forms a,b | --all) [--ours same|local|deployed|reference|dir:<path>] [--target local|deployed]
                        [--theirs-wins frag|frag] [--prefer-module <module>] [--push]

`merge` is a dry run unless --push; a push goes through core.push.push (whole-run snapshot, per-write backup, modelType carried, read-back
verified) and, on the deployed target, only after the user's go-ahead (SHREC_TARGET / --target; see core/push.py). --prefer-module M: when
theirs edited a form of another module that has a same-named copy in module M on the target, apply it to the copy in M (an override).
A NEW form (no base) needs no merge: the backend import already created it from the package; run the reconcile rules on it. Re-run the
rule `apply` on every merged form afterwards.
"""
import json, os, re, subprocess, sys, tempfile

from core import ledger, project
from core.project import require

M = object()
THEIRS_WINS = []


def safe(s): return re.sub(r'[^\w.-]', '_', s.strip())


def isid(l): return isinstance(l, list) and l and all(isinstance(x, dict) and 'id' in x for x in l)


def line_merge(base, a, b):
    """git merge-file three-way merge of a script string; None when the hunks overlap (a real conflict)."""
    d = tempfile.mkdtemp(); fs = []
    for nm, txt in (('ours', a), ('base', base), ('theirs', b)):
        f = os.path.join(d, nm)
        with open(f, 'w', encoding='utf-8', newline='') as h: h.write(txt)
        fs.append(f)
    r = subprocess.run(['git', 'merge-file', '-p', *fs], capture_output=True)
    return r.stdout.decode('utf-8') if r.returncode == 0 else None


def adopt(v, path, conf):
    """A subtree theirs ADDED (a new wrapper container ...) may carry components that already exist in the reconciled form: theirs only moved them.
    Replace each such component's raw 0.43 copy with base/ours/theirs merged, so our reconciled version is kept and theirs' changes still land."""
    if isinstance(v, dict):
        i = v.get('id')
        if i and v.get('type') and i in CTX['ours'] and i in CTX['base']:
            conf.append((path, 'moved here by theirs (new container): our reconciled version merged with theirs changes'))
            return m3(CTX['base'][i], CTX['ours'][i], v, path, conf)
        return {k: adopt(x, f'{path}/{k}', conf) for k, x in v.items()}
    if isinstance(v, list): return [adopt(x, path, conf) for x in v]
    return v


def m3(base, a, b, path, conf):
    if a == b: return a
    if base is M and a is M and b is not M: return adopt(b, path, conf)
    if base == a: return b
    if base == b: return a
    if a is M or b is M or base is M and not (isinstance(a, (dict, list)) and type(a) == type(b)):
        if a is M: conf.append((path, 'deleted by ours, changed by theirs')); return M
        if b is M: conf.append((path, 'deleted by theirs, changed by ours -> DELETED (follow theirs)')); return M
    if all(isinstance(x, list) and all(isinstance(i, str) for i in x) for x in (base, a, b)):
        rem = [i for i in base if i not in b]; add = [i for i in b if i not in base]
        conf.append((path, f'both changed (string list): merged (theirs removed {len(rem)}, added {len(add)}; ours kept)'))
        return [i for i in a if i not in rem] + [i for i in add if i not in a]
    if isinstance(a, str) and isinstance(b, str) and isinstance(base, str):
        r = line_merge(base, a, b)
        if r is not None: conf.append((path, 'both changed (str): line-merged cleanly (their lines + ours)')); return r
    if isinstance(a, dict) and isinstance(b, dict):
        bb = base if isinstance(base, dict) else {}
        out = {}
        for k in list(a) + [k for k in b if k not in a] + [k for k in bb if k not in a and k not in b]:
            r = m3(bb.get(k, M), a.get(k, M), b.get(k, M), f'{path}/{k}', conf)
            if r is not M: out[k] = r
        return out
    if isinstance(a, list) and isinstance(b, list) and isid(a + b):
        bl = base if isinstance(base, list) and isid(base) else []
        bm, am, tm = {x['id']: x for x in bl}, {x['id']: x for x in a}, {x['id']: x for x in b}
        order = [x['id'] for x in a] + [i for i in (x['id'] for x in b) if i not in am]
        out = []
        for i in order:
            nm = (am.get(i) or tm.get(i) or {}); nm = nm.get('componentName') or nm.get('propertyName') or i
            # MOVED components: theirs re-parented an existing component (wrapped it in a new container, moved it to another panel).
            # Gone from this list but alive elsewhere in their form -> not a deletion: drop it here, its new place carries it.
            if i in am and i not in tm and i in CTX['theirs']:
                conf.append((f'{path}[{nm}]', 'moved by theirs to another parent: dropped here, merged at its new place')); continue
            # Arrived here from elsewhere (it exists in base and in ours): merge base/ours/theirs so OUR reconciled version is kept, not their raw copy.
            if i in tm and i not in am and i in CTX['ours'] and i in CTX['base']:
                r = m3(CTX['base'][i], CTX['ours'][i], tm[i], f'{path}[{nm}]', conf)
                conf.append((f'{path}[{nm}]', 'moved here by theirs: our reconciled version merged with theirs changes'))
                if r is not M: out.append(r)
                continue
            r = m3(bm.get(i, M), am.get(i, M), tm.get(i, M), f'{path}[{nm}]', conf)
            if r is not M: out.append(r)
        return out
    if any(t and t in path for t in THEIRS_WINS): conf.append((path, 'both changed: THEIRS taken')); return b
    conf.append((path, 'both changed (' + type(a).__name__ + '): ours kept')); return a


def hascomp(v):
    if isinstance(v, dict): return bool(v.get('id') and v.get('type')) or any(hascomp(x) for x in v.values())
    if isinstance(v, list): return any(hascomp(x) for x in v)
    return False


def comp_index(m):
    out = {}
    def w(o):
        if isinstance(o, dict):
            if o.get('id') and o.get('type'): out[o['id']] = o
            for v in o.values(): w(v)
        elif isinstance(o, list):
            for v in o: w(v)
    w(m); return out


def _scripts_agree(b, cur, t):
    """True when a string attribute both sides changed already contains their change (an earlier line merge): not a conflict."""
    return all(isinstance(x, str) for x in (b, cur, t)) and line_merge(b, cur, t) == cur


def attr_pass(merged, base, theirs, conf):
    """Theirs attribute changes by component id, wherever the component sits in the reconciled form."""
    B, T, n = comp_index(base), comp_index(theirs), 0
    for cid, c in comp_index(merged).items():
        if cid not in B or cid not in T: continue
        b, t = B[cid], T[cid]
        for k in set(b) | set(t):
            if k in ('components', 'version') or hascomp(b.get(k)) or hascomp(t.get(k)): continue
            if b.get(k, M) == t.get(k, M): continue
            cur = c.get(k, M)
            if isid(b.get(k)) and isid(t.get(k)) and isinstance(cur, list):     # lists of id'd items (button group items ...): keyed merge
                r = m3(b[k], cur, t[k], f'[{c.get("componentName") or cid}]/{k}', conf)
                if r != cur: c[k] = r; n += 1
                continue
            if cur == t.get(k, M): continue
            if cur == b.get(k, M):
                if t.get(k, M) is M: c.pop(k, None)
                else: c[k] = t[k]
                n += 1
            elif not _scripts_agree(b.get(k), cur, t.get(k)): conf.append((f'[{c.get("componentName") or c.get("propertyName") or cid}]/{k}', 'both changed (attr): ours kept'))
    return n


def name_pass(merged, base, theirs, conf):
    """attr_pass matches by id; a reconciled component whose id was regenerated is matched by (type, componentName) instead."""
    B, T, n = comp_index(base), comp_index(theirs), 0
    mi = comp_index(merged); by_name = {}
    for c in mi.values(): by_name.setdefault((c.get('type'), c.get('componentName') or c.get('propertyName')), []).append(c)
    for cid, t in T.items():
        if cid in mi or cid not in B: continue
        b = B[cid]; cands = by_name.get((t.get('type'), t.get('componentName') or t.get('propertyName')), [])
        if len(cands) != 1: continue
        c = cands[0]
        for k in set(b) | set(t):
            if k in ('components', 'version', 'id', 'parentId') or hascomp(b.get(k)) or hascomp(t.get(k)): continue
            if b.get(k, M) == t.get(k, M): continue
            cur = c.get(k, M)
            if cur == t.get(k, M): continue
            if cur == b.get(k, M):
                if t.get(k, M) is M: c.pop(k, None)
                else: c[k] = t[k]
                n += 1
            elif not _scripts_agree(b.get(k), cur, t.get(k)): conf.append((f'[{c.get("componentName") or cid}]/{k}', 'both changed (attr, matched by name): ours kept'))
    return n


CTX = {'base': {}, 'ours': {}, 'theirs': {}}     # component indexes of the form being merged (to tell a MOVE from a delete + add)


def merge_form(base, ours, theirs):
    conf = []
    CTX['base'], CTX['ours'], CTX['theirs'] = comp_index(base), comp_index(ours), comp_index(theirs)
    merged = m3(base, ours, theirs, '', conf)
    k = attr_pass(merged, base, theirs, conf); k2 = name_pass(merged, base, theirs, conf)
    return merged, conf, k, k2


def delta(base, theirs):
    """Component-level delta base -> theirs: [(kind, type, name, id, changed attrs)]."""
    B, T = comp_index(base), comp_index(theirs); out = []
    for k in T:
        if k not in B: out.append(('ADDED', T[k].get('type'), T[k].get('componentName') or T[k].get('propertyName'), k, []))
    for k in B:
        if k not in T: out.append(('REMOVED', B[k].get('type'), B[k].get('componentName') or B[k].get('propertyName'), k, []))
    for k in T:
        if k in B and T[k] != B[k]:
            ch = sorted(a for a in set(T[k]) | set(B[k]) if a != 'components' and T[k].get(a) != B[k].get(a))
            if ch: out.append(('CHANGED', T[k].get('type'), T[k].get('componentName') or T[k].get('propertyName'), k, ch))
    return out


# ---------------------------------------------------------------- CLI
def opt(a, n, d=None): return a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d


def merge_dir(*parts):
    return project.work_path('merge', *parts, mkdir=False)


def load_raw(side, module, form):
    p = os.path.join(merge_dir(side, safe(module or '_nomodule')), safe(form) + '.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def selection(a):
    path = os.path.join(merge_dir(), 'branch_changed.json')
    if not os.path.exists(path):
        path = os.path.join(merge_dir(), 'sprint_changed.json')   # the old file name
    sc = project.read_json(path, {}) or {}
    if '--all' in a: names = [n for n, r in sc.items() if r.get('changed')]
    else: names = [x for x in opt(a, '--forms', '').split(',') if x]
    if not names: print('nothing selected: pass --forms a,b or --all (after `shrec.py branch-changed --extract`)'); sys.exit(1)
    return names, sc


def cmd_delta(a):
    names, sc = selection(a); full = '--full' in a
    for n in names:
        mod = opt(a, '--module') or (sc.get(n) or {}).get('module', '')
        base, theirs = load_raw('base', mod, n), load_raw('theirs', mod, n)
        if theirs is None: print(f'{n}: no raw export under {merge_dir()} (run `shrec.py branch-changed --extract`)'); continue
        if base is None: print(f'{n}: NEW form ({len(comp_index(theirs))} components)'); continue
        B, T = comp_index(base), comp_index(theirs)
        print(f'{n}: components {len(B)} -> {len(T)}')
        for kind, ty, nm, cid, ch in delta(base, theirs):
            print(f'  {kind:8} {ty} {nm} {cid[:10]}' + (' | ' + ', '.join(ch)[:200] if ch else ''))
            if full and kind == 'CHANGED':
                for k in ch: print('      ', k, ':', json.dumps(B[cid].get(k), ensure_ascii=False)[:200], '->', json.dumps(T[cid].get(k), ensure_ascii=False)[:300])
        fb, ft = base.get('formSettings', {}), theirs.get('formSettings', {})
        for k in sorted(set(fb) | set(ft)):
            if fb.get(k) != ft.get(k): print('  ~ formSettings.' + k, '|', json.dumps(fb.get(k))[:120], '->', json.dumps(ft.get(k))[:200])
    return 0


def ours_loader(spec):
    """(module, name) -> markup | None for a form: 'same' = the target row itself (handled inside the transform), a role, or dir:<path>."""
    if spec == 'same': return None
    if spec.startswith('dir:'):
        root = spec[4:]
        def f(mod, n):
            p = os.path.join(root, safe(mod or '_nomodule'), safe(n) + '.json')
            if not os.path.exists(p): return None
            d = json.load(open(p, encoding='utf-8')); mk = d.get('markup', d) if isinstance(d, dict) else d
            return json.loads(mk) if isinstance(mk, str) else mk
        return f
    require(spec in project.ROLES, '--ours is same, local, deployed, reference or dir:<path>')
    from core.api import FORMS, modname
    from tools.snapshot import fetch_rows
    api, items, _ = fetch_rows(spec)
    idx = {((modname(i) or '').strip(), (i.get('name') or '').strip()): i for i in items}
    def f(mod, n):
        i = idx.get((mod, n.strip()))
        if not i: return None
        mk = i.get('markup') or api.get(FORMS + '/Get', id=i['id'])['result']['markup']
        return json.loads(mk) if isinstance(mk, str) else mk
    return f


def cmd_merge(a):
    global THEIRS_WINS
    THEIRS_WINS = [x for x in (opt(a, '--theirs-wins') or '').split('|') if x]
    names, sc = selection(a); push = '--push' in a
    role = opt(a, '--target', os.environ.get('SHREC_TARGET', 'local')); require(role in ('local', 'deployed'), '--target is local or deployed')
    os.environ['SHREC_TARGET'] = role
    from core import push as pushmod
    from core.api import fetch_forms, modname
    loader = ours_loader(opt(a, '--ours', 'same'))
    prefer = opt(a, '--prefer-module') or opt(a, '--prefer-override')
    _, titems = fetch_forms(role); have = {((modname(i) or '').strip(), (i.get('name') or '').strip()) for i in titems}
    def src_mod(n): return opt(a, '--module') or (sc.get(n) or {}).get('module', '')
    def tmod_of(n):
        mod = src_mod(n)
        return prefer if prefer and mod != prefer and (prefer, n.strip()) in have else mod
    if push:   # whole-run snapshot of every form this run may write, + manifest, BEFORE the first write
        todo = [(tmod_of(n), n.strip()) for n in names if load_raw('base', src_mod(n), n) is not None]
        print('snapshot dir:', pushmod.begin_run([t for t in todo if t in have], rule='merge3', role=role))
    results = []
    for n in names:
        mod = src_mod(n)
        base, theirs = load_raw('base', mod, n), load_raw('theirs', mod, n)
        tmod = tmod_of(n)
        if tmod != mod: print(f'   ({n}: theirs edited {mod}/{n}; applying it to the {tmod} override)')
        if theirs is None: print(f'== {n}: no raw export (run `shrec.py branch-changed --extract`)'); continue
        if base is None: print(f'== {n} [{mod}]: NEW form - the backend import already created it from the package; run the reconcile rules on it'); continue
        ours_other = loader(tmod, n) if loader else None
        state = {}

        def transform(markup, _n=n, _o=ours_other, _s=state, _t=tmod, _b=base, _th=theirs):
            ours = _o if _o is not None else json.loads(json.dumps(markup))
            merged, conf, k, k2 = merge_form(_b, ours, _th)
            _s.update(conf=conf, k=k, k2=k2)
            print(f'== {_n} [{_t}]: attribute pass {k} (+{k2} by name) | notes/conflicts {len(conf)}')
            for c in conf[:30]: print('   !', c[0][-190:], '-', c[1])
            if merged == markup: return []
            markup.clear(); markup.update(merged)
            return [f'three-way merge of the pre-upgrade change onto the reconciled form ({len(conf)} notes)']
        try:
            notes = pushmod.push(tmod, n, transform, dry_run=not push, role=role, rule='merge3')
            results.append((n, bool(notes), sum(1 for c in state.get('conf', []) if 'kept' in c[1] or 'conflict' in c[1].lower())))
        except Exception as e:
            print(f'== {n}: SKIPPED - {type(e).__name__}: {str(e)[:200]}'); results.append((n, False, -1))
    changed = sum(1 for r in results if r[1])
    print(('DRY RUN - ' if not push else '') + f'{changed} of {len(results)} forms would change/changed; forms with kept-ours conflicts to review: '
          f'{[r[0] for r in results if r[2] > 0]}; skipped: {[r[0] for r in results if r[2] == -1]}')
    ledger.event('summary', env=role, script='shrec merge3', dry=not push, rules=['merge3'], forms_changed=changed, of=len(results),
                 failed=[r[0] for r in results if r[2] == -1])
    return 1 if any(r[2] == -1 for r in results) else 0


def main(argv):
    if argv[:1] == ['delta']: return cmd_delta(argv[1:])
    if argv[:1] == ['merge']: return cmd_merge(argv[1:])
    print(__doc__)
    return 2
