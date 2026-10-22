# Embedded scripts - context, async rules, current user (0.46)

Read when authoring any embedded JS (`onChangeCustom`, `onClickCustom`, `customVisibility`, `customEnabled`, `onBeforeDataLoad`, `actionConfiguration.actionArguments.expression`, code-mode `{_mode:'code', _code}` settings, etc.).

0.46 reworked the scripting API: scripts are written against a small set of typed objects. **Write new scripts with the new names.** The
legacy names still resolve at runtime (the context is a `with(context)` proxy built by `wrapConstantsData`,
`shesha-reactjs/src/providers/form/utils.ts:296-368`) but they are untyped, they are not suggested by the editor, and they may go away - so
do not introduce them, and convert them only when you are already editing the script (a mechanical bulk rename earns nothing at runtime).

---

## Lifecycle timing (`formSettings.*` hooks)

| Hook | Fires | Form context (`form`) | Use for |
|---|---|---|---|
| `onBeforeDataLoad` | before data fetch - **BEFORE the form context exists** | **undefined** | context-free prep only |
| `onDataLoaded` | after data load - fires even for create forms (data is empty) | available | `form.formArguments` reads, `form.setFieldsValue(...)`, `form.setFormData(...)` |
| `onPrepareSubmitData` | at submit, before the POST | `data` + `form` available; **must `return` the payload object**; async-capable | FK injection - see [add-dialogs.md](add-dialogs.md) |

Symptoms of form-context access in `onBeforeDataLoad`: `form is not defined` / `Cannot read properties of undefined`. Move the script to `onDataLoaded`.

- The groups index (`../../../clean-form-config/assets/groups/base.json` -> `_formSettings.scripts`) lists form members in the `onBeforeDataLoad` context - runtime disagrees; trust runtime.
- Console errors from `onBeforeDataLoad` scripts are often pre-existing - verify they predate your change before treating them as regressions.
- Seeding values in *any* hook does not make them submit - only real components (`_formFields`) serialize; required contextual FKs need a component **and** `onPrepareSubmitData` injection. See [add-dialogs.md](add-dialogs.md).

---

## Script context - new names first

