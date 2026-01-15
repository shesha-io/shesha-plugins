# Template-Based CRUD Form Creation

For CRUD operations, use templates instead of creating blank forms. This generates forms with pre-built components bound to entity properties.

## Available Templates

| Template | Description | Configuration Fields |
|----------|-------------|---------------------|
| Table View | List and search entities in a table | Model Type |
| Create View | Form for creating new entity records | Model Type |
| Details View | Display and edit entity details | Model Type, Show Key Information Bar?, Add Child Tables? |

## Template Workflow

### Step 1: Enable Templates

After filling Module, Name, Label, and Description, check the "Use Template?" checkbox:
```
Click: .ant-modal-body .ant-checkbox-input
Wait 1.5 seconds for template table to load
```

### Step 2: Select Template

A table appears with template options. Click on the desired template row:
```
Click: .tr-body:has-text("Table View")
  - or -
Click: .tr-body:has-text("Create View")
  - or -
Click: .tr-body:has-text("Details View")
```

> **Note:** If the click is intercepted by the textarea, use the script from [scripts/select-template-row.js](../scripts/select-template-row.js).

### Step 3: Click Next

Once a template is selected, the Next button becomes enabled:
```
Click: .sha-wizard button.ant-btn-primary:has-text("Next")
Wait 2 seconds for configuration form
```

### Step 4: Configure Template

**For Table View and Create View:**

Fill Model Type (required):
```
Click: [data-sha-c-name="modelType"] .ant-select-selector
Fill: [data-sha-c-name="modelType"] input.ant-select-selection-search-input
  value: {EntityName}  (e.g., OrganisationAddress)
Wait 2 seconds for search results
Click: .ant-select-item[title="Shesha.Domain.{EntityName}"]
```

**For Details View (additional options):**

1. **Model Type** (required) - same as above

2. **Show Key Information Bar?** (optional checkbox)
   - If checked, additional fields appear for key info bar properties
   - Selector: `[data-sha-c-name="showKeyInformationBar"] .ant-checkbox-input`

3. **Add Child Tables?** (optional checkbox)
   - If checked, a multi-select appears for child table entities
   - Selector: `[data-sha-c-name="addChildTables"] .ant-checkbox-input`

### Step 5: Create Form

Click Create to generate the form:
```
Click: .sha-wizard button.ant-btn-primary:has-text("Create")
Wait 3 seconds for Form Designer to load
```

## CRUD Form Naming Convention

For entity `OrganisationAddress`, create:
- `organisation-address-table` - Table View
- `organisation-address-create` - Create View
- `organisation-address-details` - Details View
