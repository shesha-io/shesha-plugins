"""REQUEST AUDIT (read-only): what does the page really ask the API for, and what does it get back?  Definition-of-Done items request-audit
and data-audit.

  shrec.py audit-requests <page-path-or-url> [--role local|deployed|reference] [--loads 3] [--viewport 1700x1000] [--wait 12000]
         [--match <regex>] [--all-api] [--expect-parent <id>] [--parent-field parentId]
         [--rows-selector <css>] [--db-count-url <api path with query>] [--full] [--json <file>]

Loads the page N times (default 3), EACH in a brand-new browser context (no cached markup, no IndexedDB: a real user's browser keeps old
markup there). Every XHR/fetch to /api/ that matches --match (default: GetAll, /Crud/, /Query, /List, /Search, /Count; --all-api shows every
/api/ XHR) is listed, NEVER de-duplicated by path (a datalist makes two requests: the first with properties=id, the second with the full
projection; a de-duplicated capture hides the second one). For each request it prints the raw URL, the decoded query parameters, the HTTP
status, the response shape and the item count, and flags:

  NO FILTER             a list request without `filter`: it returns every row of the entity (data exposure, H50)
  NO SORTING            a list request without `sorting`: the order is undefined
  TRIMMED PROPERTIES    `properties` cut to id (+ the sort field): rows get no other field and render empty or with defaults (H50, H52, H53);
                        ONLY-TRIMMED when every request of that path in the load is trimmed; a trimmed first request followed by a full one is the
                        normal two-phase fetch and is reported as info
  FILTER LACKS PARENT   with --expect-parent: the filter text never mentions that record id
  PARENT MISMATCH       with --expect-parent: rows whose <parent-field> (dotted paths allowed) differs from it = rows that belong to
                        other records (a DATA LEAK); rows that lack the field are counted separately
  LOAD DIFFERS (H53)    the set of requests / statuses / item counts of load 1 differs from a later load (the first load after a push can
                        look right and every later one wrong; never accept a first-load result)
  ROWS VS DB            --rows-selector counts the rendered rows (e.g. '[data-sha-datalist-item-type]'); --db-count-url (a GET on the role's API,
                        e.g. '/api/dynamic/<module>/<entity>/Crud/GetAll?filter=...&maxResultCount=1') gives the database count; they must be equal

Read-only: the browser guard aborts every write; nothing is clicked. Exit code 1 when a flag was raised, 2 when the page produced no
matching request. A clean audit is necessary, not sufficient: also compare with the reference and the rows' content.
Record the outcome with  shrec.py verify --kind request-audit --result ok|fail --detail "<detail>"  and  --kind data-audit ...
"""
import argparse, collections, json, os, re, sys, urllib.parse

DEFAULT_MATCH = r'GetAll|/Crud/|/Query|/List|/Search|/Count'
NOISE = re.compile(r'CheckPermissions|SyncClientApi|signalr|TokenAuth|GetCurrentLoginInfo|GetUserConfig|GetUserValue|GetSettings|FormConfiguration|ConfigurationItem|EntityConfig|ConfigurationStudio|/Metadata', re.I)
VOLATILE = {'_', 'ts', 'timestamp', 't'}
SORT_KEYS = ('sorting', 'sort', 'orderBy', 'order')


def _settle(pg, wait):
    pg.wait_for_timeout(wait)
    try: pg.wait_for_load_state('networkidle', timeout=20000)
    except Exception: pass


def parse_url(url):
    """(path, {param: [values]}) with the query decoded"""
    p = urllib.parse.urlparse(url)
    return p.path, urllib.parse.parse_qs(p.query, keep_blank_values=True)


def describe(body):
    """(shape text, items list or None, totalCount or None)"""
    if body is None: return 'not JSON / unreadable', None, None
    if isinstance(body, dict) and body.get('success') is False:
        err = body.get('error') or {}
        return 'ERROR ' + str((err.get('message') or err.get('details') or err))[:120], None, None
    res = body.get('result') if isinstance(body, dict) and 'result' in body else body
    if isinstance(res, dict) and isinstance(res.get('items'), list):
        keys = list(res['items'][0].keys())[:14] if res['items'] and isinstance(res['items'][0], dict) else []
        return f'result.items[{len(res["items"])}] totalCount={res.get("totalCount")} item keys={keys}', res['items'], res.get('totalCount')
    if isinstance(res, list): return f'result[{len(res)}]', res, None
    if isinstance(res, dict): return 'result{' + ','.join(list(res.keys())[:10]) + '}', None, None
    return f'result={str(res)[:60]}', None, None


