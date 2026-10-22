"""shrec - Shesha upgrade reconciler CLI. Run from inside the project repository (or pass --project <repo>).

Setup
  init [--name N] [--modules A,B] [--reference-api U --reference-portal U --reference-version V]
       [--local-api U --local-portal U --local-version V] [--deployed-api U --deployed-portal U --deployed-version V]
                                  create or update .shesha-reconcile/project.json and its .gitignore
  init-creds                      create the gitignored credentials template (the user types their own values)
  status                          configuration, credentials filled (booleans only), write target, versions
  probe-env <role>                read-only reachability + auth check of one role
  confirm-target --api U          record the ONE host the user confirmed as the write target (local or deployed)
  authorise-deployed --api U      record the user's go-ahead for deployed writes (expires after $SHREC_DEPLOY_TTL_MIN, default 120)
  revoke-deployed                 clear it
  versions                        configured + detected versions, and the pack that applies
  plan [--target local|deployed]  every rule's fate for the target version (apply / claimed fixed / fixed / opt-in / disabled)
Write (dry run unless --push)
  apply [--rules a,b] [--only f,g | --only-file F] [--target local|deployed] [--push]
  retire --rules a,b [--only ...] [--target ...] [--push] [--claimed]   unwind workarounds the framework now fixes
Tracking
  defect add --title T [--hazard H] [--rule R] [--form M/F] [--component C] [--status S] [--evidence E]
  defect set D-<n> [--status S] [--rule R] [--evidence E] [--title T]
  defect list [--status S]
  verify --kind K --result ok|fail|unverified [--detail D]
  note --category C --text T
  other --kind K --what W [--backup B]   a non-form configuration change (theme settings, reference list) for the export list
  report [--run R | --all] [--html]
Tools (scripts/tools/<name>.py): snapshot, capture, compare, detect, audit-requests, probe-scope, dom-chain, e2e-save,
  merge3, sync-forms, branch-changed (alias sprint-changed), restore, export-package, verify-package, migration-check, sqlq, leakcheck, report
Hygiene
  selftest                        offline rule fixtures (idempotence, retire round-trips) + syntax gate
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import project, versions, packs, engine, ledger   # noqa: E402
from core.project import ConfigError, WriteRefused           # noqa: E402

TOOLS = {'snapshot', 'capture', 'compare', 'detect', 'audit-requests', 'probe-scope', 'dom-chain', 'e2e-save', 'merge3',
         'sync-forms', 'branch-changed', 'sprint-changed', 'restore', 'export-package', 'verify-package', 'migration-check', 'sqlq', 'leakcheck',
         'report'}
STATUSES = ('open', 'pilot', 'fixed', 'framework', 'data', 'legacy', 'accepted', 'verify')
GITIGNORE = '# local only (shesha-upgrade-reconciler)\nwork/\ncredentials.local.json\n'


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def validate_url(url, role):
    p = []
    if not re.match(r'^https?://[^/\s]+$', (url or '').rstrip('/')):
        return ['must be http(s)://host[:port] with no path, query or fragment']
    if url.endswith('/'):
        p.append('remove the trailing slash')
    if project.has_userinfo(url):
        return ['no user info (user@host) in a url: credentials go only in credentials.local.json']
    local = project.is_localhost(url)
    if role == 'local' and not local:
        p.append('the local role must be a localhost address')
    if role != 'local' and local:
        p.append('a localhost address belongs to the local role')
    if role != 'local' and not url.startswith('https://'):
        p.append('a remote site must use https')
    return p


# ---------------------------------------------------------------- setup
def cmd_init(args):
    root = os.path.abspath(opt(args, '--project') or os.environ.get('SHREC_PROJECT') or os.getcwd())
    home = os.path.join(root, project.DIRNAME)
    path = os.path.join(home, 'project.json')
    cur = project.read_json(path)
    if cur is None:                        # fresh project: start from the example without its <placeholders>
        cur = project.read_json(os.path.join(HERE, '..', 'assets', 'project.example.json'), {})
        cur.pop('_comment', None)
        cur['name'], cur['modules'] = '', []
        cur['environments'] = {r: {k: v for k, v in blk.items() if '<' not in str(v)}
                               for r, blk in (cur.get('environments') or {}).items()}
        cur['environments'] = {r: blk for r, blk in cur['environments'].items() if blk.get('api')}
        for blk in cur['environments'].values():
            blk.pop('version', None)       # versions are never assumed: pass --<role>-version or detect them
    if opt(args, '--name'):
        cur['name'] = opt(args, '--name')
    if opt(args, '--modules'):
        cur['modules'] = [m.strip() for m in opt(args, '--modules').split(',') if m.strip()]
    problems = []
    envs = cur.setdefault('environments', {})
    for role in project.ROLES:
        for part in ('api', 'portal', 'version'):
            v = opt(args, f'--{role}-{part}')
            if v is None:
                continue
            if part != 'version':
                pr = validate_url(v, role)
                if pr:
                    problems.append({f'{role}-{part}': pr})
                    continue
            elif not versions.parse(v):
                problems.append({f'{role}-version': ['not a version like 0.46.1']})
                continue
            envs.setdefault(role, {})[part] = v.rstrip('/')
    ref = {project.netloc((envs.get('reference') or {}).get(p)) for p in ('api', 'portal')} - {''}
    for role in ('local', 'deployed'):
        for part in ('api', 'portal'):
            if project.netloc((envs.get(role) or {}).get(part)) in ref:
                problems.append({f'{role}-{part}': ['this is the reference host: the reference is read-only and never a write target']})
    if problems:
        out({'ok': False, 'problems': problems}, 1)
    project.write_json(path, cur)
    gi = os.path.join(home, '.gitignore')
    if not os.path.exists(gi):
        with open(gi, 'w', encoding='utf-8', newline='\n') as f:
            f.write(GITIGNORE)
    for f in ('ledger.jsonl', 'defects.jsonl'):
        p = os.path.join(home, f)
        if not os.path.exists(p):
            open(p, 'a', encoding='utf-8').close()
    out({'ok': True, 'project': path, 'next': 'shrec.py init-creds, then probe-env per role, then versions and plan'})


def cmd_init_creds(_):
    path = os.path.join(project.home(), 'credentials.local.json')
    created = False
    if not os.path.exists(path):
        project.write_json(path, {'_readme': 'Type your OWN username and password into each block you use. Gitignored: never commit '
                                             'it, never paste it into chat. reference = the pre-upgrade site (read-only); local = '
                                             'your localhost upgraded stack; deployed = the deployed upgraded site.',
                                  'reference': {'username': '', 'password': ''}, 'local': {'username': '', 'password': ''},
                                  'deployed': {'username': '', 'password': ''}})
        created = True
    ignored = subprocess.run(['git', '-C', project.root(), 'check-ignore', '-q', path]).returncode == 0
    out({'file': path, 'created': created, 'gitignored': ignored,
         'tell_the_user': 'Open the file and type your own credentials into the blocks you use; do not paste them into chat.'},
        0 if ignored else 1)


def cmd_status(_):
    envs = project.environments()
    out({'project': project.root(), 'name': project.config().get('name'), 'modules': project.config().get('modules'),
         'environments': {r: {k: v for k, v in (envs.get(r) or {}).items()} for r in project.ROLES if envs.get(r)},
         'credentials_filled': project.creds_status(), 'write_target': project.write_target(),
         'deployed_authorised': bool(envs.get('deployed')) and project.deployed_authorised((envs.get('deployed') or {}).get('api'))})


def cmd_probe_env(args):
    role = args[0] if args else None
    if role not in project.ROLES:
        out({'ok': False, 'problem': 'probe-env <reference|local|deployed>'}, 1)
    base = project.env_config(role)['api']
    res = {'role': role, 'api': base, 'problems': validate_url(base, role)}
    code, body = None, ''
    for ep in ('GetCurrentLoginInfo', 'GetCurrentLoginInformations'):     # 0.45+/0.46 and 0.43 names; GETs only
        try:
            with urllib.request.urlopen(urllib.request.Request(base + '/api/services/app/Session/' + ep,
                                                               headers={'Accept': 'application/json'}), timeout=30) as r:
                code, body = r.status, r.read(4096).decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read(4096).decode('utf-8', 'replace')
        except Exception as e:
            out(res | {'ok': False, 'error': f'{type(e).__name__}: {str(e)[:160]}',
                       'next': 'is the backend running and the URL right? Never start or restart a developer backend yourself - ask.'}, 1)
        if code != 404:
            res['login_info_endpoint'] = ep
            break
    res['http_status'] = code
    res['shesha_api'] = code in (200, 401, 403) and any(k in body for k in ('"result"', '"error"', '"success"')) or code in (401, 403)
    if not res['shesha_api']:
        out(res | {'ok': False, 'next': 'the host answered but not like a Shesha API: check the API url (not the portal url)'}, 1)
    try:
        from core.api import Api
        Api(role)
        res['auth'] = 'ok'
    except ConfigError:
        res['auth'] = 'no credentials filled in yet'
    except Exception as e:
        res['auth'] = f'rejected ({type(e).__name__})'
    out(res | {'ok': res['auth'] == 'ok'}, 0 if res['auth'] == 'ok' else 1)


def cmd_confirm_target(args):
    api = (opt(args, '--api') or '').rstrip('/')
    envs = project.environments()
    role = next((r for r in ('local', 'deployed') if (envs.get(r) or {}).get('api') == api), None)
    if not role:
        out({'ok': False, 'problem': 'pass --api with the EXACT api url configured for the local or deployed role'}, 1)
    if project.netloc(api) in project.reference_hosts():
        out({'ok': False, 'problem': 'REFUSED: that is a reference host; the reference is never written'}, 1)
    st = project.state()
    st['write_target'] = {'role': role, 'api': api, 'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    project.save_state(st)
    out({'ok': True, 'write_target': st['write_target'], 'never_written': sorted(project.reference_hosts())})


def cmd_authorise(args):
    api = (opt(args, '--api') or '').rstrip('/')
    dep = project.environments().get('deployed') or {}
    if not api or api != dep.get('api'):
        out({'ok': False, 'problem': 'pass --api with the EXACT deployed api url configured in project.json'}, 1)
    if not api.startswith('https://') or project.netloc(api) in project.reference_hosts():
        out({'ok': False, 'problem': 'deployed writes need an https host that is not a reference host'}, 1)
    st = project.state()
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    st['deployed_authorisation'] = {'api': api, 'at': now, 'epoch': time.time()}
    st['write_target'] = {'role': 'deployed', 'api': api, 'at': now}
    project.save_state(st)
    out({'ok': True, 'authorised_host': api, 'expires_after_minutes': int(os.environ.get('SHREC_DEPLOY_TTL_MIN') or project.DEPLOY_TTL_MIN),
         'also_needed_per_shell': 'SHREC_DEPLOY_CONFIRM=<this exact host> and SHREC_TARGET=deployed (or --target deployed)'})


def cmd_revoke(_):
    st = project.state()
    st.pop('deployed_authorisation', None)
    if (st.get('write_target') or {}).get('role') == 'deployed':
        st.pop('write_target', None)
    project.save_state(st)
    out({'ok': True})


def version_pair(role):
    envs = project.environments()
    tv = (envs.get(role) or {}).get('version')
    if not tv and role == 'local':
        tv = versions.detect_repo(project.root()).get('framework')
    return (envs.get('reference') or {}).get('version'), tv


def cmd_versions(_):
    det = versions.detect_repo(project.root())
    rv, tv = version_pair('local')
    pack = packs.pack_for(tv, rv)
    out({'configured': {r: (project.environments().get(r) or {}).get('version') for r in project.ROLES},
         'detected_in_repo': det, 'pair_for_local': {'from': rv, 'to': tv},
         'pack': pack and {'id': pack['id'], 'version': pack.get('version'), 'target': pack.get('target'), 'hazards': pack.get('hazards')},
         'available_packs': [{'id': p['id'], 'target': p.get('target')} for p in packs.list_packs()]})


def _rules_cfg():
    r = project.config().get('rules') or {}
    return set(r.get('enable') or ()), set(r.get('disable') or ())


def cmd_plan(args):
    role = opt(args, '--target', 'local')
    rv, tv = version_pair(role)
    pack = packs.pack_for(tv, rv)
    if not pack:
        out({'ok': False, 'problem': f'no rule pack for {rv} -> {tv}: set the versions in project.json or add a pack (references/rule-authoring.md)'}, 1)
    en, dis = _rules_cfg()
    rows = [{'rule': m['id'], 'hazard': m.get('hazard'), 'kind': m.get('kind'), 'fate': fate,
             'fixedIn': m.get('fixedIn'), 'evidence': m.get('fixedEvidence'), 'title': m.get('title')}
            for m, fate in packs.plan(pack, tv, en, dis)]
    rows += [{'rule': m['id'], 'kind': m.get('kind', 'fleet'), 'fate': 'project-rule', 'title': m.get('title')}
             for m, _, _ in packs.load_project_rules()]
    out({'pack': f"{pack['id']}@{pack.get('version')}", 'from': rv, 'to': tv, 'rules': rows,
         'retire_candidates': [r['id'] for r in packs.retire_candidates(pack, tv)]})


def _write_args(args):
    role = opt(args, '--target', os.environ.get('SHREC_TARGET', 'local'))
    if role not in ('local', 'deployed'):
        out({'ok': False, 'problem': '--target is local or deployed; the reference is never written'}, 1)
    os.environ['SHREC_TARGET'] = role
    only = opt(args, '--only')
    only = [x.strip() for x in only.split(',')] if only else None
    if opt(args, '--only-file'):
        lst = project.read_json(opt(args, '--only-file'))
        only = (only or []) + (list(lst) if isinstance(lst, (list, dict)) else [])
        if not only:
            out({'ok': False, 'problem': 'the --only-file list is empty'}, 1)
    rules = opt(args, '--rules')
    return role, only, [x.strip() for x in rules.split(',')] if rules else None, '--push' not in args


def cmd_apply(args, mode='apply'):
    role, only, rule_ids, dry = _write_args(args)
    rv, tv = version_pair(role)
    pack = packs.pack_for(tv, rv)
    if not pack:
        out({'ok': False, 'problem': f'no rule pack for {rv} -> {tv}: set the versions in project.json (`versions`, `plan`)'}, 1)
    en, dis = _rules_cfg()
    if mode == 'retire':
        if not rule_ids:
            out({'ok': False, 'problem': 'retire needs --rules (see `plan` retire_candidates)'}, 1)
        cands = {r['id']: r for r in packs.retire_candidates(pack, tv)}
        bad = [r for r in rule_ids if r not in cands or (cands[r].get('fixedEvidence') != 'verified' and '--claimed' not in args)]
        if bad:
            out({'ok': False, 'problem': f'{bad}: not retire candidates for {tv}, or the fix is only claimed by release notes '
                                         '(prove it on the target, set fixedEvidence "verified", or pass --claimed after the user agrees)'}, 1)
        rules = [(m, *packs.callables(pack, m)) for m in pack['rules'] if m['id'] in rule_ids]
    else:
        rules = engine.selected_rules(pack, tv, rule_ids, en, dis)
        targeted = [m['id'] for m, _, _ in rules if m.get('kind') == 'targeted']
        if targeted and not only:
            out({'ok': False, 'problem': f'targeted rule(s) {targeted} run only on named forms: add --only <form,...> or --only-file'}, 1)
    changed, failed, total = engine.run(pack, rules, role, only, dry, mode)
    print(('DRY RUN - ' if dry else '') + f'{mode} on {role}: forms changed {len(changed)} of {total}')
    print('by rule:', dict(engine.COUNT))
    print('failed:', failed)
    print('next: shrec.py report' + ('' if dry else '  (then clear browser form caches and close stale designer tabs)'))
    sys.exit(1 if failed else 0)


# ---------------------------------------------------------------- tracking
def _defects():
    """fold defects.jsonl (append-only; later lines for the same id win field by field) -> {id: defect}"""
    out_, path = {}, project.defects_path()
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get('id'):
                out_.setdefault(d['id'], {}).update(d)
    return out_


def _append_defect(d):
    d['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    with open(project.defects_path(), 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(d, ensure_ascii=False) + '\n')
    return d


def cmd_defect(args):
    sub = args[0] if args else 'list'
    ds = _defects()
    fields = {k: opt(args, f'--{k}') for k in ('title', 'hazard', 'rule', 'component', 'status', 'evidence', 'batch')}
    if fields['status'] and fields['status'] not in STATUSES:
        out({'ok': False, 'problem': f'status is one of {STATUSES}'}, 1)
    if sub == 'add':
        if not fields['title']:
            out({'ok': False, 'problem': 'defect add needs --title'}, 1)
        n = max([int(k.split('-')[1]) for k in ds if re.match(r'D-\d+$', k)] or [0]) + 1
        d = {'id': f'D-{n}', 'status': fields['status'] or 'open'}
        form = opt(args, '--form')
        if form:
            mod, _, name = form.partition('/')
            d['where'] = {'module': mod, 'form': name, 'component': fields['component']}
        d.update({k: v for k, v in fields.items() if v and k not in ('status', 'component')})
        out({'ok': True, 'defect': _append_defect(d)})
    if sub == 'set':
        did = args[1] if len(args) > 1 else None
        if did not in ds:
            out({'ok': False, 'problem': f'unknown defect {did}'}, 1)
        d = {'id': did, **{k: v for k, v in fields.items() if v and k != 'component'}}
        if fields['component'] or opt(args, '--form'):     # keep the same shape as `add`: where{module, form, component}
            old_where = ds[did].get('where')
            where = dict(old_where) if isinstance(old_where, dict) else ({'text': old_where} if old_where else {})
            if opt(args, '--form'):
                where['module'], _, where['form'] = opt(args, '--form').partition('/')
            if fields['component']:
                where['component'] = fields['component']
            d['where'] = where
        out({'ok': True, 'defect': _append_defect(d)})
    rows = [d for d in ds.values() if not fields['status'] or d.get('status') == fields['status']]
    out({'count': len(rows), 'defects': sorted(rows, key=lambda d: int(d['id'].split('-')[1]) if d['id'][2:].isdigit() else 0)})


def cmd_verify(args):
    kind, result = opt(args, '--kind'), opt(args, '--result')
    if not kind or result not in ('ok', 'fail', 'unverified'):
        out({'ok': False, 'problem': 'verify --kind <item> --result ok|fail|unverified [--detail D]'}, 1)
    out({'ok': True, 'event': ledger.event('verify', env=os.environ.get('SHREC_TARGET', 'local'), kind=kind, result=result,
                                           detail=opt(args, '--detail', ''))})


def cmd_note(args):
    if not opt(args, '--text'):
        out({'ok': False, 'problem': 'note --category C --text T'}, 1)
    out({'ok': True, 'event': ledger.event('note', category=opt(args, '--category', 'follow-up'), text=opt(args, '--text'))})


def cmd_other(args):
    """Record a non-form configuration change (theme settings, a reference list, ...) so the report lists it for export."""
    if not opt(args, '--kind') or not opt(args, '--what'):
        out({'ok': False, 'problem': 'other --kind <theme-settings|reference-list|...> --what <description> [--backup <path>]'}, 1)
    out({'ok': True, 'event': ledger.event('other', env=os.environ.get('SHREC_TARGET', 'local'), kind=opt(args, '--kind'),
                                           what=opt(args, '--what'), backup=opt(args, '--backup', ''))})


def cmd_selftest(args):
    import unittest
    suite = unittest.defaultTestLoader.discover(os.path.join(HERE, 'tests'), pattern='test_*.py', top_level_dir=HERE)
    r = unittest.TextTestRunner(verbosity=1 if '-q' in args else 2).run(suite)
    sys.exit(0 if r.wasSuccessful() else 1)


COMMANDS = {'init': cmd_init, 'init-creds': cmd_init_creds, 'status': cmd_status, 'probe-env': cmd_probe_env,
            'confirm-target': cmd_confirm_target, 'authorise-deployed': cmd_authorise, 'revoke-deployed': cmd_revoke,
            'versions': cmd_versions, 'plan': cmd_plan, 'apply': cmd_apply, 'retire': lambda a: cmd_apply(a, 'retire'),
            'defect': cmd_defect, 'verify': cmd_verify, 'note': cmd_note, 'other': cmd_other, 'selftest': cmd_selftest}


def main(argv):
    if '--project' in argv:
        i = argv.index('--project')
        os.environ['SHREC_PROJECT'] = os.path.abspath(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    os.environ.setdefault('SHREC_SCRIPT', f'shrec {cmd}')
    try:
        if cmd in COMMANDS:
            COMMANDS[cmd](args)
        elif cmd in TOOLS:
            import importlib
            mod = importlib.import_module('tools.' + cmd.replace('-', '_'))
            return mod.main(args) or 0
        else:
            print(f'unknown command {cmd}\n')
            print(__doc__)
            return 2
    except ConfigError as e:
        print(f'STOP: {e}')
        return 1
    except WriteRefused as e:
        print(f'REFUSED: {e}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
