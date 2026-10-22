"""Write-guarded Playwright session for the reference, local and deployed portals. Playwright is imported lazily (only when a
session is opened), so every non-browser command works without it installed.

  with session('local', log, viewport=(1568, 950)) as pg:
      pg.goto('/dynamic/<module>/<form>?id=...')       # a relative path is joined onto the role's portal url

Guard (a Playwright route on every request):
- any request to a host recorded for the reference role (api or portal), and EVERYTHING while browsing the reference role, may only
  be a GET or one of the allowlisted read-only POST queries. No flag overrides this.
- on the other roles PUT / PATCH / DELETE and every POST not on the allowlist are aborted and logged in log['blocked'].
- allow_local_writes=True (functional checks only) lets the browser write to the configured LOCAL api and nowhere else; the
  writes are recorded in log['writes'].

Login: selectors come from project.json "login" {userPlaceholder, passPlaceholder, submitText} (defaults ^user, ^pass, Sign In).
The login is cached per role for 40 minutes under <work>/.state (0.46 rate-limits logins). Credentials are never printed.
Console capture (console.error / console.warn) keeps the first $SHREC_CONSOLE_MAX characters of each message (default 2000).
The 'CONFIGURATION_ITEM_MODE' localStorage line is the 0.43 live/draft switch: it is set only when the browsed role's version is
below 0.45. The layout probe counts style tags mentioning `ant-tabs` plus the classes of project option `probeStyleClasses` (list).

CLI:  python scripts/core/browse.py <role> <path-or-url> <outprefix> [--tabs] [--wait ms] [--full]
      writes <outprefix>.png and <outprefix>.json (console, blocked writes, failed requests, layout probe, tab labels).
"""
import contextlib
import json
import os
import re
import sys
import time
import urllib.parse

if __name__ == '__main__':      # allow `python scripts/core/browse.py ...`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import project, versions
from core.metadata import role_version

# POSTs that only read, matched against the URL PATH's final segment(s) (never a substring: /Country/Crud/Create must not pass
# because it contains "/Count"). Project-specific read endpoints of custom components: project option `readPostExtra`
# (a list of final-segment regexes, e.g. ["Spreadsheet/Open"]).
READ_POST = re.compile(r'/(?:TokenAuth/Authenticate|GetAll|Get|GetJson|Query|GetByName|Autocomplete|List|Search|Count|GetValue|'
                       r'GetSettings|CheckPermissions|GetCurrentLoginInfo|GetCurrentLoginInformations|GetUserConfig|GetUserValue|'
                       r'EntityConfig/SyncClientApi|Metadata/\w+|graphql|signalr/negotiate)$', re.I)


def is_read_post(url):
    path = urllib.parse.urlsplit(url).path.rstrip('/')
    if READ_POST.search(path) or re.search(r'/signalr(?:/|$)', path, re.I):
        return True
    try:
        extra = project.option('readPostExtra', []) if project.find_root() else []
    except project.ConfigError:
        extra = []
    return any(re.search(r'/(?:' + x + r')$', path, re.I) for x in extra or [] if isinstance(x, str))
LOGIN_DEFAULTS = {'userPlaceholder': '^user', 'passPlaceholder': '^pass', 'submitText': 'Sign In'}
LOGIN_TTL = 40 * 60

PROBE = r"""(rx) => {
 const re = new RegExp(rx);
 const out = {tabs:[], htmlRenderPlaceholders:0, requiredErrors:0, emptyLabels:0, overlaps:[], spinners:0, fonts:{}, header:null};
 document.querySelectorAll('.ant-tabs').forEach((t,i)=>{ const labs=[...t.querySelectorAll(':scope > .ant-tabs-nav .ant-tabs-tab')].map(x=>x.innerText.trim());
   const cs=getComputedStyle(t.querySelector(':scope > .ant-tabs-nav')||t); out.tabs.push({i, labs, navBg:cs.backgroundColor, navH:(t.querySelector(':scope > .ant-tabs-nav')||t).getBoundingClientRect().height}); });
 out.htmlRenderPlaceholders = [...document.querySelectorAll('*')].filter(e=>e.childElementCount===0 && /provide some content for this HTML render/i.test(e.textContent||'')).length;
 out.requiredErrors = [...document.querySelectorAll('.ant-form-item-explain-error')].filter(e=>/required/i.test(e.textContent)).length;
 out.spinners = document.querySelectorAll('.ant-spin-spinning').length;
 out.styleTags = [...document.querySelectorAll('style')].filter(s=>re.test(s.textContent)).length;
 const b=document.body; const f=getComputedStyle(b); out.fonts={family:f.fontFamily,size:f.fontSize};
 const items=[...document.querySelectorAll('.ant-form-item')]; out.formItems=items.length;
 out.emptyLabels = items.filter(it=>{const l=it.querySelector('.ant-form-item-label'); return l && !l.innerText.trim();}).length;
 const h=document.querySelector('.ant-tabs'); out.firstTabsTop = h? h.getBoundingClientRect().top : null;
 return out; }"""


