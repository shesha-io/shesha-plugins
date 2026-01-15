# Form Designer Automation

After creating a form, you can programmatically add and arrange components in the Form Designer.

## Architecture

The Form Designer uses **react-sortablejs** (wrapping SortableJS) for drag-and-drop.

| Approach | Works? | Reason |
|----------|--------|--------|
| Playwright `drag()` for reordering | ✅ Yes | Same SortableJS container |
| Playwright `drag()` toolbox→canvas | ❌ No | SortableJS requires `isTrusted: true` events |
| Synthetic MouseEvents/PointerEvents | ❌ No | `isTrusted` is always `false` |
| Direct `formDesigner.addComponent()` | ✅ Yes | **Recommended** - bypasses drag entirely |

### Why Native Drag Doesn't Work for Toolbox→Canvas

SortableJS requires `isTrusted: true` events (real user input):

1. **Toolbox** uses `pull: 'clone'` to clone items
2. **Toolbox `onStart`** sets `hasDragged = true`
3. **Canvas `onSetList`** checks `if (!hasDragged) return;`
4. **Synthetic events** don't trigger SortableJS handlers, so `hasDragged` stays `false`

This is why we use the direct `formDesigner.addComponent()` API via scripts instead.

## Available Component Types

| Category | Component Types |
|----------|----------------|
| Data Entry | `textField`, `textArea`, `numberField`, `checkbox`, `switch`, `datePicker`, `timePicker`, `dateTimePicker` |
| Selection | `dropdown`, `autocomplete`, `radio`, `checkboxGroup`, `refListDropdown`, `refListCheckboxGroup` |
| Layout | `columns`, `tabs`, `panel`, `collapsiblePanel`, `wizard` |
| Display | `text`, `title`, `divider`, `space`, `alert` |
| Actions | `button`, `buttonGroup`, `link` |
| Advanced | `subForm`, `dataTable`, `childDataTable`, `codeEditor`, `richTextEditor` |

## Scripts

All Form Designer automation is done via scripts in the `scripts/` directory. Execute them using `mcp__playwright__playwright_evaluate`.

| Script | Purpose | Parameters |
|--------|---------|------------|
| [get-form-designer-context.js](../scripts/get-form-designer-context.js) | **Run first** - Exposes `window.__formDesigner` | None |
| [add-component.js](../scripts/add-component.js) | Standalone add component (self-contained) | `{componentType}`, `{containerId}`, `{index}` |
| [add-component-simple.js](../scripts/add-component-simple.js) | Add component (requires context first) | `{componentType}`, `{containerId}`, `{index}` |
| [add-styled-component.js](../scripts/add-styled-component.js) | Add component with label and background color | `{componentType}`, `{containerId}`, `{index}`, `{label}`, `{backgroundColor}` |
| [get-container-ids.js](../scripts/get-container-ids.js) | Get all container IDs for nested containers | None |
| [get-components.js](../scripts/get-components.js) | Get all components with IDs and properties | None |
| [delete-component.js](../scripts/delete-component.js) | Delete a component by ID | `{componentId}` |

## Recommended Workflow

1. **Initialize**: Run [get-form-designer-context.js](../scripts/get-form-designer-context.js)
2. **Add components**: Run [add-component-simple.js](../scripts/add-component-simple.js) with parameters replaced
3. **For nested containers**: Run [get-container-ids.js](../scripts/get-container-ids.js) to find child container IDs
4. **Inspect**: Run [get-components.js](../scripts/get-components.js) to see all components
5. **Clean up**: Run [delete-component.js](../scripts/delete-component.js) to remove components

## Adding Components to Nested Containers

To add components inside columns, panels, or tabs:

1. Add the container: Run `add-component-simple.js` with `{componentType}='columns'`, `{containerId}='root'`
2. Find nested IDs: Run `get-container-ids.js` - look for new container IDs (not `root`)
3. Add to nested: Run `add-component-simple.js` with the nested container ID from step 2

> **Note:** Container IDs are dynamically generated. You must query for them after adding the container component.

## Reordering Components

Reordering existing components works with Playwright's native drag:

```
Tool: mcp__playwright__playwright_drag
sourceSelector: .sha-component:nth-child(2) .sha-component-drag-handle
targetSelector: .sha-component:nth-child(1)
```

**Important:** Always use `.sha-component-drag-handle` as the drag source.
