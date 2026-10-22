"""End-of-run report generated from the ledger (.shesha-reconcile/ledger.jsonl) and the defect register (defects.jsonl). Never hand-written.
Run it as the LAST step of every run (a full rollout, a merge-reconcile, a single rule), also after a dry run (it then says clearly
that nothing was written).

  shrec.py report [--run <id>[,<id>...] | --all] [--html] [--out <file>]

Window: by default everything within 12 hours before the latest push (pilot, fleet, notes, verification re-runs); with no push at all,
the latest run. --run selects runs, --all takes the whole ledger. Pin one id for a whole session with SHREC_RUN=<name>.
Output: <work>/reports/<timestamp>.md (and .html with --html: one self-contained file, inline CSS, light/dark by the browser setting,
no external assets), plus <report>-export-list.txt when forms are waiting to be exported.

Sections: headline, (1) where changes were written, (2) forms by rule and batch, (3) backups and the revert commands
(`shrec.py restore ...`), (4) export list since the last `export` event, (5) defects by status and hazard, (6) retire candidates,
(7) verification and the Definition-of-Done table, (8) next steps.

HEADLINE: when anything was pushed and no `browser` verification was recorded ok AFTER the last push, the report says
"STATUS: PUSHED AND READ BACK - UNVERIFIED IN BROWSER. Do not call this done." A read-back, a 200, "forms changed 0" and component
counts prove the write persisted, NOT that the page works. A TEMPORARY probe / diagnostic note that is the LAST note for a form is
reported as a probe left behind and kept out of the export list.

Definition-of-Done kinds (record with `shrec.py verify --kind K --result ok|fail|unverified --detail D`):
  placement | request-audit | data-audit | row-content | write-path | read-path | idempotence-fixed-point | reread | reviewer
  (the old kind `owner` is accepted and shown as `reviewer`), plus browser | e2e | rerun | other.
A form is DONE only when placement, request-audit, data-audit, row-content, write-path and read-path are all recorded ok AFTER the
last push (an ok recorded before the last push is stale and does not count).

RETIRE CANDIDATES: rules the ledger shows as applied whose rule pack says the framework fixed the bug in a version at or below the
target role's version (core.packs.retire_candidates): unwind them with `shrec.py retire --rules ...`.
"""
import argparse
import datetime
import glob
import html
import json
import os
import re
import sys
import time

from core import ledger, packs, project
from core.metadata import role_version

STATUSES = ('open', 'pilot', 'fixed', 'framework', 'data', 'legacy', 'accepted', 'verify')

DOD = [
    ('placement', 'Placement: screenshot + geometry of every new or moved component vs the reference, same viewport (dom-chain)'),
    ('request-audit', 'Request audit: every XHR, no de-duplication; filter, sorting and properties right (audit-requests)'),
    ('data-audit', 'Data audit: every rendered row belongs to the record; count equals the database count'),
    ('row-content', 'Row content: every field of every row non-default and equal to the database value'),
    ('write-path', 'Write path: the real Save/Add/Delete clicked in the browser, read back through the API, test row cleaned up'),
    ('read-path', 'Read path after the write: the new row appears in the right position, the input is cleared'),
    ('idempotence-fixed-point', 'Idempotence + fixed point: a re-run reports 0 changes AND each fix says "already applied"'),
    ('reread', 'Re-read after minutes: the form diffed against what was written (the designer normalises and can re-nest)'),
    ('reviewer', 'The reviewer exercised it in their own browser (cleared form caches) and said it works'),
]
DOD_REQUIRED = ['placement', 'request-audit', 'data-audit', 'row-content', 'write-path', 'read-path']
KIND_ALIAS = {'idempotence': 'idempotence-fixed-point', 'fixed-point': 'idempotence-fixed-point', 'request': 'request-audit',
              'data': 'data-audit', 'row': 'row-content', 'write': 'write-path', 'read': 'read-path', 're-read': 'reread',
              'owner': 'reviewer', 'review': 'reviewer'}
KNOWN_KINDS = {k for k, _ in DOD} | {'browser', 'e2e', 'rerun', 'other'}
_TEMP_NOTE_CASE = re.compile(r'\bTEMP(ORARY)?\b')      # upper case anywhere ("renderer -> TEMP data dump"), never "template"
OTHER_KINDS = ('entity', 'workflow')                   # form events that are not forms: never part of the form export list


def norm_kind(k):
    k = str(k or '').strip().lower().replace('_', '-')
    return KIND_ALIAS.get(k, k)


def is_temp_note(n):
    n = str(n or '')
    return bool(re.match(r'\s*(TEMPORARY|DIAGNOSTIC)', n, re.I) or _TEMP_NOTE_CASE.search(n))


def is_temp_rule(r):
    r = str(r or '').lower()
    return r.startswith(('temp', 'diagnostic')) or any(t in r for t in ('temporary', 'diagnostic', 'debug', 'probe'))


