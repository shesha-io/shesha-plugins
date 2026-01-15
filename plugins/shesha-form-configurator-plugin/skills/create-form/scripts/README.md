# Shesha Form Creation Scripts

Fast, automated form creation for Shesha using Playwright.

## Quick Start ⚡

### 1. Install Dependencies (One-time)

```bash
npm install
```

This installs Playwright and its browser dependencies.

### 2. Create CRUD Forms

```bash
# Basic usage
node create-crud-forms-parallel.js <EntityName> <ModelType>

# Example: Create forms for Person entity
node create-crud-forms-parallel.js Person Shesha.Domain.Person
```

**Result:** Creates 3 forms in ~40 seconds:
- `person-table` - Table View
- `person-details` - Details View
- `person-create` - Create View

## Examples

```bash
# Address entity
node create-crud-forms-parallel.js Address Shesha.Domain.Address

# Booking entity
node create-crud-forms-parallel.js Booking Shesha.Domain.Booking

# OrganisationBase entity
node create-crud-forms-parallel.js OrganisationBase Shesha.Domain.OrganisationBase
```

## How It Works

The script opens **3 browser tabs simultaneously** and creates all CRUD forms in parallel:

```
┌─────────────────────────────────────┐
│ Browser (Chromium)                  │
├─────────────────────────────────────┤
│ Tab 1: Creating table view...       │
│ Tab 2: Creating details view...     │
│ Tab 3: Creating create view...      │
└─────────────────────────────────────┘
         ↓ (40 seconds later)
┌─────────────────────────────────────┐
│ ✓ person-table created              │
│ ✓ person-details created            │
│ ✓ person-create created             │
└─────────────────────────────────────┘
```

## Performance

| Approach | Time | Speed |
|----------|------|-------|
| Manual (one by one) | ~5 minutes | 1x |
| Sequential script | ~3 minutes | 1.7x |
| **Parallel script** | **~40 seconds** | **7.5x** ⚡ |

## Configuration

Edit `CONFIG` in `create-crud-forms-parallel.js`:

```javascript
const CONFIG = {
  baseUrl: 'http://localhost:3000',     // Your Shesha URL
  credentials: {
    username: 'admin',                   // Login credentials
    password: '123qwe'
  },
  module: 'Shesha.AiBoooking',          // Target module
  timeout: 60000                         // Request timeout (ms)
};
```

## Requirements

- **Node.js** v14+ installed
- **Shesha** running at `http://localhost:3000`
- Valid login credentials (default: admin/123qwe)

## Troubleshooting

### "Cannot find module 'playwright'"

Install dependencies:
```bash
npm install
```

### Timeout errors

Increase timeout in the script:
```javascript
timeout: 120000  // 2 minutes
```

### Forms not appearing

- Check Shesha is running: http://localhost:3000
- Verify entity exists in Shesha
- Check module name spelling (e.g., "Shesha.AiBoooking" not "Shesha.AiBooking")

### Browser stays open

This is normal! The script keeps the browser open for 5 seconds after completion so you can verify the forms were created.

## Output Example

```
============================================================
Creating CRUD forms for Person
Model Type: Shesha.Domain.Person
============================================================

Opening browser tabs...
✓ Three tabs opened

Checking authentication on all tabs...
  → Checking authentication...
  ✓ Already logged in
  ✓ Already logged in
  ✓ Already logged in
✓ All tabs authenticated

Creating forms in parallel...

[Tab 1] Creating table form: person-table
  → Navigating to forms page...
  ✓ On forms page
[Tab 1]   → Clicking Create New...
[Tab 1]   → Enabling template...
[Tab 1]   → Selecting Table View...
[Tab 1]   → Going to configurations...
[Tab 1]   → Selecting module...
[Tab 1]   → Filling form name: person-table
[Tab 1]   → Filling form label: Person Table
[Tab 1]   → Filling description...
[Tab 1]   → Selecting model type: Shesha.Domain.Person
[Tab 1]   → Creating form...
[Tab 1]   ✓ Form created successfully: person-table

[Tab 2] Creating details form: person-details
  ...
[Tab 2]   ✓ Form created successfully: person-details

[Tab 3] Creating create form: person-create
  ...
[Tab 3]   ✓ Form created successfully: person-create

============================================================
SUMMARY
============================================================
Total time: 42.19 seconds

✓ Successfully created:
  - person-table (table)
  - person-details (details)
  - person-create (create)

============================================================

Keeping browser open for 5 seconds...
Browser closed

✓ Script completed successfully
```

## Advanced: Batch Creation

Create forms for multiple entities:

```bash
#!/bin/bash
# create-all.sh

entities=(
  "Person:Shesha.Domain.Person"
  "Address:Shesha.Domain.Address"
  "Booking:Shesha.Domain.Booking"
)

for entity in "${entities[@]}"; do
  IFS=':' read -r name type <<< "$entity"
  echo "Creating forms for $name..."
  node create-crud-forms-parallel.js "$name" "$type"
  sleep 3
done
```

## Scripts in this Directory

| Script | Purpose |
|--------|---------|
| `create-crud-forms-parallel.js` | **Main script**: Create CRUD forms in parallel |
| `select-template-row.js` | Helper: Select template when click is intercepted |
| `get-form-designer-context.js` | Helper: Initialize Form Designer API |
| `add-component.js` | Helper: Add component (standalone) |
| `add-component-simple.js` | Helper: Add component (requires context) |
| `get-container-ids.js` | Helper: Get container IDs |
| `get-components.js` | Helper: List all components |
| `delete-component.js` | Helper: Delete a component |

## Support

- **Documentation**: See parent [SKILL.md](../SKILL.md)
- **Templates Guide**: [references/TEMPLATES.md](../references/TEMPLATES.md)
- **Troubleshooting**: [references/TROUBLESHOOTING.md](../references/TROUBLESHOOTING.md)
