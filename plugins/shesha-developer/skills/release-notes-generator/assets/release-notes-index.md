Welcome! This is the central place for {product} release notes - a running record of features, improvements, fixes, and breaking changes across all versions.

## What you'll find here

Each release gets its own dedicated page, listed in the navigation tree on the left. Release pages can include:

- 📌 **General** - framework and dependency upgrades, and changes that apply to the release as a whole.
- ⚠️ **Breaking Changes** - anything that could affect your existing implementation or require action when upgrading. Recorded in full, per version, under **[Breaking changes](release-notes/breaking-changes.md)**.
- 🚀 **New & Enhancements** - new functionality and improvements to what already existed.
- 🐞 **Bug Fixes** - issues that were caught and squashed.

## Versions

| Version | Notes |
| --- | --- |
| **vNext** (unreleased) | [vNext release notes](release-notes/vNext-release-notes.md) — the living document. Add entries here as you merge. |
| **Breaking changes** | [Breaking changes by version](release-notes/breaking-changes.md) — maintained by developers as changes are implemented. |

## How release notes are maintained

Release notes are **living documents**, not something reconstructed at release time.

1. While implementing a release-worthy change, append an entry to
   **[vNext-release-notes.md](release-notes/vNext-release-notes.md)** in the *same PR* as the code.
2. Breaking changes are mandatory to document, in their own per-version files — append to
   [`vNext-breaking-changes.md`](release-notes/breaking-changes/vNext-breaking-changes.md), stating
   the action a consumer must take.
3. At release time, the entries that shipped move into the version's page (for example `v1.2.3-release-notes.md`),
   the rest stay in vNext, and `.order` and the table above are updated.
