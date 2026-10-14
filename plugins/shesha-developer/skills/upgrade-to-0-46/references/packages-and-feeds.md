# Packages and Feeds

Phase 1. Nothing else can be diagnosed reliably until this is right.

## §1. Feed configuration — check before anything else

Three independent traps, each producing a *misleading* error.

### `nuget.config` in a `.nuget/` subfolder is never read

NuGet auto-discovers `nuget.config` by walking **up** from the project directory. It does not look inside a `.nuget/` subfolder. A long-standing `backend/.nuget/NuGet.Config` has therefore never been in effect, and restore silently falls back to machine-level sources — often an unauthenticated feed plus nuget.org's legacy **v2** endpoint, which resolves versions differently.

**Fix:** a real `backend/nuget.config`. Confirm with `dotnet nuget list source` run *from the project directory*.

### A user-level `disabledPackageSources` overrides repo config

```xml
<!-- ~/AppData/Roaming/NuGet/NuGet.Config -->
<disabledPackageSources>
  <add key="nuget.shesha.dev" value="true" />
</disabledPackageSources>
```

Disabling is **by key name** and wins even when the repo's own `nuget.config` adds that source. The symptom is `NU1101: no packages exist with this id` — a statement about *enabled* sources, not about the world. `dotnet nuget list source` shows `[Disabled]`.

### The Azure feed needs a credential provider

Once enabled, an unauthenticated Azure Artifacts feed answers **401**, which then breaks `dotnet tool install` too, since that also consults configured sources.

```bash
# correct package id - "Microsoft.CredentialProvider" does not exist on nuget.org
dotnet tool install --global Microsoft.Artifacts.CredentialProvider.NuGet.Tool --add-source https://api.nuget.org/v3/index.json --ignore-failed-sources
dotnet restore --interactive   # device-code sign-in, caches a token
```

Success = `~/.nuget/plugins/netcore/CredentialProvider.Microsoft` exists and restore has no `NU1301`.

**Key rules:**
- Diagnose feeds before diagnosing packages. `NU1101` almost never means what it says.
- A project that "works" may only be resolving from the global cache. Check `.nupkg.metadata` → `source` to see where a cached package really came from, and test a clean restore before trusting it.

## §1a. `npm view <pkg> version` lies

It returns the `latest` dist-tag, not the highest published version. A package can have newer
builds sitting behind a stale tag, so a module looks abandoned when a usable version exists. Always:

```bash
npm view <pkg> versions --json
```

This has already caused one wrong conclusion — a companion package was declared unfixable on the
strength of a `latest` that was two minor versions behind what was published.

## §1b. Never reach for `--legacy-peer-deps`

It does not resolve a peer conflict, it suppresses the report of one, and the duplicate or
wrong-major package still lands in `node_modules`. Check `.npmrc` for a `legacy-peer-deps=true`
before concluding an install is clean.

**A framework package can ship peers that contradict each other.** `@shesha-io/enterprise 8.0.0`
peer-requires `react ^19.x` while pinning `react-leaflet ^4.2.1`, which is React 18 only. Nothing
the app declares resolves that — only an override on the inner package does
(`"react-leaflet": "^5.0.0"`). Still present in the final release, not just the betas.

**Duplicate-UI-library overrides are a trade-off, not a fix.** A transitive consumer still peering
on the previous antd major makes npm install a second copy — two `ConfigProvider` contexts and two
emotion caches, so tokens set by one are invisible to components resolved from the other. Forcing
the consumer onto the app's major fixes the visible bug but pushes it outside its declared range.
Acceptable *if* the reason is written in the manifest and the real fix is pursued upstream.

**But never invent an override.** Before adding one, confirm the two consumers actually share the
dependency. A real miss: an override forced `@rc-component/trigger` to 3.10.1 "so antd and rc-picker
would share it". `rc-picker` declares `^2.0.0`, and antd does not depend on `rc-picker` at all — so
there was never a copy to share. Out-of-range and pointless, and both versions installed anyway.
**Two copies is the correct outcome when two consumers need different majors.**

Verify the result by each `package.json`'s `name` field, not by path — a scoped package such as
`@react-awesome-query-builder/antd` sits in a directory ending in `antd` and double-counts.

## §2. Version drift — pin exactly

The Shesha feeds carry higher parallel lines that no longer track development:

| Package family | Stray higher versions |
|---|---|
| `Shesha.Core` / `.Application` / `.FluentMigrator` / `.Framework` | `1.0.0`, `1.0.1` |
| `Shesha.Framework` (nuget.org) | unlisted `4.37.x` (`published: 1900-01-01`) |

`Version="0.46.0"` means `>= 0.46.0`, so resolution drifts up to these. The 1.0.x chain then demands siblings that do not exist, producing a **contradictory** error:

```
NU1102: Unable to find package Shesha.Application with version (>= 0.46.0)
  - Found 830 version(s) in nuget.org [ Nearest version: 0.46.0 ]
```

**Fix — one line per repo.** Every reference uses `Version="$(SheshaVersion)"`, and the property is used nowhere else, so bracket the property value:

```xml
<SheshaVersion>[0.46.0]</SheshaVersion>
```

Do not chase this per-csproj. Once a package whose own dependency declarations pin `Shesha.*` exactly has resolved, it anchors the graph and the brackets can come off — verify the assets file after doing so.

**Red herrings:** a stale NuGet HTTP cache, and locally built `1.0.x` packages in `~/.nuget/packages`. Clearing the cache changes nothing; the listed nuget.org `1.0.0` is the real cause. A minimal probe project restores `0.46.0` fine, which proves the package is healthy and the *range* is the problem.

## §3. `packages.lock.json` blocks new packages

With `<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>`, adding a package can fail with `NU1101` even though the source works — the lock records the requirement with no resolution, and **`--force` does not rebuild it**.

```bash
find . -name packages.lock.json -not -path '*/obj/*' -delete
dotnet restore     # regenerates them
```

Symptom worth recognising: one project resolves the package while another reports it missing.

## §4. Companion packages are the real blocker

Packages compiled against `Shesha.Framework 0.43.37` **compile fine and fail at runtime**:

```
TypeLoadException: Could not load type 'Shesha.Configuration.Runtime.IEntityConfigurationStore'
from assembly 'Shesha.Framework, Version=0.46.0.0'
```

NuGet resolves happily because `0.43.37 < 0.46.0` satisfies `>= 0.43.37`. The dangling reference lives inside a third-party assembly, so your own code never mentions it.

**Audit before upgrading.** For each companion package, read the cached nuspec:

```bash
grep -oE '<dependency id="Shesha.Framework" version="[^"]*"' ~/.nuget/packages/<pkg>/<ver>/*.nuspec
```

Anything still declaring `0.43.x` must be **rebuilt and republished** against 0.46.0 — there is no downstream fix, and no version of the consuming app can shim a removed interface. In practice the offenders are the optional product modules that release on their own cadence, so audit every non-framework `Shesha.*` and vendor package before starting.

To find which assembly holds a missing type:

```bash
find bin -name '*.dll' -exec sh -c 'grep -qa "IEntityConfigurationStore" "$1" && echo "$1"' _ {} \;
```


## §5. Package floors and vulnerability noise

| Package | Floor | Why |
|---|---|---|
| `System.ValueTuple` | `4.6.2` | `Shesha.NHibernate 0.46.0` |
| `Microsoft.Identity.Client` | `4.83.1` | `Azure.Core 1.53.0` |
| `Azure.Identity` | declare explicitly | no longer arrives transitively; `Microsoft.Graph` never supplied it |

**NuGetAudit** on net10.0 audits transitive packages by default — expect ~470 warnings from ~16 distinct advisories. `NuGetAuditMode=direct` reduces it to what you control (~20).

`AutoMapper 14.0.0` (high severity, GHSA-rvv3-g6hj-g44x) is **not fixable downstream**: `Abp.AutoMapper` pins it, `AutoMapper.Collection 11.0.0` constrains to `[14.0.0, 15.0.0)`, `14.0.0` is the only 14.x, and the fix is `15.1.1`. Escalate upstream; do not force it.

---

## §6. `NU1605` downgrades after the framework bump

0.46 pulls newer transitives than 0.43 did, so an app pinning one of them directly now *downgrades*
it, and most repos treat that as an error:

| Package | Bump the app's direct pin to |
|---|---|
| `System.IdentityModel.Tokens.Jwt` | `8.16.0` (pulled via `Microsoft.AspNetCore.Authentication.JwtBearer 10.0.5`) |
| `System.ValueTuple` | `4.6.2` (pulled via `Shesha.FluentMigrator 0.46.0`) |

Read the error's dependency chain rather than guessing the floor — it names the package that
demands the higher version. Derive floors from a project already proven on 0.46, and bump only
packages the project already referenced.