def console_max():
    try:
        return max(100, int(os.environ.get('SHREC_CONSOLE_MAX') or 2000))
    except ValueError:
        return 2000


def probe_pattern():
    """Regex source for the probe's style-tag count: `ant-tabs` plus the classes of option probeStyleClasses."""
    extra = project.option('probeStyleClasses', []) or []
    parts = ['ant-tabs'] + [re.escape(str(x)) for x in extra if str(x).strip()]
    return '|'.join(parts)


def login_config():
    cfg = dict(LOGIN_DEFAULTS)
    try:
        cfg.update({k: v for k, v in (project.config().get('login') or {}).items() if v})
    except project.ConfigError:
        pass
    return cfg


def sets_config_item_mode(role):
    """True only for a role whose version is known and below 0.45 (versioned configuration items)."""
    v = role_version(role)
    return bool(v) and versions.parse(v) is not None and versions.cmp(v, '0.45.0') < 0


def portal_base(role):
    base = project.env_config(role).get('portal')
    if not base:
        raise project.ConfigError(f"environment '{role}' has no \"portal\" url in project.json")
    return base.rstrip('/')


def blocked_by_guard(role, url, method, ref_hosts, local_api, allow_local_writes):
    """(verdict, label). verdict: 'allow' | 'allow-local-write' | 'block'. Pure function: unit-tested offline."""
    write = method in ('PUT', 'PATCH', 'DELETE') or (method == 'POST' and not is_read_post(url))
    if role == 'reference' or project.netloc(url) in ref_hosts:
        return ('block', 'REFERENCE-WRITE-REFUSED') if write else ('allow', '')
    if allow_local_writes and role == 'local' and local_api and url.startswith(local_api + '/'):
        return ('allow-local-write', '') if method != 'GET' else ('allow', '')
    return ('block', '') if write else ('allow', '')


def _login(pg, role):
    cfg = login_config()
    pg.goto(portal_base(role) + '/login', wait_until='domcontentloaded', timeout=180000)
    pg.wait_for_timeout(3000)
    user, pwd = project.credentials(role)        # never printed
    pg.get_by_placeholder(re.compile(cfg['userPlaceholder'], re.I)).first.fill(user, timeout=120000)
    pg.get_by_placeholder(re.compile(cfg['passPlaceholder'], re.I)).first.fill(pwd)
    pg.get_by_role('button', name=cfg['submitText'], exact=True).first.click(timeout=120000)
    pg.wait_for_url(lambda u: '/login' not in u, timeout=180000)


