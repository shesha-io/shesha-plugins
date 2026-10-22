"""Rule packs and the rule contract.

A pack is a folder scripts/packs/<pack>/ with pack.json and rule modules. pack.json:
  {"id": "0.46", "version": "1.0.0", "target": ">=0.46.0 <0.47.0", "sourceBelow": "0.46.0",
   "hazards": "shesha-developer-0-46:shesha-form-edit references/render-hazards-046.md",
   "rules": [ {rule}, ... ]}                      # list order = application order
A rule entry:
  {"id": "editmode", "entry": "editmode:apply", "retire": "editmode:retire" | null, "hazard": "H15",
   "title": "...", "kind": "fleet" | "targeted" | "opt-in", "syntaxGate": true,
   "marker": "/*reconciler:046-editmode*/" | null, "fixedIn": "0.46.1" | null,
   "fixedEvidence": "release-notes" | "verified" | null, "options": ["optionKey", ...]}

Rule contract (pack rules and project rules alike):
  apply(ctx, markup) -> int      mutate the parsed markup in place, return the number of changes, add one note per
                                 change with ctx.note(); refuse (raise WriteRefused via core.project.require) when an
                                 anchor is not what the rule expects; return 0 when already applied (idempotent).
  retire(ctx, markup) -> int     optional: undo exactly what apply wrote (found by its marker), once the framework
                                 fixed the bug. retire(apply(x)) must equal x.
Project rules live in <project>/.shesha-reconcile/rules/*.py and define RULE = {same fields as a pack entry} plus
apply (and optionally retire). They run after the pack rules, in file-name order.
"""
import importlib
import importlib.util
import json
import os

from core import project, versions

PACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'packs')


class Ctx:
    """Per-form rule context. Shared, lazily computed data lives on the session (one per run)."""

    def __init__(self, session, module, name):
        self.session, self.module, self.name = session, module, name.strip()
        self.form = f'{module}/{self.name}'
        self.notes = []

    # notes: plain = an edit; INFO / REVIEW prefixes never cause a write on their own
    def note(self, text):
        self.notes.append(text)

    def info(self, text):
        self.notes.append('INFO ' + text)

    def review(self, text):
        self.notes.append('INFO REVIEW ' + text)

    def opt(self, key, default=None):
        return self.session.options.get(key, default)

    @property
    def role(self):
        return self.session.role

    @property
    def versions(self):
        return self.session.versions

    def hosted_forms(self):
        """{'Module/name'} of every form that another form renders (subForm / dataList / list item / dialog)."""
        return self.session.lazy('hosted_forms', self.session.compute_hosted)

    def reference_components(self):
        """{component id: component} from the reference snapshot (read-only, taken by `shrec.py snapshot`)."""
        return self.session.lazy('reference_components', self.session.compute_reference_components)

    def api(self):
        from core.api import Api
        return self.session.lazy('api', lambda: Api(self.session.role))

    def cache(self, key, fn):
        return self.session.lazy(key, fn)


