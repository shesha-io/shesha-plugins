"""Project location, configuration, environment roles, credentials and the write-safety primitives.

A project is any repository holding `.shesha-reconcile/project.json` (created by `shrec.py init`). Resolution order:
`--project <dir>` (set by shrec.py into $SHREC_PROJECT), then $SHREC_PROJECT, then the nearest parent of the current
directory that holds `.shesha-reconcile/project.json`.

Environment roles (never project names):
  reference  the pre-upgrade site you compare against - READ-ONLY, always, whatever else is configured
  local      the developer's post-upgrade stack on localhost - writable once confirmed as the write target
  deployed   a deployed post-upgrade site - writable only after an explicit, time-limited authorisation

Committed: project.json, ledger.jsonl, defects.jsonl, decisions.md, rules/.
Local only (gitignored): work/ (state.json, snapshots, backups, sweeps, reports, browser logins) and credentials.local.json.
Credentials are never printed, logged or returned to the caller's output.
"""
import json
import os
import time
import urllib.parse

ROLES = ('reference', 'local', 'deployed')
DIRNAME = '.shesha-reconcile'
LOCAL_DEFAULTS = {'api': 'http://localhost:21021', 'portal': 'http://localhost:3000'}
DEPLOY_TTL_MIN = 120      # a deployed-write authorisation expires after this many minutes ($SHREC_DEPLOY_TTL_MIN overrides)


class WriteRefused(AssertionError):
    """A safety guard said no. Subclasses AssertionError so runners can catch both, but it is raised explicitly:
    unlike `assert` it survives `python -O`."""


class ConfigError(RuntimeError):
    """The project is not configured for what was asked; the message says which command fixes it."""


def require(cond, msg='refused'):
    """Safety guard: raise WriteRefused(msg) unless cond. Use this, never `assert`, for anything that protects a write."""
    if not cond:
        raise WriteRefused(msg)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')


LOOPBACK = ('localhost', '127.0.0.1', '::1')
DEFAULT_PORTS = {'http': 80, 'https': 443}


def host_key(url):
    """Canonical 'host:port' of a url for identity checks: lower case, userinfo dropped, trailing dot dropped, default port
    made explicit, every loopback alias folded to 'localhost'. '' when it is not a url. Two urls naming the same server
    get the same key, so a reference host cannot be written under another spelling."""
    try:
        p = urllib.parse.urlsplit(url or '')
        host, port = (p.hostname or '').rstrip('.'), p.port
    except ValueError:
        return ''
    if not host:
        return ''
    if host in LOOPBACK:
        host = 'localhost'
    return f'{host}:{port or DEFAULT_PORTS.get(p.scheme.lower(), 0)}'


def netloc(url):
    """canonical host:port of a url (see host_key), '' when it is not a url"""
    return host_key(url)


def has_userinfo(url):
    return '@' in (urllib.parse.urlsplit(url or '').netloc or '')


def is_localhost(url):
    return not has_userinfo(url) and host_key(url).startswith('localhost:')


# ---------------------------------------------------------------- locations
def find_root(start=None):
    """The project repository root (the directory holding .shesha-reconcile/), or None."""
    env = os.environ.get('SHREC_PROJECT')
    if env:
        return os.path.abspath(env)
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, DIRNAME, 'project.json')):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def root():
    r = find_root()
    if not r:
        raise ConfigError('no .shesha-reconcile/project.json found from here: run `python <skill>/scripts/shrec.py init` in the '
                          'project repository, or pass --project <repo>')
    return r


def home():
    return os.path.join(root(), DIRNAME)


def work():
    return os.environ.get('SHREC_WORK') or os.path.join(home(), 'work')


def work_path(*parts, mkdir=True):
    """<work>/<parts...>; creates the parent directory (never at import time)."""
    p = os.path.join(work(), *parts)
    if mkdir:
        os.makedirs(p if not os.path.splitext(p)[1] else os.path.dirname(p), exist_ok=True)
    return p


def ledger_path():
    return os.path.join(home(), 'ledger.jsonl')


def defects_path():
    return os.path.join(home(), 'defects.jsonl')


def state_path():
    return work_path('state.json')


