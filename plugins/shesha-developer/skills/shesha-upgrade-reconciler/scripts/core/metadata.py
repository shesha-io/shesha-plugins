"""Entity metadata and environment-version helpers shared by rules and tools (one cache instead of one per rule).

Metadata
  m = Metadata(api)                              api = anything with .get(path, **params) (core.api.Api, or a fake in tests)
  m.props('Module.Domain.Thing')                 list of property dicts from Metadata/Get, or None when the type is unknown
  m.prop_map('Module.Domain.Thing')              {path.lower(): property}
  m.paths('...')                                 {camelCasePath, ...}
  m.resolve('Thing', 'Module')                   full entity type name for a short class name, or None

Entity type resolution tries, in order: the name as given (when it already holds a dot), then for every namespace prefix of the
project option `entityNamespaces` (a list; `{module}` is replaced by the module name; default ["{module}.Domain"]):
`<prefix>.<Short>` and `<prefix>.<Short>s.<Short>`, and finally the bare short name. Nothing project specific is built in.

Metadata/Get is called as GET /api/services/app/Metadata/Get?entityType=<type>[&container=<container>].

role_version(role) is the version of an environment: project.json "environments.<role>.version", else (local only) the
Shesha pin detected in the repository. None when neither is known (callers must then not assume a version).
"""
from core import project, versions
from core.tree import camel

META_PATH = '/api/services/app/Metadata/Get'
DEFAULT_NAMESPACES = ('{module}.Domain',)


def role_version(role):
    """The configured (or, for local, repository-detected) version string of an environment role, or None."""
    try:
        v = (project.environments().get(role) or {}).get('version')
        if not v and role == 'local':
            v = versions.detect_repo(project.root()).get('backend')
        return v or None
    except project.ConfigError:
        return None


def namespaces():
    ns = project.option('entityNamespaces', None) if project.find_root() else None
    return list(ns) if isinstance(ns, (list, tuple)) and ns else list(DEFAULT_NAMESPACES)


class Metadata:
    def __init__(self, api, container=None, namespace_list=None):
        self.api, self.container, self.cache = api, container, {}
        self._ns = list(namespace_list) if namespace_list is not None else None

    def props(self, entity_type):
        """Property list of an entity type, or None when the server does not know it. Cached per instance."""
        if not entity_type:
            return None
        key = (self.container, entity_type)
        if key not in self.cache:
            params = {'entityType': entity_type}
            if self.container:
                params['container'] = self.container
            try:
                res = (self.api.get(META_PATH, **params) or {}).get('result') or {}
                self.cache[key] = res.get('properties') or None
            except Exception:
                self.cache[key] = None
        return self.cache[key]

    def prop_map(self, entity_type):
        return {(p.get('path') or '').lower(): p for p in (self.props(entity_type) or [])}

    def paths(self, entity_type):
        """camelCase property paths of the entity type (a set; empty when unknown)."""
        return {camel(p.get('path') or '') for p in (self.props(entity_type) or []) if p.get('path')}

    def candidates(self, short, module=None):
        if '.' in (short or ''):
            yield short
        ns = self._ns if self._ns is not None else namespaces()
        for prefix in ns:
            if '{module}' in prefix and not module:
                continue
            p = prefix.replace('{module}', module or '').strip('.')
            if not p:
                continue
            yield f'{p}.{short}'
            yield f'{p}.{short}s.{short}'
        yield short

    def resolve(self, short, module=None):
        """The first candidate entity type the server knows (has properties for), or None."""
        seen = set()
        for cand in self.candidates(short, module):
            if cand in seen:
                continue
            seen.add(cand)
            if self.props(cand):
                return cand
        return None


def reference_list(prop):
    """{'name', 'module'} of the reference list a property is bound to, or None (both metadata shapes)."""
    if not prop:
        return None
    r = prop.get('referenceListId')
    if isinstance(r, dict) and r.get('name'):
        return {'name': r['name'], 'module': r.get('module')}
    if prop.get('referenceListName'):
        return {'name': prop['referenceListName'], 'module': prop.get('referenceListModule')}
    return None
