/**
 * Parallel CRUD Form Creator for Shesha
 *
 * This script creates Table, Details, and Create views for entities in parallel
 * using multiple browser tabs for faster execution.
 *
 * Usage: node create-crud-forms-parallel.js <EntityName> <ModelType>
 */

const { chromium } = require('playwright');

// Configuration
const CONFIG = {
  baseUrl: 'http://localhost:3000',
  credentials: {
    username: 'admin',
    password: '123qwe'
  },
  module: 'Shesha.AiBoooking',
  timeout: 60000
};

// Form templates configuration
const TEMPLATES = {
  table: {
    label: 'Table View',
    suffix: '-table',
    labelSuffix: ' Table',
    descriptionTemplate: (entity) => `Table view for listing and searching ${entity} records`
  },
  details: {
    label: 'Details View',
    suffix: '-details',
    labelSuffix: ' Details',
    descriptionTemplate: (entity) => `Details view for displaying and editing ${entity} information`
  },
  create: {
    label: 'Create View',
    suffix: '-create',
    labelSuffix: ' Create',
    descriptionTemplate: (entity) => `Create view for adding new ${entity} records`
  }
};

/**
 * Wait helper function
 */
async function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Login to Shesha (handles already logged in state)
 */
async function login(page) {
  console.log('  → Checking authentication...');
  await page.goto(CONFIG.baseUrl, { waitUntil: 'load', timeout: CONFIG.timeout });

  await wait(2000);

  // Check if already logged in by looking for the user menu or dashboard elements
  const isLoggedIn = await page.locator('text=System Administrator').isVisible().catch(() => false);

  if (isLoggedIn) {
    console.log('  ✓ Already logged in');
    return;
  }

  // Not logged in, proceed with login
  console.log('  → Logging in...');

  // Wait for login page to load
  const usernameField = await page.waitForSelector('input[placeholder="Username"]', { timeout: 30000 });

  if (usernameField) {
    // Fill credentials
    await page.fill('input[placeholder="Username"]', CONFIG.credentials.username);
    await page.fill('input[placeholder="Password"]', CONFIG.credentials.password);

    // Click login button
    await page.click('button.ant-btn-primary');

    // Wait for redirect to home page
    await page.waitForLoadState('networkidle');
    await wait(2000);

    console.log('  ✓ Logged in successfully');
  }
}

/**
 * Navigate to forms page
 */
async function navigateToForms(page) {
  console.log('  → Navigating to forms page...');
  await page.goto(`${CONFIG.baseUrl}/dynamic/shesha/forms`, {
    waitUntil: 'load',
    timeout: CONFIG.timeout
  });
  await wait(2000);
  console.log('  ✓ On forms page');
}

/**
 * Create a single form using template
 */
async function createForm(page, entityName, modelType, formType, tabName) {
  const template = TEMPLATES[formType];
  const formName = entityName.toLowerCase() + template.suffix;
  const formLabel = entityName + template.labelSuffix;
  const description = template.descriptionTemplate(entityName);

  console.log(`\n[${tabName}] Creating ${formType} form: ${formName}`);

  try {
    // Navigate to forms page
    await navigateToForms(page);

    // Click "Create New"
    console.log(`[${tabName}]   → Clicking Create New...`);
    await page.click('text=Create New');
    await wait(1000);

    // Enable template
    console.log(`[${tabName}]   → Enabling template...`);
    await page.click('.ant-modal input[type="checkbox"]');
    await wait(1000);

    // Select template type - use more specific selector to avoid existing forms in the list
    console.log(`[${tabName}]   → Selecting ${template.label}...`);
    // Click on the template row within the modal - find by exact label match
    const templateRow = page.locator('.ant-modal').getByRole('row').filter({ has: page.getByText(template.label, { exact: true }) });
    await templateRow.click();
    await wait(500);

    // Click Next
    console.log(`[${tabName}]   → Going to configurations...`);
    await page.click('button:has-text("Next")');
    await wait(1000);

    // Select module
    console.log(`[${tabName}]   → Selecting module...`);
    const moduleSelector = '.ant-modal .ant-select-selector >> nth=0';
    await page.click(moduleSelector);
    await wait(500);
    await page.click(`.ant-select-item[title="${CONFIG.module}"]`);
    await wait(500);

    // Fill form name
    console.log(`[${tabName}]   → Filling form name: ${formName}`);
    await page.fill('.ant-modal-body input.ant-input >> nth=0', formName);
    await wait(300);

    // Fill form label
    console.log(`[${tabName}]   → Filling form label: ${formLabel}`);
    await page.fill('.ant-modal-body input.ant-input >> nth=1', formLabel);
    await wait(300);

    // Fill description
    console.log(`[${tabName}]   → Filling description...`);
    await page.fill('.ant-modal-body textarea', description);
    await wait(300);

    // Select model type
    console.log(`[${tabName}]   → Selecting model type: ${modelType}`);
    const modelTypeSelector = '.ant-modal .ant-select-selector >> nth=1';
    await page.click(modelTypeSelector);
    await wait(500);

    // Type to search for model
    const searchTerm = modelType.split('.').pop().toLowerCase();
    for (const char of searchTerm) {
      await page.keyboard.press(char);
      await wait(50);
    }
    await wait(1000);

    // Click the model type
    await page.click(`.ant-select-item[title="${modelType}"]`);
    await wait(500);

    // Click Create button
    console.log(`[${tabName}]   → Creating form...`);
    await page.click('.ant-modal button.ant-btn-primary');

    // Wait for success message or form designer to load
    await wait(3000);

    console.log(`[${tabName}]   ✓ Form created successfully: ${formName}`);

    return { success: true, formName, formType };

  } catch (error) {
    console.error(`[${tabName}]   ✗ Error creating form:`, error.message);
    return { success: false, formName, formType, error: error.message };
  }
}

