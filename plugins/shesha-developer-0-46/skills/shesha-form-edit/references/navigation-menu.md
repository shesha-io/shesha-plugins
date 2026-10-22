# Adding forms to the app navigation / menu

Read when a task ends with "add it to the menu / navigation / sidebar". Auth + API conventions: [api.md](api.md). Navigate action shape also appears in [components/actions.md](components/actions.md).

---

## Where navigation lives

| Surface | Storage | Edit path |
|---|---|---|
| Sidebar (main) menu | Shesha **setting**: module `Shesha`, name `Shesha.MainMenuSettings` (category `Frontend`, accessor `mainMenu`, dataType `object`) | Settings API (below) or in-app settings UI |
| Header bar | Ordinary form passed to `MainLayout` as `headerFormId` in the frontend layout — edit it like any form via this skill | FormConfiguration API |
| Custom pages | Hard-coded Next.js routes in the portal `src/app/` | Code change |

The sidebar menu is **NOT** a form or configuration item — it is a **client-specific setting** keyed by the front-end application. Reading it without the right app key silently returns an empty default (`{"version":2,"items":[]}`) — the single biggest trap here.

**Find the app key**: grep the portal for `<ShaApplicationProvider applicationKey=` — if absent, the key is the built-in default `default-app`. The frontend transmits it on every request via the `sha-frontend-application` header.

---

## READ the current menu

```
GET /api/services/app/Settings/GetValue?name=Shesha.MainMenuSettings&module=Shesha&appKey=default-app
Authorization: Bearer <token>
```

`appKey` works as a query parameter, or as the `sha-frontend-application: default-app` header — either is sufficient. **Omitting both returns `{"version":2,"items":[]}` even when the real menu has items.** If you get an empty menu on an app that visibly has one, you used the wrong/no app key.

Discovery: `GET /api/services/app/Settings/GetConfigurations` lists all settings (the menu appears as module `Shesha` / name `Shesha.MainMenuSettings` / category `Frontend`).

---

## Value shape (version 2)

```json
{
  "version": 2,
  "items": [ /* ISidebarMenuItem[] */ ]
}
```

Item types: `button` (nav entry), `group` (collapsible section with `childItems`), `divider`.

### Button → dynamic form (the common case)

```json
{
  "id": "<21-char-nanoid>",
  "title": "<Display Title>",
  "tooltip": "",
  "itemType": "button",
  "buttonAction": "navigate",
  "icon": "<AntdIconName>",
  "actionConfiguration": {
    "_type": "action-config",
    "actionOwner": "shesha.common",
    "actionName": "Navigate",
    "actionArguments": {
      "navigationType": "form",
      "formId": { "name": "<form-name>", "module": "<Module>" },
      "queryParameters": []
    },
    "handleFail": false,
    "handleSuccess": false
  }
}
```

- `formId` navigation renders at `/dynamic/<Module>/<form-name>`; the parser treats a 2-segment `/dynamic/<form>` as module-less, 3-segment as `module` + `name`.
- For a plain URL instead: `"actionArguments": { "navigationType": "url", "url": "/settings/theme/", "queryParameters": [] }` (used by built-in items like Theme, Settings, Configuration Studio).
- `queryParameters` is `[{ "key": "...", "value": "..." }]` — e.g. pre-filter a table view.
- `buttonAction: "navigate"` is a legacy mirror field; the in-app editor still writes it alongside `actionConfiguration`. Include it for consistency with editor-written items.
- `icon` is an AntD icon name string (`"UserOutlined"`, `"ToolOutlined"`, `"SettingOutlined"`); omit for no icon.
- `id` is a 21-char nanoid in editor-written data; any unique string renders (unverified — confirm against the target app), but generate a nanoid to be safe.
- `actionConfiguration` is a full configurable-action config — `Show Dialog` etc. also work here (legacy `buttonAction: "dialogue"` maps to actionArguments `{ modalTitle, formId, showModalFooter: true }`).
- Editor-written items may carry `"chosen": false, "selected": false` — drag-and-drop artifacts; harmless, no need to add them.

### Group

```json
{
  "id": "<nanoid>",
  "title": "<Section Title>",
  "itemType": "group",
  "icon": "<AntdIconName>",
  "childItems": [ /* buttons / nested groups */ ]
}
```

Groups nest (verified two levels live). Children go in `childItems`, not `components`.

### Visibility / permissions