def prop_tokens(props):
    """top-level property names of a `properties` value ('id creationTime', 'id name { id }', 'id,name')"""
    s = re.sub(r'\{[^{}]*\}', ' ', props or '')
    return [t for t in re.findall(r'[A-Za-z_][\w.]*', s)]


def sort_fields(params):
    out = set()
    for k in SORT_KEYS:
        for v in params.get(k, []):
            out |= {t for t in re.findall(r'[A-Za-z_][\w.]*', v) if t.lower() not in ('asc', 'desc', 'ascending', 'descending')}
    return out


def get_path(item, dotted):
    cur = item
    for part in dotted.split('.'):
        if isinstance(cur, dict) and part in cur: cur = cur[part]
        else: return None, False
    if isinstance(cur, dict): cur = cur.get('id', cur)
    return cur, True


def is_list_request(path, params, items):
    return items is not None or 'maxResultCount' in params or re.search(r'GetAll|/Query|/List|/Search', path) is not None


def analyse(entry, expect_parent=None, parent_field='parentId'):
    """flags (list of str) for one captured request entry; also sets entry['trimmed'] / entry['listlike']"""
    flags = []
    path, params, items = entry['path'], entry['params'], entry['items']
    entry['listlike'] = is_list_request(path, params, items)
    entry['trimmed'] = False
    if entry['listlike'] and entry['status'] and entry['status'] < 400:
        filt = ' '.join(params.get('filter', [])).strip()
        if filt in ('', '{}', 'null', 'undefined'): flags.append('NO FILTER: returns every row of the entity (possible data exposure)')
        if not any(params.get(k) and ''.join(params[k]).strip() for k in SORT_KEYS): flags.append('NO SORTING: row order is undefined')
        if 'properties' in params:
            toks = prop_tokens(' '.join(params['properties']))
            extra = [t for t in toks if t != 'id' and t not in sort_fields(params)]
            if not toks: flags.append('EMPTY PROPERTIES (properties= with no value)')
            elif not extra: entry['trimmed'] = True; flags.append(f'TRIMMED PROPERTIES: only {toks} (id + sort field): rows get no other field')
        if expect_parent:
            blob = ' '.join(v for vs in params.values() for v in vs)
            if expect_parent.lower() not in blob.lower(): flags.append(f'FILTER LACKS PARENT: no parameter mentions {expect_parent}')
            if items:
                bad, absent, seen = 0, 0, set()
                for it in items:
                    val, present = get_path(it, parent_field)
                    if not present: absent += 1
                    elif str(val).lower() != expect_parent.lower(): bad += 1; seen.add(str(val))
                if bad: flags.append(f'PARENT MISMATCH (DATA LEAK): {bad} of {len(items)} rows have {parent_field} != expected, e.g. {sorted(seen)[:3]}')
                if absent: flags.append(f'PARENT UNKNOWN: {absent} of {len(items)} rows carry no {parent_field} (properties trimmed?)')
    return flags


def signature(e):
    prm = {k: v for k, v in e['params'].items() if k not in VOLATILE}
    return (e['method'], e['path'], json.dumps(prm, sort_keys=True), e['status'], e['count'])


def collect_load(pg, target, wait=12000, match=DEFAULT_MATCH, all_api=False, rows_selector=None):
    """Load `target` on an already open page and return {'entries': [...], 'rows': int|None}. Does NOT de-duplicate."""
    rx = re.compile(match)
    reqs = collections.OrderedDict()

    def on_request(r):
        if r.resource_type in ('xhr', 'fetch') and '/api/' in r.url: reqs[r] = {'method': r.method, 'url': r.url, 'seq': len(reqs) + 1, 'resp': None, 'failed': None}
    def on_response(r):
        if r.request in reqs: reqs[r.request]['resp'] = r
    def on_failed(r):
        if r in reqs: reqs[r]['failed'] = str(r.failure)[:120]
    pg.on('request', on_request); pg.on('response', on_response); pg.on('requestfailed', on_failed)
    pg.goto(target); _settle(pg, wait)
    out = []
    for e in reqs.values():
        path, params = parse_url(e['url'])
        if not all_api and (NOISE.search(e['url']) or not rx.search(e['url'])): continue
        status, body = None, None
        if e['resp'] is not None:
            status = e['resp'].status
            try: body = e['resp'].json()
            except Exception: body = None
        shape, items, total = describe(body)
        out.append({'seq': e['seq'], 'method': e['method'], 'url': e['url'], 'path': path, 'params': params, 'status': status or 'FAILED',
                    'failed': e['failed'], 'shape': shape, 'items': items, 'total': total, 'count': len(items) if items is not None else None})
    rows = None
    if rows_selector:
        try: rows = pg.locator(rows_selector).count()
        except Exception: rows = None
    return {'entries': out, 'rows': rows}


