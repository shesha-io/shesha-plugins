# button / buttonGroup / buttons (toolbar) / link / subForm — actions and configurable-action shape

All interactive — require `editMode: "editable"`.

> **Action rows use `buttonGroup`, not standalone `button`.** Every form action (Save/Submit,
> Back, Cancel, Edit, Delete, Refresh, Add) belongs inside a single `buttonGroup` as an
> `items[]` entry. A loose top-level `button` in the action row reads as ungrouped/inconsistent
> layout (and a Refresh/Columns button in a table toolbar is the same defect). Reserve the standalone `button` below for a button
> placed inline beside text/content (e.g. a link-style action next to a paragraph) — not the
> form's primary action row. See [buttonGroup](#buttongroup-action-row--preferred) first.

---

## buttonGroup (action row — PREFERRED)

The default container for a form's actions. One `buttonGroup` holds every action as an item;
each item carries its own `actionConfiguration`. `buttonAction` is the shorthand the designer
uses; `actionConfiguration.actionName`/`actionOwner` is what executes.

```json
{
  "id": "<uuid>",
  "type": "buttonGroup",
  "componentName": "formActions",
  "propertyName": "formActions",
  "label": "Form Actions",
  "hideLabel": true,
  "isInline": true,
  "editMode": "editable",
  "parentId": "<parent id>",
  "items": [
    {
      "id": "<uuid>",
      "itemType": "item",
      "itemSubType": "button",
      "sortOrder": 0,
      "name": "btnSave",
      "label": "Save",
      "buttonType": "primary",
      "icon": "SaveOutlined",
      "buttonAction": "submit",
      "actionConfiguration": { "_type": "action-config", "actionName": "Submit", "actionOwner": "shesha.form", "handleSuccess": false, "handleFail": false }
    },
    {
      "id": "<uuid>",
      "itemType": "item",
      "itemSubType": "button",
      "sortOrder": 1,
      "name": "btnBack",
      "label": "Back",
      "buttonType": "default",
      "icon": "ArrowLeftOutlined",
      "buttonAction": "navigate",
      "actionConfiguration": { "_type": "action-config", "actionName": "Navigate", "actionOwner": "shesha.common", "actionArguments": { "navigationType": "url", "url": "/dynamic/<module>/<list-form>" }, "handleSuccess": false, "handleFail": false }
    }
  ]
}
```

Common `buttonAction` → `actionConfiguration` pairings: `submit` → `Submit`/`shesha.form`;
`navigate` → `Navigate`/`shesha.common`; `cancelFormEdit` → `Cancel Edit`/`shesha.form`;
`startFormEdit` → `Start Edit`/`shesha.form`; `dialogue` → `Show Dialog`/`shesha.common`;
`executeScript` → `Execute Script`/`shesha.common`. Exactly one item is `buttonType: "primary"`
(the forward action); Back/Cancel/Delete are `default` or `link`. Copy a real `buttonGroup`
from a seed in `../../assets/examples/` and swap the items.

---

## button (single — inline only)

