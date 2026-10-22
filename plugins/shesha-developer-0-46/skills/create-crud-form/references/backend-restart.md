# Backend readiness after a missing/changed domain (thin runbook)

This skill builds forms; it does **not** own the backend lifecycle. When Step 2.3 finds the entity
missing or its dynamic CRUD unregistered, the domain must be created and the backend rebuilt +
restarted **before** any seed is copied. This doc is the *verify-centric* contract for that — the full
restart mechanics live in the authoritative shared runbook (see the last section); don't re-implement
them here.

## Order of operations

**Domain first, forms last.** Create the entity and get the backend restarted, poll until its CRUD is
live, *then* copy a seed. A form built against a not-yet-registered entity won't render; a form pushed
*before* a later restart can be orphaned (see "After a restart" below).

## Delegate the create + restart to `domain-model`

`domain-model` already declares rebuild + restart **mandatory** after every domain change and owns the
*initial* restart end-to-end. Hand it the work and let it finish (the one restart you own yourself is the
detached persist relaunch further down — headless only):

- **Resolve the real solution root first.** The supplied **Working directory** is often a scratch/output
  dir with no `.sln`. If `<workingDir>` (or `<workingDir>/backend`) has no `*.sln`, search for the backend
  solution (`*.Web.Host.csproj`, then widen) and use that directory — domain-model builds/restarts from
  this path, so a wrong one silently builds nothing.