# ---------------------------------------------------------------- configuration
def config():
    cfg = read_json(os.path.join(home(), 'project.json'))
    if not isinstance(cfg, dict):
        raise ConfigError(f'{DIRNAME}/project.json is missing or not valid JSON: run `shrec.py init`')
    return cfg


def option(key, default=None):
    """A project option (project.json "options"). Rules read project-specific values ONLY through this."""
    return (config().get('options') or {}).get(key, default)


def modules():
    m = config().get('modules') or []
    if not m:
        raise ConfigError('project.json has no "modules": list the configuration modules this project owns')
    return m


def app_key():
    return config().get('appKey') or 'default-app'


def state():
    return read_json(state_path(), {}) or {}


def save_state(st):
    write_json(state_path(), st)


def environments():
    """{role: {api, portal, version, ...}} from project.json, plus local defaults and the session state (authorisations)."""
    cfg = config().get('environments') or {}
    st = state()
    out = {'local': dict(LOCAL_DEFAULTS)}
    for role in ROLES:
        blk = cfg.get(role)
        if isinstance(blk, dict):
            out.setdefault(role, {}).update({k: (v.rstrip('/') if isinstance(v, str) else v) for k, v in blk.items()})
    dep = out.get('deployed')
    auth = st.get('deployed_authorisation') or {}
    if dep and auth.get('api') == dep.get('api'):
        dep['authorised_at'] = auth.get('at')
    return out


def env_config(role):
    if role not in ROLES:
        raise ConfigError(f'unknown environment role {role!r}: use one of {", ".join(ROLES)}')
    cfg = environments().get(role)
    if not cfg or not cfg.get('api'):
        raise ConfigError(f"environment '{role}' is not configured: add it under \"environments\" in project.json (shrec.py init)")
    for part in ('api', 'portal'):
        if has_userinfo(cfg.get(part)):     # credentials never live in a url (and are never sent to one)
            raise ConfigError(f"environments.{role}.{part} contains user info ('user@host'): remove it from project.json")
    return cfg


def reference_hosts():
    """Every host recorded for the reference role (api + portal). No write path may ever target these."""
    ref = environments().get('reference') or {}
    return {h for h in (netloc(ref.get('api')), netloc(ref.get('portal'))) if h}


def write_target():
    """The write target the user confirmed this session ({'role', 'api', 'at'}) or None."""
    return state().get('write_target')


def deployed_authorised(api):
    """True while the user's deployed-write authorisation for exactly this api is younger than the TTL."""
    auth = state().get('deployed_authorisation') or {}
    if auth.get('api') != api or not auth.get('epoch'):
        return False
    try:
        ttl = int(os.environ.get('SHREC_DEPLOY_TTL_MIN') or DEPLOY_TTL_MIN)
    except ValueError:
        ttl = DEPLOY_TTL_MIN
    return time.time() - float(auth['epoch']) < ttl * 60


# ---------------------------------------------------------------- credentials
def credential_files():
    files = []
    try:
        files.append(os.path.join(home(), 'credentials.local.json'))
    except ConfigError:
        pass
    if os.environ.get('SHREC_CREDS'):
        files.append(os.environ['SHREC_CREDS'])
    r = find_root()
    if r:
        files.append(os.path.join(r, '.sheshadev.local.json'))   # shared Shesha developer credentials file, if the team uses one
    return files


def _block(data, role):
    if not isinstance(data, dict):
        return None
    if isinstance(data.get(role), dict):
        return data[role]
    if 'username' in data or 'password' in data:
        return data          # flat file: the same account for every role
    return None


def credentials(role):
    """(username, password) for the role. Raises a message-only error; never echoes a value."""
    for path in credential_files():
        b = _block(read_json(path), role)
        if b and str(b.get('username') or '').strip() and str(b.get('password') or ''):
            return b['username'], b['password']
    raise ConfigError(f"no credentials for '{role}': run `shrec.py init-creds`, then type your own username and password into "
                      f'{DIRNAME}/credentials.local.json (gitignored). Never paste them into chat.')


def creds_status():
    out = {}
    for role in ROLES:
        try:
            credentials(role)
            out[role] = True
        except ConfigError:
            out[role] = False
    return out
