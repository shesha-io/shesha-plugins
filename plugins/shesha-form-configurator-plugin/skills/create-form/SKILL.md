---
name: create-form
description: Creates new forms in the Shesha low-code application using Playwright browser automation. Use this skill when you need to create a new form, scaffold a UI component, or set up form configuration in Shesha. Handles login, navigation, form creation dialog, and opens the Form Designer. Requires Shesha running at localhost:3000 and Playwright MCP tools.
license: MIT
user-invocable: true
compatibility: Requires Playwright MCP server and Shesha application running locally
metadata:
  author: aibooking
  version: "1.0"
  platform: shesha
allowed-tools: mcp__playwright__playwright_navigate, mcp__playwright__playwright_screenshot, mcp__playwright__playwright_click, mcp__playwright__playwright_fill, mcp__playwright__playwright_evaluate, mcp__playwright__playwright_press_key, mcp__playwright__playwright_close, mcp__playwright__playwright_drag
---

# Create Form in Shesha

Automates creation of new forms in Shesha using Playwright browser automation.

## Quick Start: Parallel CRUD Creation (Recommended ⚡)

**Fast-track CRUD form creation using the parallel script (4-7x faster!)**

### Setup (One-time)

```bash
cd shesha-form-configurator-plugin/skills/create-form/scripts
npm install
```

### Usage

```bash
# Create all 3 CRUD forms in parallel (~40 seconds)
node create-crud-forms-parallel.js <EntityName> <ModelType>

# Examples:
node create-crud-forms-parallel.js Person Shesha.Domain.Person
node create-crud-forms-parallel.js Booking Shesha.Domain.Booking
node create-crud-forms-parallel.js Address Shesha.Domain.Address
```

**What it creates:**
- `entityname-table` - Table View (list/search)
- `entityname-details` - Details View (view/edit)
- `entityname-create` - Create View (new records)

**Performance:**
- Sequential: ~3-5 minutes
- Parallel: ~40 seconds ⚡
- Opens 3 browser tabs simultaneously

---

## Prerequisites

- Shesha running at `http://localhost:3000`
- Playwright MCP server configured
- Login credentials: admin/123qwe

## Input Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `formName` | Yes | Kebab-case identifier | `booking-form` |
| `formLabel` | No | Human-readable label | `Booking Form` |
| `formDescription` | No | Purpose description | `Form for creating bookings` |
| `moduleName` | No | Target module | `Shesha.AiBoooking` (default) |

## Workflow

### 1. Authentication

1. Navigate to `http://localhost:3000` with `headless: false`
2. Fill username: `input[placeholder="Username"]` → `admin`
3. Fill password: `input[placeholder="Password"]` → `123qwe`
4. Click: `button.ant-btn-primary`
5. Wait 3 seconds

### 2. Navigate to Forms

1. Navigate to `http://localhost:3000/dynamic/shesha/forms`
2. Wait 3 seconds

### 3. Open Create Dialog

1. Click: `text=Create New`
2. Wait 2 seconds

### 4. Fill Form Details

**Select Module:**
```
Click: .ant-modal .ant-select-selector
Wait 1 second
Click: .ant-select-item[title="Shesha.AiBoooking"]
```

**Fill Fields** (use `mcp__playwright__playwright_fill`):
- Name: `.ant-modal-body input.ant-input >> nth=0`
- Label: `.ant-modal-body input.ant-input >> nth=1`
- Description: `.ant-modal-body textarea`

> **IMPORTANT:** Use native Playwright `fill`, NOT JavaScript evaluation. JavaScript only updates DOM visually without updating React state.

### 5. Submit

Click: `.ant-modal button.ant-btn-primary`

Wait 3 seconds for Form Designer to load.

### 6. Verify Success

Form Designer opens with title `Shesha.AiBoooking/{formName}` and DRAFT status. Take a screenshot to confirm.

## Critical Notes

1. **Use native `playwright_fill`** - JavaScript evaluation doesn't update React state
2. **Create button location** - Inside `.ant-modal`, NOT in `.ant-modal-footer`
3. **Timing** - Wait 2-3 seconds after navigation/dialog actions
4. **Module spelling** - It's "Shesha.AiB**ooo**king" (three O's)

## Output

```
## Form Created Successfully

- **Module:** Shesha.AiBoooking
- **Name:** {formName}
- **Label:** {formLabel}
- **Status:** Draft, Version 1

Form Designer is now open and ready for component design.
```

## Advanced Features

- **Template-based CRUD forms:** See [references/TEMPLATES.md](references/TEMPLATES.md)
- **Form Designer automation:** See [references/FORM-DESIGNER.md](references/FORM-DESIGNER.md)
- **All CSS selectors:** See [references/SELECTORS.md](references/SELECTORS.md)
- **Troubleshooting:** See [references/TROUBLESHOOTING.md](references/TROUBLESHOOTING.md)

## Scripts

| Script | Purpose |
|--------|---------|
| [create-crud-forms-parallel.js](scripts/create-crud-forms-parallel.js) | **⚡ Create CRUD forms in parallel (FAST!)** |
| [select-template-row.js](scripts/select-template-row.js) | Select template when click is intercepted |
| [get-form-designer-context.js](scripts/get-form-designer-context.js) | Initialize Form Designer API |
| [add-component.js](scripts/add-component.js) | Add component (standalone) |
| [add-component-simple.js](scripts/add-component-simple.js) | Add component (requires context) |
| [get-container-ids.js](scripts/get-container-ids.js) | Get container IDs |
| [get-components.js](scripts/get-components.js) | List all components |
| [delete-component.js](scripts/delete-component.js) | Delete a component |

---

## How Parallel CRUD Creation Works

The `create-crud-forms-parallel.js` script dramatically speeds up CRUD form creation by:

1. **Opening 3 browser tabs simultaneously**
2. **Authenticating all tabs in parallel**
3. **Creating all 3 forms concurrently:**
   - Tab 1: Table View (list/search)
   - Tab 2: Details View (display/edit)
   - Tab 3: Create View (new records)

### Architecture

```
Browser Context
├── Tab 1 → Table View   ──┐
├── Tab 2 → Details View ──┤ All running in parallel
└── Tab 3 → Create View  ──┘
```

### Features

- **Smart Authentication**: Detects if already logged in
- **Error Handling**: Continues even if one form fails
- **Progress Tracking**: Real-time console output
- **Summary Report**: Shows success/failure for each form

### Configuration

Edit the `CONFIG` object in the script to customize:

```javascript
const CONFIG = {
  baseUrl: 'http://localhost:3000',     // Shesha URL
  credentials: {
    username: 'admin',                   // Login username
    password: '123qwe'                   // Login password
  },
  module: 'Shesha.AiBoooking',          // Target module
  timeout: 60000                         // Navigation timeout
};
```

### Troubleshooting

**Script fails with "Cannot find module 'playwright'"**
```bash
cd shesha-form-configurator-plugin/skills/create-form/scripts
npm install
```

**Forms not created correctly**
- Check that Shesha is running at localhost:3000
- Verify the entity exists: `Shesha.Domain.YourEntity`
- Ensure the module name is correct (check for typos)

**Timeout errors**
- Increase timeout in CONFIG (line 20): `timeout: 120000`
- Check your network connection
- Verify Shesha is responsive
