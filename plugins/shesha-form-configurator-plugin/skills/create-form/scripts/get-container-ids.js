/**
 * Get Container IDs
 *
 * Retrieves all visible container IDs in the Form Designer canvas.
 * Use this to find container IDs for nested containers (columns, panels, tabs)
 * after adding a container component.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   Run this script after adding a container component to get its child container IDs.
 *
 * @returns {array} Array of container info objects with containerId, childCount, dimensions
 */
(function() {
  const allContainers = document.querySelectorAll('.sha-components-container-inner');
  const containerInfo = [];

  allContainers.forEach((container, i) => {
    const rect = container.getBoundingClientRect();

    // Skip hidden/zero-size containers
    if (rect.width === 0 && rect.height === 0) return;

    // Get containerId from React fiber
    const reactFiberKey = Object.keys(container).find(k => k.startsWith('__reactFiber'));
    let containerId = null;
    let parentComponentType = null;

    if (reactFiberKey) {
      let fiber = container[reactFiberKey];
      let depth = 0;
      while (fiber && depth < 15) {
        if (fiber.memoizedProps?.containerId && !containerId) {
          containerId = fiber.memoizedProps.containerId;
        }
        // Try to find parent component type
        if (fiber.memoizedProps?.componentType) {
          parentComponentType = fiber.memoizedProps.componentType;
        }
        if (containerId) break;
        fiber = fiber.return;
        depth++;
      }
    }

    // Get child components
    const childComponents = container.querySelectorAll(':scope > .sha-component');
    const childTexts = Array.from(childComponents).map(c =>
      c.textContent?.substring(0, 25).trim()
    );

    // Check for drop hint (empty container)
    const hasDropHint = !!container.querySelector('.sha-drop-hint');

    containerInfo.push({
      index: i,
      containerId: containerId,
      isRoot: containerId === 'root',
      childCount: childComponents.length,
      children: childTexts,
      hasDropHint: hasDropHint,
      dimensions: {
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        top: Math.round(rect.top),
        left: Math.round(rect.left)
      }
    });
  });

  return containerInfo;
})();
