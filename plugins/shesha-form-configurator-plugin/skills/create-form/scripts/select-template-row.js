/**
 * Select Template Row
 *
 * Clicks on a template row in the Create Form wizard when the normal
 * Playwright click is intercepted by overlapping elements (e.g., textarea).
 *
 * Usage via mcp__playwright__playwright_evaluate:
 *   Replace {templateType} with: "Table View", "Create View", or "Details View"
 *
 * @param {string} templateType - The template to select
 * @returns {object} Result indicating success or failure
 */
(function(templateType) {
  const templateDescriptions = {
    'Table View': 'list and search',
    'Create View': 'Create View',
    'Details View': 'display and edit'
  };

  const description = templateDescriptions[templateType];
  if (!description) {
    return { success: false, error: `Unknown template type: ${templateType}` };
  }

  const rows = Array.from(document.querySelectorAll('.tr-body'));
  const targetRow = rows.find(row =>
    row.textContent.includes(templateType) &&
    row.textContent.toLowerCase().includes(description.toLowerCase())
  );

  if (!targetRow) {
    return { success: false, error: `Template row "${templateType}" not found` };
  }

  targetRow.scrollIntoView({ behavior: 'instant', block: 'center' });
  targetRow.click();

  return { success: true, templateType: templateType };
})('{templateType}')