| Use (0.46) | What it is | Legacy name (still resolves, do not write) |
|---|---|---|
| `data` | current form values object, keyed by `propertyName` | `data` (unchanged), `formData` |
| `form` | form API: `form.data`, `form.setFormData({values, mergeValues})`, `form.formMode` (`'designer' \| 'edit' \| 'readonly'`), `form.formArguments`, `form.initialValues`, `form.parentFormValues` | `formData`, `setFormData`, `formMode` |
| `user` | current user: `isLoggedIn`, `id`, `userName`, `firstName`, `lastName`, `personId`, `hasPermissionAsync(name)`, `hasRoleAsync(name)`, `getUserSettingValueAsync(...)`; **`{ isLoggedIn:false }` when anonymous** | `application.user` |
| `actions.callApi` | HTTP client (`get/post/put/patch/delete/request`) | `http` |
| `actions.showMessage` | antd message (`success/error/warning/info/loading`) | `message` |
| `actions.showDialog(args)` / `actions.showConfirmation(args)` | open a form in a modal / confirm modal (both return promises) | `modal.showForm` / `modal.confirm` |
| `actions.navigateToUrl(url, query?)` / `actions.navigateToForm(formId, args?)` | navigation | `application.navigator.*` |
| `utils.moment`, `utils.evaluateString`, `utils.saveAs(data, name)`, `utils.getFormUrl`, `utils.prepareUrl`, `utils.modal` | helpers | `moment`, `evaluateString`, `fileSaver`, `application.navigator.*` |
| `page.state` | page-scoped shared state (read and write properties); `page.location` = `window.location` | `pageContext` |
| `storage` | web-storage data context (use instead of raw `localStorage`) | - |
| component APIs (typed in `publicJsApis/apis/components.d.ts`, e.g. a table's `selectedRow`) | per-component API registered by the component at runtime; **verify the accessor on the running app** before relying on it | bare `selectedRow` (still resolves) |
| `contexts.<name>` | other data contexts by name; `contexts.appContext` is app-wide state | unchanged |
| `query` | query-string parameters | unchanged |
| `application` | still present (`application.settings`, `application.navigator`) | unchanged |
| `event`, `value` | in event handlers: the DOM/antd event; the new value in onChange-style handlers | unchanged |

Mapping to apply **when you are already editing a script** (all verified as the same object, `script-api-renames` from the
0.46 source): `pageContext` -> `page.state`; `http.get(` -> `actions.callApi.get(`; `message.error(` -> `actions.showMessage.error(`;
`moment(` -> `utils.moment(`; `modal.showForm(` -> `actions.showDialog(`; `modal.confirm(` -> `actions.showConfirmation(`;
`fileSaver(` -> `utils.saveAs(`; `application.user.x` -> `user.x`; `formData` -> `form.data`; `setFormData(p)` -> `form.setFormData(p)`;
`formMode` -> `form.formMode`. **Skip any rewrite where the script declares its own binding with that name** - a local `const message`
in a `catch`, or a `new FormData()` assigned to `formData`. `globalState`/`setGlobalState` and bare `selectedRow` have no mechanical
replacement - see below.

**Forbidden / avoid** (house rule): `globalState`, `setGlobalState` (use `contexts.appContext` or `page.state`, see
[shared-state.md](shared-state.md)); `window.localStorage` / `sessionStorage` (XSS-readable; use `storage` if you must persist).

**Do not use `console.log`** - `clean-form-config` strips them; the user runs a hardened build.

> Note the user field names: the typed `user` exposes `firstName` / `lastName` (and `userName`, `personId`, `id`). Older recipes used
> `application.user.name` / `.surname` / `.emailAddress` / `.mobileNumber`; those depend on what the app's `application.user` still
> carries - verify on the running app before relying on them (`JSON.stringify(user)` once in a throwaway script, then remove it).

---

## Current user - use `user`, not an API call

```js
const personId = user?.personId;
const fullName = `${user?.firstName ?? ''} ${user?.lastName ?? ''}`.trim();
const canApprove = await user?.hasPermissionAsync?.('Pages.Approve');
```

`user` is populated synchronously for an authenticated session; when anonymous it is `{ isLoggedIn: false }`, so check
`user?.isLoggedIn` rather than truthiness, and always optional-chain.

**Don't** make an extra `Session/GetCurrentLoginInformations` round-trip for fields `user` already has. Exception: session id,
tenant info, or fields `user` does not carry.

---

## Render-time scripts must tolerate missing data

Scripts in code-mode settings (`visible`, `editMode`, `style`, `desktop.*.color`, `content`, ...) run on **every render, including
before `data` is loaded**. A throw is swallowed and a throwing visibility is treated as **visible**. Use optional chaining on every
hop and give a default:

```js
// BAD  - throws before data loads, so the component shows
return data.account.status === 'Active';
return data?.account.status === 'Active';
// GOOD
return data?.account?.status === 'Active';
```

Never use `?.` on an **assignment target** (`data?.a = 1` is a SyntaxError); guard with `if (data) { ... }`. Arrays from `data`/`value`
are mutated in place by the form - copy before keeping them (`(data?.items ?? []).slice()`). Full catalog:
[../render-hazards-046.md](../render-hazards-046.md) H10, H11.

---

## Async + try/catch (mandatory for API calls)

```js
try {
  const response = await actions.callApi.get('/api/services/<module>/Member/GetTier', { params: { id: data?.id } });
  form.setFormData({ values: { tier: response.data.result }, mergeValues: true });
} catch (err) {
  actions.showMessage.error(err?.response?.data?.error?.message ?? 'Failed to load tier');
}
```

For event-handler-style properties (`onChangeCustom`, `onClickCustom`) Shesha generates the function - `await` works directly in the
script body. **Banned:** `.then(...).catch(...)` chains (convert to `async`/`await` + `try/catch`); bare `await` outside an async
wrapper in arbitrary helpers; an un-awaited, un-caught promise. `clean-form-config` auto-fixes the unambiguous cases - invoke it after
any script edit.

---

## Expression Editor (replaces key/value variable lists)

0.46 replaced the key/value "variable" lists (request params, dialog `formArguments`, filters) with the **Expression Editor**
(`expressionEditor` component, `designer-components/expressionEditor`): one script/expression that produces the whole object instead of
rows of `{key, value}`. The stored shape differs per component, so **read the property's current shape from
`assets/components-kb/<type>.json` (`ownProps`) or from a live form that already renders** before authoring; keep a legacy list only
where the KB still lists it, and never invent the expression shape. `Property Name` (`propertyName`) is a plain identifier/path in 0.46 and **no longer accepts JavaScript**; computed bindings go in
the component's code-mode settings, not in `propertyName`.

---

## Multiline JS in JSON and ids

Escape newlines as `\n` inside JSON strings; build the tree in Node and `JSON.stringify` it - never hand-edit deeply nested
escaped strings. Scripts that reference component ids break when ids are regenerated: prefer `data.<propertyName>` over ids. Syntax-gate every edited script before pushing ([../api.md](../api.md) section 9).
