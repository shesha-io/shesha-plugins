/**
 * Add Styled Component
 *
 * Adds a component and immediately applies styling (label, background color, etc.)
 * in a single operation. Run get-form-designer-context.js first to expose the context.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   Replace the parameters before executing:
 *   - {componentType}: e.g., 'collapsiblePanel', 'textField', 'button'
 *   - {containerId}: e.g., 'root' or a nested container ID
 *   - {index}: position number (0 = top)
 *   - {label}: display label for the component
 *   - {backgroundColor}: hex color code (e.g., '#D9F7BE' for light green)
 *
 * Common background colors:
 *   - Light Green: #D9F7BE (success, personal info)
 *   - Light Purple: #EFDBFF (account, settings)
 *   - Light Blue: #BAE7FF (information)
 *   - Light Cyan: #B5F5EC (actions)
 *   - Light Orange: #FFE7BA (warnings)
 *
 * @returns {object} Result with componentId and success status
 */
(function(componentType, containerId, index, label, backgroundColor) {
  if (!window.__formDesigner) {
    return {
      success: false,
      error: 'formDesigner not found. Run get-form-designer-context.js first.'
    };
  }

  if (!componentType) {
    return { success: false, error: 'componentType is required' };
  }

  try {
    // Step 1: Get existing component IDs before adding
    const existingIds = new Set();
    document.querySelectorAll('.sha-component').forEach(comp => {
      const reactFiberKey = Object.keys(comp).find(k => k.startsWith('__reactFiber'));
      if (reactFiberKey) {
        let fiber = comp[reactFiberKey];
        let depth = 0;
        while (fiber && depth < 10) {
          if (fiber.memoizedProps?.id) {
            existingIds.add(fiber.memoizedProps.id);
            break;
          }
          fiber = fiber.return;
          depth++;
        }
      }
    });

    // Step 2: Add the component
    window.__formDesigner.addComponent({
      containerId: containerId || 'root',
      componentType: componentType,
      index: typeof index === 'number' ? index : 0
    });

    // Step 3: Find the newly added component by comparing IDs
    let newComponentId = null;
    document.querySelectorAll('.sha-component').forEach(comp => {
      const reactFiberKey = Object.keys(comp).find(k => k.startsWith('__reactFiber'));
      if (reactFiberKey) {
        let fiber = comp[reactFiberKey];
        let depth = 0;
        while (fiber && depth < 10) {
          if (fiber.memoizedProps?.id) {
            const id = fiber.memoizedProps.id;
            if (!existingIds.has(id)) {
              newComponentId = id;
            }
            break;
          }
          fiber = fiber.return;
          depth++;
        }
      }
    });

    if (!newComponentId) {
      return {
        success: true,
        warning: 'Component added but could not find ID to apply styles. Apply styles manually.',
        message: `Added ${componentType} to ${containerId || 'root'} at index ${index || 0}`
      };
    }

    // Step 4: Apply styling
    const settings = {};

    if (label) {
      settings.label = label;
    }

    if (backgroundColor) {
      settings.background = { type: 'color', color: backgroundColor };
    }

    if (Object.keys(settings).length > 0) {
      window.__formDesigner.updateComponent({
        componentId: newComponentId,
        settings: settings
      });
    }

    return {
      success: true,
      componentId: newComponentId,
      message: `Added ${componentType} with label "${label || 'default'}" and background "${backgroundColor || 'none'}"`
    };
  } catch (e) {
    return { success: false, error: e.message };
  }
})('{componentType}', '{containerId}', {index}, '{label}', '{backgroundColor}');
