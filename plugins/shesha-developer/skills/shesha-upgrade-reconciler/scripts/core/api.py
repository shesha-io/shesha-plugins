"""Read-only Shesha API client by environment role. Usage: Api('reference' | 'local' | 'deployed').get('/api/...', **params)

Only GET is sent, plus the token request and the read-only POST queries listed in READ_ONLY_POSTS. Writes live in
push.py behind their own guards. Never prints a credential or a token.
"""
import json
import urllib.parse
import urllib.request

from core.project import credentials, env_config

_TOK = {}
# The only non-GET requests this client sends. Extend only with a known read-only query endpoint, never with a mutation.
READ_ONLY_POSTS = ('/api/TokenAuth/Authenticate', '/ConfigurationStudio/ExportPackage')   # path suffixes; export only reads
FORMS = '/api/services/Shesha/FormConfiguration'
PAGE = 500


def modname(item):
    """module name of a GetAll / Get row (0.43 and 0.46 shapes)"""
    m = item.get('module')
    return (m.get('name') if isinstance(m, dict) else m) or ''


class Api:
    def __init__(self, role):
        self.role = self.env = role
        self.base = env_config(role)['api']
        if role not in _TOK:
            user, pwd = credentials(role)
            r = self._raw('POST', '/api/TokenAuth/Authenticate', {'userNameOrEmailAddress': user, 'password': pwd}, auth=False)
            _TOK[role] = r['result']['accessToken']
        self.token = _TOK[role]

    def _raw(self, method, path, body=None, params=None, auth=True, binary=False):
        if method != 'GET' and not any(path.split('?')[0].endswith(p) for p in READ_ONLY_POSTS):
            raise RuntimeError('READ-ONLY client: refusing ' + method + ' ' + path)
        url = self.base + path + ('?' + urllib.parse.urlencode(params) if params else '')
        h = {'Content-Type': 'application/json'}
        if auth:
            h['Authorization'] = 'Bearer ' + self.token
        req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, h, method=method)
        with urllib.request.urlopen(req, timeout=180) as r:
            self.last_headers = dict(r.headers.items())    # e.g. the package file name of an export
            data = r.read()
            if binary:
                return data
            t = data.decode('utf-8', 'replace')
            try:
                return json.loads(t)
            except ValueError:
                return t

    def get(self, path, **params):
        return self._raw('GET', path, params=params or None)

    def post_query(self, path, body, binary=False):
        """A POST that only reads (must be listed in READ_ONLY_POSTS)."""
        return self._raw('POST', path, body, binary=binary)

    def get_all(self, path, page=PAGE, **params):
        """Every item of a paged GetAll: pages until totalCount, so a large configuration is never silently truncated."""
        items, skip = [], 0
        while True:
            r = self.get(path, SkipCount=skip, MaxResultCount=page, **params)['result']
            batch = r.get('items') or []
            items.extend(batch)
            total = r.get('totalCount')
            skip += len(batch)
            if not batch or (total is not None and skip >= total) or (total is None and len(batch) < page):
                break
        return items


def fetch_forms(role, modules=None):
    """(api, [form rows]) for one role, optionally limited to module names."""
    a = Api(role)
    items = a.get_all(FORMS + '/GetAll')
    if modules:
        wanted = set(modules)
        items = [i for i in items if modname(i).strip() in wanted]
    return a, items


def get_form(a, module, name):
    """Fresh read of one form by module + name (unique match required)."""
    ids = [i['id'] for i in a.get_all(FORMS + '/GetAll') if modname(i).strip() == module and (i.get('name') or '').strip() == name.strip()]
    if len(ids) != 1:
        raise RuntimeError(f'{module}/{name}: {len(ids)} matches')
    return a.get(FORMS + '/Get', id=ids[0])['result']
