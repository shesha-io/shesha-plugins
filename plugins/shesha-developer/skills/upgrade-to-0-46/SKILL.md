---
name: upgrade-to-0-46
description: Upgrades a Shesha application from the 0.43 line or an internal 0.0.0-build line to Shesha 0.46.0. Covers NuGet and npm version pinning, the Configuration Items rewrite, Abp 10.3 and removed framework APIs, the Next 16 frontend stack, Configuration Studio, and the migration failures that only appear at start-up. Use when the user asks to upgrade Shesha, move to 0.46, or is debugging SqlException or TypeLoadException failures after such an upgrade.
---

# Upgrade to Shesha 0.46.0

Upgrade a Shesha application to Shesha `0.46.0` based on $ARGUMENTS.

## The one thing to internalise first

A clean build proves almost nothing here. Three of the four failure classes below are invisible at compile time:

- **Version drift** resolves silently to the wrong package
- **Companion packages** compiled against 0.43 fail at *type load*, not compile
- **Migration failures** only happen when the app first talks to a database

Budget accordingly: compiling is the early, easy part.

## Phases

Work in this order. Each phase surfaces problems the previous one was hiding.

| # | Phase | Reference |
|---|-------|-----------|
| 1 | Feeds, credentials, version pins | [references/packages-and-feeds.md](references/packages-and-feeds.md) |
| 2 | Backend code migration | [references/backend-apis.md](references/backend-apis.md) |
| 3 | Frontend stack + Configuration Studio | [references/frontend-stack.md](references/frontend-stack.md) |
| 4 | Start-up / migration failures | [references/migration-failures.md](references/migration-failures.md) |

## Target versions

```xml
<!-- backend/Directory.Build.props -->
<SheshaVersion>0.46.0</SheshaVersion>
<TargetFramework>net10.0</TargetFramework>
```

```jsonc
// adminportal/package.json
"@shesha-io/reactjs": "0.46.0",
"react":  "^19.2.4",   "next":       "^16.3.1",
"antd":   "^6.6.2",    "antd-style": "^4.1.0"
```

Verify the resolved graph, not the declared versions:

```bash
dotnet restore && python -c "import json;d=json.load(open('obj/project.assets.json'));t=next(iter(d['targets'].values()));print([k for k in sorted(t) if k.startswith('Shesha')])"
```

## Order of operations that actually works

1. **Fix feeds first.** A disabled or unauthenticated feed reports missing packages as though they do not exist. Diagnosing anything else before this wastes hours.
2. **Pin exactly** (`[0.46.0]`) until the resolved graph is proven correct.
3. **Backend compiles** — expect a cascade: each fixed project reveals the next one's errors.
4. **Run the app against a real database.** This is where the upgrade is actually tested.
5. **Frontend last** — it is independent and rarely blocks the backend.
6. **Reconcile the forms** — once the backend starts cleanly against an upgraded database, run `shesha-upgrade-reconciler` to make the application's forms look and behave as they did before the upgrade.

## Do not trust these signals

| Signal | Why it misleads |
|---|---|
| `dotnet build` succeeds | Says nothing about type load or migrations |
| `NU1101 no packages exist with this id` | Usually a *disabled* or unauthenticated source |
| A migration is in `VersionInfo` | May have been backfilled, never executed |
| Another project "works" | Its packages may only be in the global cache |
| `column_id` has no gaps | bacpac import renumbers, destroying the evidence |

## Verification checklist

- [ ] `dotnet restore` clean, and resolved `Shesha.*` are all `0.46.0`
- [ ] No package still declaring `Shesha.Framework 0.43.x` (see phase 1 — this is the TypeLoadException source)
- [ ] Backend builds, **including projects outside the main .sln**
- [ ] App starts against an upgraded database and serves an authenticated endpoint
- [ ] Adminportal typechecks and `/configuration-studio` returns 200
- [ ] Any migration workaround is written down and owned by a ticket

Now perform the upgrade described in: $ARGUMENTS
