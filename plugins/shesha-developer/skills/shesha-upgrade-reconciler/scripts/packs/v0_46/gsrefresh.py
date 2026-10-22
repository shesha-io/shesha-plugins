"""Rule `gsrefresh` (H41): 0.46 no longer puts data table contexts into `globalState`.

Symptom on 0.46: an `Execute Script` action that ends with `globalState?.<ctx>?.refreshTable()` refreshes nothing (for
example a table row keeps its old status after a dialog closes until the page is reloaded); 0.43 refreshed it.
Cause: `contexts.<ctx>` holds the table state only (no refreshTable).
Writes: the dead call is replaced by a marker comment and the standard `Refresh table` action (actionOwner = that context's
component id) is chained after the script, ahead of any existing onSuccess. Only contexts defined once in the SAME form
are handled; a context in another (host) form is reported (INFO) and left alone.
Marker: /*reconciler:046-refresh-chain*/ in the script (the dead call is gone after the first run).  Options: none.
"""
import re

MARK = '/*reconciler:046-refresh-chain*/'
CALL = re.compile(r'globalState\s*\??\.\s*([A-Za-z_$][\w$]*)\s*\??\.\s*refreshTable\s*\(\s*\)\s*;?')


def _contexts(m):
    seen = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get('type') == 'datatableContext' and o.get('componentName'):
                seen.setdefault(o['componentName'], []).append(o['id'])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(m)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def apply(ctx, m):
    ids = _contexts(m)
    n = 0

    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            args = o.get('actionArguments') if o.get('actionName') == 'Execute Script' else None
            ex = args.get('expression') if isinstance(args, dict) else None
            if isinstance(ex, str):
                calls = list(CALL.finditer(ex))
                if calls:
                    names = list(dict.fromkeys(c.group(1) for c in calls))
                    if len(names) == 1 and names[0] in ids:
                        for c in calls:
                            ex = ex.replace(c.group(0), f'{MARK} /* table refresh moved to a chained Refresh table action (H41) */')
                        args['expression'] = ex
                        tail = {'_type': 'action-config', 'actionName': 'Refresh table', 'actionOwner': ids[names[0]],
                                'handleSuccess': bool(o.get('handleSuccess') and o.get('onSuccess')), 'handleFail': False}
                        if o.get('handleSuccess') and o.get('onSuccess'):
                            tail['onSuccess'] = o['onSuccess']
                        o['handleSuccess'] = True
                        o['onSuccess'] = tail
                        n += 1
                        ctx.note(f'script refresh of {names[0]} -> chained Refresh table (H41)')
                    else:
                        ctx.info(f'refresh of {names[:4]} not converted - context not defined once in this form (H41, review by hand)')
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(m)
    return n
