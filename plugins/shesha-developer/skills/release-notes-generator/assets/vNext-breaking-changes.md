# vNext — Breaking Changes (Unreleased)

**This is a living document, owned by developers.** If you implement a breaking change, record it
here in the **same pull request** as the code. A breaking change reconstructed at release time is a
breaking change that ships undocumented.

> This file covers **breaking changes only**. The release notes themselves are maintained
> separately — see [Release notes](../../release-notes.md).

Entries must land on the branch published as the wiki. If the change was implemented on a release
branch, make sure the entry also reaches that branch.

## What counts as a breaking change?

Anything that can break an existing implementation, or that requires action when upgrading:

- A removed or renamed entity property, database column, or table
- A property changing type — for example free text becoming a reference list
- A removed, renamed, or re-signatured API endpoint or DTO field
- A new or tightened uniqueness / validation constraint that existing data may violate
- A renamed or removed reference list, permission, setting, or configuration item
- Form or component configuration that must be reconfigured to keep working
- A changed default that alters existing behaviour

If you are unsure, record it.

## Entries

*Nothing recorded yet.*

<!--
Copy this template for each breaking change, newest first. "Action required" is the part consumers
actually need — never leave it out. Link the work item.

### <Area> — <what changed>

**What changed:** ...

**Why:** ... (work item link)

**Action required:** ... (migration steps, configuration to update, forms to reconfigure, data to verify)

**Affected:** <entities / endpoints / modules / forms>
-->

---

## At release time

The release notes generator moves the entries that shipped in the version into
`v{version}-breaking-changes.md`, leaves the rest here, and updates [`.order`](.order) and the
[Breaking changes](../breaking-changes.md) page.
