/**
 * Delete Component
 *
 * Deletes a component from the Form Designer canvas by its ID.
 * Run get-form-designer-context.js first to expose the context.
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   1. First run get-form-designer-context.js
 *   2. Get component IDs using get-container-ids.js or browser inspection
 *   3. Run this script with {componentId} replaced
 *
 * @param {string} componentId - The component ID to delete
 * @returns {object} Result with success status
 */
(function(componentId) {
  if (!window.__formDesigner) {
    return {
      success: false,
      error: 'formDesigner not found. Run get-form-designer-context.js first.'
    };
  }

  if (!componentId) {
    return { success: false, error: 'componentId is required' };
  }

  try {
    window.__formDesigner.deleteComponent({ componentId: componentId });
    return { success: true, message: `Deleted component ${componentId}` };
  } catch (e) {
    return { success: false, error: e.message };
  }
})('{componentId}');
