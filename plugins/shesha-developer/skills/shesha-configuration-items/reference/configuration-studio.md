# Configuration Studio Integration (Alternative to Admin Forms)

An alternative to building standalone admin forms/screens (artifact 8, [admin-forms.md](admin-forms.md)):
surface the configuration item natively inside Configuration Studio — under **New**, with its own
create wizard and document editor, the same way built-in item types like Reference Lists and Roles
work. Ask the user which they want before scaffolding artifact 8; the two are not combined.

Configuration Studio integration only applies to entities extending `ConfigurationItem` (not the
lighter `ConfigurationItemBase` this skill defaults to) — `ConfigurationItem` carries the revision
history, `[FixedView]`-driven menu wiring, and generic create/update endpoints Configuration Studio
depends on. If the entity was scaffolded as a `ConfigurationItemBase` subclass per this skill's
default template, it needs to extend `ConfigurationItem` instead before this applies.

## 1. Backend: make it appear in the **New** menu

Add `[FixedView(ConfigurationItemsViews.Create, {ModuleName}, "{create-form-name}")]` to the entity:

```csharp
[DiscriminatorValue(ItemTypeName)]
[JoinedProperty("{Prefix}_{ConfigName}s")]
[Entity(FriendlyName = "{Friendly Name}")]
[FixedView(ConfigurationItemsViews.Create, {ModuleClass}.ModuleName, "{item-type-name}-create")]
public class {ConfigName} : ConfigurationItem
{
    public const string ItemTypeName = "{item-type-name}";
    public override string ItemType => ItemTypeName;
}
```

Without this attribute, `CreateFormId` stays null and the item type never appears under **New** —
Configuration Studio only lists item types with a non-null create form.

**The entity must own at least one genuine `NotNullable()` column with a default.** NHibernate's
`<join>` mapping silently skips inserting the joined-table row when every one of its own (non-key)
columns would be null. An entity with no real columns of its own (only `Id`) will have every
instance created through the normal flow end up with a base `configuration_items` row but **no
matching row in its own joined table** — and since the read-side join is effectively an inner join,
those instances become invisible to every query against the entity, including any dropdown/lookup
endpoint you add later. Give it a real, meaningful boolean or similar (e.g. `IsActive`,
`NotNullable`, default `true`) — not just a placeholder column, and not reliance on app code always
setting *some* property, which is fragile if any other code path constructs/saves the entity
directly.

## 2. Backend: the create form and document editor form

Two forms are needed: `{item-type-name}-create` (the create wizard) and `{item-type-name}-details`
(the document editor opened by the `DocumentDefinition` in §3). Both are module = the one named in
`[FixedView(...)]`.

**If a Shesha MCP server is available** (check for MCP tools with names containing "shesha" or
"form"), use it to create both forms now, same as artifact 8's standalone-screen path does — do not
just describe them to the user. Field content for both should mirror artifact 8's "Important
Fields" table (`Name`, `Label`, `Module`, `Description`, plus custom properties), but:

- The **create form**'s Submit action must call `POST /api/services/app/ConfigurationStudio/CreateItem`,
  not the entity's generic dynamic-CRUD `Create` endpoint. If the form's Form Settings have
  `modelType` set to the entity's fully qualified name with no explicit `postUrl`, it silently falls
  back to the dynamic-entity endpoint instead — which doesn't understand
  `moduleId`/`itemType`/`discriminator` and rejects the payload with `Property 'discriminator' not
  found for '{Entity}'`.
- Configuration Studio automatically passes `moduleId`, `folderId`, `itemType`, `discriminator` into
  the create form as `formArguments` — bind the Module field to `formArguments.moduleId` instead of
  asking the user to pick it manually.
- The **details form** doesn't need `Module`/`itemType`/`discriminator` fields — it edits an
  already-created item's own properties.

**If Shesha MCP is NOT available**, notify the user with the same structure as artifact 8's
MCP-unavailable notice: name both forms, their module, their required fields, and that they must be
built manually in the Shesha Form Designer because no MCP server is connected.

## 3. Frontend: `DocumentDefinition`

In the consuming module's frontend package, define a `DocumentDefinition` using
`getGenericDefinition` — the same helper Shesha's own Reference List / Role / Notification item
types use to render a form-backed document editor:

```tsx
import { DocumentDefinition, getGenericDefinition } from '@shesha-io/reactjs';
import { SomeOutlined } from '@ant-design/icons';

export const {ConfigName}DocumentDefinition: DocumentDefinition = getGenericDefinition(
  '{item-type-name}',
  {
    icon: <SomeOutlined />,
    formId: { module: '{ModuleName}', name: '{item-type-name}-details' },
  },
);
```

Register it alongside whatever else the module's application plugin already sets up:

```tsx
import { DocumentDefinitionRegistration } from '@shesha-io/reactjs';

<DocumentDefinitionRegistration definitions={[{ConfigName}DocumentDefinition]} />
```

## 4. Verify

```http
GET /api/services/app/Entities/GetAll?entityType={FullyQualifiedEntityTypeName}&maxResultCount=1
```

Then in Configuration Studio: **New** should list the item type, creating one should land on the
document editor form, and re-opening an existing item should load the same form correctly. If the
item disappears from lookups/dropdowns after creation despite a successful create, check §1's
joined-table column requirement first.
