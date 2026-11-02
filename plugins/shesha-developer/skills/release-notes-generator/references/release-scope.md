# Release Scope

How to find what is in `{version}` and not in the previous stable release. Commands are in [azure-cli.md](azure-cli.md).

Contents: Version matching · Release branches and tags · Method A: package feeds · Method B: pipeline builds · Method C: git evidence · Cross-check and gaps

## Version matching

Only **stable** versions count, everywhere a version is matched (packages, builds, Releases, tags, version bumps, previous release):

| On the package / build / tag | `8.0.0`? |
|---|---|
| `8.0.0`, `v8.0.0`, `Release 8.0.0`, `8.0.0.1234`, `8.0.0+1234` | ✅ |
| `8.0.0-alpha`, `8.0.0-rc1`, `8.0.0-ci.45` (anything after `-`) | ❌ pre-release |
| `18.0.0`, `8.0.01`, `8.0.1` | ❌ different version |

- Regex (escape dots): `(^|[^0-9.])8\.0\.0([.+][0-9]+)?($| )`.
- **Previous release** = the highest stable version below `{version}`. Pre-releases in between are part of this release.
- Feature-branch, PR-validation and CI-only packages or builds are never release artifacts.
- Unlisted or deleted package versions with provenance still count; say so when confirming the scope.

## Release branches and tags

Naming varies by project (`releases/8.0`, `release-2.9`, `release/v2.9`, `Rel_2.9.1`), sometimes within one repo. List **every** branch and tag and classify each whole name (after `refs/heads/` / `refs/tags/`), case-insensitive:

- **Branch**: `^(releases?|rel)[/_.-]v?{ver}$`, `{ver}` = `{major}.{minor}` or `{version}`.
- **Tag**: the same with `{ver}` = `{version}`, or `^v?{version}$`.

| Name | For 2.9.1 |
|---|---|
| `releases/2.9`, `release-2.9`, `release/v2.9`, `release/2.9.1` | ✅ branch |
| `release-2.9.1`, `v2.9.1` | ✅ tag |
| `release-2.7-beta`, `releases/2.5-old`, `feature/x-release-2.6`, `bugfix/fix-releases-8.0`, `users/x/release-2.9` | ❌ |

- A branch named by a build (`sourceBranch` in provenance or the release run) wins whatever its name.
- Several match (e.g. `release-1.2` and `releases/1.2`) → the one containing this release's commit (`git branch -r --contains {sha}`) with the latest commit before the publish date; still tied → ask.
- None match → show branches containing `{major}.{minor}` and ask.
- Tags are often incomplete: a missing tag doesn't mean the version wasn't released.

## Method A: package feeds

Use whenever the release is published as packages.

1. **List feeds**, organisation and project scoped. Ignore upstream packages (saved from nuget.org / npmjs).
2. **Find every package at `{version}`**, NuGet and npm, and each one's **previous stable version**.
3. **Read both versions' provenance and publish time.** Group packages from the same publish (same build, or same repo within minutes).
4. **Repository per group**: provenance repository; else package metadata (`repository`, nuspec `<repository>`) only if it points to a repo in this organisation; else the starting repository if its packages match; else ask.
5. **Boundaries per repository:**
   - **A1, build provenance** (`provenanceSource` = `InternalBuild`, build and commit present for both versions): range = previous commit → this commit. Also take *work items between builds* and *changes between builds* while both builds exist.
   - **A2, publish times** (no build data: published with a personal token): find the release branch, take its tip at each publish time, `git rev-list -1 --first-parent --before="{publishDate}" origin/{branch}`. Cross-check against PRs completed into the branch between the two times; settle any PR in only one list with git: its commit is in the range (`git merge-base --is-ancestor {sha} {end}` and not `{start}`) → in, otherwise → *Excluded* with the reason. Add to the draft header and report: "Feed provenance for {package} has no build data; publishing with the pipeline's own identity would give exact provenance."
6. **Missing side**: publishing only NuGet or only npm is normal. Flag it only if the previous version had both and `{version}` doesn't, or a group has no previous version.

Doesn't apply to a repository with no packages, or packages that can't be tied to a repo and branch: use B, then C, for that repository.

## Method B: pipeline builds

1. The main release pipeline (not CI, PR-validation or feature-branch pipelines; ask if several qualify), or classic Release definitions.
2. This release's build, first that applies: a classic Release naming `{version}` → its artifact build; a run whose build number or tag contains `{version}`; a run on the `{version}` tag or version-bump commit; not shipped yet → latest successful run on the release branch.
3. The previous release's build the same way, from the same pipeline; prefer one deployed to production.
4. Range = *work items between builds* and *changes between builds* (classic: *release work items* against the base release).

Fall back to C when there's no pipeline, versions can't be matched to builds, the builds are from different pipelines, or retention deleted one.

## Method C: git evidence

`git fetch --all --tags --prune`. This release's end = its tag, else its release branch. Find the previous release's end from every source, preferring the higher one when they disagree:

| # | Source | How |
|---|---|---|
| 1 | Tags | release tags for `{previous}` |
| 2 | Version-bump commits | the commit on the release branch where the version became `{previous}` (command below) |
| 3 | Pipeline runs | source commit of the previous release's build (Method B step 3) |
| 4 | Release PRs / merges | PRs titled "Release {previous}", release-branch merges into the default branch |
| 5 | Work items | iteration path or tag naming `{previous}` (supporting only) |

```bash
git log -E -G'"version": *"5\.1\.7"|<Version>5\.1\.7<' --format='%h %as %s' origin/{branch} -- ':(glob)**/package.json' ':(glob)**/Directory.Build.props' ':(glob)**/*.csproj'
```

Range = `{previous end}..{this end}`. No evidence at all → ask for a start (version, build, commit, PR or date); never take the whole branch history.

## Cross-check and gaps

- When a build diff and a git range both exist for a repository, settle a work item found by only one with git: any of its commits in the range → in, otherwise → *Excluded* with the reason.
- Methods B/C: if a version sits between the previous release and `{version}` (e.g. asked for 5.1.8, found 5.1.7), say so and offer: generate it separately first, fold it into `{version}`, or start after it.
