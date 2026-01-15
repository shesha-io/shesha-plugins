/**
 * Add Component (Simple Version)
 *
 * Adds a component using the pre-exposed window.__formDesigner context.
 * Run get-form-designer-context.js first to expose the context.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   1. First run get-form-designer-context.js
 *   2. Then run this script with parameters replaced:
 *      - {componentType}: e.g., 'textField', 'dropdown', 'columns'
 *      - {containerId}: e.g., 'root' or a nested container ID
 *      - {index}: position number (0 = top)
 *
 * @param {string} componentType - Component type identifier
 * @param {string} containerId - Target container ID
 * @param {number} index - Position to insert
 * @returns {object} Result with success status
 */
(function(componentType, containerId, index) {
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
    window.__formDesigner.addComponent({
      containerId: containerId || 'root',
      componentType: componentType,
      index: typeof index === 'number' ? index : 0
    });

    return {
      success: true,
      message: `Added ${componentType} to ${containerId || 'root'} at index ${index || 0}`
    };
  } catch (e) {
    return { success: false, error: e.message };
  }
})('{componentType}', '{containerId}', {index});
