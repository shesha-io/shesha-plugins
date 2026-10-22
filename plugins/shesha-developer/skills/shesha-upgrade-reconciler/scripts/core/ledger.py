"""Append-only ledger: <project>/.shesha-reconcile/ledger.jsonl (committed). One JSON object per line; never rewritten.

Every line carries: ts, run, batch, env (role), host, pack ("<id>@<version>" or null), versions {from, to}.
Event shapes:
  run-start  script, mode (dry-run|push), reference_hosts, snapshot_dir?, forms?
  form       module, form, form_id, rule, rules {rule: [notes]}, notes, result, mode, reason?, backup?,
             before_sha256?, after_sha256?        result = pushed | dry-run | no-change | skipped-anchor | failed
  retire     same fields as form, for a rule being unwound after the framework fixed it
  restore    module, form, source (backup path), result
  other      kind (theme-settings | reference-list | entity | workflow | ...), what, backup?
  note       category (backend-migration | follow-up | data | ...), text
  verify     kind (a Definition-of-Done item | browser | e2e | rerun | other), result (ok|fail|unverified), detail
  export     package, forms [module/name], file?
  summary    script, dry, rules, forms_changed, of, failed, by_rule
`shrec.py report` derives status, the export list and retire candidates from this file. No credential or token is
ever written here.
"""
import hashlib
import json
import os
import time

from core import project

_RUN = {}
_CTX = {'pack': None, 'versions': None}


def run_id():
    """one id per process unless $SHREC_RUN pins several processes to one run (e.g. a pilot and its re-run)"""
    if 'id' not in _RUN:
        _RUN['id'] = os.environ.get('SHREC_RUN') or time.strftime('%Y%m%d-%H%M%S')
    return _RUN['id']


def batch_id():
    """$SHREC_BATCH names a batch (one rule rollout, one merge); defaults to the run id."""
    return os.environ.get('SHREC_BATCH') or run_id()


def set_context(pack=None, versions=None):
    if pack is not None:
        _CTX['pack'] = pack
    if versions is not None:
        _CTX['versions'] = versions


def sha256(text):
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def event(event_type, /, env=None, host=None, **fields):
    """Append one event; `fields` may carry its own `kind` (verify / other events), hence the positional-only name."""
    e = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'event': event_type, 'run': run_id(), 'batch': batch_id(), 'env': env, 'host': host,
         'pack': _CTX['pack'], 'versions': _CTX['versions']}
    clash = {'ts', 'event', 'run', 'batch'} & set(fields)
    if clash:                       # the audit identity of a line is never overridable by a caller
        raise ValueError(f'ledger fields {sorted(clash)} are set by the ledger itself')
    e.update(fields)
    path = project.ledger_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
    return e


def read(run=None, path=None):
    path = path or project.ledger_path()
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if run is None or e.get('run') == run:
                out.append(e)
    return out
