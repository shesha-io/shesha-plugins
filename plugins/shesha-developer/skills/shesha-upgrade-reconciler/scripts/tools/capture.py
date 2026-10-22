"""Page sweep (read-only, write-guarded browser): render each page of the project's pages file on one role, take a full-page
screenshot of the page and of each top-level tab (and each tab of the first nested tab set) and run the DEFECTS probe on each.

  shrec.py capture <reference|local|deployed> [start] [end]

Pages: project.json "pages" (a file name relative to .shesha-reconcile/, default pages.json): a JSON list of
{"module": "<Configuration.Module>", "form": "<form name>", "id": "<record id>" | "-"}. The route is
/dynamic/<module>/<form>?id=<id> ("-" = no id). The same ids must exist in both databases for a side-by-side comparison.
Viewport: project option `viewport` ([width, height], default [1568, 950]).

Output: <work>/sweep/<role>/<module>__<form>[-t<k>[-s<j>]].png and <module>__<form>.json. The json holds url, main (the probe of
the page), tabs [{i, label, defects, sub: [{j, label, defects}]}], console (errors) and error. The reconciliation-assessor agent
consumes the probe fields: labelOverflow, scrollers, textareaScroll, tags, refListStatus, htmlRenderEmpty, htmlRenders, empty32,
panels, buttonsEmpty, statistics, placeholdersNoData, errors, docH, labelCount.
"""
import json
import os
import re
import sys

from core import project
from core.browse import session, settle as _settle

DEFECTS = r"""() => {
 const vis = e => e && e.offsetParent && e.getBoundingClientRect().height > 0;
 const nm = e => { const c = e.closest('[data-sha-c-name]'); return c ? c.dataset.shaCName : null; };
 const o = {};
 const labels = [...document.querySelectorAll('.ant-form-item-label label')].filter(vis);
 o.labelCount = labels.length;
 o.labelOverflow = labels.filter(l => l.scrollHeight > l.clientHeight + 2).map(l => l.textContent.trim().slice(0, 60));
 o.scrollers = [...document.querySelectorAll('*')].filter(e => { if (!vis(e)) return false; const s = getComputedStyle(e);
     const x = /(auto|scroll)/.test(s.overflowX) && e.scrollWidth > e.clientWidth + 1, y = /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1 && e.clientHeight < 700;
     return (x || y) && !e.matches('.ant-table-body,.ant-table-content,.ant-select-selector,textarea'); })
   .slice(0, 15).map(e => ({ name: nm(e), cls: String(e.className).split(' ')[0], x: e.scrollWidth - e.clientWidth, y: e.scrollHeight - e.clientHeight, h: e.clientHeight }));
 o.textareaScroll = [...document.querySelectorAll('textarea')].filter(vis).filter(t => t.scrollHeight > t.clientHeight + 2).length;
 o.tags = [...document.querySelectorAll('.ant-tag')].filter(vis).map(t => t.textContent.trim()).filter(Boolean).slice(0, 30);
 o.refListStatus = [...document.querySelectorAll('[data-sha-c-type="refListStatus"]')].map(e => ({ name: e.dataset.shaCName, h: Math.round(e.getBoundingClientRect().height), text: (e.innerText || '').trim().slice(0, 30), shown: vis(e) }));
 o.htmlRenderEmpty = [...document.querySelectorAll('[data-sha-c-type="htmlRender"]')].filter(e => e.querySelector('.ant-empty') || /provide some content/i.test(e.innerText || '')).map(e => e.dataset.shaCName);
 o.htmlRenders = [...document.querySelectorAll('[data-sha-c-type="htmlRender"]')].filter(vis).map(e => ({ name: e.dataset.shaCName, w: Math.round(e.getBoundingClientRect().width), h: Math.round(e.getBoundingClientRect().height), mb: getComputedStyle(e).marginBottom })).slice(0, 25);
 o.empty32 = [...document.querySelectorAll('.sha-components-container')].filter(vis).filter(e => Math.round(e.getBoundingClientRect().height) === 32 && !(e.innerText || '').trim() && !e.querySelector('input,button,img,svg,.ant-tag')).length;
 o.panels = [...document.querySelectorAll('.ant-collapse-header')].filter(vis).slice(0, 12).map(h => { const s = getComputedStyle(h); return { title: h.innerText.trim().slice(0, 40), h: Math.round(h.getBoundingClientRect().height), pad: s.padding, bt: s.borderTopWidth + ' ' + s.borderTopColor, fw: getComputedStyle(h.querySelector('.ant-collapse-title') || h).fontWeight }; });
 o.buttonsEmpty = [...document.querySelectorAll('.ant-btn')].filter(vis).filter(b => !(b.innerText || '').trim() && !b.querySelector('svg,img,.anticon')).length;
 o.statistics = [...document.querySelectorAll('[data-sha-c-type="statistic"], [data-sha-c-type="kpi"], [data-sha-c-type="card"]')].filter(vis).slice(0, 12).map(e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e.firstElementChild || e); return { type: e.dataset.shaCType, name: e.dataset.shaCName, x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), bl: s.borderLeftWidth + ' ' + s.borderLeftColor }; });
 o.placeholdersNoData = [...document.querySelectorAll('.ant-empty-description')].filter(vis).map(e => (nm(e) || '?') + ':' + e.textContent.trim()).slice(0, 12);
 o.errors = [...document.querySelectorAll('.ant-alert-error,.ant-result-error,.ant-result-warning')].filter(vis).map(e => e.innerText.trim().slice(0, 120));
 o.docH = Math.max(document.documentElement.scrollHeight, ...[...document.querySelectorAll('.ant-layout-content *')].slice(0, 3).map(e => e.scrollHeight));
 return o; }"""


