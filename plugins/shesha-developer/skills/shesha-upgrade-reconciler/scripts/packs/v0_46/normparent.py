"""Rule `normparent` (H47): every component's parentId names the container that really holds it in the markup tree.

Symptom on 0.46: after someone opens and saves the form in the designer, a component jumps into a different container
(for example a panel that a merge placed correctly but whose parentId still names its old container renders under the
page content). Read-back equality, "forms changed 0" and component counts all pass while this is waiting to happen.
Cause: 0.43 renders by NESTING and ignores `parentId`; the 0.46 designer rebuilds the tree from `parentId` on save.

What counts as "the holder":
  - the markup root holds its children as parentId 'root';
  - any `components` list belongs to the nearest enclosing dict that has an `id`: a component (container,
    datatableContext ...), a tab pane (`tabs[]`), a column (`columns[]`), a wizard step or a panel part (`header` /
    `content` / `customHeader`);
  - collapsiblePanel / columns children are stored with the part's id (dominant 0.46 shape) AND, in forms never re-saved by
    the 0.46 designer, with the owning component's id: both are accepted, only an id that names neither is stale;
  - a component that appears in two lists (the legacy duplicate list kept on `columns` / `collapsiblePanel`) is fine when
    its parentId matches ANY of its places;
  - a component with NO parentId is left alone, and keys starting with '_' (the `_reconcilerOriginal` stash) are not
    part of the tree.

Writes: only the `parentId` string. It never moves, copies or deletes a component and never adds a missing parentId.
Idempotent: after a run every parentId is in its accepted set.
Marker: none.  Options: none.  `analyse(markup)` is the read-only half (for detectors).
"""
from packs.v0_46.common import flush

ROOT = 'root'
OWNER_ACCEPTED = {'collapsiblePanel', 'columns'}   # parentId may also name the owning component (see above)


def _scan(o, holder, encl, out, is_root=False):
    """holder: id string / ROOT / None (unknown: skip); encl: nearest enclosing component dict (has `type` and `id`) or None."""
    if isinstance(o, dict):
        is_comp = 'type' in o and isinstance(o.get('id'), str)
        if is_root:
            h = ROOT
        elif isinstance(o.get('id'), str):
            h = o['id']
        else:
            h = None
        if is_comp:
            encl = o
        pane_like = (not is_comp) and h not in (None, ROOT)
        for k, v in o.items():
            if k.startswith('_') or not isinstance(v, (dict, list)):
                continue
            if k == 'components' and isinstance(v, list) and h is not None:
                accept = {h}
                if pane_like and encl is not None and encl.get('type') in OWNER_ACCEPTED:
                    accept.add(encl['id'])
                siblings = [c for c in v if isinstance(c, dict) and 'type' in c and isinstance(c.get('id'), str)]
                for c in siblings:
                    out.append({'comp': c, 'holder': h, 'accept': accept, 'pane_like': pane_like, 'siblings': siblings})
            _scan(v, h, encl, out)
    elif isinstance(o, list):
        for v in o:
            _scan(v, holder, encl, out)


def placements(markup):
    out = []
    if isinstance(markup, dict):
        _scan(markup, ROOT, None, out, is_root=True)
    return out


def _expected(p):
    """parentId to write for a placement: the holder, except that for panel/column children the form's own sibling convention wins."""
    if len(p['accept']) == 1:
        return p['holder']
    votes = {}
    for s in p['siblings']:
        pid = s.get('parentId')
        if pid in p['accept']:
            votes[pid] = votes.get(pid, 0) + 1
    if votes:
        best = max(votes.values())
        winners = [k for k, v in votes.items() if v == best]
        if len(winners) == 1:
            return winners[0]
    return p['holder']


def analyse(markup):
    """Read-only. [{'comp', 'current', 'expected', 'holder', 'accepted'}] for every component whose parentId names nothing that holds it."""
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
        out.append({'comp': c, 'current': pid, 'expected': _expected(canon[c['id']]), 'holder': canon[c['id']]['holder'],
                    'accepted': sorted(accepted[c['id']])})
    return out


def _short(i):
    return str(i)[:8] + ('..' if len(str(i)) > 8 else '')


def apply_all(markup, notes):
    """Normalise every stale parentId in place; one note per fixed component. Returns the number of components changed."""
    n = 0
    for s in analyse(markup):
        c = s['comp']
        c['parentId'] = s['expected']
        n += 1
        notes.append(f'{c.get("componentName") or c.get("propertyName") or c.get("type")} ({c.get("type")}): parentId {_short(s["current"])} -> '
                     f'{_short(s["expected"])} (the container that holds it; stale id would re-nest it on a designer save, H47)')
    return n


def apply(ctx, markup):
    notes = []
    n = apply_all(markup, notes)
    flush(ctx, notes)
    return n
