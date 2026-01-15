# Selector Reference

Quick reference for all CSS selectors used in the create-form skill.

## Authentication Selectors

| Element | Selector |
|---------|----------|
| Username input | `input[placeholder="Username"]` |
| Password input | `input[placeholder="Password"]` |
| Sign in button | `button.ant-btn-primary` |

## Form List Page

| Element | Selector |
|---------|----------|
| Create New button | `text=Create New` |
| Search input | `.ant-input-search input` |

## Create Form Dialog

| Element | Selector |
|---------|----------|
| Module dropdown | `.ant-modal .ant-select-selector` |
| Module option | `.ant-select-item[title="Shesha.AiBoooking"]` |
| Name input | `.ant-modal-body input.ant-input >> nth=0` |
| Label input | `.ant-modal-body input.ant-input >> nth=1` |
| Description textarea | `.ant-modal-body textarea` |
| Create button | `.ant-modal button.ant-btn-primary` |
| Use Template checkbox | `.ant-modal-body .ant-checkbox-input` |

> **Note:** The Create button is inside `.ant-modal` (within the form body), NOT in `.ant-modal-footer`.

## Template Wizard

| Element | Selector |
|---------|----------|
| Template table rows | `.tr-body` |
| Table View row | `.tr-body:has-text("Table View")` |
| Create View row | `.tr-body:has-text("Create View")` |
| Details View row | `.tr-body:has-text("Details View")` |
| Next button | `.sha-wizard button.ant-btn-primary:has-text("Next")` |
| Back button | `.sha-wizard button:has-text("Back")` |
| Create button (wizard) | `.sha-wizard button.ant-btn-primary:has-text("Create")` |

## Template Configuration

| Element | Selector |
|---------|----------|
| Model Type dropdown | `[data-sha-c-name="modelType"] .ant-select-selector` |
| Model Type search input | `[data-sha-c-name="modelType"] input.ant-select-selection-search-input` |
| Show Key Info Bar checkbox | `[data-sha-c-name="showKeyInformationBar"] .ant-checkbox-input` |
| Add Child Tables checkbox | `[data-sha-c-name="addChildTables"] .ant-checkbox-input` |

## Form Designer

| Element | Selector |
|---------|----------|
| Toolbox component | `.sha-toolbox-component` |
| Canvas container | `.sha-components-container-inner` (index 4 for main) |
| Component on canvas | `.sha-component` |
| Drag handle | `.sha-component-drag-handle` |
| Drop hint | `.sha-drop-hint` |
| Selected component | `.sha-component.selected` |
| Properties panel | `.sha-designer-toolbar-right` |
| Toolbox panel | `.sha-toolbox-panel-components` |