def two_phase_notes(entries):
    """per path: info when a trimmed request is followed by a full one; flag when every request of the path is trimmed"""
    flags, info = [], []
    by = collections.defaultdict(list)
    for e in entries:
        if e['listlike'] and isinstance(e['status'], int) and e['status'] < 400: by[e['path']].append(e)
    for path, es in by.items():
        if all(x['trimmed'] for x in es):
            if any(x['trimmed'] for x in es): flags.append(f'ONLY-TRIMMED: every {path} request of this load has properties cut to id (+ sort field): the rows will render empty')
        else:
            for i, x in enumerate(es):
                if x['trimmed'] and not all(y['trimmed'] for y in es[i + 1:]):    # a later request of this path has the full projection
                    x['flags'] = [f for f in x['flags'] if not f.startswith(('TRIMMED PROPERTIES', 'PARENT UNKNOWN'))]
                    info.append(f'{path}: request #{x["seq"]} is id-only and a later request fetches the full projection (normal datalist two-phase fetch; '
                                'H53: the later response may never reach the rows, so check the rendered rows)')
    return flags, info


def diff_loads(loads):
    """H53: compare load 1 with every later load; returns a list of difference strings"""
    out = []
    base = collections.Counter(signature(e) for e in loads[0]['entries'])
    for k, ld in enumerate(loads[1:], 2):
        cur = collections.Counter(signature(e) for e in ld['entries'])
        only1, onlyk = base - cur, cur - base
        lab = lambda s: f'{s[0]} {s[1]} status {s[3]} items {s[4]} properties={(json.loads(s[2]).get("properties") or ["(none)"])[0][:60]}'
        for s in only1: out.append(f'LOAD DIFFERS (H53): only in load 1, not in load {k}: {lab(s)}')
        for s in onlyk: out.append(f'LOAD DIFFERS (H53): only in load {k}, not in load 1: {lab(s)}')
        if loads[0]['rows'] is not None and ld['rows'] is not None and loads[0]['rows'] != ld['rows']:
            out.append(f'LOAD DIFFERS (H53): rendered rows {loads[0]["rows"]} in load 1 but {ld["rows"]} in load {k}')
    return out


def db_count(env, url):
    """GET the count on the SAME API host as the role (the token is never sent anywhere else). Returns (count, detail)."""
    from core.api import Api
    p = urllib.parse.urlparse(url)
    a = Api(env)
    if p.scheme:
        if urllib.parse.urlparse(a.base).netloc.lower() != p.netloc.lower(): raise SystemExit(f'--db-count-url host {p.netloc} is not the {env} role API host')
    params = {k: v[0] for k, v in urllib.parse.parse_qs(p.query, keep_blank_values=True).items()}
    res = (a.get(p.path, **params) or {}).get('result')
    if isinstance(res, dict):
        if res.get('totalCount') is not None: return int(res['totalCount']), f'totalCount of {p.path}'
        if isinstance(res.get('items'), list): return len(res['items']), f'items of {p.path}'
    if isinstance(res, list): return len(res), f'list of {p.path}'
    if isinstance(res, (int, float)): return int(res), f'value of {p.path}'
    raise SystemExit(f'--db-count-url returned no count: {str(res)[:120]}')


