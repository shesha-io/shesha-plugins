# Intake interview

Contents: detect first | the one question set | credentials | the reference site | the plan and one confirmation | writing to a deployed site | the end-of-run question

Run this BEFORE touching anything. Ask everything in ONE go: a single `AskUserQuestion` call that carries 4 questions together (load the tool first with
ToolSearch `select:AskUserQuestion` if it is deferred), then ONE plan confirmation. That is two interactions in total, plus the credentials file, which is
not a question. Work out every default BEFORE asking (see "Detect first") so the user mostly accepts the first option of each question. The tool adds
"Other" for free text.

All commands are `python <skill>/scripts/shrec.py <command>`, run from inside the project repository (or with `--project <repo>`). Setup commands print JSON;
`ok: false` means the interview has to resolve something before going on (read `problem` / `problems` / `next`). Never ask for, print, log or echo a
password or token.

## Detect first (no questions)

Gather what can be known without asking, so the options are real choices and not free text:

- `shrec.py status`: an existing `.shesha-reconcile/project.json` means the project is already configured. Do not repeat the interview: show what it holds and
  ask only "Use the same setup?" (Yes / Start again) together with the end-of-run question set.
- `git fetch origin`, `git branch --show-current`, `git status --short` (a dirty tree is reported in the plan), and the remote branches that look like the
  source of the change: the newest feature branches (`git branch -r --list "origin/<prefix>/*"`) and any branch named after the upgrade (the
  target default is the upgrade branch, else the current branch).
- `shrec.py versions`: the configured and detected versions and the rule pack that applies. A local stack's version is read from the repository's package pins
  (the frontend `@shesha-io/reactjs` version, which is the framework release version; the backend NuGet pin only as a fallback), because a running 0.46 backend exposes no framework-version endpoint. Deployed and reference
  versions come from `project.json`. Never assume a version: ask when it is neither configured nor detectable.
- `shrec.py status` also lists which credential blocks are filled (booleans only).
- `shrec.py probe-env local` (is a local stack answering) and, once configured, `probe-env reference` / `probe-env deployed`. Read-only.

## The one question set (ONE `AskUserQuestion` call, 4 questions, answered together)

| # | Question | Options (first = recommended / default) |
|---|---|---|
| 1 | What do you want to do? | **Merge a branch onto the reconciled forms** (merge-reconcile) / Full upgrade of ALL forms / One rule only (run or retire a single rule on the forms it applies to) |
| 2 | Where does the change come from? (merge only; skip for a full upgrade or one rule) | **Branch `origin/<newest feature branch>`** (detected) / Another branch (type it in Other) / A `.shaconfig` package file (type the path in Other) |
| 3 | Where should I write? | **Local upgraded stack** (`localhost:21021` / `:3000`, or the ports detected) / A DEPLOYED upgraded site (type the portal and API URLs in Other, or pick the one in `project.json`) |
| 4 | Is there a pre-upgrade reference to compare against (read-only)? | **Yes: the reference site recorded in `project.json`** (detected) / Yes: another site (type the portal and API URLs in Other) / Yes: a snapshot or package of the pre-upgrade forms (type the path in Other) / No reference |

When the answer to 1 is "One rule only", read the rule id from the user's free text, put it in the plan and skip question 2. For a single `.shaconfig` (answer
to 2) no branch is stored: `branch-changed --package <file> --target-ref <the target branch>` uses the packages already on the target branch as the base of each
form.

The branch a merge lands on is NOT a question: default it to the detected upgrade branch or the current branch, show it in the plan, and let the user correct it
there in free text. Same for local ports. When a typed value is missing or invalid, put ALL the problems in ONE message (a short list) and let the user answer
them in one reply. Do not go back to asking single questions.

Then record the answers (each validates its input; a localhost address is only valid for the local role and a remote site must be https):

```bash
shrec.py init --name <project> --modules <Module.A,Module.B> \
  --reference-api <url> --reference-portal <url> --reference-version <0.43.x> \
  --local-api <url> --local-portal <url> --local-version <0.46.x> \
  --deployed-api <url> --deployed-portal <url> --deployed-version <0.46.x>
shrec.py probe-env <reference|local|deployed>        # one per role, read-only
```