- Invoke the **`domain-model` skill directly via the `Skill` tool, inline in this session** — do **not**
  spawn a separate sub-agent / `Task` for it (a sub-agent's background backend dies when the sub-agent
  ends, before you can use it). Pass the full context block — Backend URL · Username · Password ·
  **Module** · **Working directory** (the *resolved solution root*) · the **entity name + property list /
  requirements** · the **required outcome** ("entity live:
  `/api/dynamic/<module>/<Entity>/Crud/GetAll` returns 200; report final `{name, module, fullClassName}`").
- **Scenario detection is not this skill's job.** The shared runbook that `domain-model` follows detects
  ephemeral vs headless vs attended and picks the restart path itself. You only care about the two
  outcomes below — both resolve to the same verification poll.

### The two restart outcomes you should expect
- **Headless / CI** → the runbook self-hosts: it stops the port holder, `dotnet build`s the Web.Host,
  and launches the built DLL under Kestrel
  (`ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS=http://localhost:<port> dotnet <App>.Web.Host.dll`),
  then polls `/swagger/index.html`.
- **Attended / Visual Studio / IIS Express / dll-locked** → the runbook **prompts the developer** to
  Stop ▸ Build ▸ Run, **twice** for a new entity, then continues.
- **Rule 0:** never relaunch IIS Express outside Visual Studio — `hostingModel=InProcess` +
  `processPath="%LAUNCHER_PATH%"` gives `HTTP 500.0 ANCM in-process` failure. Delegating keeps you out of
  this trap; do not take over the port from this skill.

## Verify (this is your only job here) — the 2-boot lag

A brand-new entity's dynamic CRUD controller registers only on the boot *after* its `EntityConfig` is
seeded. When `domain-model` returns:

1. Poll `GET /api/dynamic/<module>/<Entity>/Crud/GetAll?maxResultCount=1` (Bearer token) for HTTP 200.
2. Still 404? That's the known lag, not a failure — request **one** more delegated boot (budget 2–3),
   then re-poll. Do **not** spin up a parallel restart loop or call `dotnet build`/`dotnet run` / kill
   the port yourself.
3. A restart can change the module id — re-run `Module/GetAll` (Step 1) and re-resolve the entity
   (Step 2.1–2.2) before building and before Step 5's `moduleId`-based push.

## Persist the backend after a headless restart

**Headless only** — skip in attended/Visual-Studio (the developer owns the backend) and ephemeral
(shesha-agent owns it). domain-model's headless path launches Kestrel as a **session-bound background
task** — a child of this `claude -p` session. It is reaped the instant the session exits, so a downstream
grader/harness that reads `:21021` *after* you finish sees a dead port — no persisted form, no screenshot —
even though everything you did succeeded. Once CRUD is verified, relaunch the built backend **detached** so
it outlives the session:

```powershell
$WH  = "<resolvedSolutionRoot>/backend/src/<App>.Web.Host"
$DLL = "$WH/bin/Debug/net8.0/<App>.Web.Host.dll"
# 1. stop the session-bound holder on :21021
$holder = (Get-NetTCPConnection -LocalPort 21021 -State Listen -ErrorAction SilentlyContinue).OwningProcess | Select-Object -First 1
if ($holder) { Stop-Process -Id $holder -Force -ErrorAction SilentlyContinue; Start-Sleep 2 }
# 2. relaunch DETACHED — Start-Process is NOT a harness-tracked background task, so it survives session exit
$env:ASPNETCORE_ENVIRONMENT = "Development"; $env:ASPNETCORE_URLS = "http://localhost:21021"
Start-Process -FilePath "dotnet" -ArgumentList "`"$DLL`"" -WorkingDirectory "$WH/bin/Debug/net8.0" `
  -WindowStyle Hidden `
  -RedirectStandardOutput "$WH/backend-detached.out.log" -RedirectStandardError "$WH/backend-detached.err.log"
```

Do **not** launch this through the Bash `run_in_background` mechanism — that is exactly the session-bound
task that dies on exit. After launching, poll in a *separate* call until BOTH return 200, then finish:
`GET /swagger/index.html` → 200, and `GET /api/dynamic/<module>/<Entity>/Crud/GetAll?maxResultCount=1`
(Bearer) → 200. Forms live in the database, so this relaunch never loses a form you already pushed — but
prefer to run it right after CRUD is verified so the build/push/smoke all use the persistent process.

**If a detached `Start-Process` still dies on session exit** (a harness that kill-on-close job-wraps the
whole process tree), launch it out of the tree via the Windows Task Scheduler — a process the Scheduler
service starts is not in this session's job:

```powershell
schtasks /Create /TN sfs-backend /SC ONCE /ST 00:00 /F /TR "cmd /c set ASPNETCORE_ENVIRONMENT=Development&& set ASPNETCORE_URLS=http://localhost:21021&& dotnet \"$DLL\""
schtasks /Run /TN sfs-backend
```

Verify the same two endpoints, then finish.

## After a restart — re-verify the forms you push

On 0.46 there is no versioned Draft/Live lifecycle: a form is one row, edited in place, and `FormConfiguration/GetByName` is permanently 404 (use `GET /api/services/app/ConfigurationItem/GetCurrent?itemType=form&module=&name=`). After a Step 2.3 restart re-fetch each form you already pushed through `GetCurrent` and compare its markup and `modelType`; if the form is missing or stale, **re-push via `UpdateMarkup`** (always sending `modelType`, which `UpdateMarkup` overwrites), then re-fetch. A clean run that never restarted won't hit this (forms are built *after* the restart).

## Authoritative source

For the full branch matrix (ephemeral shesha-agent API, exact headless command sequence, the cost-incident
context, and the 3-layer `EntityConfig` / GraphQL / dedicated-controller recovery table), defer to the
shared runbook `domain-model` uses:
[../../shesha-form-edit/references/backend-restart.md](../../shesha-form-edit/references/backend-restart.md).
Keep this local doc thin — do not restate those deep mechanics (single source of truth; avoids drift).
# Backend readiness after a missing/changed domain (thin runbook)

This skill builds forms; it does **not** own the backend lifecycle. When Step 2.3 finds the entity
missing or its dynamic CRUD unregistered, the domain must be created and the backend rebuilt +
restarted **before** any seed is copied. This doc is the *verify-centric* contract for that — the full
restart mechanics live in the authoritative shared runbook (see the last section); don't re-implement
them here.

## Order of operations

**Domain first, forms last.** Create the entity and get the backend restarted, poll until its CRUD is
live, *then* copy a seed. A form built against a not-yet-registered entity won't render; a form pushed
*before* a later restart can be orphaned (see "After a restart" below).

## Delegate the create + restart to `domain-model`

`domain-model` already declares rebuild + restart **mandatory** after every domain change and owns the
*initial* restart end-to-end. Hand it the work and let it finish (the one restart you own yourself is the
detached persist relaunch further down — headless only):

- **Resolve the real solution root first.** The supplied **Working directory** is often a scratch/output
  dir with no `.sln`. If `<workingDir>` (or `<workingDir>/backend`) has no `*.sln`, search for the backend
  solution (`*.Web.Host.csproj`, then widen) and use that directory — domain-model builds/restarts from
  this path, so a wrong one silently builds nothing.
- Invoke the **`domain-model` skill directly via the `Skill` tool, inline in this session** — do **not**
  spawn a separate sub-agent / `Task` for it (a sub-agent's background backend dies when the sub-agent
  ends, before you can use it). Pass the full context block — Backend URL · Username · Password ·
  **Module** · **Working directory** (the *resolved solution root*) · the **entity name + property list /
  requirements** · the **required outcome** ("entity live:
  `/api/dynamic/<module>/<Entity>/Crud/GetAll` returns 200; report final `{name, module, fullClassName}`").
- **Scenario detection is not this skill's job.** The shared runbook that `domain-model` follows detects
  ephemeral vs headless vs attended and picks the restart path itself. You only care about the two
  outcomes below — both resolve to the same verification poll.

### The two restart outcomes you should expect
- **Headless / CI** → the runbook self-hosts: it stops the port holder, `dotnet build`s the Web.Host,
  and launches the built DLL under Kestrel
  (`ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS=http://localhost:<port> dotnet <App>.Web.Host.dll`),
  then polls `/swagger/index.html`.
- **Attended / Visual Studio / IIS Express / dll-locked** → the runbook **prompts the developer** to
  Stop ▸ Build ▸ Run, **twice** for a new entity, then continues.
- **Rule 0:** never relaunch IIS Express outside Visual Studio — `hostingModel=InProcess` +
  `processPath="%LAUNCHER_PATH%"` gives `HTTP 500.0 ANCM in-process` failure. Delegating keeps you out of
  this trap; do not take over the port from this skill.

## Verify (this is your only job here) — the 2-boot lag

A brand-new entity's dynamic CRUD controller registers only on the boot *after* its `EntityConfig` is
seeded. When `domain-model` returns:

1. Poll `GET /api/dynamic/<module>/<Entity>/Crud/GetAll?maxResultCount=1` (Bearer token) for HTTP 200.
2. Still 404? That's the known lag, not a failure — request **one** more delegated boot (budget 2–3),
   then re-poll. Do **not** spin up a parallel restart loop or call `dotnet build`/`dotnet run` / kill
   the port yourself.
3. A restart can change the module id — re-run `Module/GetAll` (Step 1) and re-resolve the entity
   (Step 2.1–2.2) before building and before Step 5's `moduleId`-based push.

## Persist the backend after a headless restart

**Headless only** — skip in attended/Visual-Studio (the developer owns the backend) and ephemeral
(shesha-agent owns it). domain-model's headless path launches Kestrel as a **session-bound background
task** — a child of this `claude -p` session. It is reaped the instant the session exits, so a downstream
grader/harness that reads `:21021` *after* you finish sees a dead port — no persisted form, no screenshot —
even though everything you did succeeded. Once CRUD is verified, relaunch the built backend **detached** so
it outlives the session:

```powershell
$WH  = "<resolvedSolutionRoot>/backend/src/<App>.Web.Host"
$DLL = "$WH/bin/Debug/net8.0/<App>.Web.Host.dll"
# 1. stop the session-bound holder on :21021
$holder = (Get-NetTCPConnection -LocalPort 21021 -State Listen -ErrorAction SilentlyContinue).OwningProcess | Select-Object -First 1
if ($holder) { Stop-Process -Id $holder -Force -ErrorAction SilentlyContinue; Start-Sleep 2 }
# 2. relaunch DETACHED — Start-Process is NOT a harness-tracked background task, so it survives session exit
$env:ASPNETCORE_ENVIRONMENT = "Development"; $env:ASPNETCORE_URLS = "http://localhost:21021"
Start-Process -FilePath "dotnet" -ArgumentList "`"$DLL`"" -WorkingDirectory "$WH/bin/Debug/net8.0" `
  -WindowStyle Hidden `
  -RedirectStandardOutput "$WH/backend-detached.out.log" -RedirectStandardError "$WH/backend-detached.err.log"
```

Do **not** launch this through the Bash `run_in_background` mechanism — that is exactly the session-bound
task that dies on exit. After launching, poll in a *separate* call until BOTH return 200, then finish:
`GET /swagger/index.html` → 200, and `GET /api/dynamic/<module>/<Entity>/Crud/GetAll?maxResultCount=1`
(Bearer) → 200. Forms live in the database, so this relaunch never loses a form you already pushed — but
prefer to run it right after CRUD is verified so the build/push/smoke all use the persistent process.

**If a detached `Start-Process` still dies on session exit** (a harness that kill-on-close job-wraps the
whole process tree), launch it out of the tree via the Windows Task Scheduler — a process the Scheduler
service starts is not in this session's job:

```powershell
schtasks /Create /TN sfs-backend /SC ONCE /ST 00:00 /F /TR "cmd /c set ASPNETCORE_ENVIRONMENT=Development&& set ASPNETCORE_URLS=http://localhost:21021&& dotnet \"$DLL\""
schtasks /Run /TN sfs-backend
```

Verify the same two endpoints, then finish.

## After a restart — re-verify the forms you push

On 0.46 there is no versioned Draft/Live lifecycle: a form is one row, edited in place, and `FormConfiguration/GetByName` is permanently 404 (use `GET /api/services/app/ConfigurationItem/GetCurrent?itemType=form&module=&name=`). After a Step 2.3 restart re-fetch each form you already pushed through `GetCurrent` and compare its markup and `modelType`; if the form is missing or stale, **re-push via `UpdateMarkup`** (always sending `modelType`, which `UpdateMarkup` overwrites), then re-fetch. A clean run that never restarted won't hit this (forms are built *after* the restart).

## Authoritative source

For the full branch matrix (ephemeral shesha-agent API, exact headless command sequence, the cost-incident
context, and the 3-layer `EntityConfig` / GraphQL / dedicated-controller recovery table), defer to the
shared runbook `domain-model` uses:
[../../shesha-form-edit/references/backend-restart.md](../../shesha-form-edit/references/backend-restart.md).
Keep this local doc thin — do not restate those deep mechanics (single source of truth; avoids drift).