def show_load(k, n, target, ld, full):
    print(f'\n=== LOAD {k}/{n}  (fresh browser context)  {target}')
    if not ld['entries']: print('  (no matching API request)')
    lim = 100000 if full else 600
    for e in ld['entries']:
        print(f'  #{e["seq"]} {e["status"]} {e["method"]} {e["path"]}   {e["shape"]}')
        print(f'      URL: {e["url"] if full else e["url"][:400]}')
        for kk, vs in e['params'].items(): print(f'      {kk} = {" | ".join(vs)[:lim]}')
        if e.get('failed'): print(f'      FAILED: {e["failed"]}')
        for f in e['flags']: print(f'      FLAG {f}')
    for f in ld['flags2']: print(f'  FLAG {f}')
    for f in ld['info']: print(f'  info {f}')
    if ld['rows'] is not None: print(f'  rendered rows ({ld["rows_selector"]}): {ld["rows"]}')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Request audit (read-only). See the module docstring.')
    ap.add_argument('page', help='page path (/dynamic/Module/form?id=..) or full URL')
    ap.add_argument('--role', default='local', choices=['local', 'deployed', 'reference'])
    ap.add_argument('--loads', type=int, default=3, help='fresh-context loads (default 3, minimum useful: 3)')
    ap.add_argument('--viewport', default='1700x1000')
    ap.add_argument('--wait', type=int, default=12000)
    ap.add_argument('--match', default=DEFAULT_MATCH, help='regex on the request URL (default: ' + DEFAULT_MATCH + ')')
    ap.add_argument('--all-api', action='store_true', help='list every XHR/fetch to /api/ (permission checks and config reads included)')
    ap.add_argument('--expect-parent', help='the id of the parent record every row must belong to')
    ap.add_argument('--parent-field', default='parentId', help='row field holding the parent record id (default parentId; dotted ok)')
    ap.add_argument('--rows-selector', help="CSS selector of one rendered row, e.g. '[data-sha-datalist-item-type]'")
    ap.add_argument('--db-count-url', help='API GET that returns the database count (path + query)')
    ap.add_argument('--full', action='store_true', help='do not truncate URLs / parameter values')
    ap.add_argument('--json', help='also write the raw audit to this file')
    a = ap.parse_args(argv)
    from core.browse import session
    w, h = (int(x) for x in a.viewport.lower().split('x'))
    loads, allflags = [], []
    for k in range(1, a.loads + 1):
        with session(a.role, viewport=(w, h)) as pg:      # a new browser + context per load: no cached markup, no IndexedDB
            ld = collect_load(pg, a.page, a.wait, a.match, a.all_api, a.rows_selector)
        for e in ld['entries']: e['flags'] = analyse(e, a.expect_parent, a.parent_field)
        ld['flags2'], ld['info'] = two_phase_notes(ld['entries'])
        ld['rows_selector'] = a.rows_selector
        loads.append(ld); show_load(k, a.loads, a.page, ld, a.full)
        allflags += [f for e in ld['entries'] for f in e['flags']] + ld['flags2']
    print('\n=== SUMMARY')
    if a.loads < 3: print(f'  note: only {a.loads} load(s); the first load after a push can mislead (H53): use at least 3')
    diffs = diff_loads(loads) if len(loads) > 1 else []
    for d in diffs: print('  FLAG ' + d)
    allflags += diffs
    if a.db_count_url:
        n, how = db_count(a.role, a.db_count_url)
        print(f'  database count: {n} ({how})')
        for k, ld in enumerate(loads, 1):
            if ld['rows'] is not None and ld['rows'] != n: allflags.append(f'ROWS VS DB: load {k} rendered {ld["rows"]} rows, the database has {n}'); print('  FLAG ' + allflags[-1])
            lst = [e for e in ld['entries'] if e['listlike'] and e['count'] is not None and not e['trimmed']]
            if lst:      # the last full-projection list response: its totalCount (else its item count) must equal the database count
                last = lst[-1]; got = last['total'] if last['total'] is not None else last['count']
                if got != n:
                    allflags.append(f'ROWS VS DB: load {k} last full list response #{last["seq"]} holds {got} (items {last["count"]}, totalCount {last["total"]}), the database count is {n}')
                    print('  FLAG ' + allflags[-1])
        if not a.rows_selector: print('  (give --rows-selector to compare the RENDERED rows with the database as well)')
    uniq = collections.Counter(allflags)
    if uniq:
        print(f'  {len(uniq)} distinct flag(s) over {a.loads} load(s):')
        for f, c in uniq.items(): print(f'   - x{c} {f}')
    elif any(ld['entries'] for ld in loads): print('  no flags: filter, sorting, projection and (when given) parent / counts look right in every load')
    if a.json:
        with open(a.json, 'w', encoding='utf-8', newline='\n') as f:
            json.dump([{'rows': ld['rows'], 'entries': [{k: v for k, v in e.items() if k != 'items'} for e in ld['entries']], 'flags': ld['flags2']} for ld in loads], f, indent=1, default=str)
    print('\nrecord the outcome:  shrec.py verify --kind request-audit --result ok|fail --detail "<detail>"   and   --kind data-audit ...')
    return 2 if not any(ld['entries'] for ld in loads) else (1 if allflags else 0)


if __name__ == '__main__':
    sys.exit(main())
