/**
 * Get Components
 *
 * Retrieves all components currently on the Form Designer canvas with their IDs.
 * Useful for getting component IDs needed for delete, update, or reorder operations.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   Run this script to get a list of all components with their IDs and properties.
 *
 * @returns {array} Array of component info objects
 */
(function() {
  const components = document.querySelectorAll('.sha-component');
  const componentInfo = [];

  components.forEach((component, i) => {
    const rect = component.getBoundingClientRect();

    // Skip hidden components
    if (rect.width === 0 && rect.height === 0) return;

    // Get component ID from React fiber
    const reactFiberKey = Object.keys(component).find(k => k.startsWith('__reactFiber'));
    let componentId = null;
    let componentType = null;
    let containerId = null;

    if (reactFiberKey) {
      let fiber = component[reactFiberKey];
      let depth = 0;
      while (fiber && depth < 10) {
        if (fiber.memoizedProps?.id && !componentId) {
          componentId = fiber.memoizedProps.id;
        }
        if (fiber.memoizedProps?.type && !componentType) {
          componentType = fiber.memoizedProps.type;
        }
        if (fiber.memoizedProps?.containerId && !containerId) {
          containerId = fiber.memoizedProps.containerId;
        }
        if (componentId && componentType) break;
        fiber = fiber.return;
        depth++;
      }
    }

    // Get display text
    const text = component.textContent?.substring(0, 30).trim();

    // Check if selected
    const isSelected = component.classList.contains('selected');

    // Check for nested containers (if it's a layout component)
    const nestedContainers = component.querySelectorAll(':scope .sha-components-container-inner');

    componentInfo.push({
      index: i,
      componentId: componentId,
      componentType: componentType,
      containerId: containerId,
      text: text,
      isSelected: isSelected,
      hasNestedContainers: nestedContainers.length,
      position: {
        top: Math.round(rect.top),
        left: Math.round(rect.left),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });
  });

  return componentInfo;
})();
