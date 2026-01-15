/**
 * Add Component to Form Designer Canvas
 *
 * This script adds a component to the Form Designer by accessing the
 * formDesigner React context directly, bypassing SortableJS drag-and-drop.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   Replace {componentType}, {containerId}, and {index} with actual values.
 *
 * @param {string} componentType - Component type (e.g., 'textField', 'dropdown')
 * @param {string} containerId - Container ID ('root' for main canvas)
 * @param {number} index - Position to insert (0 = top)
 */
(function(componentType, containerId, index) {
  // Find the main canvas container (typically index 4)
  const containers = document.querySelectorAll('.sha-components-container-inner');
  let canvas = null;

  // Find the container with child components or use index 4 as default
  for (let i = 0; i < containers.length; i++) {
    const sortableKey = Object.keys(containers[i]).find(k => k.startsWith('Sortable'));
    if (sortableKey && containers[i].getBoundingClientRect().width > 0) {
      canvas = containers[i];
      break;
    }
  }

  if (!canvas) {
    canvas = containers[4]; // Fallback to index 4
  }

  if (!canvas) {
    throw new Error('Could not find canvas container');
  }

  // Get React fiber to access context
  const reactFiberKey = Object.keys(canvas).find(k => k.startsWith('__reactFiber'));
  if (!reactFiberKey) {
    throw new Error('Could not find React fiber on canvas');
  }

  const fiber = canvas[reactFiberKey];

  // Navigate fiber tree to find formDesigner context
  function findFormDesignerContext(fiber) {
    let current = fiber;
    while (current) {
      // Check memoizedProps for context provider value
      if (current.memoizedProps?.value?.addComponent) {
        return current.memoizedProps.value;
      }
      // Check context dependencies
      if (current.dependencies?.firstContext) {
        let ctx = current.dependencies.firstContext;
        while (ctx) {
          if (ctx.context?._currentValue?.addComponent) {
            return ctx.context._currentValue;
          }
          ctx = ctx.next;
        }
      }
      current = current.return;
    }
    return null;
  }

  const formDesigner = findFormDesignerContext(fiber);

  if (!formDesigner) {
    throw new Error('Could not find formDesigner context');
  }

  if (typeof formDesigner.addComponent !== 'function') {
    throw new Error('formDesigner.addComponent is not a function');
  }

  // Add the component
  formDesigner.addComponent({
    containerId: containerId || 'root',
    componentType: componentType,
    index: typeof index === 'number' ? index : 0
  });

  return `Added ${componentType} to ${containerId || 'root'} at index ${index || 0}`;
})('{componentType}', '{containerId}', {index});
