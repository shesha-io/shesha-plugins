# vNext — Unreleased

**This is a living document.** It accumulates release-worthy changes as they are merged, so that
release notes never have to be reconstructed (or guessed at) when a version is cut.

> **If you are implementing a change:** append your entry to the relevant section below, in the
> **same pull request** as the code change. Delete the *"Nothing recorded yet"* line from any section
> you add to, and leave the empty sections in place for the next person.
>
> **Breaking changes do not go in this file** — record them in
> [`breaking-changes/vNext-breaking-changes.md`](breaking-changes/vNext-breaking-changes.md).

---

## 📌 General

*Nothing recorded yet.*

<!--
Framework/dependency version bumps and anything that applies to the release as a whole, e.g.:
- Upgraded to Shesha framework {new version}
-->

## ⚠️ Breaking Changes

Recorded separately, in
**[breaking-changes/vNext-breaking-changes.md](breaking-changes/vNext-breaking-changes.md)**.
Add breaking changes there, not here.

## 🚀 New & Enhancements

*Nothing recorded yet.*

<!--
New capabilities and improvements to existing ones. Link the work item, e.g.:
- **{Area}: {What changed}** - {How it behaves now}. ([#{id}](https://dev.azure.com/{org}/{project}/_workitems/edit/{id}))
-->

## 🐞 Bug Fixes

*Nothing recorded yet.*

---

## At release time

The release notes generator moves the entries that shipped in the version into `v{version}-release-notes.md`,
leaves the rest here, and updates [`.order`](.order) and the table in
[release-notes.md](../release-notes.md).
