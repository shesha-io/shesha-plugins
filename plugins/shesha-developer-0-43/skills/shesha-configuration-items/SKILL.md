---
name: shesha-configuration-items
description: Creates and updates custom configuration items in Shesha framework .NET applications. Scaffolds domain entities extending ConfigurationItemBase, FluentMigrator joined-table migrations, managers, and import/export distribution classes in the Domain layer, plus IoC registration in the Application layer. Use when the user asks to create, scaffold, implement, or update configuration items, configuration types, or configurable settings in a Shesha project. Also use when implementing features from a PRD or specification that require new configuration item types with admin UI, versioning, or import/export support.
---

# Shesha Configuration Item Implementation

Scaffold and manage custom configuration items for a Shesha/.NET/ABP/NHibernate application based on $ARGUMENTS.

## Instructions

- Inspect nearby files to determine the correct namespace root, module name, and DB prefix.
- All entity properties must be `virtual` (NHibernate requirement).
- Use `Guid` as entity ID type.
- Follow existing project conventions for naming and folder layout.
- If the user is updating an existing configuration item, read the entity class and latest migration first.

## Artifact Catalog

| # | Artifact | Project | Reference |
|---|----------|---------|-----------|
| 1 | Domain Entity | Domain | [reference/entity.md](reference/entity.md) |
| 2 | Database Migration | Domain | [reference/migration.md](reference/migration.md) |
| 3 | Manager | Domain | [reference/manager.md](reference/manager.md) |
| 4 | Distribution DTO | Domain | [reference/distribution.md](reference/distribution.md) §1 |
| 5 | Exporter | Domain | [reference/distribution.md](reference/distribution.md) §2 |
| 6 | Importer | Domain | [reference/distribution.md](reference/distribution.md) §3 |
| 7 | Module Registration | Application | [reference/registration.md](reference/registration.md) |
| 8 | Admin Forms | (UI) | [reference/admin-forms.md](reference/admin-forms.md) |

## Folder Structure

```
{Module}.Domain/
  Domain/{ConfigName}s/
    {ConfigName}.cs                        ← Entity (artifact 1)
    RefList{EnumName}.cs                   ← Related reference list enums
    I{ConfigName}Manager.cs                ← Manager interface (artifact 3)
    {ConfigName}Manager.cs                 ← Manager implementation (artifact 3)
    Distribution/
      Distributed{ConfigName}.cs           ← Distribution DTO (artifact 4)
      I{ConfigName}Export.cs               ← Exporter interface (artifact 5)
      {ConfigName}Export.cs                ← Exporter implementation (artifact 5)
      I{ConfigName}Import.cs               ← Importer interface (artifact 6)
      {ConfigName}Import.cs                ← Importer implementation (artifact 6)
  Migrations/
    M{YYYYMMDDHHmmss}.cs                  ← Migration (artifact 2)

{Module}.Application/
  {Module}ApplicationModule.cs             ← Registration (artifact 7)
```

## Quick Reference

### Required Attributes

| Attribute | Purpose | Example |
|-----------|---------|---------|
| `[DiscriminatorValue(ItemTypeName)]` | Sets `ItemType` column value | `[DiscriminatorValue("leave-type-configs")]` |
| `[JoinedProperty("Table")]` | Names the joined table | `[JoinedProperty("Leave_LeaveTypeConfigs")]` |

### Required Members

| Member | Type | Purpose |
|--------|------|---------|
| `ItemTypeName` | `const string` | Kebab-case discriminator value |
| `ItemType` | `override string` | Returns `ItemTypeName` |

### Base Classes

| Artifact | Base Class |
|----------|-----------|
| Entity | `ConfigurationItemBase` (from `Shesha.Domain`) |
| Manager | `ConfigurationItemManager<T>` (from `Shesha.ConfigurationItems`) |
| Importer | `ConfigurationItemImportBase` (from `Shesha.Services.ConfigurationItems`) |
| Distribution DTO | `DistributedConfigurableItemBase` (from `Shesha.ConfigurationItems.Distribution`) |

### Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| `ItemTypeName` | kebab-case | `"approval-config"` |
| Joined table | `{Prefix}_{ConfigName}s` | `Leave_LeaveTypeConfigs` |
| DB columns | `{Prefix}_{PropertyName}` | `Leave_AllowBackDating` |
| Reference list columns | `{Prefix}_{Name}Lkp` | `Leave_TypeOfDaysLkp` |
| FK columns | `{Prefix}_{Name}Id` | `Leave_OverflowLeaveTypeId` |

### Key Interfaces

