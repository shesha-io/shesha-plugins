# Backend restart after a domain change (the reliable runbook)

A **domain change** (new/changed entity, property, reference list, or migration) only takes effect
after the .NET backend is **rebuilt and restarted** — Shesha applies migrations and seeds
`EntityConfig` on startup. Doing this badly is the single biggest cost/failure sink (one harness run
burned **$12.50 / 27 min** on 14 restart attempts and corrupted an existing form). Follow this
runbook instead of improvising.

> **Order of operations:** do ALL domain changes + the restart **first**, then build forms **last**.
> A form built before the entity is ready won't render; and a form pushed *before* a later restart
> can be orphaned by that restart (see "re-verify forms" below).

---

## Rule 0 — never relaunch IIS Express outside Visual Studio

The dev backend is usually hosted by **IIS Express**, launched and managed by Visual Studio. Its
`applicationhost.config` uses `hostingModel="InProcess"` with `processPath="%LAUNCHER_PATH%"` — that
env var is only set by VS, so relaunching `iisexpress.exe` yourself gives **`HTTP Error 500.0 — ANCM
In-Process handler load failure`**. Do **not** try to relaunch IIS Express. Use the Kestrel path below
(headless) or hand back to VS (attended).

---

## Ephemeral / shesha-agent sandbox — check this FIRST

If the `SHESHA_AGENT_API_URL` and `SHESHA_SESSION_ID` environment variables are set, you're running
inside a shesha-agent ephemeral session, not on a developer's machine or in CI. The backend there
already runs under `dotnet watch`, and a separate system handles rebuild/redeploy — **do not** take
over the port or run `dotnet build`/`dotnet run` yourself (the Headless section below does exactly
that, and it will race the live process, producing MSB3027/MSB3021 file-copy errors). Instead,
trigger and wait for the restart yourself over shesha-agent's own API:

```bash
curl -X POST "$SHESHA_AGENT_API_URL/api/app-restart/$SHESHA_SESSION_ID/restart-changed-apps"

# Poll until the backend is running (a few minutes' timeout is reasonable)
until curl -s "$SHESHA_AGENT_API_URL/api/app-restart/$SHESHA_SESSION_ID/app-statuses" \
    | grep -q '"backend":"running"'; do
  sleep 3
done
```

Then verify against `$SHESHA_BACKEND_URL` (never `localhost`) — including the same 2-boot lag
described below for a brand-new entity: poll `Crud/GetAll`, and re-run the two commands above once
more if it 404s, since the controller only registers on the boot after `EntityConfig` is seeded.

Skip the rest of this doc in this case — the Headless and Attended sections below both assume you can
freely stop/rebuild/relaunch the backend process yourself, which you must never do here.

---

## Headless / CI / harness — take over the port with Kestrel

You're headless when the task supplied a context block (Backend URL / Module / Working directory) or
you're in `claude -p`. Run this **once** as a single combined sequence (don't probe step-by-step):

```bash
WH="<workingDir>/backend/src/<App>.Web.Host"          # e.g. .../boxfusion.test/backend/src/boxfusion.test.Web.Host
DLL="$WH/bin/Debug/net8.0/<App>.Web.Host.dll"          # e.g. boxfusion.test.Web.Host.dll
BASE="http://localhost:21021"

# 1. Stop whatever holds the port (IIS Express + its tray, or the port owner)
powershell -NoProfile -Command "Get-Process iisexpress,iisexpresstray -ErrorAction SilentlyContinue | Stop-Process -Force"
# (fallback: kill the PID returned by `Get-NetTCPConnection -LocalPort 21021 -State Listen`)

# 2. Build (Web.Host build compiles the Domain project + migration too)
dotnet build "$WH/<App>.Web.Host.csproj" -c Debug --nologo -v m

# 3. Launch Kestrel in the BACKGROUND on :21021 (NOT `dotnet run` — run the built DLL; it's faster and
#    avoids a rebuild). ASPNETCORE_ENVIRONMENT=Development is required (Production 500s here).
ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS="$BASE" dotnet "$DLL"   # run via run_in_background

# 4. Poll until Shesha finishes booting (migrations + bootstrappers ~10–30s)
#    until: curl -s -o /dev/null -w '%{http_code}' "$BASE/swagger/index.html"  == 200
```

Launch step 3 with `run_in_background: true` (it's a long-lived server) and then poll in a separate
call. Write any scratch scripts into `$RUN_DIR/staged/`, **not `/tmp`** (git-bash `/tmp` ≠ Windows paths).

### The 2-boot lag (new entities only) — handle it deterministically

A **newly added** entity's dynamic CRUD controller registers only on the boot *after* its
`EntityConfig` is seeded. So the first boot brings the app up but the new entity's endpoint 404s. After
step 4 succeeds, verify the entity and restart **once more** if needed — don't flail:

```bash
# dynamic CRUD endpoint format:  /api/dynamic/<module>/<Entity>/Crud/GetAll
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/dynamic/<module>/<Entity>/Crud/GetAll?MaxResultCount=1")
# 200 → ready.  404/500 → repeat steps 1–4 ONCE; the controller registers on the second boot.
```

For a brand-new entity, just **plan for two boots** up front (build once, then boot → boot) rather than
discovering the 404 and reacting.

**Two is the floor, not the ceiling — budget 2–3.** Recovering a badly broken or from-scratch
registration has needed a third boot in practice. Three layers recover *independently*, so "still 404"
does not mean "the last boot did nothing" — check each one rather than re-booting blindly:

| Layer | How to check | Typically recovers |
|---|---|---|
| `EntityConfig` metadata | `Entities/GetAll`, `EntityConfig/GetMainDataList` | boot 1 |
| GraphQL projection | the entity's projection endpoint stops 500ing | boot 1 |
| Dedicated `<Entity>Crud` controller | `/api/dynamic/<module>/<Entity>/Crud/GetAll` returns 200 | boot 2, sometimes 3 |

There is no one-liner for "is the dedicated CRUD swagger doc populated yet". The manual route is to read
the service list embedded in `swagger/index.html`, then fetch
`swagger/service:<Entity>Crud/swagger.json` and confirm `paths` is non-empty — worth knowing before you
spend time rediscovering the URL scheme by grepping rendered HTML.

---

## After ANY restart - re-verify the forms you'll touch

Startup re-runs the configuration bootstrappers (`ConfigurableModuleBootstrapper` / `ImportConfigurationAsync`), which on
0.43/0.45 could orphan a previously-edited form's "live" revision. **0.46 has no Draft/Live lifecycle**, so that failure mode does
not exist - but a restart can still re-import module-shipped forms over your in-place edits. After any restart, re-read each form
you will touch with `ConfigurationItem/GetCurrent?ItemType=form&Module=&Name=` ([api.md](api.md) section 3) and compare against
your last pushed markup and `modelType`; re-push only if it differs (and only with the owner's go-ahead on a shared backend).

Because you build forms **after** the restart, a clean single run normally won't hit this - re-verify defensively.

---

## Attended / real-world (Visual Studio is running the app)

Do **NOT** kill VS's IIS Express or take over the port — that breaks the developer's session. Instead:

1. Tell the developer: *"I created/changed an entity + migration — rebuild and restart the app in
   Visual Studio (Stop ▸ Build ▸ Run), then I'll continue."* For a **new** entity, ask them to restart
   **twice** (the 2-boot lag).
2. Poll the entity's `Crud/GetAll` until it returns 200, then resume form work.
3. Only offer the headless Kestrel takeover above if the developer explicitly prefers it.

This keeps the skill usable in normal development, not just the test harness.
