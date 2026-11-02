# Docs Release Files

How to read a repo's vNext files and update its `docs/release-notes/` at release. Repos differ in file names, headings, separate breaking-changes files and index pages: **follow each repo's own conventions**. Only a repo with no release-notes structure gets the default layout.

Contents: Discover the repo's layout · Wiki branch and checkout · Reading vNext entries · Attributing entries to the release · Files written at release · Repos without the structure

## Discover the repo's layout

From the wiki branch, list `docs/` and `docs/release-notes/` recursively and record what exists (case-insensitive names):

| Role | Look for | If absent |
|---|---|---|
| **vNext release notes** | `docs/release-notes/vNext*.md` that isn't about breaking changes (e.g. `vNext-release-notes.md`, `vNext.md`) | No developer entries: notes come from work items only |
| **vNext breaking changes** | A `vNext*.md` with "breaking" in its name, anywhere under `docs/release-notes/` (e.g. `breaking-changes/vNext-breaking-changes.md`) | Breaking changes, if any, are a section inside the vNext release notes |
| **Version pages** | Existing per-version pages (`v{x.y.z}-release-notes.md`, or older names such as `v5.1.6.md`) | — |
| **Breaking-changes pages** | Existing per-version files beside the vNext breaking changes file (e.g. `v5.1.7-breaking-changes.md`) | Only written when the repo has a separate vNext breaking changes file; then `v{version}-breaking-changes.md` |
| **Index pages** | `docs/release-notes.md`, `docs/release-notes/breaking-changes.md` (pages with a version table) | Don't create one |
| **`.order` files** | `docs/.order`, `docs/release-notes/.order`, and one in each subfolder | Create it: the standard requires a `.order` at the root of `docs/` and in each subfolder |

**Name the new version page as the standard does**, always with the full version: `v{version}-release-notes.md` (e.g. `v8.0.2-release-notes.md`), even where older pages use another pattern (`v5.1.6.md`, `v2.0.md`). Never rename existing pages: the wiki derives page titles from file names, and links would break. Keep `docs/release-notes/` lowercase.

## Wiki branch and checkout

1. **Find the wiki branch.** List the project's wikis (*code wikis* in [azure-cli.md](azure-cli.md#repos-prs-and-work-items)). Use the code wiki whose `repositoryId` is this repo's id and whose `mappedPath` is `/docs`: its `versions[0].version` is the wiki branch. Otherwise (no code wiki, or one mapped to another folder such as `/docs/wiki`) use the repo's **default branch** from the repository data (`main`, `master` or other): never assume `main`. Report a wiki that is mapped elsewhere or publishes a non-default branch.
2. **Read** the vNext files from `origin/{wikiBranch}` after a fetch (`git show origin/{wikiBranch}:{path}`), and also from this release's end commit (`git show {end}:{path}`) when they exist there: an entry made on a release branch may not have reached the wiki branch yet. Use the union, de-duplicated by entry text.
3. **Write** into the local clone, on a branch that contains `origin/{wikiBranch}`'s tip:
   - The checked-out branch already contains it (`git merge-base --is-ancestor origin/{wikiBranch} HEAD`) → write there.
   - Otherwise, if the working tree is clean (`git status --porcelain` is empty) → `git switch -c docs/release-notes-v{version} origin/{wikiBranch}` and tell the user in the report.
   - Otherwise (uncommitted changes) → ask before switching. Never stash, reset or discard the user's changes.

When the release spans several repositories (e.g. separate backend and frontend repos), write the notes once, in the starting repository, and read vNext files from every repository in scope.

The version page describes the release branch's code but lives on the wiki branch: don't compare the notes with the wiki branch's code.

## Reading vNext entries

Developers write vNext files freely, so parse by structure, not by one template:

- **Sections** are `##` headings. Map each by meaning, case-insensitive, ignoring emoji; take the **first** row that matches:

  | Heading mentions | Category |
  |---|---|
  | historical, previous, past, archive, at release time, how to, what counts | Not entries: ignore the whole section |
  | breaking | ⚠️ Breaking Changes |
  | migration, guidance, deployment, configuration, notes, other | No fixed category: categorise each entry by its content with Step 5's rules; an entry that tells consumers to take an action when upgrading is ⚠️ Breaking Changes |
  | fix, bug, resolved | 🐞 Bug Fixes |
  | new, feature, enhancement, improvement, added, changed | 🚀 New & Enhancements |
  | general, upgrade, framework, dependency, platform, infrastructure, security | 📌 General |
  | anything else | Categorise each entry by its content, as in the migration row |

- **Area subheadings**: a `###` heading inside a section (e.g. `### Submissions`) names the area of the entries under it. In a separate breaking changes file, everything is ⚠️ Breaking Changes whatever the heading, and each `###` block (or top-level list item) outside the ignored sections is one entry, with its heading as area and title.
- **An entry** is one top-level list item (`- ` or `* `) with all its continuation lines and nested sub-items. Ignore prose paragraphs, HTML comments, blockquotes of instructions, placeholder lines such as `*Nothing recorded yet.*`, and pointer sections that only link to another file.