def rules_of(e):
    """{rule id: [notes]} of one form event"""
    rules = e.get('rules')
    if isinstance(rules, dict) and rules:
        return {k: list(v or []) for k, v in rules.items()}
    out = {}
    for r in str(e.get('rule') or '').split(','):
        if r.strip():
            out[r.strip()] = []
    notes = list(e.get('notes') or [])
    if out:
        first = next(iter(out))
        out[first] = notes
    else:
        out[''] = notes
    return out


def event_notes(e):
    """flat list of the change notes of one form event (rules dict order, else the plain notes)"""
    rules = e.get('rules')
    if isinstance(rules, dict) and rules:
        return [n for ns in rules.values() for n in (ns or [])]
    return list(e.get('notes') or [])


def is_write(e):
    return e.get('event') in ('form', 'retire')


def pushed_events(ev):
    return [e for e in ev if is_write(e) and e.get('result') in ('pushed', 'written-unverified')]


def is_form_event(e):
    return e.get('kind') not in OTHER_KINDS


def leftovers(pushed):
    """forms whose LAST pushed note is a TEMPORARY/diagnostic one: a probe left behind. {(module, form): note}"""
    last = {}
    for e in sorted(pushed, key=lambda x: x['ts']):
        last[(e.get('module'), e.get('form'))] = e
    out = {}
    for k, e in last.items():
        ns = event_notes(e)
        if ns and is_temp_note(ns[-1]):
            out[k] = ns[-1]
    return out


def verify_state(ev, kind, last_push_ts):
    """(state, event): ok | fail | unverified | stale | none. The newest record of the kind counts; an ok recorded before the last push is stale."""
    recs = [e for e in ev if e.get('event') == 'verify' and norm_kind(e.get('kind')) == kind]
    if not recs:
        return 'none', None
    e = max(recs, key=lambda x: x['ts'])
    res = e.get('result')
    if res == 'ok' and last_push_ts and e['ts'] < last_push_ts:
        return 'stale', e
    return res if res in ('ok', 'fail', 'unverified') else 'unverified', e


def dod_status(ev, last_push_ts):
    """([(kind, text, state, event)] for the nine items, [required kinds that are not ok])"""
    rows = [(k, t) + verify_state(ev, k, last_push_ts) for k, t in DOD]
    missing = [k for k in DOD_REQUIRED if next(r[2] for r in rows if r[0] == k) != 'ok']
    return rows, missing


def status_line(ev, pushed):
    """the headline: never lets a pushed-and-read-back result read as done"""
    if not pushed:
        return ['**STATUS: DRY RUN - nothing written**']
    last_ts = max(e['ts'] for e in pushed)
    st, e = verify_state(ev, 'browser', last_ts)
    left = leftovers(pushed)
    if st == 'ok' and not left:
        out = ['**STATUS: browser-verified (see section 7)**']
    else:
        out = ['**STATUS: PUSHED AND READ BACK - UNVERIFIED IN BROWSER. Do not call this done.**']
        if st == 'ok':
            out.append('(a browser check was recorded ok, but a TEMPORARY probe is still in a form: what was verified is not what is stored)')
        elif st == 'stale':
            out.append(f'(a browser check was recorded at {e["ts"]}, BEFORE the last push at {last_ts}: it does not cover the current state)')
        elif st == 'fail':
            out.append(f'(the last browser check FAILED: {e.get("detail")})')
    _, missing = dod_status(ev, last_ts)
    if missing:
        out.append(f'Definition of Done: {len(DOD_REQUIRED) - len(missing)} of {len(DOD_REQUIRED)} required items recorded ok; '
                   f'missing: {", ".join(missing)} (section 7).')
    for (m, f), n in sorted(left.items()):
        out.append(f'**WARNING: a TEMPORARY change is the last note on {m}/{f} ("{n[:90]}"): a probe was left behind. '
                   f'Remove it: shrec.py probe-scope {m}/{f} --remove --push (or restore the backup).**')
    return out


def window(events, run=None, all_=False):
    if all_:
        return list(events)
    if run:
        ids = set(run.split(','))
        return [e for e in events if e.get('run') in ids]
    pushed_ts = [e['ts'] for e in pushed_events(events)]
    if pushed_ts:     # a session: everything within 12 h before the latest push (pilot, fleet, notes, re-runs) up to now
        cutoff = (datetime.datetime.fromisoformat(max(pushed_ts)) - datetime.timedelta(hours=12)).isoformat(timespec='seconds')
        return [e for e in events if e['ts'] >= cutoff]
    last = events[-1]['run'] if events else None
    return [e for e in events if e.get('run') == last]


def short(notes, n=3, w=170):
    s = '; '.join(str(x).replace('\n', ' ') for x in notes[:n])
    return (s[:w] + '...') if len(s) > w else s + (f' (+{len(notes) - n} more)' if len(notes) > n else '')


def count_files(d, sub):
    return len(glob.glob(os.path.join(d, sub, '*.json')))


def fold_defects(path=None):
    """defects.jsonl is append-only: later lines with the same id win field by field. {id: defect}"""
    path = path or project.defects_path()
    out = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get('id'):
                    out.setdefault(d['id'], {}).update(d)
    return out


