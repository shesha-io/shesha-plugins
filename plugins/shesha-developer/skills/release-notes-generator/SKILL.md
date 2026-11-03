---
name: release-notes-generator
description: Generates the release notes for an Azure DevOps product version in one run, for any project in the organisation. Works out the release's exact commits, pull requests and work items from the package feeds (falling back to pipeline builds, then git), combines them with the developers' vNext entries that shipped in the version, and writes docs/release-notes/v{version}-release-notes.md (General, Breaking Changes, New & Enhancements, Bug Fixes) following the repo's own docs layout, published as its wiki, plus a review draft kept outside the repo. Use when the user asks to generate or create release notes, a changelog or "what's new" for a version (e.g. "release notes for 5.1.8").
---

# Release Notes Generator

Generate release notes for $ARGUMENTS.

Each repo's `docs/` folder is published as its wiki, and developers record release-worthy and breaking changes in vNext files under `docs/release-notes/` as they merge. At release, this skill finds what shipped in the version from Azure DevOps, takes the vNext entries that belong to it, fills the gaps from work items, and writes:

| Output | Where | Content |
|---|---|---|
| **Draft** `v{version}-draft.md` | `~/release-notes-drafts/{repo}/`, **never under `docs/`** (it would be published) | The notes with work item links, plus *Needs review*, *vNext entries* and *Excluded* |
| **Final** `v{version}-release-notes.md` | `docs/release-notes/` | The draft's sections without links |
| **Docs updates** | `docs/` | Shipped entries moved out of vNext, `.order` files updated (created where missing, as the standard requires), plus the repo's own breaking-changes page and index tables where it has them |

- **One run.** The user names the version; Steps 1-9 run without stopping, except where a step says to ask. The final is derived from the draft in the same run, so they never disagree.
- **Only this release.** Earlier versions' notes, pages and drafts are never read. vNext entries for other releases stay where they are. Running again regenerates everything.
- **Any project.** Repos name branches, lay out vNext files and use the standard differently: discover and follow each repo's conventions. A repo without vNext files still gets notes, from work items.

```
Progress:
- [ ] 1 Inputs     - [ ] 4 Filter       - [ ] 7 Draft
- [ ] 2 Scope      - [ ] 5 Categorise   - [ ] 8 Final + docs updates
- [ ] 3 Collect    - [ ] 6 Write items  - [ ] 9 Report
```

## Accuracy