| Interface | Namespace | Purpose |
|-----------|-----------|---------|
| `IConfigurationItemManager<T>` | `Shesha.ConfigurationItems` | Manager contract |
| `IConfigurableItemExport<T>` | `Shesha.ConfigurationItems.Distribution` | Export contract |
| `IConfigurableItemImport<T>` | `Shesha.ConfigurationItems.Distribution` | Import contract |
| `IConfigurationItemsImportContext` | `Shesha.ConfigurationItems.Distribution` | Import context |

### IoC Registration Methods

```csharp
IocManager
    .RegisterConfigurableItemManager<TEntity, TInterface, TImpl>()
    .RegisterConfigurableItemExport<TEntity, TInterface, TImpl>()
    .RegisterConfigurableItemImport<TEntity, TInterface, TImpl>();
```

Register in the **Application module's** `PreInitialize()`. Methods are chainable.

## Workflow

Determine the type of change, then follow the appropriate path:

**Creating a new configuration item type?** Follow the New Config Item workflow.
**Adding properties to an existing configuration item?** Follow the Update workflow.

### New Configuration Item Workflow

```
- [ ] Step 1: Gather requirements (properties, types, reference lists, relationships)
- [ ] Step 2: Create entity class extending ConfigurationItemBase (artifact 1)
- [ ] Step 3: Create FluentMigrator migration for joined table (artifact 2)
- [ ] Step 4: Create manager interface and implementation (artifact 3)
- [ ] Step 5: Create distribution DTO, exporter, and importer (artifacts 4-6)
- [ ] Step 6: Register manager, exporter, and importer in Application module (artifact 7)
- [ ] Step 7: Verify NHibernate mappings (see Verification section below)
- [ ] Step 8: Create admin forms via Shesha MCP or notify user (artifact 8)
```

### Update Existing Config Item Workflow

```
- [ ] Step 1: Read existing entity class and identify current properties
- [ ] Step 2: Add/modify properties on the entity class
- [ ] Step 3: Create new migration to alter the joined table
- [ ] Step 4: Update distribution DTO with new properties
- [ ] Step 5: Update exporter and importer to map new properties
- [ ] Step 6: Verify NHibernate mappings (see Verification section below)
```

### Verification

After creating or updating a configuration item, verify the NHibernate mappings work by hitting these two API endpoints (requires the server to be running with the new migration applied):

**1. Verify the specific config item type:**
```
GET /api/services/app/Entities/GetAll?entityType={FullyQualifiedEntityTypeName}&maxResultCount=1
```
Expected: `{"success": true, "result": {"totalCount": 0, ...}}`

**2. Verify the polymorphic ConfigurationItemBase query (exercises ALL joined tables):**
```
GET /api/services/app/Entities/GetAll?entityType=Shesha.Domain.ConfigurationItemBase&maxResultCount=1
```
Expected: `{"success": true, "result": {"totalCount": N, ...}}` where N > 0

If either endpoint returns `success: false` with a SQL error mentioning "Invalid column name", the migration column names don't match NHibernate's expected naming convention. The most common cause is FK columns missing the `{Prefix}_` prefix in `[JoinedProperty]` tables.

### Key Rules

- **Normalize on first version** — call `entity.Normalize()` when creating the first version of an item (in `CopyAsync` and importers). This sets `Origin` to self-reference.
- **Origin on subsequent versions** — set `Origin = item.Origin` in `CreateNewVersionAsync`.
- **Virtual properties** — every entity property must be `virtual` for NHibernate.
- **FK to ConfigurationItems** — the joined table MUST have a FK from `Id` to `Frwk_ConfigurationItems.Id`.
- **FK column prefix** — ALL columns in `[JoinedProperty]` tables MUST use the `{Prefix}_` prefix, including FK columns. NHibernate's convention prefixes every column with the table prefix. Example: table `MOD_MyConfigs` → FK column must be `MOD_RelatedEntityId`, NOT `RelatedEntityId`.
- **ITransientDependency** — exporters and importers must implement `ITransientDependency`.
- **Match by Name + Module** — importers identify existing items by `Name` + `Module.Name` + `IsLast`.
- **Cross-config-item references use Name + Module, NOT Guid** — when a config item references another `ConfigurationItemBase` entity, the distribution DTO MUST use `string {Related}Name` + `string {Related}Module` pairs. The exporter maps from navigation properties (`entity.Related?.Name`, `entity.Related?.Module?.Name`), and the importer resolves back via `Name + Module + IsLast` query. GUIDs are environment-specific and make packages non-portable. Only internal versioning fields (`OriginId`, `BaseItem`, `ParentVersionId`) use GUIDs. See [reference/distribution.md](reference/distribution.md) §Cross-Config-Item References.
- **Only register what you implement** — skip manager registration if not needed; skip export/import if not needed.

For each step, read the relevant reference file from the artifact catalog above.

Now generate the requested configuration item artifact(s) based on: $ARGUMENTS