def _defect_sort(d):
    m = re.match(r'D-(\d+)$', d.get('id', ''))
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------- export list
def export_rows(ev, since=None):
    """One row per changed FORM since `since` (a form pushed several times is one row): module, form, role, host, rules, notes, id, link.
    Probes that were removed again, forms last written by a restore, forms still carrying a probe, entities and workflows are not exportable changes."""
    rows = {}
    pushed_ev = [e for e in pushed_events(ev) if is_form_event(e) and (not since or e['ts'] > since)]
    for e in sorted(pushed_ev, key=lambda x: x['ts']):
        key = (e.get('module'), e.get('form'))
        r = rows.setdefault(key, {'module': key[0], 'form': key[1], 'env': e.get('env'), 'host': e.get('host'), 'rules': [], 'notes': [],
                                  'form_id': e.get('form_id'), 'real': False})
        r['env'], r['host'] = e.get('env'), e.get('host')
        r['form_id'] = e.get('form_id') or r['form_id']
        for rule, notes in rules_of(e).items():
            if is_temp_rule(rule):
                continue                      # a TEMPORARY probe / diagnostic is not part of the change to export
            if rule and rule not in r['rules']:
                r['rules'].append(rule)
            for n in notes:
                if is_temp_note(n):
                    continue
                r['real'] = True
                if n not in r['notes']:
                    r['notes'].append(n)
    last = {}
    for e in sorted(pushed_ev, key=lambda x: x['ts']):
        last[(e.get('module'), e.get('form'))] = e
    left = leftovers(pushed_ev)
    for k, e in last.items():
        ns = event_notes(e)
        if ns and all(str(n).startswith('restored from run') for n in ns):
            rows.pop(k, None)               # last write was a restore: back to what it was, nothing to export
        elif k in rows and not rows[k]['real'] and k not in left:
            rows.pop(k, None)               # only temporary probes touched it and they were removed again
    for k in left:
        rows.pop(k, None)                   # a form still carrying a probe must not be exported: it would ship the probe
    for r in rows.values():
        r['link'] = ''
        try:
            portal = project.env_config(r['env']).get('portal') if r['env'] in project.ROLES else None
            if portal and r['form_id']:
                r['link'] = f"{portal.rstrip('/')}/shesha/forms-designer?id={r['form_id']}"
        except project.ConfigError:
            pass
    return [rows[k] for k in sorted(rows, key=lambda k: (str(k[0]), str(k[1])))]


def export_list_text(rows):
    """The plain list, one `Module/Form` per line, to paste into an export dialog or a command."""
    return '\n'.join(f"{r['module']}/{r['form']}" for r in rows) + ('\n' if rows else '')


def last_export_ts(events):
    ts = [e['ts'] for e in events if e.get('event') == 'export']
    return max(ts) if ts else None


# ---------------------------------------------------------------- retire candidates
def retire_candidates(ev):
    """(rows, note). rows: [(rule meta, applied form count)] for rules applied per the ledger whose pack fixedIn <= the target version."""
    applied, retired = {}, {}
    for e in ev:
        if not is_write(e) or e.get('result') not in ('pushed', 'written-unverified'):
            continue
        for rule in rules_of(e):
            if not rule:
                continue
            if e['event'] == 'retire':
                retired[rule] = max(retired.get(rule, ''), e['ts'])
            else:
                applied.setdefault(rule, {'forms': set(), 'last': ''})
                applied[rule]['forms'].add(f"{e.get('module')}/{e.get('form')}")
                applied[rule]['last'] = max(applied[rule]['last'], e['ts'])
    for rule in list(applied):
        if retired.get(rule, '') > applied[rule]['last']:
            applied.pop(rule)               # already unwound after its last application
    if not applied:
        return [], 'no rule application is recorded in this window'
    pushed = sorted(pushed_events(ev), key=lambda x: x['ts'])
    role = (pushed[-1].get('env') if pushed else None) or 'local'
    if role not in project.ROLES:
        role = 'local'
    tv = role_version(role)
    if not tv:
        return [], f'the version of the {role} role is unknown (set environments.{role}.version in project.json)'
    pack = packs.pack_for(tv, role_version('reference'))
    if not pack:
        return [], f'no rule pack for target version {tv}'
    rows = [(r, len(applied[r['id']]['forms'])) for r in packs.retire_candidates(pack, tv) if r['id'] in applied]
    return rows, f'pack {pack.get("id")}@{pack.get("version")}, target {role} {tv}'


# ---------------------------------------------------------------- the report
def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')


