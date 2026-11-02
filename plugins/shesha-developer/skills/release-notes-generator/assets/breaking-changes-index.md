# Breaking Changes

A per-version record of changes that can break an existing implementation or require action when
upgrading. Breaking changes are documented **as they are implemented**, not reconstructed at release
time.

## Versions

| Version | Notes |
| --- | --- |
| **vNext** (unreleased) | [vNext breaking changes](breaking-changes/vNext-breaking-changes.md) — add your entry here |

## How this works

1. While implementing a breaking change, append an entry to
   **[vNext-breaking-changes.md](breaking-changes/vNext-breaking-changes.md)** in the **same PR** as
   the code. Always state the action a consumer has to take.
2. At release, the entries that shipped move into the version's file (for example
   `v1.2.3-breaking-changes.md`), the rest stay in vNext, and the table above is updated.

Entries must land on the branch published as the wiki. If the change was implemented on a release
branch, make sure the entry also reaches that branch.

> This folder is for breaking changes only. The release notes themselves are maintained separately —
> see [Release notes](../release-notes.md).
