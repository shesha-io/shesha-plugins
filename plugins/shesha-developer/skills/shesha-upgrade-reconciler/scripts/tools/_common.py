"""Small helpers shared by the tools (not a command)."""
import json
import os
import time

from core import ledger, project


def log_event(name, env=None, host=None, **fields):
    """Append a ledger event (events may carry their own `kind` field: verify, other, entity/workflow writes). Falls back to
    appending the line directly in the documented ledger format if core.ledger.event() raises TypeError."""
    try:
        return ledger.event(name, env=env, host=host, **fields)
    except TypeError:
        if 'kind' not in fields:
            raise
    e = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'event': name, 'run': ledger.run_id(), 'batch': ledger.batch_id(), 'env': env,
         'host': host, 'pack': getattr(ledger, '_CTX', {}).get('pack'), 'versions': getattr(ledger, '_CTX', {}).get('versions')}
    e.update(fields)
    path = project.ledger_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
    return e
