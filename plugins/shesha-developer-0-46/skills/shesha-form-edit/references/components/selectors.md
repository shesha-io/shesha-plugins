# Entity-bound selectors — autocomplete, entityPicker

Both bind to entity types. Both require `editMode: "editable"`.

## autocomplete

Async lookup, type-ahead. Bind to entity, set `entityType`, optional `displayPropertyName`:

```json
{
  "id": "...",
  "type": "autocomplete",
  "propertyName": "subscription",
  "label": "Subscription",
  "entityType": "MyApp.Membership.Domain.Domain.Subscription",
  "displayPropertyName": "_displayName",
  "filter": "...",
  "editMode": "editable"
}
```

For URL-based autocomplete (custom endpoint instead of entity CRUD): set `dataSourceType: "url"` and provide `dataSourceUrl`.

## entityPicker

Modal-based entity picker with full search. Heavier than `autocomplete` but supports filtering by columns:

```json
{
  "id": "...",
  "type": "entityPicker",
  "propertyName": "tier",
  "entityType": "MyApp.Membership.Domain.Domain.Tier",
  "displayEntityKey": "name",
  "modalTitle": "Select Tier",
  "items": [ /* table columns config */ ],
  "editMode": "editable"
}
```

## When to use which

| Use | When |
|---|---|
| `autocomplete` | Small-to-medium pick lists, type-ahead is enough, no need to see other columns |
| `entityPicker` | Big lists, user needs to see multiple columns to choose, filtering by non-display fields |
| `dropdown` (refList) | Fixed reference list, not an entity (see [dropdowns.md](dropdowns.md)) |