## Attributing entries to the release

An entry belongs to this release only if it can be tied to the release's scope (Step 2). Collect its evidence:

1. **References in the text**: work items (`_workitems/edit/{id}`, `#{id}`, `AB#{id}`) and PRs (`PR {n}`, lists like `PR {n}, PR {m}`, `!{n}`, `/pullrequest/{n}` links).
2. **The PR that added it**, when the text names none: find the commit that first added the entry, `git log --reverse --format=%H -S"{distinctive text from its first line}" origin/{wikiBranch} -- {file} | head -1` (repeat on `{end}` for entries only on the release branch; a partial clone fetches the file's blobs on demand), then its PR with the *PR query by commit* call in [azure-cli.md](azure-cli.md#repos-prs-and-work-items), in one call for all entries. This works whatever the merge strategy (rebase and squash merges leave no `Merged PR` commit to read).
3. The PRs' linked work items, and the original's for a cherry-pick (Step 3).

Then decide:

| Evidence | Outcome |
|---|---|
| All its work items / PRs are in this release's scope (or the adding commit is in `{start}..{end}`) | **In this release**: used in Step 3b, moved out of vNext in Step 8 |
| Some are in scope, some are not | Leave the entry in vNext; put a line for the in-scope part under *Needs review*: "vNext entry only partly shipped in {version}" |
| All shipped in `{prev}` or earlier | Not this release (already released). Leave it; report "appears already released in ≤{prev}" |
| All are later than this release, or not shipped | Not this release. Leave it |
| No work item and no PR found | Leave it; report "can't be attributed: check whether it shipped in {version}" |

Never move an entry on wording alone.

## Files written at release

All under `docs/`. Keep each edited file's existing text, structure and line endings apart from the change described. Only touch files that exist in the repo, plus the new version pages and any missing `.order` files.

| File | Change |
|---|---|
| Version page `release-notes/v{version}-release-notes.md` | The final (Step 8 in SKILL.md). |
| Version breaking-changes page | Only if the repo has a separate vNext breaking changes file and an in-release breaking change exists: named like the repo's existing ones (default `v{version}-breaking-changes.md`), beside the vNext file. Heading `# v{version} — Breaking Changes`, then each in-release entry **verbatim**, newest first. No template comment or footer. |
| vNext release notes | Remove the in-release entries (and an area `###` heading left with no entries). Put `*Nothing recorded yet.*` under a section left empty if the file already uses that line, otherwise leave the section empty. If it has separate "new features" and "improvements" sections, merge them into one `## 🚀 New & Enhancements` section in the first one's place. Keep everything else, including headings, prose, comments and footers. |
| vNext breaking changes | Remove the in-release entries; same empty-section rule. |
| `.order` files | Create any that are missing: `docs/.order` listing the pages and folders already in `docs/` (`readme` first if it exists, then `release-notes`, then the rest alphabetically), and `.order` in each `docs/release-notes/` folder listing its pages, vNext first, then versions newest first. In an existing one, add the version page name (no `.md`, e.g. `v8.0.2-release-notes`) below the vNext entries and above lower versions; same for a new breaking-changes page in its folder. Don't add a line that is already there. |
| Index pages that exist | Add a row for the version to the version table, in the style of the existing rows, below vNext rows and above lower versions; same for the breaking-changes index when a page was written. If the page lists separate "New Features" and "Improvements" section descriptions, replace them with one **🚀 New & Enhancements** line. |

If a version row or `.order` line for `{version}` already exists, leave it. If a version page or breaking-changes page for `{version}` already exists and differs, show what would be lost and ask.

## Repos without the structure

Only when `docs/release-notes/` has **no vNext file and no version page**, create the default layout from the skill's assets, replacing `{product}` with the project name:

| File | Asset |
|---|---|
| `docs/release-notes.md` | [../assets/release-notes-index.md](../assets/release-notes-index.md) |
| `docs/release-notes/vNext-release-notes.md` | [../assets/vNext-release-notes.md](../assets/vNext-release-notes.md) |
| `docs/release-notes/breaking-changes.md` | [../assets/breaking-changes-index.md](../assets/breaking-changes-index.md) |
| `docs/release-notes/breaking-changes/vNext-breaking-changes.md` | [../assets/vNext-breaking-changes.md](../assets/vNext-breaking-changes.md) |
| `.order` files | `docs/release-notes/.order`: `breaking-changes`, `vNext-release-notes`; `docs/release-notes/breaking-changes/.order`: `vNext-breaking-changes`; `docs/.order` as in *Files written at release* (add `release-notes` if it already exists) |

Then write the version's files as above. A repo with a partial structure of its own (e.g. only a vNext file, or only version pages) keeps it: add nothing but the version page, missing `.order` files and the edits above. Don't create `docs/readme.md` or switch on wiki publishing: tell the user in the report that the standard also needs those.