@contextlib.contextmanager
def session(role, log=None, viewport=(1600, 1000), allow_local_writes=False):
    """Yields a logged-in, write-guarded Playwright page. log: dict that collects console / blocked / failed (/ writes)."""
    from playwright.sync_api import sync_playwright          # lazy: only browser commands need it
    if role not in project.ROLES:
        raise project.ConfigError(f'unknown role {role!r}')
    log = log if log is not None else {}
    for k in ('console', 'blocked', 'failed'):
        log.setdefault(k, [])
    local_api = project.env_config('local')['api'] if role == 'local' else ''
    if allow_local_writes:
        project.require(role == 'local' and project.is_localhost(local_api),
                        'allow_local_writes is only for the local role on a localhost api')
    sf = project.work_path('.state', f'{role}.json')
    fresh = os.path.exists(sf) and time.time() - os.path.getmtime(sf) < LOGIN_TTL
    cap = console_max()
    ref_hosts = project.reference_hosts()
    set_mode = sets_config_item_mode(role)
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        ctx = br.new_context(viewport={'width': viewport[0], 'height': viewport[1]}, storage_state=sf if fresh else None,
                             service_workers='block')   # route() does not see service-worker requests: block them
        if set_mode:
            ctx.add_init_script("try{localStorage.setItem('CONFIGURATION_ITEM_MODE','\"live\"')}catch(e){}")

        def guard(route, req):
            verdict, label = blocked_by_guard(role, req.url, req.method, ref_hosts, local_api, allow_local_writes)
            if verdict == 'block':
                log['blocked'].append((label + ' ' if label else '') + req.method + ' ' + req.url)
                return route.abort()
            if verdict == 'allow-local-write':
                log.setdefault('writes', []).append(req.method + ' ' + req.url[:160])
            return route.continue_()
        ctx.route('**/*', guard)
        pg = ctx.new_page()
        pg.on('console', lambda m: m.type in ('error', 'warning') and log['console'].append(m.type + ': ' + m.text[:cap]))
        pg.on('requestfailed', lambda r: log['failed'].append(r.method + ' ' + r.url[:200]))
        pg.on('response', lambda r: r.status >= 400 and log['failed'].append(f'{r.status} {r.request.method} {r.url[:200]}'))

        def save_state():
            tmp = sf + f'.{os.getpid()}.tmp'
            ctx.storage_state(path=tmp)
            os.replace(tmp, sf)
        if not fresh:
            _login(pg, role)
            save_state()
        orig_goto = pg.goto

        def goto(url, **kw):
            url = url if url.startswith('http') else portal_base(role) + url
            r = orig_goto(url, **({'wait_until': 'domcontentloaded'} | kw))
            pg.wait_for_timeout(1500)
            if '/login' in pg.url:            # the cached session expired
                _login(pg, role)
                save_state()
                r = orig_goto(url, **({'wait_until': 'domcontentloaded'} | kw))
            return r
        pg.goto = goto
        try:
            yield pg
        finally:
            br.close()


def settle(pg, wait=6000, idle=20000):
    pg.wait_for_timeout(wait)
    try:
        pg.wait_for_load_state('networkidle', timeout=idle)
    except Exception:
        pass


def run(role, target, outp, walk_tabs=False, wait=6000, full=False):
    log = {'url': target}
    pattern = probe_pattern()
    with session(role, log) as pg:
        pg.goto(target)
        settle(pg, wait)
        log['finalUrl'] = pg.url
        pg.screenshot(path=outp + '.png', full_page=full)
        log['probe'] = pg.evaluate(PROBE, pattern)
        log['sidebar'] = pg.evaluate("() => [...document.querySelectorAll('a[href]')].map(a=>({t:(a.innerText||a.getAttribute('title')||a.getAttribute('aria-label')||'').trim(),h:a.getAttribute('href')})).filter(x=>/dynamic|shesha|settings/.test(x.h))")
        if walk_tabs:
            tabs = pg.locator('.ant-tabs').first.locator(':scope > .ant-tabs-nav .ant-tabs-tab')
            for i in range(tabs.count()):
                try:
                    tabs.nth(i).click()
                    settle(pg, wait)
                    pg.screenshot(path=f'{outp}-tab{i}.png', full_page=full)
                    log.setdefault('tabProbes', []).append(pg.evaluate(PROBE, pattern))
                except Exception as e:
                    log.setdefault('tabErrors', []).append(f'{i}: {e}'[:200])
    os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
    with open(outp + '.json', 'w', encoding='utf-8', newline='\n') as f:
        json.dump(log, f, indent=1)
    return log


def main(argv):
    if len(argv) < 3 or argv[0] not in project.ROLES:
        print(__doc__)
        return 2
    role, tgt, outp = argv[0], argv[1], argv[2]
    w = int(argv[argv.index('--wait') + 1]) if '--wait' in argv else 6000
    r = run(role, tgt, outp, '--tabs' in argv, w, '--full' in argv)
    print(json.dumps({'finalUrl': r.get('finalUrl'), 'probe': r.get('probe'), 'blocked': len(r['blocked']),
                      'console': len(r['console']), 'failed': len(r['failed'])}, indent=0)[:1500])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
