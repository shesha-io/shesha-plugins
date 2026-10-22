"""Side-by-side geometry of one page on two roles (headless, read-only, write-guarded).

  shrec.py compare <page path> [--labels] [--roles reference,local] [--selector CSS] [--wait ms] [--viewport 1600x1000]

<page path> is a portal path such as /dynamic/<module>/<form>?id=<record id> (use a record that exists in BOTH databases).
Portal bases come from project.json environments.<role>.portal. The first role is the baseline, the second is compared to it.

Default: label/value geometry of every form item - label right edge, control left/right edge, top and item height, relative to the
first tab set - and the number of inner scrollers. Prints one row per label with the dx / dy deltas.
--labels: label column width, label width, number of text lines, item height, font and padding per form item (finds wrapped or
clipped labels).

Output: <work>/sweep/cmp-<slug>.json (<slug>-labels for --labels) and a screenshot per role <work>/sweep/cmp-<role>-<slug>.png.
Same viewport on both roles: a comparison at different sizes is meaningless.
"""
import argparse
import json
import os
import re

from core import project
from core.browse import session, settle

GEOMETRY_JS = """() => { const vis=e=>e.offsetParent&&e.getBoundingClientRect().height>0; const root=document.querySelector('.ant-tabs')||document.body; const R=root.getBoundingClientRect();
 const items=[...document.querySelectorAll('.ant-form-item')].filter(vis).map(it=>{const l=it.querySelector('.ant-form-item-label label'); const c=it.querySelector('.ant-form-item-control'); if(!l||!c) return null; const lr=l.getBoundingClientRect(), cr=c.getBoundingClientRect();
   return [l.textContent.trim().slice(0,40), Math.round(lr.right-R.left), Math.round(cr.left-R.left), Math.round(cr.right-R.left), Math.round(lr.top-R.top), Math.round(it.getBoundingClientRect().height)]}).filter(Boolean);
 const scrollers=[...document.querySelectorAll('*')].filter(e=>{const s=getComputedStyle(e); return /(auto|scroll)/.test(s.overflowX) && e.scrollWidth>e.clientWidth+1;}).length;
 return {tabsX: Math.round(R.left), tabsW: Math.round(R.width), scrollers, items}; }"""

LABELS_JS = """() => { const vis=e=>e.offsetParent&&e.getBoundingClientRect().height>0;
 return [...document.querySelectorAll('.ant-form-item')].filter(vis).map(it=>{ const lc=it.querySelector('.ant-form-item-label'); const l=lc&&lc.querySelector('label'); if(!l) return null;
   const range=document.createRange(); range.selectNodeContents(l); const rects=[...range.getClientRects()]; const lines=new Set(rects.map(r=>Math.round(r.top))).size;
   const s=getComputedStyle(l), cs=getComputedStyle(lc);
   return [l.textContent.trim().slice(0,34), Math.round(lc.getBoundingClientRect().width), Math.round(l.getBoundingClientRect().width), lines, Math.round(it.getBoundingClientRect().height), s.fontSize, s.fontWeight, s.fontFamily.split(',')[0], cs.paddingRight, cs.flex.slice(0,12), Math.round(it.getBoundingClientRect().width)]; }).filter(Boolean); }"""


def slug_of(path):
    p = re.sub(r'^https?://[^/]+', '', path).split('?')[0]
    p = re.sub(r'^/?dynamic/', '', p).strip('/')
    return re.sub(r'[^\w.-]', '_', p.replace('/', '__')) or 'page'


def geometry_rows(base, other, limit=40):
    """[(label, base row | None, other row | None, (dx_label_right, dx_ctl_left, dx_ctl_right, dy) | None)] - pure function."""
    om = {}
    for it in other['items']:
        om.setdefault(it[0], it)
    rows = []
    for it in base['items'][:limit]:
        o = om.get(it[0])
        rows.append((it[0], it[1:], o[1:] if o else None, (o[1] - it[1], o[2] - it[2], o[3] - it[3], o[4] - it[4]) if o else None))
    return rows


def label_rows(base, other, limit=30):
    """[(label, base row, other row)] for labels present on both - pure function."""
    om = {}
    for r in other:
        om.setdefault(r[0], r)
    return [(r[0], r, om[r[0]]) for r in base[:limit] if r[0] in om]


def main(argv):
    ap = argparse.ArgumentParser(prog='shrec compare', description=__doc__.split('\n')[0])
    ap.add_argument('path', help='portal path, e.g. /dynamic/<module>/<form>?id=<id>')
    ap.add_argument('--labels', action='store_true', help='label column widths / line counts instead of control geometry')
    ap.add_argument('--roles', default='reference,local', help='baseline,compared (default reference,local)')
    ap.add_argument('--selector', default='.ant-form-item-label', help='CSS selector to wait for')
    ap.add_argument('--wait', type=int, default=None, help='settle time in ms (default 8000, 12000 with --labels)')
    ap.add_argument('--viewport', default='1600x1000')
    a = ap.parse_args(argv)
    roles = [r.strip() for r in a.roles.split(',') if r.strip()]
    if len(roles) != 2 or any(r not in project.ROLES for r in roles):
        ap.error('--roles needs exactly two of: ' + ', '.join(project.ROLES))
    w, h = (int(x) for x in a.viewport.lower().split('x'))
    wait = a.wait if a.wait is not None else (12000 if a.labels else 8000)
    slug = slug_of(a.path)
    out_dir = project.work_path('sweep', mkdir=False)
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for role in roles:
        with session(role, {}, viewport=(w, h)) as pg:
            pg.goto(a.path, timeout=180000)
            try:
                pg.wait_for_selector(a.selector, timeout=180000)
            except Exception:
                pass
            settle(pg, wait)
            out[role] = pg.evaluate(LABELS_JS if a.labels else GEOMETRY_JS)
            pg.screenshot(path=os.path.join(out_dir, f'cmp-{role}-{slug}.png'))
    b, o = roles
    if a.labels:
        print(f'{"label":34} | {b}: colW lblW lines itemH font | {o}: colW lblW lines itemH font | itemW {b}/{o}')
        for lab, r, x in label_rows(out[b], out[o]):
            print(f'{lab:34} | {r[1]:4} {r[2]:4} {r[3]} {r[4]:3} {r[5]} {r[6]} {r[7][:10]} pr{r[8]} | '
                  f'{x[1]:4} {x[2]:4} {x[3]} {x[4]:3} {x[5]} {x[6]} {x[7][:10]} pr{x[8]} | {r[10]}/{x[10]}')
        fname = f'cmp-{slug}-labels.json'
    else:
        pb, po = out[b], out[o]
        print(f'tabs x/w  {b}', pb['tabsX'], pb['tabsW'], f'| {o}', po['tabsX'], po['tabsW'], f'| scrollers {b}', pb['scrollers'], o, po['scrollers'])
        print(f'{"label":40} {b + " lblR ctlL ctlR top h":>26} | {o:>24} | dx')
        for lab, r, x, d in geometry_rows(pb, po):
            if x is None:
                print(f'{lab:40} {str(r):>26} | missing')
            else:
                print(f'{lab:40} {str(r):>26} | {str(x):>24} | {d[0]:+d} {d[1]:+d} {d[2]:+d} dy{d[3]:+d}')
        fname = f'cmp-{slug}.json'
    with open(os.path.join(out_dir, fname), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, indent=1)
    print('written:', os.path.join(out_dir, fname))
    return 0