class Session:
    """What every rule of one run shares: target role, version pair, project options, lazy caches.
    Tests and offline parity runs inject `forms` (list of rows with module/name/markup) and `reference` markups."""

    def __init__(self, role='local', options=None, versions_pair=None, forms=None, reference=None):
        self.role = role
        self.options = dict(options or {})
        self.versions = versions_pair or {}
        self._forms, self._reference = forms, reference
        self._cache = {}

    def lazy(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def forms(self):
        if self._forms is None:
            from core.api import fetch_forms
            _, self._forms = fetch_forms(self.role)
        return self._forms

    def compute_hosted(self):
        from core.tree import form_refs
        out = set()
        for row in self.forms():
            mk = row.get('markup')
            try:
                out |= form_refs(json.loads(mk) if isinstance(mk, str) else (mk or {}))
            except ValueError:
                continue
        return out

    def compute_reference_components(self):
        from core.tree import walk
        markups = self._reference
        if markups is None:
            markups = []
            snap = project.work_path('snapshots', 'reference', mkdir=False)
            for dirpath, _, files in os.walk(snap):
                for f in files:
                    if f.endswith('.json') and not f.endswith('-index.json'):
                        d = project.read_json(os.path.join(dirpath, f), {}) or {}
                        markups.append(d.get('markup'))
        out = {}
        for mk in markups:
            try:
                tree = json.loads(mk) if isinstance(mk, str) else (mk or {})
            except ValueError:
                continue
            for c, _, _ in walk(tree):
                out[c['id']] = c
        return out


# ---------------------------------------------------------------- loading
def list_packs():
    out = []
    if not os.path.isdir(PACKS_DIR):
        return out
    for d in sorted(os.listdir(PACKS_DIR)):
        man = project.read_json(os.path.join(PACKS_DIR, d, 'pack.json'))
        if isinstance(man, dict):
            man['_dir'] = d
            out.append(man)
    return out


def _resolve(pack_dir, entry):
    if not entry:
        return None
    mod, fn = entry.split(':')
    m = importlib.import_module(f'packs.{pack_dir}.{mod}')
    return getattr(m, fn)


def load_project_rules():
    """[(meta, apply, retire)] from <project>/.shesha-reconcile/rules/*.py"""
    out = []
    try:
        d = os.path.join(project.home(), 'rules')
    except project.ConfigError:
        return out
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith('.py') or f.startswith('_'):
            continue
        spec = importlib.util.spec_from_file_location(f'project_rules.{f[:-3]}', os.path.join(d, f))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        meta = dict(getattr(m, 'RULE', {}) or {})
        meta.setdefault('id', f[:-3])
        meta['project'] = True
        out.append((meta, m.apply, getattr(m, 'retire', None)))
    return out


def pack_for(target_version, source_version=None):
    """The pack whose target range holds the target version, or None.

    `sourceBelow` marks where the pack's upgrade rules start (a full upgrade comes from below it). A patch upgrade
    inside the same line (e.g. 0.46.0 -> 0.46.1) still uses the pack - that is when fixed rules are retired - so the
    source only disqualifies a pack when it is NEWER than the target (a downgrade)."""
    for man in list_packs():
        if target_version and versions.satisfies(target_version, man.get('target')):
            if source_version and versions.parse(source_version) and versions.cmp(source_version, target_version) > 0:
                continue
            return man
    return None


def plan(pack, target_version, enable=(), disable=()):
    """Decide every rule's fate for this target version:
    'apply' | 'apply-claimed-fixed' (release notes say fixed, not verified: still applied, warn) |
    'skip-fixed' (fix verified in target) | 'opt-in' (kind opt-in and not enabled) | 'targeted' (only when named) |
    'disabled'."""
    out = []
    for r in (pack or {}).get('rules', []):
        rid = r['id']
        if rid in disable:
            fate = 'disabled'
        elif r.get('kind') == 'opt-in' and rid not in enable:
            fate = 'opt-in'
        elif r.get('kind') == 'targeted':
            fate = 'targeted'          # runs only when named in --rules, on the forms named in --only
        elif r.get('fixedIn') and target_version and versions.cmp(target_version, r['fixedIn']) >= 0:
            fate = 'skip-fixed' if r.get('fixedEvidence') == 'verified' else 'apply-claimed-fixed'
        else:
            fate = 'apply'
        out.append((r, fate))
    return out


def retire_candidates(pack, target_version):
    """Rules whose fix is in the target version (any evidence) and that can be unwound."""
    return [r for r in (pack or {}).get('rules', [])
            if r.get('fixedIn') and r.get('retire') and target_version and versions.cmp(target_version, r['fixedIn']) >= 0]


def callables(pack, rule):
    """(apply, retire) for a pack rule entry."""
    return _resolve(pack['_dir'], rule.get('entry')), _resolve(pack['_dir'], rule.get('retire'))