Use only for a button rendered inline beside text/content, not the action row (the action row
uses [buttonGroup](#buttongroup-action-row--preferred)).

```json
{
  "id": "...",
  "type": "button",
  "label": "Approve",
  "buttonType": "primary",
  "icon": "CheckOutlined",
  "editMode": "editable",
  "actionConfiguration": {
    "actionOwner": "Shesha.Common",
    "actionName": "ExecuteScript",
    "actionArguments": {
      "expression": "try { await actions.callApi.post('/api/services/MyApp.Membership/Application/Approve', { id: data.id }); actions.showMessage.success('Approved'); } catch (err) { actions.showMessage.error(err?.response?.data?.error?.message ?? 'Failed'); }"
    }
  }
}
```

`actionConfiguration` is the standard configurable-action shape. Common `actionName` values:

| actionName | What it does |
|---|---|
| `ExecuteScript` | Run JS (above example) |
| `Navigate` / `NavigateAction` | Go to URL — `actionArguments: { navigationType: "url", url: "..." }` |
| `ShowDialog` / `ShowModal` | Open modal |
| `Submit` (in form) | Submit the parent form |
| `ExecuteEndpoint` | Call a configured endpoint with mapped args |
| `Sign In` (`actionOwner: "shesha.common"`) | Read form's `userNameOrEmailAddress` + `password`, call `TokenAuth/Authenticate`. After success, `actionResponse.url` holds the Shesha-default landing URL. Compose with `onSuccess` for custom routing. |

### onSuccess / onFail composition

```json
"actionConfiguration": {
  "actionOwner": "shesha.common",
  "actionName": "Sign In",
  "handleSuccess": true,
  "handleFail": true,
  "onSuccess": {
    "_type": "action-config",
    "actionOwner": "shesha.common",
    "actionName": "Execute Script",
    "actionArguments": {
      "expression": "const tier = contexts.appContext.selectedTier; if (tier) { application.navigator.navigateToUrl('/dynamic/MyApp.Membership/member-registration'); } else { application.navigator.navigateToUrl(actionResponse?.url || '/dynamic/MyApp.Membership/tier-pricing'); }"
    }
  },
  "onFail": {
    "actionOwner": "shesha.common",
    "actionName": "Execute Script",
    "actionArguments": {
      "expression": "if (actionError?.response) { actions.showMessage.error(actionError.response.data.error.details || actionError.response.data.error.message, 5); }"
    }
  }
}
```

`actionResponse` (in `onSuccess`) and `actionError` (in `onFail`) are the globals exposed in those nested scripts.

---

## buttons (toolbar — plural)

`items` array of `{ id, type: 'button' | 'separator' | 'group', ... }`. Each button-typed item carries its own `actionConfiguration`.

---

## link

Inline anchor link — for "Sign in", "Forgot password", "Create one" style links inside a text row. **Not** a button styled as link; the visual rendering and the action wiring are different.

```json
{
  "id": "...",
  "type": "link",
  "propertyName": "signInLink",
  "componentName": "signInLink",
  "label": "link1",
  "hideLabel": true,
  "content": "Sign in",
  "target": "_self",
  "editMode": "editable",
  "actionConfiguration": {
    "_type": "action-config",
    "actionName": "Navigate",
    "actionOwner": "shesha.common",
    "handleSuccess": false,
    "handleFail": false,
    "actionArguments": {
      "navigationType": "url",
      "url": "/no-auth/MyApp.Membership/auth-login"
    }
  }
}
```

Notes:
- The visible text comes from `content`, **not** `label`. `label` is the designer-side caption (kept hidden via `hideLabel: true`).
- `target` is `"_self"` (default) or `"_blank"`.
- `editMode: "editable"` is required, otherwise the click is swallowed.
- Compose with a parent sub-`container` (`flexDirection: "row"`, `alignItems: "baseline"`) when placing inline alongside `text`.

---

## subForm

Embed another form configuration:

```json
{
  "id": "...",
  "type": "subForm",
  "propertyName": "address",
  "formId": { "module": "Shesha", "name": "address-edit" },
  "modelType": "Shesha.Domain.Address",
  "queryParamsExpression": "{ id: data.address?.id }"
}
```

---

## OTP endpoints (auth-flow specific)

For auth/registration flows that use OTP:

| Endpoint | Body |
|---|---|
| `POST /api/services/app/Otp/SendPin` | `{ sendTo, sendType: 1=phone \| 2=email }` |
| `POST /Otp/VerifyPin` | `{ operationId, pin }` |
| `POST /Otp/ResendPin` | `{ operationId }` |

Stash the returned `operationId` between pages via `contexts.appContext.otpOperationId` (NOT `localStorage` — see [shared-state.md](shared-state.md)).

---

## Implicit submit on entity forms

Most member/details forms have an implicit submit button via `formSettings.onSubmit`. Explicit `button` with `actionName: "Submit"` is for custom toolbars.