/**
 * Create all CRUD forms for an entity in parallel
 */
async function createCRUDFormsParallel(entityName, modelType) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Creating CRUD forms for ${entityName}`);
  console.log(`Model Type: ${modelType}`);
  console.log(`${'='.repeat(60)}\n`);

  const browser = await chromium.launch({
    headless: false,
    slowMo: 100 // Slight delay to make actions visible
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 }
    });

    // Create three pages (tabs)
    console.log('Opening browser tabs...');
    const [page1, page2, page3] = await Promise.all([
      context.newPage(),
      context.newPage(),
      context.newPage()
    ]);

    console.log('✓ Three tabs opened\n');

    // Login to all tabs in parallel (now handles already-logged-in state)
    console.log('Checking authentication on all tabs...');
    await Promise.all([
      login(page1),
      login(page2),
      login(page3)
    ]);
    console.log('✓ All tabs authenticated\n');

    // Create forms in parallel
    console.log('Creating forms in parallel...');
    const startTime = Date.now();

    const results = await Promise.all([
      createForm(page1, entityName, modelType, 'table', 'Tab 1'),
      createForm(page2, entityName, modelType, 'details', 'Tab 2'),
      createForm(page3, entityName, modelType, 'create', 'Tab 3')
    ]);

    const endTime = Date.now();
    const duration = ((endTime - startTime) / 1000).toFixed(2);

    // Print summary
    console.log(`\n${'='.repeat(60)}`);
    console.log('SUMMARY');
    console.log(`${'='.repeat(60)}`);
    console.log(`Total time: ${duration} seconds\n`);

    const successful = results.filter(r => r.success);
    const failed = results.filter(r => !r.success);

    if (successful.length > 0) {
      console.log('✓ Successfully created:');
      successful.forEach(r => console.log(`  - ${r.formName} (${r.formType})`));
    }

    if (failed.length > 0) {
      console.log('\n✗ Failed to create:');
      failed.forEach(r => console.log(`  - ${r.formName} (${r.formType}): ${r.error}`));
    }

    console.log(`\n${'='.repeat(60)}\n`);

    // Keep browser open for 5 seconds to see results
    console.log('Keeping browser open for 5 seconds...');
    await wait(5000);

  } finally {
    await browser.close();
    console.log('Browser closed');
  }
}

/**
 * Main execution
 */
async function main() {
  const args = process.argv.slice(2);

  // Default entity if none specified
  const entityName = args[0] || 'OrganisationBase';
  const modelType = args[1] || `Shesha.Domain.${entityName}`;

  try {
    await createCRUDFormsParallel(entityName, modelType);
    console.log('\n✓ Script completed successfully');
    process.exit(0);
  } catch (error) {
    console.error('\n✗ Script failed:', error);
    process.exit(1);
  }
}

// Run the script
if (require.main === module) {
  main();
}

module.exports = { createCRUDFormsParallel, createForm };
