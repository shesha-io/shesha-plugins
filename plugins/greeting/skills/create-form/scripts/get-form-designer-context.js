/**
 * Get Form Designer Context
 *
 * Finds and exposes the formDesigner React context on window.__formDesigner
 * for subsequent operations. This is a helper that should be run first
 * before using add-component.js or other form designer scripts.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   Run this script first, then use window.__formDesigner in subsequent calls.
 *
 * @returns {object} Result with available methods and success status
 */
(function() {
  // Find all canvas containers
  const containers = document.querySelectorAll('.sha-components-container-inner');
  let canvas = null;

  // Find the main canvas (has SortableJS and visible)
  for (let i = 0; i < containers.length; i++) {
    const rect = containers[i].getBoundingClientRect();
    const sortableKey = Object.keys(containers[i]).find(k => k.startsWith('Sortable'));
    if (sortableKey && rect.width > 0 && rect.height > 0) {
      canvas = containers[i];
      break;
    }
  }

  if (!canvas) {
    // Fallback to index 4 (typical main canvas position)
    canvas = containers[4];
  }

  if (!canvas) {
    return { success: false, error: 'Could not find canvas container' };
  }

  // Get React fiber
  const reactFiberKey = Object.keys(canvas).find(k => k.startsWith('__reactFiber'));
  if (!reactFiberKey) {
    return { success: false, error: 'Could not find React fiber on canvas' };
  }

  const fiber = canvas[reactFiberKey];

  // Navigate fiber tree to find formDesigner context
  function findFormDesignerContext(fiber) {
    let current = fiber;
    while (current) {
      if (current.memoizedProps?.value?.addComponent) {
        return current.memoizedProps.value;
      }
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
    return { success: false, error: 'Could not find formDesigner context' };
  }

  // Expose on window for subsequent calls
  window.__formDesigner = formDesigner;

  // Return available methods
  const methods = Object.keys(formDesigner).filter(k => typeof formDesigner[k] === 'function');

  return {
    success: true,
    availableMethods: methods,
    message: 'formDesigner context exposed on window.__formDesigner'
  };
})();