- Every item traces to a source in this release's scope: a work item, a completed PR, or a vNext entry attributed to this release. No source, no item.
- Write only what the sources support; never guess cause, impact, area, version, date or count. When a work item is thin, read everything before giving up: its description, repro steps, acceptance criteria and comments, its parent story, the PR descriptions and commit messages, and the changed file paths (for the area). A clear title alone ("Inbox export fails for large lists") is enough for an item.
- **No secrets or personal data.** The notes are published to the wiki. Never carry over from work items, PRs, commits or vNext entries: passwords, API keys, tokens, connection strings, certificates, server or database names with credentials; names, ID numbers, email addresses or phone numbers of people; client-confidential data or production data samples. Describe the change without them (`Login fails for users with expired passwords`, not the user's name). If a change can't be described without them, leave it out of the notes and say so in the report.
- A General item (e.g. a framework upgrade) needs a change in scope that made it; take the version from the change (`Directory.Build.props`, `package.json`).
- Omit empty sections. Before saving, check no template placeholder (`{Area`, `{Subheading`, `{Explanation}`, `{General change`, `{version_number}`, `{release_date}`) remains.

## Step 1: Inputs

Resolve **organisation**, **project**, **starting repository** and **version**.

- **Local mode**: parse `git remote get-url origin`: `https://dev.azure.com/{org}/{project}/_git/{repo}` (ignore any `{user}@`), `https://{org}.visualstudio.com/{project}/_git/{repo}`, or `git@ssh.dev.azure.com:v3/{org}/{project}/{repo}`. URL-decode segments. Not Azure DevOps → ask for the URL.
- **URL mode**: the same patterns. `https://dev.azure.com/{org}/_git/{repo}` has no project: list the organisation's repositories and take that repo's `project.name`. A project URL without a repo is fine (Step 2 finds the repos). A package feed URL gives org, project, feed, package and version.
- **Version**: use it exactly as given. If it isn't a stable package version, list the nearest ones and ask; if missing, list recent ones and ask. Never reinterpret it; for a pre-release (`8.0.0-beta`), confirm first.
- **Checkout**: the final and docs updates go into the starting repository's local clone, on a branch containing the **wiki branch** (the branch its `docs/` wiki publishes; not necessarily `main`). Find it and prepare the branch as in [references/docs-release-files.md](references/docs-release-files.md#wiki-branch-and-checkout). In URL mode with no local clone, ask where it is.

## Step 2: Scope

The scope is everything in `{version}` (stable) that was not in the previous stable version, from Azure DevOps and git alone: no notes file decides it. Follow [references/release-scope.md](references/release-scope.md):

- **Method A, package feeds** (default): compare the provenance and publish times of the NuGet/npm packages at `{version}` and at the previous stable version.
- **Method B, pipeline builds**, then **Method C, git evidence**, only for a repository whose packages can't be tied to a repo and branch, or that publishes none.

Show the scope before collecting, one line per repository:

```
{version} (stable), previous stable {prev}
{repo} @ {branch}  {NuGet|npm} {package(s)}  {prev} → {version}  {A1 build {id} → {id} | A2 published {time} → {time} | B | C}: {start sha} → {end sha}
```

Continue unless something is missing or inconsistent (a package side missing, groups disagreeing on the previous version, an unknown repo or branch, a fallback to B/C): then ask. Record the method, packages, builds or times, branch and range per repository in the draft header.

## Step 3: Collect

**Access**, first that works: the **Azure DevOps MCP tools** when connected to this organisation (they can't read feeds, diff builds or query links); the **Azure CLI** ([references/azure-cli.md](references/azure-cli.md)) for everything else; **REST with a PAT** ([references/azure-devops-api.md](references/azure-devops-api.md)) only if `az` is unavailable. On an MCP not-found or unauthorised, switch to the CLI.

**Commits**: per repository, run the bundled script on its range, from the local clone (or a temporary `git clone --filter=blob:none --no-checkout` in a scratch directory for other repos, deleted afterwards). Output goes to scratch, never the project:

```bash
git -C "{repo-dir}" fetch --all --tags --prune
cd "{repo-dir}" && bash "<skill-base-dir>/scripts/collect-changes.sh" "{start}..{end}" > "<scratch-dir>/changes-{repo}.tsv"
```

Columns: `sha date author subject pr_ids work_item_ids` (from `Merged PR` subjects and `#id` / `AB#id` mentions).

**Enrich**, across all repositories:

1. **PRs** of **every** commit in the range: the script only sees `Merged PR` merge commits, and many repos rebase or squash, so look up all commits with the *PR query by commit* call (bulk). Keep completed PRs.
2. **Cherry-picks**: trace "Cherry-pick PR {n}" titles and `(cherry picked from commit {sha})` messages to the original and use its work items.
3. **Work items** = build-diff lists + PR links + cherry-pick originals + commit artifact links (*artifact link query*) + commit mentions. Fetch in bulk at organisation level. Keep type, title, state, tags, description / repro steps, acceptance criteria, area path, created date, Found In, iteration path and relations; fetch comments only for items whose fields are too thin to write from.
4. Roll Tasks into their parent. Test Case / Plan / Suite items → *Excluded* ("test artefact"). A work item in several repos is one item.

Each work item, with its PRs and commits, is one **release item**, whatever its state. Settle these cases from the data rather than flagging them:

| Situation | Outcome |
|---|---|
| PR or commit with no work item | Its title or description describes a user-visible change → an item written from the PR. Clearly internal (chore, refactor, CI, formatting, tooling) → *Excluded*. Can't tell → *Needs review* |
| Work item also has PRs/commits before this release's start | An item written only from its PRs in this release's range (for a bug: a follow-up fix) |
| State `Removed` but its code shipped | An item: the code shipped (reverted code is caught in Step 4) |
| Work item can't be fetched | Report only: "#{id}: no access" |
| Tagged or iterated for `{version}` with no code in the range | Report only: "#{id}: planned for {version}, not shipped" |

### 3b. vNext entries

Discover the repo's release-notes layout, read its vNext file(s), split them into entries and attribute each to this release or not, as in [references/docs-release-files.md](references/docs-release-files.md). Then:

- An in-release entry whose work item is a release item gives that item its **section and content**. It is never held back by the Step 4 bug check or for lack of detail: the developer recorded it deliberately.
- An in-release entry tied only by PR or commit is its own item.
- A breaking-change entry is a ⚠️ Breaking Changes item.
- A release item with no entry is written from its work item and reported as "not recorded in vNext".
- A change in scope that looks breaking (tagged breaking, or removes or renames a property, column, endpoint, DTO field, reference list or setting) with no breaking-change entry → *Needs review*: "possible breaking change with no vNext entry; action required unknown".

## Step 4: Filter

To *Excluded*, with a reason: merge-from-main / sync commits, version bumps, reverts (and what they revert), abandoned PRs or PRs into other branches, and test-only, CI-only or formatting-only changes. Keep refactors only if a user or integrator would notice.

**Bugs that never shipped**: Bug Fixes is for bugs users could hit in a previous release. Without a vNext entry, a bug goes to *Excluded* ("introduced and fixed during {version}; never shipped") when its Found In is this version or release branch, it is linked to a Story/Feature in this release, or its iteration is this release's and it was created after the previous release. Otherwise it goes in Bug Fixes.

## Step 5: Categorise

| Section | Goes here |
|---|---|
| 📌 **General** | Framework, dependency, platform, infrastructure and security changes |
| ⚠️ **Breaking Changes** | In-release vNext breaking-change entries only |
| 🚀 **New & Enhancements** | Requirement-type work items (User Story, Product Backlog Item, Requirement, Issue, Feature): new capabilities and improvements |
| 🐞 **Bug Fixes** | Bugs, or work items fixing broken behaviour, that shipped before this release |

An item with a vNext entry takes the entry's section, mapped by meaning. Otherwise: `Bug` → Bug Fixes; tag `Upgrade` or a purely framework / dependency / platform change → General; else New & Enhancements. This order always gives an answer: never hold an item back over its category.

**What stays in *Needs review*** (nothing else does): a possible breaking change with no vNext entry; a vNext entry that only partly shipped; a PR with no work item that can't be judged user-visible or internal; and an item whose sources, all read, say nothing about what changed.

## Step 6: Write items

Follow [assets/release-notes-template.md](assets/release-notes-template.md) exactly. Its bullets and every example here are format placeholders: never copy them.

- **Title and date**: `## Release {version}` and `*Released {yyyy-mm-dd}*`, the actual publish date (package `publishDate`, build finish or deployment date, or tag date), or `*Unreleased*`.
- **Sections** are `###`; every item starts with `- `.
- **Item**: `- **{Area}: {Subheading}** - {Explanation}`, or `- **{Subheading}** - {Explanation}` with no area. General items are plain text and end at the version: `- Upgraded to Shesha framework {new version}`, with the version taken from the change itself. Nothing after the version: no brackets, package names, projects or files, even when the source (a commit, PR or vNext entry) lists them. Not ``- Upgraded to Shesha framework 0.46.1 (`Shesha.*` NuGet packages and `@shesha-io/reactjs`)``.
- **Area** (optional): a component, module, screen or feature named by the source (area path, title, tags, changed paths), in the reader's terms. Same kind of label throughout. Never invented.
- **Shared area**: when two or more items in a section share one, write `- **{Area}:**` once and nest the items under it, indented **four** spaces. Sort by area, then subheading.
- **Subheading**: 2-5 words naming what changed, without repeating the section's meaning ("Fixed", "New", "Improved").
- **Explanation**: plain language for a reader who knows the product but not the ticket. Don't start with "Fixed", "Added" or "Improved". Backticks for code identifiers. Never paste commit messages, ticket numbers or names.
  - **New & Enhancements**: one sentence on what the user can now do or what now behaves differently, about 25 words at most.
  - **Bug Fixes**: say both **what went wrong** and **what happens now**, so nobody has to guess which one the sentence describes: `{what happens now}. Previously, {what went wrong}.` (two short sentences, about 35 words at most). Take both halves from the bug's title, repro steps or PR. If the source doesn't make clear what went wrong, drop the "Previously" sentence and just explain clearly how it works now, in one sentence that can't be misread. Never write an "X instead of Y" sentence that leaves the reader unsure which side was broken.
- **Read it as a stranger.** Before keeping an item, check that someone who never saw the work item can tell from the item alone what changed (and, for a bug, what was broken). If not, rewrite it.
- **From a vNext entry**: condense to this format, keeping the user-visible outcome and adding nothing. Drop implementation detail and "no action required" lines.
- **Breaking Changes**: one line per entry. If the repo keeps per-version breaking-changes pages, end the section with `See [v{version} breaking changes]({relative path}) for the action required.`; otherwise put the action in the item: `… Action required: {action}`.

**Cut repetition.** Reread the whole notes before writing the draft:

- **Merge** items describing the same change, and two sides of one fix (export and import, save and load) when one sentence carries both.
- **The explanation adds information**, never restating the subheading or area (not `**Report Export** - Reports export…`).
- **No subheading twice** across the notes; related items get subheadings naming their distinct points.
- **No filler**: drop "again", "correctly" and "properly" where the sentence says what actually happens instead; don't repeat a phrase across neighbouring items. Clarity wins over brevity: keep any word the reader needs to understand the change.
- **No implementation detail** (form, class or migration names) unless the reader must act on or search for it.

| Source | Item |
|---|---|
| Bug, area path `Proj\Reporting`, "Report export times out for >10k rows" | `- **Reporting: Large Exports** - Reports with more than 10,000 rows export in full. Previously the export timed out and no file was produced.` |
| Bug, area path `Proj\Leave`, "Returned request disappears from initiator's list", repro: it moves to Drafts | `- **Leave: Returned Requests** - A request sent back to its initiator stays in their *My Items* list. Previously it moved to *Draft*.` (without the repro: `- **Leave: Returned Requests** - A request sent back to its initiator appears in their *My Items* list.`) |
| User Story, no area, "Allow admins to reset user MFA" | `- **Admin MFA Reset** - Administrators can reset a user's multi-factor authentication` |
| Bug, "Fix save issue", no detail; PR "Persist leave balance on save" changes `Leave/` | `- **Leave: Balance Saving** - A leave balance is kept when the record is saved.` (written from the PR) |
| Bug, "Fix save issue", and every source is empty | *Needs review*: `- **Saving** - Saving works`, "no source says what was fixed or where" |

## Step 7: Draft

Write `~/release-notes-drafts/{repo}/v{version}-draft.md`, overwriting any earlier one: the template layout with each item's work item links appended, then the review sections:

```markdown
<!-- DRAFT {yyyy-mm-dd}, {org}/{project}, previous stable {prev}
     {repo}: {method}, {packages}, {start sha}..{end sha}   (one line per repository) -->
## Release {version}

*Released {yyyy-mm-dd}*

### 🚀 New & Enhancements

- **{Area}: {Subheading}** - {Explanation} ([#{wi}](https://dev.azure.com/{org}/{project}/_workitems/edit/{wi}))

(… every template section, same format …)

---

### ⚠️ Needs review

- **{Area}: {Subheading}** - {Explanation} ([#{wi}](…))

  *Category: 🐞 Bug Fixes. Needs review: {why}*

### vNext entries

- In {version}: **{entry title}** (PR {n}, [#{wi}](…)) → {section}

  > {the entry's full original text}

- Left in vNext: **{entry title}**: {already released in ≤{prev} | not in this release | can't be attributed}

### Excluded

- {work item link, PR or commit}: {reason}
```

*Needs review* lines are written exactly as they would appear in their section, single-line, so the user can copy one into the final by hand; the skill never adds them to the final.

## Step 8: Final and docs updates

On the checkout from Step 1 (creating the release-notes structure first if the repo has none, per [references/docs-release-files.md](references/docs-release-files.md#repos-without-the-structure)), write `docs/release-notes/v{version}-release-notes.md` (the standard's naming, whatever older pages are called) from the draft: same title, date, sections and wording; work item links and the draft comment removed; everything from `---` down removed. The only link kept is the Breaking Changes page link. Change no wording in this step. If the file already exists and differs, show what would be lost and ask before overwriting.

Then apply the docs updates in [references/docs-release-files.md](references/docs-release-files.md#files-written-at-release): move the in-release entries out of the vNext file(s) (merging separate new-features and improvements sections into 🚀 New & Enhancements), update the `.order` files (creating any the standard requires that are missing), and update the breaking-changes page and index tables only where the repo has them. Touch nothing else.

## Step 9: Report

- The draft path, and every file written or changed under `docs/` and on which branch (created by the skill or not); they reach the wiki once merged into the wiki branch.
- The scope per repository (method, packages, builds, range) and the branch naming found.
- Counts per section; vNext entries moved; release items not recorded in vNext; entries left behind as already released or unattributable.
- Every *Needs review* item with its reason: these are not in the final, so the user decides before committing.
- Work items with no access, and work items planned for `{version}` that didn't ship.
- If the structure was created: that the standard also needs `docs/readme.md` and wiki publishing switched on.

## Rules

- Never commit, push or publish unless the user asks.
- Never stash, reset or discard the user's changes; never edit earlier versions' pages.
- Read-only on Azure DevOps.
- A PAT is a secret: read it from the environment; never write or echo it.