def build(ev, all_events=None, defects=None, now=None):
    """The report as markdown text. `ev` = the window; `all_events` = the whole ledger (to find the last export)."""
    all_events = ev if all_events is None else all_events
    L = []
    A = L.append
    forms = [e for e in ev if is_write(e)]
    pushed = pushed_events(ev)
    runs = sorted({e.get('run') for e in ev if e.get('run')})
    A(f'# Reconciliation report - {now or time.strftime("%Y-%m-%d %H:%M")}')
    for ln in status_line(ev, pushed):
        A(ln + '  ')
    A('')
    A(f'Generated from ledger.jsonl (runs: {", ".join(runs) or "none"}). Nothing here was typed by hand.\n')

    # ---- 1 where
    A('## 1. Where changes were written')
    targets = sorted({(e.get('env'), e.get('host')) for e in pushed}, key=str)
    if not targets:
        dry = sorted({(e.get('env'), e.get('host')) for e in forms if e.get('mode') == 'dry-run'}, key=str)
        A('**NOTHING WAS WRITTEN. This was a dry run (no --push).**'
          + (f' The target would have been: {", ".join(f"{str(r).upper()} ({h})" for r, h in dry)}.' if dry else ''))
    else:
        for role, host in targets:
            A(f'**Changes were written to: {str(role).upper()} - API {host}**')
        if len(targets) > 1:
            A('WARNING: this window wrote to more than one environment. Check that this is what you meant.')
    refs = sorted({h for e in ev for h in (e.get('reference_hosts') or [])})
    if not refs:
        try:
            refs = sorted(project.reference_hosts())
        except project.ConfigError:
            refs = []
    A(f'Reference (read-only, GET only, never written): {", ".join(refs) or "none used"}\n')

    # ---- 2 forms
    A('## 2. Forms')
    upd, skipped, failed, final = {}, [], [], {}
    for e in forms:
        final[(e.get('env'), e.get('module'), e.get('form'))] = e
    for e in sorted(pushed, key=lambda x: x['ts']):    # one entry per (rule, form): identical notes of repeated pushes are listed once
        for rule, notes in rules_of(e).items():
            label = (rule or '(unnamed)') + (' [retire]' if e['event'] == 'retire' else '')
            d = upd.setdefault(label, {}).setdefault(f"{e.get('module')}/{e.get('form')}", {'count': 0, 'notes': []})
            d['count'] += 1
            for n in notes or []:
                if n not in d['notes']:
                    d['notes'].append(n)
    left = leftovers(pushed)
    pushed_keys = {(e.get('env'), e.get('module'), e.get('form')) for e in pushed}
    for k, e in final.items():
        if k in pushed_keys:
            continue
        if e.get('result') == 'skipped-anchor':
            skipped.append((f'{k[1]}/{k[2]}', 'anchor missing: ' + (e.get('reason') or '')))
        elif e.get('result') == 'failed':
            failed.append((f'{k[1]}/{k[2]}', e.get('reason') or ''))
    for e in pushed:     # a write that was sent but not confirmed: listed for export AND flagged for a check
        if e.get('result') == 'written-unverified':
            failed.append((f"{e.get('module')}/{e.get('form')}", 'WRITTEN, UNVERIFIED - check the form, restore it from before/ if wrong: '
                           + (e.get('reason') or '')))
    for k in sorted(pushed_keys, key=str):
        last_ok = max(x['ts'] for x in pushed if (x.get('env'), x.get('module'), x.get('form')) == k)
        later = [e for e in forms if (e.get('env'), e.get('module'), e.get('form')) == k and e.get('result') == 'failed' and e['ts'] > last_ok]
        if later:
            failed.append((f'{k[1]}/{k[2]}', 'a later write failed: ' + (later[-1].get('reason') or '')))
    done_names = {f'{k[1]}/{k[2]}' for k in pushed_keys}
    nochange = sorted({f"{e.get('module')}/{e.get('form')}" for e in forms if e.get('result') == 'no-change'} - done_names)
    would = sorted({f"{e.get('module')}/{e.get('form')}" for e in forms if e.get('result') == 'dry-run'} - done_names)
    A(f'Updated: **{len(pushed_keys)}** | would change (dry run, not written): {len(would)} | skipped: {len(skipped)} | '
      f'failed: {len(failed)} | already applied / no change: {len(nochange)}\n')
    if upd:
        A('### Updated, by rule')
        for rule in sorted(upd):
            tmp = is_temp_rule(rule) or any(is_temp_note(n) for d in upd[rule].values() for n in d['notes'])
            A(f'#### {rule}' + ('  [TEMPORARY / diagnostic: not part of the final change, must not be exported]' if tmp else ''))
            for f, d in sorted(upd[rule].items()):
                cnt = f' (x{d["count"]})' if d['count'] > 1 else ''
                A(f'- {f}{cnt}: {short(d["notes"]) or "changed"}')
            A('')
        batches = {}
        for e in pushed:
            b = batches.setdefault(e.get('batch') or e.get('run') or '-', {'forms': set(), 'rules': set()})
            b['forms'].add(f"{e.get('module')}/{e.get('form')}")
            b['rules'].update(r for r in rules_of(e) if r)
        A('### By batch')
        A('| Batch | Forms | Rules |\n|---|---|---|')
        for b in sorted(batches):
            A(f"| {b} | {len(batches[b]['forms'])} | {', '.join(sorted(batches[b]['rules'])).replace('|', '/')} |")
        A('')
        for (m, f), n in sorted(left.items()):
            A(f'**WARNING - probe left behind: the last note for `{m}/{f}` is TEMPORARY ("{n[:100]}"). Remove it '
              f'(`shrec.py probe-scope {m}/{f} --remove --push`, or restore the backup) before anything is exported.**\n')
    if would and not pushed_keys:
        A('### Would change (dry run)')
        for f in would[:80]:
            A(f'- {f}')
        A('')
    if skipped:
        A('### Skipped')
        for f, why in sorted(skipped):
            A(f'- {f}: {why[:200]}')
        A('')
    if failed:
        A('### Failed')
        for f, why in sorted(failed):
            A(f'- {f}: {why[:200]}')
        A('')
    if nochange:
        A('### Already applied / no change')
        A(', '.join(nochange[:40]) + (f' ... (+{len(nochange) - 40} more)' if len(nochange) > 40 else ''))
        A('')

    # ---- 3 backups
    A('## 3. Backups and how to revert')
    seen = set()
    ex_rule = next((r for r in sorted(upd) if not is_temp_rule(r) and '[retire]' not in r), None)
    for e in pushed:
        role = e.get('env')
        d = project.work_path('backups', str(role), str(e.get('run')), mkdir=False)
        if d in seen:
            continue
        seen.add(d)
        A(f'- `{d}`: {count_files(d, "snapshot")} forms in the whole-run snapshot, {count_files(d, "before")} per-write backups, '
          f'{count_files(d, "after")} "after" files, manifest.json')
        A(f'  - revert the whole run (dry run first): `shrec.py restore --run {e.get("run")} --target {role} --all`, then add `--push`')
        first = sorted(k for k in pushed_keys if k[0] == role)[:1]
        if ex_rule and first:
            A(f'  - revert one rule: `shrec.py restore --run {e.get("run")} --target {role} --rule {ex_rule}`; '
              f'one form: `shrec.py restore --run {e.get("run")} --target {role} --form {first[0][1]}/{first[0][2]}`')
        A('  - restoring is a write: same host confirmation, backs up the current row first, reads back; clear browser form caches afterwards')
    if not seen:
        A('No backups were needed: nothing was written.')
    A('')

    # ---- 4 export
    since = last_export_ts(all_events)
    rows = export_rows(ev, since)
    A('## 4. What to export (manually, once the reviewer is happy and has tested - nothing was exported by this report)')
    A(f'Changes since the last export event ({since})' if since else 'No export event is recorded yet: every change in this window counts.')
    blocked = sorted(leftovers([e for e in pushed if is_form_event(e) and (not since or e['ts'] > since)]))
    if blocked:
        A('\n**NOT exportable until the probe is removed:** ' + ', '.join(f'{m}/{f}' for m, f in blocked) + '.')
    if rows:
        role0 = rows[0]['env'] or 'local'
        A(f'\nThese {len(rows)} forms changed. Export ONLY these (a subset package is the smallest blast radius; later-named packages '
          'overwrite earlier ones). No package was exported and no PR was opened:\n')
        A('```')
        A(f'shrec.py export-package --target {role0} --forms {",".join(r["module"] + "/" + r["form"] for r in rows)} --apply --reviewer-approved')
        A('```')
        A('(`--reviewer-approved` only once the reviewer has said to export. Then verify with '
          f'`shrec.py verify-package <package> --forms-file <list file> --compare-role {role0}`.)')
    else:
        A('\nNo forms are ready to export from this window.')
    oth = [e for e in ev if e.get('event') == 'other'] + [e for e in pushed if not is_form_event(e)]
    A('\nOther configs touched (not forms):' if oth else '\nOther configs touched (not forms): none recorded.')
    for e in oth:
        if e.get('event') == 'other':
            A(f"- {e.get('kind')}: {e.get('what')}" + (f" (backup {e['backup']})" if e.get('backup') else ''))
        else:
            A(f"- {e.get('kind')}: {e.get('module')} / {e.get('form')}: {short(event_notes(e), 2, 120)}" + (f" (backup {e['backup']})" if e.get('backup') else ''))
    notes = [e for e in ev if e.get('event') == 'note']
    A('\nNon-config follow-ups found:' if notes else '\nNon-config follow-ups found: none recorded.')
    for e in notes:
        A(f"- {e.get('category')}: {e.get('text')}")
    A('Not detectable by this tool - check and record with `shrec.py note`: backend migrations (migration-check), file blobs and '
      'templates in the target file store, reference-list items missing on the target.\n')
    if rows:
        A('### Forms to export - checklist')
        A('| # | Module | Form | What changed | Open in the designer |')
        A('|---|---|---|---|---|')
        for i, r in enumerate(rows, 1):
            what = short(r['notes'], n=2, w=110) or ', '.join(r['rules']) or 'changed'
            A(f"| {i} | {r['module']} | `{r['form']}` | {what.replace('|', '/')} | {('[open](' + r['link'] + ')') if r['link'] else '-'} |")
        A('\nTick them off as you export:\n')
        for r in rows:
            A(f"- [ ] {r['module']} / {r['form']}")
        A('')

    # ---- 5 defects
    defects = fold_defects() if defects is None else defects
    A('## 5. Defects')
    if not defects:
        A('No defects are recorded (`shrec.py defect add ...`).')
    else:
        applied_rules = set(upd) | {r.replace(' [retire]', '') for r in upd}
        by_status = {}
        for d in defects.values():
            by_status.setdefault(d.get('status') or 'open', []).append(d)
        A('Status: ' + ' | '.join(f'{s} {len(by_status.get(s, []))}' for s in STATUSES if by_status.get(s))
          + (' | other ' + str(sum(len(v) for k, v in by_status.items() if k not in STATUSES)) if any(k not in STATUSES for k in by_status) else ''))
        A('')
        A('### By status')
        A('| ID | Status | Hazard | Where | Title | Rule | Evidence |\n|---|---|---|---|---|---|---|')
        order = list(STATUSES) + sorted(k for k in by_status if k not in STATUSES)
        for s in order:
            for d in sorted(by_status.get(s, []), key=_defect_sort):
                w = d.get('where') or d.get('where_text') or {}
                where = (str(w) if not isinstance(w, dict)            # hand-written / imported registers may hold free text
                         else '/'.join(str(x) for x in (w.get('module'), w.get('form'), w.get('component')) if x)) or '-'
                rule = d.get('rule') or ''
                rlink = f'[{rule}](#{slug(rule)})' if rule and rule in applied_rules else (f'`{rule}`' if rule else '-')
                A(f"| {d['id']} | {s} | {d.get('hazard') or '-'} | {where} | {str(d.get('title') or '').replace('|', '/')[:90]} | {rlink} | "
                  f"{str(d.get('evidence') or '-').replace('|', '/')[:80]} |")
        A('')
        A('### By hazard')
        haz = {}
        for d in defects.values():
            h = d.setdefault('hazard', None) or '(none)'
            x = haz.setdefault(h, {'n': 0, 'open': 0, 'rules': set()})
            x['n'] += 1
            x['open'] += 1 if (d.get('status') or 'open') in ('open', 'pilot', 'verify') else 0
            if d.get('rule'):
                x['rules'].add(d['rule'])
        A('| Hazard | Defects | Still open (open, pilot, verify) | Rules |\n|---|---|---|---|')
        for h in sorted(haz):
            A(f"| {h} | {haz[h]['n']} | {haz[h]['open']} | {', '.join(sorted(haz[h]['rules'])) or '-'} |")
    A('')

    # ---- 6 retire candidates
    A('## 6. RETIRE CANDIDATES')
    cands, why = retire_candidates(ev)
    if cands:
        A(f'The framework fixed these in a version at or below the target ({why}); the workarounds the ledger shows applied can be unwound '
          '(prove the fix on the target first when the pack only claims it from release notes):\n')
        A('| Rule | Fixed in | Evidence | Forms where applied |\n|---|---|---|---|')
        for r, n in cands:
            A(f"| {r['id']} | {r.get('fixedIn')} | {r.get('fixedEvidence') or 'unverified claim'} | {n} |")
        A('\nUnwind: `shrec.py retire --rules ' + ','.join(r['id'] for r, _ in cands) + '` (dry run; add --push; --claimed when the fix is only claimed).')
    else:
        A(f'None ({why}).')
    A('')

    # ---- 7 verification
    A('## 7. Verification')
    sums = [e for e in ev if e.get('event') == 'summary']
    first_push_ts = min((e['ts'] for e in pushed), default=None)
    reruns = [s for s in sums if s.get('dry') and first_push_ts and s['ts'] > first_push_ts]
    if pushed:
        if reruns and reruns[-1].get('forms_changed') == 0:
            A(f"- Re-run after the push (dry run): **forms changed 0** ({reruns[-1].get('script')}, {reruns[-1]['ts']}) - the write persisted and the rules are idempotent.")
        elif reruns:
            A(f"- Re-run after the push: forms changed {reruns[-1].get('forms_changed')} (expected 0) - INVESTIGATE: {reruns[-1].get('failed')}")
        else:
            A('- Re-run after the push: **NOT DONE** - run the same command again without --push and expect "forms changed 0".')
        A('- Per-write read-back (markup and modelType equal what was sent): done by the push helper for every pushed form.'
          if not failed else '- Per-write read-back: see the failed list above.')
        A('- These prove the write PERSISTED. They do not prove the page WORKS: see the Definition of Done below.')
    ver = sorted((e for e in ev if e.get('event') == 'verify'), key=lambda x: x['ts'])
    last_push = max((e['ts'] for e in pushed), default=None)
    for e in ver:
        stale = ' (STALE: recorded before the last push)' if e.get('result') == 'ok' and last_push and e['ts'] < last_push else ''
        A(f"- {norm_kind(e.get('kind'))}: {e.get('result')}{stale} - {e.get('detail')}")
    kinds = {norm_kind(e.get('kind')) for e in ver}
    for k, msg in (('browser', 'browser check of the changed pages (the reviewer\'s own browser, after clearing the form caches)'),
                   ('e2e', 'e2e save check on forms with a Save (e2e-save)')):
        if k not in kinds:
            A(f'- UNVERIFIED: {msg}')
    dod_rows, dod_missing = dod_status(ev, last_push) if pushed else ([], [])
    if pushed:
        A('\n### Definition of Done (every item measured in a FRESH browser context, 3+ loads; record with `shrec.py verify --kind K --result ok|fail|unverified --detail D`)')
        A('| # | Item (kind) | State | Detail |\n|---|---|---|---|')
        label = {'ok': 'ok', 'fail': '**FAIL**', 'unverified': 'UNVERIFIED', 'stale': '**STALE** (recorded before the last push)', 'none': '**NOT RECORDED**'}
        for i, (k, text, st, e) in enumerate(dod_rows, 1):
            req = ' *(required)*' if k in DOD_REQUIRED else ''
            A(f"| {i} | {text} (`{k}`){req} | {label[st]} | {((e or {}).get('detail') or '').replace('|', '/')[:140]} |")
        if dod_missing:
            A(f'\n**Iron rule: "done" needs placement, request-audit, data-audit, row-content, write-path and read-path recorded ok. '
              f'Not yet ok: {", ".join(dod_missing)}. Write "pushed and read back, UNVERIFIED in browser", never "done" or "fixed".**')
        else:
            A('\nAll six required items are recorded ok after the last push. Items 7-9 are still needed before export.')
    A('')

    # ---- 8 next
    A('## 8. Next steps')
    n = [0]

    def step(t):
        n[0] += 1
        A(f'{n[0]}. {t}')
    for (m, f), _ in sorted(left.items()):
        step(f'**Remove the probe left in {m}/{f}** (`shrec.py probe-scope {m}/{f} --remove --push`), then re-run this report.')
    if pushed and dod_missing:
        step(f'**Definition of Done items not recorded ok: {", ".join(dod_missing)}.** Measure them in a fresh browser context, 3+ loads '
             '(`dom-chain` placement, `audit-requests` request + data audit, the real Save/Add click on the local role, row content against the '
             'database), then record each with `shrec.py verify --kind <kind> --result ok|fail --detail "<detail>"`.')
    if pushed:
        extra = [k for k, _, st, _ in dod_rows if k not in DOD_REQUIRED and st != 'ok']
        if extra:
            step(f'Also still open before export: {", ".join(extra)}.')
    if cands:
        step('Review the retire candidates (section 6) once the reviewer has accepted the current state.')
    step('Clear the browser form caches, close stale designer tabs on the changed forms (a stale tab saves old markup over the push), and check '
         'the pages in a real browser: that is the completion signal.')
    step('Record every UNVERIFIED item above (`shrec.py verify ...`) once checked.')
    step('When the reviewer is happy: export the subset from section 4, verify the package, commit explicit paths and open the PR. '
         '**Never merge a PR** - the repository maintainer merges.')
    if failed or skipped:
        step('Review the failed / skipped forms: a missing anchor means the form differs from what the rule expects; do not force it.')
    return '\n'.join(L) + '\n'


