# Troubleshooting Guide

Common issues and solutions when using the create-form skill.

## Authentication Issues

### Login fails or times out

**Symptoms:**
- Button click doesn't respond
- Page stays on login screen

**Solutions:**
1. Verify Shesha is running at `http://localhost:3000`
2. Check credentials are correct (default: admin/123qwe)
3. Increase wait time after clicking sign in to 4-5 seconds
4. Clear browser state and retry

### Session expired

**Symptoms:**
- Redirected to login after navigation

**Solutions:**
1. Re-run the full workflow from login
2. Check for any authentication token issues in console

## Form Creation Issues

### Create button is disabled

**Symptoms:**
- Cannot click Create button
- Button appears grayed out

**Solutions:**
1. Ensure Name field is filled (it's required)
2. Verify Module is selected
3. Check for validation errors in the form

### Fields not updating / Form submits empty (only moduleId sent)

**Symptoms:**
- Label or Description appear empty after creation
- React state not reflecting input values
- API payload only contains `moduleId`, missing `name`, `label`, `description`
- Fields appear filled visually but submit as empty

**Root Cause:**
JavaScript-based filling (`element.value = x` + `dispatchEvent`) only updates the DOM visually. React's synthetic event system doesn't recognize native DOM events, so component state remains empty. When the form submits, React reads from its internal state (not the DOM), sending empty values.

**Solution - Use native Playwright fill method:**
```
mcp__playwright__playwright_fill
  selector: .ant-modal-body input.ant-input >> nth=0
  value: your-form-name

mcp__playwright__playwright_fill
  selector: .ant-modal-body input.ant-input >> nth=1
  value: Your Form Label

mcp__playwright__playwright_fill
  selector: .ant-modal-body textarea
  value: Your description here
```

Native Playwright `fill` simulates actual keyboard input, which React's event delegation properly captures and updates internal state.

**DO NOT use JavaScript evaluation:**
- `playwright_evaluate` with `element.value = x`
- `dispatchEvent(new Event('input'))` or `dispatchEvent(new Event('change'))`

### Modal Create button click doesn't work / Timeout

**Symptoms:**
- Clicking Create button has no effect
- Timeout errors on button click
- Selector `.ant-modal-footer button.ant-btn-primary` times out

**Root Cause:**
The Create button is NOT in `.ant-modal-footer`. It's inside the modal body (within a Shesha dynamic form). The footer selector will never find it.

**Solution - Use correct selector:**
```
mcp__playwright__playwright_click
  selector: .ant-modal button.ant-btn-primary
```

**Additional checks:**
1. Verify modal is fully loaded before clicking (wait 2 seconds)
2. Check if another modal or overlay is blocking
3. Ensure form validation passed (Name field is required)

## Navigation Issues

### 404 error on forms page

**Symptoms:**
- Page not found when navigating to forms

**Solutions:**
1. Use correct URL: `http://localhost:3000/dynamic/shesha/forms`
2. Not: `/shesha/forms` or `/shesha/forms-designer/forms`

### Sidebar menu not visible

**Symptoms:**
- Cannot find Configurations menu
- Sidebar appears collapsed

**Solutions:**
1. Use direct URL navigation (recommended)
2. Or click sidebar toggle: `.ant-layout-sider-trigger`

### Page loads but content missing

**Symptoms:**
- Empty table or loading spinner

**Solutions:**
1. Increase wait time to 4-5 seconds
2. Check browser console for errors
3. Verify API is responding

## Module Selection Issues

### Module dropdown doesn't open

**Symptoms:**
- Click on dropdown has no effect

**Solutions:**
1. Wait for dialog to fully render (2 seconds)
2. Use exact selector: `.ant-modal .ant-select-selector`

### Module option not found

**Symptoms:**
- "Shesha.AiBoooking" not in dropdown

**Solutions:**
1. Verify spelling: `Shesha.AiBoooking` (three O's)
2. Check available modules - may be `ShaCompanyName.ShaProjectName`
3. Use title selector: `.ant-select-item[title="Shesha.AiBoooking"]`

## Verification Issues

### Form not in list after creation

**Symptoms:**
- Search returns no results
- Form count didn't increase

**Solutions:**
1. Form Designer opens automatically - check if you're in designer
2. Navigate back to forms list: `http://localhost:3000/dynamic/shesha/forms`
3. Refresh the page
4. Search by exact name (case-sensitive)

### Form Designer doesn't load

**Symptoms:**
- Blank page after creation
- Spinner doesn't stop

**Solutions:**
1. Wait longer (5+ seconds)
2. Check browser console for errors
3. Manually navigate to forms list and open the form

## General Tips

1. **Always take screenshots** at each step for debugging
2. **Check browser console** using `mcp__playwright__playwright_console_logs`
3. **Increase timeouts** if on slower connections
4. **Use headless: false** to visually verify actions
5. **Clear browser state** between retry attempts
