# Azure DevOps REST Fallback

Only when `az` is unavailable and can't be installed. The calls are those in [azure-cli.md](azure-cli.md), sent with curl.

## Auth

A Personal Access Token with **Code**, **Work Items**, **Build** and **Packaging** (Read) scopes, in `AZURE_DEVOPS_EXT_PAT`. If it is unset, ask the user to set it themselves; never ask for the token in chat.

```bash
auth=(-u ":$AZURE_DEVOPS_EXT_PAT")
curl -s "${auth[@]}" "https://dev.azure.com/$ORG/$PROJECT/_apis/{path}?api-version=7.1&{params}"
curl -s "${auth[@]}" -H "Content-Type: application/json" -d @body.json "https://dev.azure.com/$ORG/$PROJECT/_apis/{path}?api-version=7.1"
```

- Take `{path}` and parameters from the matching row in azure-cli.md (e.g. `git/repositories/$REPO/pullrequestquery`, `wit/workitems?ids=…&$expand=relations`, `build/workitems?fromBuildId=…&toBuildId=…`).
- Feeds use `https://feeds.dev.azure.com/$ORG[/$PROJECT]/_apis/packaging/…`; organisation-level calls (all repos, work items in bulk) drop `/$PROJECT`.
- Escape `$` in query names (`\$top`, `\$expand`) and URL-encode names with spaces.
- Paged lists return a `continuationToken` or take `$skip`: repeat until done.