# ---------------------------------------------------------------- html
CSS = """
:root{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--card:#f6f8fa;--warn-bg:#fff4e5;--warn-fg:#7a3e00;--warn-line:#f0b663;
--ok-bg:#e8f6ec;--ok-fg:#14532d;--ok-line:#7bc99a;--code:#eff1f3;--link:#0b5fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1318;--fg:#e6e9ee;--muted:#9aa4b2;--line:#2b333d;--card:#171c23;
--warn-bg:#3a2a12;--warn-fg:#ffd8a0;--warn-line:#8a6420;--ok-bg:#12301e;--ok-fg:#b6e8c8;--ok-line:#2f7a4a;--code:#1d242c;--link:#7aa7ff}}
:root[data-theme="dark"]{--bg:#0f1318;--fg:#e6e9ee;--muted:#9aa4b2;--line:#2b333d;--card:#171c23;--warn-bg:#3a2a12;--warn-fg:#ffd8a0;
--warn-line:#8a6420;--ok-bg:#12301e;--ok-fg:#b6e8c8;--ok-line:#2f7a4a;--code:#1d242c;--link:#7aa7ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;margin:0 0 12px}h2{font-size:1.2rem;margin:32px 0 10px;
padding-bottom:6px;border-bottom:1px solid var(--line)}h3{font-size:1.05rem;margin:22px 0 8px}h4{font-size:.98rem;margin:16px 0 6px}
p{margin:8px 0}a{color:var(--link)}code{background:var(--code);padding:1px 5px;border-radius:4px;font:13px/1.4 ui-monospace,Consolas,monospace}
pre{background:var(--code);padding:12px;border-radius:6px;overflow:auto}pre code{background:none;padding:0}
.banner{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:8px 0 16px;background:var(--card)}
.banner.warn{background:var(--warn-bg);color:var(--warn-fg);border-color:var(--warn-line)}.banner.ok{background:var(--ok-bg);color:var(--ok-fg);border-color:var(--ok-line)}
.tablewrap{overflow-x:auto;margin:10px 0}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}th{background:var(--card)}
ul,ol{padding-left:22px;margin:8px 0}li.sub{margin-left:22px;list-style:circle}li.task{list-style:none;margin-left:-18px}
@media (max-width:600px){main{padding:16px}}
"""