`init` refuses a local or deployed host that equals a reference host. With "No pre-upgrade reference" omit the reference flags and say in the plan that the
run goes without side-by-side comparison (the rules still run; verification is then against the data and the reviewer's own eyes). Check that any branch
named in the answers exists (`git rev-parse --verify origin/<name>`); fetching is allowed, merging is not yet.

## Credentials (not a question)

1. `shrec.py status` shows which blocks are filled. When all the blocks in use are filled, mention it in the plan and move on.
2. Otherwise run `shrec.py init-creds`: it creates `.shesha-reconcile/credentials.local.json` from a template (empty username and password for `reference`,
   `local`, `deployed`), never overwrites an existing file, and reports whether git ignores it (it exits non-zero when it does not: fix the ignore first).
3. Put this line in the plan: "Open `.shesha-reconcile/credentials.local.json` and type your own username and password into the blocks you use. Do not paste
   them here; I will not read them back." The plan confirmation doubles as "done": after it, run `probe-env` per role and report only "login ok / rejected".
4. Fallbacks the tool still honours after that file: `$SHREC_CREDS` (a path) and a flat `.sheshadev.local.json` in the repository root (one account for every
   role). Never put credentials in `project.json`, a command line, a commit message, a log or a PR description.

## About the reference site

The reference is NEVER written, always. Recording it tells every write path which hosts are the reference: the API client sends only GETs (plus the token
request and read-only queries), the browser helper aborts writes to its hosts, the push and restore paths refuse them, `confirm-target` refuses them. If the user
asks to write to the reference, refuse and explain: it is what everyone compares against and the tool has no write path to it. Never start, stop, rebuild or
restart a developer's backend to make a probe pass: ask.

## The plan, and ONE confirmation (one `AskUserQuestion`, not several)

Play the plan back as a short list the user can correct, then ask a SINGLE question that also records the write target. Plan template:

- Mode: merge-reconcile of `<branch>` into `<target>` / merge of a single package / full upgrade / one rule `<id>`.
- Versions: from `<reference version>` to `<target version>`, rule pack `<id@version>` (from `shrec.py versions`), and `shrec.py plan` output (each rule's fate:
  apply, claimed fixed, fixed, opt-in, disabled).
- Environments: reference `<host or none>` (READ-ONLY), local `<host>`, deployed `<host or none>`.
- Git: "I will create a new branch off `<target>` and check it out in this checkout (no git worktrees). Your current branch is `<b>`; uncommitted changes:
  `<none / yes: please commit or stash them yourself first>`."
- Read-only: the reference site (always), every GET on the deployed site, git, snapshots, package reads.
- Backups: before ANY write the full row of every form about to be touched is saved under `.shesha-reconcile/work/backups/<role>/<run>/` (a whole-run snapshot
  plus a per-write backup verified from disk); `shrec.py restore` puts them back. A push that cannot back up is refused.
- Written, and where: the forms on `<exact api url>` (local or deployed), backed up first and read back; nothing on a deployed site until the user says so
  separately.
- What will NOT happen: no work items, no merging a PR, no staging everything, no hand-built `.shaconfig`, no publishing a Draft to Live, no backend restart
  without asking, no git worktrees, no export and no PR unless the user asks at the end.
- Credentials: `<filled / the template was created: type your own values into credentials.local.json>`.
- First step: a pilot on 2-3 forms, run twice, then the fleet. The end of the run prints a report (`shrec.py report`) with where changes went, which forms
  changed, how to revert, and exactly what to export.

The single question: "I will write ONLY to `<exact api url>` (<local|deployed>) and start read-only. OK?" Options: **Yes, proceed** / Change something (type it
in Other) / Cancel. On Yes record the host: `shrec.py confirm-target --api <that exact url>` (refused when it is a reference host; the url must equal the one
configured for the local or deployed role). Every write asserts it matches this confirmed host. "Proceed" starts the read-only phases only.

## Writing to a deployed site (a separate, explicit gate)

When a flow reaches the first deployed write, stop, show the dry-run notes and ask: "Write these changes to `<exact host>` now?" (Yes, write to `<host>` / No,
keep it as a dry run). This is the only later question besides the end-of-run one. Only on Yes:

```bash
shrec.py authorise-deployed --api <the exact deployed API url from project.json>
export SHREC_DEPLOY_CONFIRM=<that same url>          # PowerShell: $env:SHREC_DEPLOY_CONFIRM = '<url>'
export SHREC_TARGET=deployed                          # or pass --target deployed on every write command
```

Then run the rule with `--target deployed --push`. Three conditions must all hold on every deployed write, and each is re-asserted per request:

1. `authorise-deployed` was run for exactly this host and is younger than its time limit (`$SHREC_DEPLOY_TTL_MIN`, default 120 minutes). It also records the host as
   the confirmed write target.
2. `SHREC_DEPLOY_CONFIRM` in the current shell equals the exact deployed API url (e.g. `https://api.example.com`).
3. The host is https, equals the deployed api in `project.json`, and is not a reference host.

Whole rows are backed up before each write, `modelType` is carried forward, and the form is read back. End the authorisation with `shrec.py revoke-deployed`
when the writing is done. A previous session's go-ahead never carries over: ask again in every session.

## The end-of-run question (one `AskUserQuestion`)

After `shrec.py report` prints the summary (forms changed, what to export, how to revert), ask once: "Are you happy with the result and have you tested it?"
Options: **Not yet, I will test first** / Yes, export the package and open the PR for me / Yes, I will export and open the PR myself. Export, commit, push and
the PR happen only on the second answer ([merge-reconcile.md](merge-reconcile.md) step 10, [packages-and-export.md](packages-and-export.md)). Never merge a PR.