- `requiredPermissions: ["<Permission.Name>"]` — item is hidden unless the user holds **any** of the listed permissions (evaluated via `anyOfPermissionsGranted`).
- The frontend also prefetches `POST /api/services/Shesha/FormConfiguration/CheckPermissions` for all `navigationType: "form"` items and hides entries whose target form the user cannot access — a correctly-added item that doesn't show may be a form-permission issue, not a menu bug.
- The item editor exposes a `hidden` switch (jsSetting-capable); a v2 migration renames legacy `hidden` to `visibility` (exact runtime semantics of `visibility` unverified — confirm against the target app; prefer `requiredPermissions` for access control).

---

## ADD an item

There is **no per-item endpoint** — the menu is one setting value. Read-modify-write the whole object:

1. GET the current value (with `appKey`!) — always fresh, never from a stale dump; last write wins.
2. Append/insert your item (top level or into a group's `childItems`).
3. Push:

```
POST /api/services/app/Settings/UpdateValue
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Shesha.MainMenuSettings",
  "module": "Shesha",
  "appKey": "default-app",
  "value": { "version": 2, "items": [ /* full updated array */ ] }
}
```

- Body schema is `UpdateSettingValueInput { name, module, value, appKey }` — `value` is the menu **object**, not a stringified blob (this is what the frontend's own `saveMainMenu` sends). (write path verified against swagger schema + frontend source; not executed live — confirm against the target app)
- `appKey` in the **body** for writes; forgetting it writes the app-agnostic default that your portal never reads — symptom: success response, no visible change.
- Keep `"version": 2` and the current item shape. Older shapes are auto-migrated client-side, but don't rely on it.
4. Re-fetch via GetValue and confirm your item survived — same verify-by-refetch discipline as [verification.md](verification.md).

---

## What it takes to see the change

| Layer | Behavior |
|---|---|
| Browser | Menu is fetched at app mount — a normal page reload shows the new item. No dev-server restart. |
| IndexedDB form cache | Caches **forms**, not the menu setting. If the *target form* renders stale after navigation, clear IndexedDB from a static page (`/favicon.ico` first — in-app `deleteDatabase` blocks). |
| Backend | ABP setting cache is invalidated by UpdateValue (unverified — confirm against the target app; if a stale value persists, restart the backend). |

Before adding the item, verify the target actually loads at `/dynamic/<Module>/<form-name>` — a menu entry to a broken form just relocates the failure. Table views are safe to deep-link; `*-details` forms need an `id` and have page-context caveats (see [verification.md](verification.md) / detail-page-pattern.md).

---

## Manual / in-app alternative

Settings UI at `/shesha/settings` → module **Shesha** → category **Frontend** → **Main Menu Settings** renders the dedicated `mainMenuEditor` component (drag-and-drop, item settings with Item Type dropdown `Button | Divider`, Security tab for `requiredPermissions`). Use it when a human will maintain the menu; use the API when scripting.

---

## Fallback — if the API path cannot be verified on the target app

1. Confirm the setting exists: `GET /api/services/app/Settings/GetConfigurations` and search for `MainMenuSettings`. Older/forked Shesha versions stored the sidebar as a configurable-component configuration item instead of a setting (unverified — confirm against the target app); if no menu setting exists, inspect the portal bundle for the setting name it reads (`grep -oE '.{100}MainMenuSettings.{200}' node_modules/@shesha-io/reactjs/dist/index.js`).
2. If `GetValue` returns empty for every app key you try, list registered front-end apps / check the portal's `ShaApplicationProvider` props before assuming the menu is empty.
3. If writes 401: the Settings service may be permission-hardened — child endpoints inherit the parent service's restriction; check permissioned-objects.
4. If still blocked, route the task to the `shesha-settings` skill (settings CRUD is its domain) or hand the user the in-app path above.

---

### Worked example (project-specific)

RequirementsStudio, verified live 2026-06-11 against `http://localhost:21021`:

- App key: `default-app` (RS `adminportal/src/app/app-provider.tsx` sets no `applicationKey`). Without the header/param, GetValue returned `{"version":2,"items":[]}`; with it, the real 3-group menu.
- Live structure: groups `Administration` (icon `ToolOutlined`), `Configurations` (`SettingOutlined`), `Requirements Studio` (no icon) — the last holding 17 buttons, all `navigationType: "form"` pointing at module `Shesha.RequirementsStudio` table forms (`base-project-table`, `module-definition-table`, `release-definition-table`, …), all icon-less.
- A new RS table entry is the button JSON above with `"formId": { "name": "view-definition-table", "module": "Shesha.RequirementsStudio" }`, appended to the `Requirements Studio` group's `childItems`.
- RS's header (`MainLayout headerFormId={{module: "Shesha.RequirementsStudio", name: "header"}}`) contains only `logoLink`/`logoImage`, `headerAppControl`, and `profileDropdown` — no nav items; all RS navigation lives in the sidebar setting.