def settle(pg, wait):
    """Fixed wait plus a SHORT network-idle wait: SignalR keeps the network busy, so a long idle wait always times out."""
    _settle(pg, wait, idle=4000)


def tabs_of(pg, nth_set):
    return pg.locator('.ant-tabs').nth(nth_set).locator(':scope > .ant-tabs-nav .ant-tabs-tab')


def pages_file():
    name = project.config().get('pages') or 'pages.json'
    return name if os.path.isabs(name) else os.path.join(project.home(), name)


def load_pages():
    path = pages_file()
    pages = project.read_json(path)
    if not isinstance(pages, list) or not pages:
        raise project.ConfigError(f'{path} is missing or not a non-empty JSON list of {{module, form, id}} (see assets/pages.example.json)')
    return [p for p in pages if isinstance(p, dict) and p.get('module') and p.get('form')]


def page_url(p):
    rid = p.get('id') or '-'
    return f"/dynamic/{p['module']}/{p['form']}" + (f'?id={rid}' if rid != '-' else '')


def page_tag(p):
    return re.sub(r'[^\w.-]', '_', f"{p['module']}__{p['form']}")


def viewport():
    vp = project.option('viewport', [1568, 950])
    try:
        return int(vp[0]), int(vp[1])
    except (TypeError, ValueError, IndexError):
        return 1568, 950


def main(argv):
    if not argv or argv[0] not in project.ROLES:
        print(__doc__)
        return 2
    role = argv[0]
    pages = load_pages()
    a = int(argv[1]) if len(argv) > 1 else 0
    b = int(argv[2]) if len(argv) > 2 else len(pages)
    out = project.work_path('sweep', role, mkdir=False)
    os.makedirs(out, exist_ok=True)
    vp = viewport()
    failures = 0
    for p in pages[a:b]:
        tag = page_tag(p)
        log = {}
        try:
            with session(role, log, viewport=vp) as pg:
                pg.goto(page_url(p), timeout=180000)
                try:
                    pg.wait_for_selector('.sha-form, .ant-table, .ant-result', timeout=120000)
                except Exception:
                    pass
                settle(pg, 7000)
                pg.screenshot(path=f'{out}/{tag}.png', full_page=True)
                log['url'] = pg.url
                log['main'] = pg.evaluate(DEFECTS)
                log['tabs'] = []
                t0 = tabs_of(pg, 0)
                n = t0.count()
                for k in range(min(n, 8)):
                    try:
                        lab = t0.nth(k).inner_text().strip()
                        t0.nth(k).click()
                        settle(pg, 3500)
                        pg.screenshot(path=f'{out}/{tag}-t{k}.png', full_page=True)
                        entry = {'i': k, 'label': lab, 'defects': pg.evaluate(DEFECTS), 'sub': []}
                        if pg.locator('.ant-tabs').count() > 1:       # the first nested tab set inside the active pane
                            t1 = tabs_of(pg, 1)
                            for j in range(1, min(t1.count(), 7)):    # tab 0 is already shown
                                try:
                                    l2 = t1.nth(j).inner_text().strip()
                                    t1.nth(j).click()
                                    settle(pg, 3000)
                                    pg.screenshot(path=f'{out}/{tag}-t{k}-s{j}.png', full_page=True)
                                    entry['sub'].append({'j': j, 'label': l2, 'defects': pg.evaluate(DEFECTS)})
                                except Exception as e:
                                    entry.setdefault('subErrors', []).append(str(e)[:150])
                        log['tabs'].append(entry)
                    except Exception as e:
                        log.setdefault('tabErrors', []).append(f'{k}: {e}'[:200])
        except Exception as e:
            log['error'] = str(e)[:300]
        log['console'] = [c for c in log.get('console', []) if 'error' in c][:30]
        failures += 1 if log.get('error') else 0
        with open(f'{out}/{tag}.json', 'w', encoding='utf-8', newline='\n') as f:
            json.dump(log, f, indent=1)
        print(role, tag, 'ERR' if log.get('error') else 'ok', len(log.get('tabs', [])), 'tabs', flush=True)
    return 1 if failures else 0