def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*([^*\s][^*]*?)\*', r'<em>\1</em>', s)

    def link(m):
        text, url = m.group(1), html.unescape(m.group(2))
        if re.match(r'^(https?://|#|[\w./-]+$)', url):
            return f'<a href="{html.escape(url, quote=True)}">{text}</a>'
        return text
    return re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', link, s)


def md_to_html(md, title='Reconciliation report'):
    """Convert the markdown subset this report emits (headings, paragraphs, lists, tables, code fences, bold/code/links) to one page."""
    out, lines, i = [], md.split('\n'), 0
    first_para = True
    while i < len(lines):
        ln = lines[i]
        if ln.startswith('```'):
            j, buf = i + 1, []
            while j < len(lines) and not lines[j].startswith('```'):
                buf.append(lines[j])
                j += 1
            out.append('<pre><code>' + html.escape('\n'.join(buf)) + '</code></pre>')
            i = j + 1
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', ln)
        if m:
            lvl = len(m.group(1))
            text = re.sub(r'\s+\[TEMPORARY.*$', '', m.group(2)) if lvl == 4 else m.group(2)
            out.append(f'<h{lvl} id="{slug(text)}">{_inline(m.group(2))}</h{lvl}>')
            i += 1
            continue
        if ln.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(re.match(r'^:?-{3,}:?$', c) for c in r)]
            t = '<div class="tablewrap"><table><thead><tr>' + ''.join(f'<th>{_inline(c)}</th>' for c in head) + '</tr></thead><tbody>'
            t += ''.join('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in r) + '</tr>' for r in body)
            out.append(t + '</tbody></table></div>')
            continue
        if re.match(r'^\s*(- |\d+\. )', ln):
            ordered = bool(re.match(r'^\d+\. ', ln))
            items = []
            while i < len(lines) and re.match(r'^\s*(- |\d+\. )', lines[i]):
                raw = lines[i]
                sub = raw.startswith('  ')
                body = re.sub(r'^\s*(- |\d+\. )', '', raw)
                cls = ' class="sub"' if sub else ''
                if body.startswith('[ ] ') or body.startswith('[x] '):
                    items.append(f'<li class="task"><input type="checkbox" disabled{" checked" if body[1] == "x" else ""}> {_inline(body[4:])}</li>')
                else:
                    items.append(f'<li{cls}>{_inline(body)}</li>')
                i += 1
            tag = 'ol' if ordered else 'ul'
            out.append(f'<{tag}>' + ''.join(items) + f'</{tag}>')
            continue
        if not ln.strip():
            i += 1
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,4}\s|\||```|\s*(- |\d+\. ))', lines[i]):
            buf.append(lines[i].rstrip())
            i += 1
        para = '<br>'.join(_inline(b) for b in buf)
        if first_para and out:                    # the headline block right under the title
            cls = 'ok' if 'browser-verified' in para else ('warn' if 'UNVERIFIED' in para or 'WARNING' in para else '')
            out.append(f'<div class="banner {cls}">{para}</div>')
            first_para = False
        else:
            out.append(f'<p>{para}</p>')
    body = '\n'.join(out)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>\n{body}\n</main></body></html>\n')


# ---------------------------------------------------------------- cli
def main(argv):
    ap = argparse.ArgumentParser(prog='shrec report', description='End-of-run report from the ledger.')
    ap.add_argument('--run', help='run id(s), comma separated')
    ap.add_argument('--all', action='store_true', help='the whole ledger')
    ap.add_argument('--html', action='store_true', help='also write a self-contained .html')
    ap.add_argument('--out', help='markdown output file (default <work>/reports/<timestamp>.md)')
    a = ap.parse_args(argv)
    everything = ledger.read()
    ev = window(everything, a.run, a.all)
    text = build(ev, everything)
    out = a.out or os.path.join(project.work_path('reports', mkdir=False), time.strftime('%Y%m%d-%H%M%S') + '.md')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode())
    print('saved:', out)
    if a.html:
        hp = os.path.splitext(out)[0] + '.html'
        with open(hp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(md_to_html(text, 'Reconciliation report'))
        print('saved:', hp)
    rows = export_rows(ev, last_export_ts(everything))
    if rows:
        lst = os.path.splitext(out)[0] + '-export-list.txt'
        with open(lst, 'w', encoding='utf-8', newline='\n') as f:
            f.write(export_list_text(rows))
        print(f'export list ({len(rows)} forms, one Module/Form per line): {lst}')
    return 0
