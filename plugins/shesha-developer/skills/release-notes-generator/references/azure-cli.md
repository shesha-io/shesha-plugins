# Azure CLI Route

Default route for anything the Azure DevOps MCP tools can't do. Uses the user's `az login` sign-in, so no PAT is needed.

Contents: Setup · Calling conventions · Repos, PRs and work items · Package feeds · Pipeline builds · Gotchas

## Setup

Run in order; stop at the first failure and give the user the fix:

| Check | Fix |
|---|---|
| `az version` | Install: Windows `winget install -e --id Microsoft.AzureCLI`, macOS `brew install azure-cli` |
| `az extension show --name azure-devops` | `az extension add --name azure-devops` |
| `az account show` | The user runs `! az login` themselves |
| `az devops project show --project "{project}" --org https://dev.azure.com/{org}` | No access: the user needs it granted, or `az login --tenant {tenant}` |

Never run `az devops configure --defaults` (it changes global settings): pass `--org` / `--project` on every call.

## Calling conventions

```bash
ORG="https://dev.azure.com/{org}"
ADO_RES=499b84ac-1321-427f-aa17-267ca6975798   # Azure DevOps resource id, for az rest
```

- Add `-o json` and parse JSON.
- `az rest --resource $ADO_RES` covers everything with no `az` command. **Never put `?a=1&b=2` in `--url`**: on Windows `&` silently cuts the URL. Pass values with `--uri-parameters api-version=7.1 '$top=1000'`, `$` names in single quotes.
- POST bodies go in a file (`--body @"<scratch-dir>/body.json" --headers Content-Type=application/json`).

## Repos, PRs and work items

| Need | Command |
|---|---|
| All repos in the organisation (project of a repo) | `az rest --resource $ADO_RES --url "$ORG/_apis/git/repositories" --uri-parameters api-version=7.1` → `name`, `project.name`, `defaultBranch` |
| Branches / tags (classify locally) | `az repos ref list --repository "{repo}" --filter heads/` (or `tags`) `--org "$ORG" --project "{project}"` |
| Code wikis (wiki branch) | `az devops wiki list --org "$ORG" --project "{project}"` → the `codeWiki` with this `repositoryId`: `mappedPath`, `versions[0].version` |
| **PR query by commit** | POST `$ORG/{project}/_apis/git/repositories/{repo}/pullrequestquery`, body `{"queries":[{"type":"commit","items":["{sha}",…]}]}` → `results[0]["{sha}"][].pullRequestId`, `status`, `targetRefName`. A few hundred commits per call |
| One PR / its work items | `az repos pr show --id {pr} --org "$ORG"` / `az repos pr work-item list --id {pr} --org "$ORG"` |
| Completed PRs into a branch | `az repos pr list --repository "{repo}" --target-branch refs/heads/{branch} --status completed --top 100 --skip {n} --org "$ORG" --project "{project}"` |
| **Artifact link query** (work items linked to commits / PRs) | POST `$ORG/{project}/_apis/wit/artifacturiquery`, body `{"artifactUris":["vstfs:///Git/Commit/{projectId}%2F{repoId}%2F{sha}","vstfs:///Git/PullRequestId/{projectId}%2F{repoId}%2F{prId}"]}` (GUIDs from `az repos show`) |
| Work items in bulk (≤200) | `az rest --resource $ADO_RES --url "$ORG/_apis/wit/workitems" --uri-parameters ids=1,2,3 '$expand=relations' api-version=7.1` |
| WIQL | `az boards query --wiql "SELECT [System.Id] FROM WorkItems WHERE …" --org "$ORG" --project "{project}"` |

Useful fields: `System.WorkItemType`, `System.Title`, `System.State`, `System.Tags`, `System.AreaPath`, `System.Description`, `Microsoft.VSTS.TCM.ReproSteps`, `System.CreatedDate`, `System.IterationPath`, `Microsoft.VSTS.Build.FoundIn` (may not exist: no evidence). Parent = relation `System.LinkTypes.Hierarchy-Reverse`; related = `System.LinkTypes.Related`; the id is the last segment of `url`. Work item link: `https://dev.azure.com/{org}/{project}/_workitems/edit/{id}`.

## Package feeds

Feeds are on `https://feeds.dev.azure.com/{org}` (organisation) and `https://feeds.dev.azure.com/{org}/{project}` (project); use the base matching each feed (`project` is null for organisation feeds).

| Need | `az rest --resource $ADO_RES --url …` |
|---|---|
| Feeds (both bases) | `"{base}/_apis/packaging/feeds" --uri-parameters api-version=7.1` |
| Packages with all versions | `"{base}/_apis/packaging/Feeds/{feedId}/packages" --uri-parameters protocolType={NuGet\|npm} includeAllVersions=true '$top=1000' '$skip={n}' api-version=7.1` (`packageNameQuery=` to narrow; npm without the scope) |
| One package's versions | `"{base}/_apis/packaging/Feeds/{feedId}/Packages/{packageId}/versions" --uri-parameters includeDeleted=true api-version=7.1` → `version`, `publishDate`, `isListed`, `isDeleted` |
| **Provenance** of a version | `"{base}/_apis/packaging/Feeds/{feedId}/Packages/{packageId}/Versions/{packageVersionId}/provenance" --uri-parameters api-version=7.1-preview.1` |
| npm metadata (`repository`, `gitHead`) | `"https://pkgs.dev.azure.com/{org}[/{project}]/_packaging/{feedName}/npm/registry/{@scope/name}"` → `versions["{version}"]` |
| NuGet metadata (`<repository>`) | `…/_packaging/{feedName}/nuget/v3/index.json` → `PackageBaseAddress/3.0.0` URL + `{id-lower}/{version}/{id-lower}.nuspec` |

- Ids are the GUIDs from the previous calls.
- **A1**: `provenanceSource` = `InternalBuild`; `data` holds `Build.BuildId`, `Build.SourceVersion`, `Build.SourceBranch`, `Build.Repository.Name` (keys vary: print `data` once and map).
- **A2**: `provenanceSource` null, `data` only `Common.IdentityDisplayName`: published with a personal token; use `publishDate`.

## Pipeline builds

| Need | Command |
|---|---|
| Pipelines / runs | `az pipelines list` / `az pipelines runs list --pipeline-ids {id} --status completed --result succeeded --query-order FinishTimeDesc --top 200` (+ `--org "$ORG" --project "{project}"`) |
| Classic releases | `az pipelines release definition list`, `az pipelines release list --definition-id {id}`, `az pipelines release show --id {id}` (artifact build id, stage status) |
| **Work items between builds** | `az rest --resource $ADO_RES --url "$ORG/{project}/_apis/build/workitems" --uri-parameters fromBuildId={prev} toBuildId={this} '$top=1000' api-version=7.1` |
| **Changes between builds** | same with `/_apis/build/changes` and `api-version=7.1-preview.2` |
| Classic release work items | `"https://vsrm.dev.azure.com/{org}/{project}/_apis/release/releases/{id}/workitems" --uri-parameters baseReleaseId={prevId} '$top=1000' api-version=7.1` (undocumented; on failure use the builds) |

Both builds must be from the same pipeline; a 404 means retention deleted it.

## Gotchas

- **Git Bash** converts `/docs`-style arguments into Windows paths (`C:/Program Files/Git/docs`): prefix calls with `MSYS_NO_PATHCONV=1`.
- **Non-ASCII output** (emoji in Markdown files) can come back empty on Windows: fetch file content with `--output-file`.
- **HTML fields**: strip tags from descriptions and repro steps.
- **Paging**: `pr list` → repeat with `--skip`; `runs list` has none → raise `--top`.
- **Speed**: about a second per call; always use the bulk calls.
