# Render hazards on Shesha 0.46

Things that look fine in stored markup and break (or silently change) when the 0.46 portal renders it.
Each hazard: **symptom -> cause (source) -> detection predicate over stored markup -> fix**.

Evidence tags: **[proven]** = reproduced on a running 0.46 app (2026-10-01); **[source]** = read from
`release-0.46.0` source only. Paths are relative to `shesha-reactjs/src/` (frontend) or `shesha-core/src/` (backend).
Run the detectors with `node scripts/scan-hazards.mjs <markup.json | dir>` (see [Scanner](#scanner)).

Fleet-wide fixes for these hazards are packaged as rules in `shesha-developer:shesha-upgrade-reconciler` (`references/pack-0.46.md`); a hazard found on many forms belongs there rather than in a per-form edit.

Quick index

| # | Hazard | Tag |
|---|---|---|
| H1 | Form API moved: `GetByName` 404, `UpdateMarkup` overwrites `modelType`, no Draft/Live | proven |
| H2 | Admin portal serves a stale form from IndexedDB | proven |
| H3 | `htmlRender` drops a leading `<style>` (sanitiser) | proven |
| H4 | `htmlRender` shows "Please, provide some content" | proven |
| H5 | `htmlRender` with `contentType: 'html'` ignores `renderer` | proven |
| H6 | Hidden components are not mounted (hidden CSS carriers never inject) | proven |
| H7 | antd 6 tabs DOM: old `.ant-tabs-content-holder` selectors match nothing | proven |
| H8 | `text` v7 reads `desktop.stylingBoxJson` / `desktop.font.size`, not the legacy keys | proven |
| H9 | Migrations inject style defaults; hidden components keep wrapper size (phantom gaps) | proven |
| H10 | Render-time script throws before data loads; a throwing visibility means VISIBLE | proven |
| H11 | Arrays read from `data`/`value` are mutated in place by the form | proven |
| H12 | `ReferenceList/GetItems` is gone (404) | proven |
| H13 | `refListStatus` inside a `subForm` throws "Component with id ... is not found" | proven (framework bug) |
| H14 | `subForm` with `labelCol: 0` hides the labels of hosted fields | proven (core issue) |
| H15 | `editMode` returning a boolean `false` now means DISABLED, not read-only | source |
| H16 | `columns` blocks lose gutter compensation (inset by `gutter/2`) | source |
| H17 | `datatable` migrations force zebra rows / hover / single selection over stored values | source |
| H18 | `text` v7 content: `{{` becomes `{{data.` on load | source |
| H19 | `text` ignores `hidden`/`visible` in live mode | proven (framework bug) |
| H20 | Multi-line field labels overlap the next row (label height fixed at 32px) | proven (antd 6) |
| H21 | Every field row is 35px, not 32px; a positive field margin cannot shrink the gap | proven |
| H22 | A hidden or empty `container` still takes 32px | proven |
| H23 | A negative right margin on `columns` adds horizontal scrollbars | proven |
| H24 | `tabs` lose the gap between the tab bar and the first field | proven |
| H25 | A `text` used as a label paints the primary colour / the wrong font | proven |
| H26 | Buttons with an empty code label render as blank 32px buttons | proven |
| H27 | A designer tab opened before an API write saves the old markup over it | proven (tooling) |
| H28 | A value the host form shows disappears after a subform loads (status tag shows, then goes blank) | proven |
| H29 | Partial device blocks make the style migration ignore top-level styles and defaults (no row gap, collapsed boxes) | proven |
| H30 | Collapsible panel headers taller with 8px padding all round | proven |
| H31 | Reviving an old CSS carrier activates CSS written for the old DOM, which can break the page | proven |
| H32 | Lookups naming renamed framework entity types show blank values | proven |
| H33 | A status tag with no value draws an empty grey chip | proven |
| H34 | An optional filter item that does not resolve is sent as `null`, so the table loads nothing (400) | proven |
| H35 | Custom dialog footer buttons ignore their `editMode` / visibility scripts | proven |
| H36 | A `[default]` column on a URL-sourced table shows a reference-list value as the raw number | proven |
| H37 | Searchable reference-list dropdowns filter by option value, not label | proven (framework) |
| H38 | An entity autocomplete with no stored sort lists options in database order | proven |
| H39 | `delete data.x` in an action script does nothing, so `...data` still posts the helper fields | proven |
| H40 | A URL-sourced table fetches once with an empty id before the record loads and never again | proven |
| H41 | `globalState.<tableContext>` no longer exists; refresh/read tables through `contexts.<name>` | proven |
| H42 | Saves rejected: "Property '<x>' is readonly" (calculated properties posted back) | proven |
| H43 | A leftover required filter on a URL-sourced table keeps it from ever fetching | proven |
| H44 | `onAfterDataLoad` on a page form receives only the id as `data`; the record is `form.data` | proven |
| H45 | A subform names a framework form 0.46 no longer ships (empty box, "form not found") | proven |
| H46 | Subform filter expressions cannot see the host record (`data`, `pageContext`, `query` unresolved) | proven |
| H47 | A stale `parentId` makes the designer re-nest a component into its old parent on the next save | proven |
| H48 | Flex-item sizing comes from the device block's `dimensions`, not from `style` | proven |
| H49 | Scripts inside a sub-form (or a dialog-opened form) run against the HOST page form: `data` is empty, record ids resolve to `undefined` | proven |
| H50 | A Url data context drops the endpoint's query string and rebuilds filter, sorting and properties (data leak) | proven |
| H51 | Which id expression resolves inside a nested sub-form's `permanentFilter` | proven |
| H52 | Hidden data-holder fields are not mounted; a list row sees only what is mounted directly under it | proven |
| H53 | A datalist makes two requests; the first load after a push can look right and later loads wrong | proven (symptom), source (cause inferred) |

---

## H1 Form API moved (tooling)

* **Symptom:** `FormConfiguration/GetByName` returns 404; a script written for 0.43/0.45 that does `CreateNewVersion` / `UpdateStatus` fails; after `UpdateMarkup` the form's `modelType` is blank or changed.
* **Cause:** 0.46 has one row per form, edited in place; history is an automatic revision table. `FormConfigurationAppService` has no `GetByName` and no versioning calls (`Shesha.Web.FormsDesigner/Services/FormConfigurationAppService.cs:73-298`). `UpdateMarkupAsync` does `form.Markup = input.Markup; form.ModelType = input.ModelType;` (`:161-190`) - an omitted `modelType` clears it, a different one replaces it. Resolution by name goes through `Shesha.Application/ConfigurationItems/ConfigurationItemAppService.cs:30-65`.
* **Detect (tooling):** any recipe or script containing `GetByName`, `CreateNewVersion`, `UpdateStatus`, `versionStatus`, `isLastVersion`; any `UpdateMarkup` body without `modelType`.
* **Fix:** resolve with `ConfigurationItem/GetCurrent?ItemType=form&Module=&Name=`; push with `UpdateMarkup {id, markup, modelType}` where `modelType` is the value you just read; read back and compare. Recipes: [api.md](api.md).

## H2 Stale form from IndexedDB

* **Symptom:** API read-back shows your change; the portal still renders the old form (or a mix).
* **Cause:** the admin portal caches forms client-side in IndexedDB databases `form:default-app` and `form_lookup:default-app` (and the legacy `forms`), keyed by `cacheMd5`. The server `ConfigurationItem/CleanClientSideCache` only clears the server md5 cache (`ConfigurationItemAppService.cs:93-97`).
* **Detect:** browser output disagrees with a verified API re-fetch.
* **Fix:** delete the databases from a static page (`/favicon.ico`) where no app holds connections, then load the form - recipe in [verification.md section 2](verification.md). Do this before judging any change.

## H3 `htmlRender` drops a leading `<style>`

* **Symptom:** a form that used an `htmlRender` to inject CSS (custom tab styling, section styling) is unstyled.
* **Cause:** `sanitize` defaults to `true`; content goes through `DOMPurify.sanitize(html)` (`designer-components/htmlRender/index.tsx:39`, default at `:52-56`, migration `:62-67`). DOMPurify moves a `<style>` at the start of a fragment to `<head>` and drops it; a renderer that is only `<style>` becomes `""`.
* **Detect:** `c.type==='htmlRender' && /<style/i.test(c.renderer ?? c.html ?? '') && c.sanitize !== false`.
* **Fix:** set `sanitize: false` on the carrier (the branch at `:39` honours it), or prefix real content (`<div></div><style>...</style>` survives). The carrier must also be mounted (H6).

## H4 "Please, provide some content for this HTML render"

* **Symptom:** an antd Empty illustration with that text where an `htmlRender` is.
* **Cause:** the rendered/sanitised string is empty or whitespace, so `<Empty description="Please, provide some content for this HTML render" />` is shown (`htmlRender/index.tsx:42`). Typical: a style-only renderer after H3, a renderer that returns `''`/`undefined`, or `contentType:'html'` without `html` (H5).
* **Detect:** `c.type==='htmlRender'` and (renderer empty, or carrier-only: `!/<(?!\/?style)[a-z]/i.test(renderer.replace(/<style[\s\S]*?<\/style>/gi,''))`).
* **Fix:** for a pure CSS carrier set `sanitize:false` and keep the component zero-size with its own `style`/dimensions (the Empty placeholder still renders if the output is empty - emit at least a `<div></div>`); for content make the renderer return a non-empty string on every path.

## H5 `contentType: 'html'` ignores `renderer`

* **Symptom:** a script-driven `htmlRender` renders nothing/placeholder after someone "set content type to HTML".
* **Cause:** `const html = (model.contentType === 'html' ? model.html : calculatedModel.getContent(...))` (`htmlRender/index.tsx:38`). With `contentType:'html'` only the `html` property is read.
* **Detect:** `c.type==='htmlRender' && c.contentType==='html' && !c.html`.
* **Fix:** either put the markup in `html`, or remove `contentType` / set it to the script mode and keep `renderer`.

## H6 Hidden components are not mounted

* **Symptom:** an invisible helper (CSS carrier, data holder, hidden input with `initialValue`) has no effect any more.
* **Cause:** 0.43 passed `hidden` to antd `Form.Item` and kept children mounted; 0.46 returns `null` before rendering when hidden (`components/formDesigner/components/configurableFormItemLive.tsx:68`). `hidden` is `hidden || visible===false || !permissions || !visiblePermissions || !isComponentFiltered` (`components/formDesigner/formComponent/formComponentModelPreparer.tsx:106-114`).
* **Detect:** `c.hidden===true || c.visible===false` (or a code-mode `hidden`/`visible`) on `htmlRender`, or on an input that carries `defaultValue`/`initialValue` or a validator.
* **Fix:** do not hide side-effect components. Keep a CSS carrier visible and collapse it (`desktop.dimensions` height 0, `overflow:hidden`, no margin) or put the CSS in the target component's own `style`. Move default values to `formSettings.onAfterDataLoad`.

## H7 antd 6 tabs DOM

* **Symptom:** custom CSS written against tabs (custom tab styling, counters, pane styling) matches nothing.
* **Cause:** antd 6 / `@rc-component/tabs` renamed the DOM: `.ant-tabs-content-holder > .ant-tabs-content > .ant-tabs-tabpane` is now `.ant-tabs-body-holder > .ant-tabs-body > .ant-tabs-content` (pane = `.ant-tabs-content`). The tabs component `style` (e.g. `counterReset`) is no longer put on each pane inline; it becomes a class rule on the holder/`.ant-tabs-content` (`designer-components/tabs/styles.ts:58,73`; `tabs/index.tsx`). Collapse also changed (`.ant-collapse-content-box` is now `.ant-collapse-body`, header text `.ant-collapse-title`).
* **Detect:** any string (renderer, `style`, `className` CSS) matching `/ant-tabs-(content-holder|tabpane)|\[style\*=/` or `/ant-collapse-content-box/`; `c.type==='tabs' && /counter-?reset/i.test(c.style)`.
* **Fix:** rewrite selectors to the antd 6 chain and prefer the Shesha anchors, which survive library changes: live components carry `data-sha-c-id`, `data-sha-c-name`, `data-sha-c-type` (`components/formDesigner/formComponent/knownFormComponent.tsx:98-124`), e.g. `[data-sha-c-name="tabs1"] .ant-tabs-body-holder`. For per-pane styling give each tab item a `className` (it lands on `.ant-tabs-content`). Do not rely on hashed `css-xxxx` classes.

## H8 `text` v7 style keys

* **Symptom:** `text` padding/margin or font size from the markup has no effect; legacy `fontSize: 'text-xl'` renders at a different size.
* **Cause:** text v7 reads `desktop.stylingBoxJson` (an object) - not the `stylingBox` string; `desktop.font.size` overrides legacy `fontSize`; the legacy `padding: 'padding-base'` token is ignored (`designer-components/text/utils.ts`, `text/index.tsx:62-85`). The v5 migration converts tokens with a hard-coded 14px root and drops line height; `text-2xl`/`text-6xl` fall back to 14px (`text/models.ts:22,26`, `text/utils.ts:45`).
* **Detect:** `c.type==='text' && (c.stylingBox || c.fontSize || c.padding) && !c.desktop?.stylingBoxJson`.
* **Fix:** author v7 shape: `version: 7`, `desktop: { font: { size: 16, weight: '400', color: '...' }, stylingBoxJson: { _type:'styleBox', paddingTop:'0', ... } }` and no legacy keys.

## H9 Migration-injected defaults and phantom gaps

* **Symptom:** extra whitespace between sections; hidden blocks still reserve space; containers taller than their content.
* **Cause:** on load every component runs its migrations; style migrations fill defaults the stored markup never had (container `dimensions.minHeight: '32px'`, `columns` marginBottom 5, input heights 24/32/40, alert +8px padding) (`designer-components/_common-migrations/migrateStyles.ts:34-131`, `container/data.ts:157-232`). A component hidden by CSS-only means (or a container wrapper whose children are all hidden) keeps its own wrapper dimensions.
* **Detect:** `c.type==='container' && !c.desktop` (never saw the style step) or `version` below the current style-block step in [component-kb.md](component-kb.md); a container whose children are all hidden.
* **Fix:** write the structured `desktop` block explicitly with `dimensions: { height: 'auto', minHeight: '0' }` where no floor is wanted; set the real `version` so migrations do not run; remove or `visible:false` the whole empty container, not just its children. For the 32px container floor specifically see H22.

## H10 Render-time script throws before data loads

* **Symptom:** a field/section that should be hidden is shown; console shows `Cannot read properties of undefined`; styling from a script (`color`, `style`) is missing on first paint.
* **Cause:** scripts in code-mode settings (`{_mode:'code', _code, _value}`) run on every render, including before `data` is populated. A throw is swallowed (`providers/form/utils/scripts.ts:22,50`) and a throwing visibility is treated as VISIBLE (migrated `visible` carries `_value: true`). The style migration copies code settings into `desktop|tablet|mobile.*` (e.g. `font.color`), so the same script runs in several places.
* **Detect:** in every `_code` (anywhere in a component, including `desktop/tablet/mobile.*`) a read chain like `data.a.b` or `data?.a.b` - i.e. a `.` access after a possibly-undefined hop: `/\b(data|form\.data|contexts?\.\w+|page\.state)(\?\.|\.)\w+\.\w+/` without `?.` on every hop.
* **Fix:** optional chaining on **every** hop in render-time scripts (`data?.a?.b`), with a safe default (`Boolean(data?.a?.b)`). **Never** use `?.` on an assignment target (`data?.a = 1` is a syntax error) - guard with `if` instead. Syntax-gate edited scripts ([api.md section 9](api.md)).

## H11 Arrays from `data`/`value` are mutated in place

* **Symptom:** "changed?" comparisons always say unchanged; a stored snapshot silently follows later edits.
* **Cause:** the form hands scripts the live array object from form data; later edits mutate that same array.
* **Detect:** a script that stores `data.someArray` / `value` for later comparison without copying (`/=\s*(data|value)[\w.?]*\s*;/` where the value is an array).
* **Fix:** copy at the point of storing: `const before = (data?.items ?? []).slice()` (or `structuredClone`). Compare against the copy.

## H12 `ReferenceList/GetItems` is gone

* **Symptom:** 404 from a script or custom endpoint call that fetched reference-list items.
* **Cause:** the 0.43 `ReferenceList` service surface was replaced by the configuration-item loader.
* **Detect:** any string matching `/ReferenceList\/GetItems/`.
* **Fix:** `GET /api/services/app/ConfigurationItem/GetCurrent?ItemType=reference-list&Module=<mod>&Name=<list>` (items are in `result.configuration`), or `ReferenceList/GetByName` where a compatibility endpoint exists on that app. For dropdowns prefer `dataSourceType: "referenceList"` with `referenceListId: {module, name}` and let the component load it. Probe first; do not assume.

## H13 `refListStatus` inside a `subForm`

* **Symptom:** a `subForm` that hosts a `refListStatus` throws `Component with id ... is not found` and the form errors out.
* **Cause:** `refListStatus/index.tsx:50` calls `useComponentModel(model.id)` from the markup context (`providers/form/providers/formMarkupProvider.tsx:27` throws when the id is absent); sub-forms do not provide that context. Framework bug.
* **Detect:** a `refListStatus` anywhere under a `subForm` (or a form that is itself rendered as a sub-form / row template).
* **Fix:** flag it to the framework owners. Workaround: render the status in the parent form, or show the reference-list value with a read-only `dropdown`/`text` bound to the display value inside the sub-form.

## H14 `subForm` `labelCol: 0`

* **Symptom:** fields inside a `subForm` have no visible labels.
* **Cause:** the sub-form label span is `model.hideLabel === true ? 0 : model.labelCol ?? 0` (`designer-components/subForm/index.tsx:87`); the host's `labelCol` is applied to the hosted fields, so 0 hides their labels. Known core issue.
* **Detect:** `c.type==='subForm' && !(c.labelCol>0)`.
* **Fix:** a positive span on the sub-form component, e.g. `labelCol: 8, wrapperCol: 16` (the core fix ships 8), or `10/14` when long labels need more room; keep `hideLabel` for the sub-form's own label only. A wider span reduces wrapping but does not stop a wrapped label overlapping (see H20).
* **Fixed in:** Shesha 0.46.1 release notes add a migration for sub-form `labelCol` / `wrapCol` - verify on a running 0.46.1 which spans it writes before relying on it; the reconciler's `labelcol` rule is a project choice (opt-in) and has no retire.

## H15 `editMode` boolean false = disabled

* **Symptom:** a read-only view shows greyed (disabled) controls; after Edit, controls whose `editMode` script returns `'edit'` / `'readonly'` (or `false`) stay disabled; a button whose `editMode` is `'readOnly'` stays clickable.
* **Cause:** `getDisabledAndReadOnly`: `false -> {disabled:true}`, `true|'editable' -> editable`, `'readOnly' -> readOnly`, anything else (incl. `'disabled'`) -> disabled (`components/formDesigner/formComponent/formComponentApi.ts:18-27`). 0.43 treated `false` as read-only.
* **Detect:** `c.editMode === false` or `editMode._mode==='code' && /return\s+(true|false)\b/.test(editMode._code)`.
* **Buttons:** `'readOnly'` maps to `{disabled:false, readOnly:true}` and a button honours only `disabled`, so a read-only button is clickable on 0.46 (0.43 disabled it). Return `'disabled'` for buttons.
* **Fix:** return the strings `'editable' | 'readOnly' | 'disabled' | 'inherited'` (`'disabled'` for buttons that must not be clicked). For existing scripts, wrap the result and map `true`/`'edit'` -> `'editable'`, `false`/`'readonly'` -> `'readOnly'` (buttons: `'disabled'`). See [edit-mode.md](components/edit-mode.md).
* **Fixed in:** Shesha 0.46.1 release notes report this fixed - verify on a running 0.46.1 before relying on it; the reconciler's retire command unwinds the workaround.

## H16 `columns` gutter

* **Symptom:** `columns` content is inset by `gutterX/2` on both outer sides compared with older versions.
* **Cause:** the Row is forced to `marginLeft/marginRight: 0` while each Col keeps `paddingInline: gutter/2` (`designer-components/columns/columns.tsx:57`).
* **Detect:** `c.type==='columns' && gutterX > 0`.
* **Fix:** for new work, use flex `container` rows for splits, not `columns`. For existing `columns`, restore the LEFT inset only: Margin left `-(gutterX/2)` on the columns component. Store it where the stored version survives migration: below v4 the v4 step replaces `desktop` with the top-level props, so write the top-level `stylingBox` JSON string; at v6+ write `desktop/tablet/mobile.stylingBoxJson`. Do not add a negative right margin (H23). Leave an author's explicit horizontal margin alone.

## H17 `datatable` forced defaults

* **Symptom:** zebra rows, hover highlight, grey header, single-row selection appear on tables that stored none of it.
* **Cause:** steps v12-v31 in `designer-components/dataTable/table/tableComponent.tsx:273-389` force `striped=true`, `hoverHighlight=true` (even over a stored `false`), row height/padding, header colours, `useMultiselect false -> selectionMode single`.
* **Detect:** `c.type==='datatable' && (c.version ?? -1) < <current>` in the KB.
* **Fix:** author at the current `version` with explicit `striped`, `hoverHighlight`, `selectionMode` so no step runs.

## H18 `text` v7 content rewrite

* **Symptom:** `{{data.x}}` in a legacy `text` shows empty after load.
* **Cause:** v7 migration rewrites `{{` to `{{data.` for content stored below v7, so `{{data.x}}` becomes `{{data.data.x}}` (`text/index.tsx:73-85`).
* **Detect:** `c.type==='text' && c.contentDisplay!=='name' && (c.version ?? -1) < 7 && /\{\{\s*(data|contexts)\./.test(c.content)`.
* **Fix:** author new text at `version: 7` with `{{data.x}}` (or `contentDisplay: 'name'` + `propertyName`); for legacy text lower the prefix (`{{x}}`) before it migrates.

## H19 `text` ignores `hidden`/`visible`

* **Symptom:** conditional texts (validation hints, notes, banners) always show; changing the condition has no effect.
* **Cause:** in live mode 0.46 hides a component only inside `ConfigurableFormItem` (`components/formDesigner/components/configurableFormItemLive.tsx:68`) or when its own Factory checks `model.hidden`. `text` (`designer-components/text/index.tsx` -> `genericText.tsx`) does neither, and the generic wrapper `knownFormComponent.tsx` has no hidden guard. Proven by interception: `visible: {_mode:'value', _value:false}`, `visible` code `return false;` and `hidden: true` all left every text on screen. `collapsiblePanel` was suspected from source but does honour `visible:false` on a running app - check other non-form-item types the same way before assuming.
* **Detect:** `c.type==='text'` with a `visible`/`hidden` setting that is code, `false`/`true` respectively, or a value-mode `false`/`true`.
* **Fix (workaround until the framework enforces it):** keep the visibility setting and also drive `display:none` from the same expression through `style`, which `text` applies to its own element (`genericText.tsx:45`). Wrap, do not replace: the existing style result is preserved and the wrapper is marked so it can be removed when the framework is fixed:

```js
/*reconciler:046-visibility-style*/
const __vis = (() => { /* the visible expression body, or !(hidden) */ })();
const __base = (() => { /* the original style body, or return {}; */ })() || {};
return __vis === false ? Object.assign({}, __base, { display: 'none' }) : __base;
```

Apply it to the root `style` and to any `desktop`/`tablet`/`mobile` block that has its own `style` (a device `style` overrides the root one). Verify both directions: the hidden case disappears and a forced-visible case still shows.
* **Fixed in:** Shesha 0.46.1 release notes report this fixed - verify on a running 0.46.1 before relying on it; the reconciler's retire command unwinds the workaround.

## H20 Multi-line labels overlap the next row

* **Symptom:** a long field label wraps onto two or more lines and its text runs into the field below; the row does not grow.
* **Cause:** antd 6 `.ant-form-item .ant-form-item-label > label { height: var(--ant-form-label-height) }` (32px). The variable is defined by the `css-var-*` class on the label column itself, so nothing set on an ancestor (a container's or subform's custom style) can override it. The label COLUMN follows the field's Appearance > Height when that is an exact value (`components/formDesigner/components/styles.ts`), but the label element stays 32px, so a field Height of `auto` does not help either. Line counts are unchanged from older versions; only the height behaviour changed (measured: 2/3/4-line labels gave rows of 38/49/60px before, 35px on 0.46).
* **Detect:** in the browser, `label.scrollHeight > label.clientHeight + 2` for `.ant-form-item-label label`. Wrapping depends on the label column width, so measure at the target screen width instead of guessing from label length.
* **Fix (configuration only):** move the label out of the field. Replace the field with:
  - a horizontal row `container` (align items centre, no wrap, gap 0) that takes the field's own visibility condition;
  - a `text` label inside it: width = the label column share (labelCol 8 -> 33.333%, 10 -> 41.667%), right-aligned, weight 700, 14px, `rgba(0,0,0,0.88)`, padding-right 13px (antd's label `::after` gap), `contentType: 'custom'` and font type `inherit` (H25);
  - a field holder `container` with width `stretch` holding the original field with `hideLabel: true`.

  The input then starts at the same x as the inputs of the neighbouring fields. Copy the `text` and `container` shapes from working instances in the same form, not from documentation. Skip required fields unless the required mark is rebuilt (the field's red `*` goes with its label). Vertical label layout (`ant-form-item-vertical`) also lets labels grow, but mixed into a horizontal form it looks inconsistent.
* **Fixed in:** Shesha 0.46.1 release notes report this fixed - verify on a running 0.46.1 before relying on it; the reconciler's retire command unwinds the workaround.

## H21 Field rows are 35px

* **Symptom:** every field row is 3px taller than before; a long column of fields drifts down (row pitch 40px instead of 37px).
* **Cause:** `components/formDesigner/styles/shaComponentStyles.ts:20-24` gives every field label column `padding-bottom: 3px` (not configurable). The 5px gap between rows is antd's `.ant-form-item-row` margin, which collapses with the field's own bottom margin, so a positive field margin (e.g. 2) changes nothing.
* **Detect:** `.ant-form-item` height 35 where the control is 32.
* **Fix:** field Appearance > Margin bottom `-3`. The negative margin collapses with the row's +5: 5 + (-3) = 2, and 35 + 2 = a 37px pitch. Store it the same way as H16 (top-level `stylingBox` below the style step, device `stylingBoxJson` above it); skip fields whose author stored a bottom margin.

## H22 Hidden or empty containers take 32px

* **Symptom:** blank bands between sections where a container is hidden or has no visible content; field columns step out of line beside them.
* **Cause:** the container dimension default `minHeight: '32px'` (`designer-components/container/data.ts:163`) is applied by a generated class on the component wrapper, which a hidden container still renders (empty). Separately, framework CSS `.sha-form .sha-components-container { min-height: 32px }` (`components/configurableForm/styles/styles.ts:33-35`) applies to every inner container including column cells; no setting reaches that rule.
* **Detect:** a visible, empty `.sha-component[data-sha-c-type="container"]` 32px tall; a `.sha-components-container` exactly 32px with no content.
* **Fix:** container Appearance > Dimensions > Min height `0px` (wrapper). Skip containers whose author stored a real floor. The inner-container rule only matters for empty cells.

## H23 Negative right margins scroll

* **Symptom:** horizontal scrollbars appear inside tab bodies and containers after compensating `columns` with negative margins on both sides.
* **Cause:** containers migrate to `overflow: auto` (the container v6 migration defaults `overflow: true`) and the tabs body hard-codes `overflow: auto` (`designer-components/tabs/styles.ts`). A right margin of `-gutter/2` makes the columns block wider than its scrolling parent; a left overflow is not scrollable.
* **Fix:** left margin only (H16). The right edge stays `gutter/2` inside, which reads fine.

## H24 Tab bar gap

* **Symptom:** the first field sits right under the tab bar.
* **Cause:** 0.46 tabs set `.ant-tabs-nav { margin: 0 }`; antd's default was a 16px bottom margin.
* **Fix:** usually none needed; if the gap is wanted, give the first container in each pane a top margin of 16 in its Appearance.

## H25 `text` as a label: colour and font

* **Symptom:** a `text` copied from a heading or a coloured text paints the primary colour, or renders in the text default font instead of the app font.
* **Cause:** `designer-components/text/genericText.tsx`: `contentType: 'primary'` adds the primary class and ignores `font.color`; only `contentType: 'custom'` uses `font.color`. An absent `font.type` falls back to the text default family (Segoe UI) rather than the theme font (`_settings/utils/font/utils.tsx`).
* **Fix:** `contentType: 'custom'`, an explicit `font.color`, `font.type: 'inherit'`.

## H26 Buttons with an empty code label

* **Symptom:** blank 32px buttons (37px with margin) appear in a form, often inside field columns where they push one column's rows down.
* **Cause:** a `button` whose `label` is `{ _mode: 'code', _code: null }` renders an empty label. The same markup also rendered blank buttons before 0.46, so it is legacy configuration, not a regression; it becomes noticeable once other gaps are fixed.
* **Fix:** do not delete them unless the owner confirms they are unused (they may carry actions). Move them out of the columns into one row container placed after the columns, and give that row container `visible: false` (a hidden container renders nothing and leaves no gap). Related: a `columns` block holding only one conditional `text` (a validation hint) keeps 1px plus its margin when the text is hidden (H19); give the columns block the text's own visibility condition.

## H27 Stale designer tab overwrites API writes

* **Symptom:** after a markup push through the API, Configuration Studio still shows the old form; saving from it brings the old markup back.
* **Cause:** the designer holds the markup it loaded in memory. `UpdateMarkup` writes in place with no revision (H1), so a save from a tab opened before the push overwrites the push.
* **Fix:** close the form's tab in Configuration Studio and reopen it from the Explorer (or reload the page) after every API push; never save from a tab older than the last push. Say so whenever you push to a backend someone else is designing on.

## H28 Host values disappear after a subform loads

* **Symptom:** a tag or field in the host form shows its value, then goes blank a moment later (e.g. a status tag next to the page title).
* **Cause:** a `subForm` with `dataSource: 'api'` and an explicit `properties` list loads its entity and writes the result into the host's field named by its `propertyName`, replacing the host's copy of that object. Any `<propertyName>.<x>` the HOST shows but the subform does not fetch is gone after the subform's `Crud/Get` returns. Timeline proven in the browser: tag rendered at 13s, blank at 15s, right after the subform's request; the host's own request did return the value.
* **Detect:** for each api `subForm` with a `properties` string: the top-level names of every host component `propertyName` starting with `<subForm.propertyName>.`, minus the names in the properties list.
* **Fix:** append the missing names to the subform's `properties` list. Verify by watching the tag for 30+ seconds after load.

## H29 Partial device blocks drop styles and defaults

* **Symptom:** components stored at an old version look wrong in ways their settings do not explain: horizontal rows with no gap (table toolbars where search, filter, refresh, columns and pager touch), boxes collapsing, top-level styles ignored.
* **Cause:** the style migration builds each device block from `prev[screen]` when that block exists and from the top-level props only when it does not (`_common-migrations/migrateStyles.ts`, `migratePrevStyles`). A partial block - only a `className`, or a single value written by a tool - therefore wins over every top-level style, and the container's later step copies `gap: prev.gap` (often unset), giving `gap: 0`.
* **Detect:** a component below its style-block step (see [component-kb.md](component-kb.md)) whose `desktop/tablet/mobile` blocks hold only a few keys; a horizontal container with no `gap` in any block and no top-level `gap`.
* **Fix:** never create a partial device block on a component below its style step - write the value at the top level instead (e.g. `dimensions.minHeight`). Where partial blocks already exist, add the missing value to every block (`gap: '8px'` restores a spaced row). If a tool created a partial block, remove it again.

## H30 Panel headers

* **Symptom:** collapsible panel headers are 52-56px with 8px padding on every side; before they were 50px with 5px top and 10px left padding.
* **Cause:** the panel migration writes default `headerStyles` (padding 8 all round) into every device block (`collapsiblePanel/collapsiblePanelComponent.tsx`).
* **Fix:** where the stored header padding is still exactly the default, set `headerStyles.stylingBoxJson` padding to 5 / 0 / 0 / 10 in each device block.

## H31 Reactivated CSS carriers

* **Symptom:** after making an htmlRender CSS carrier work again (H3-H6), a section of the same form collapses or overlaps (e.g. read-only boxes shrink to about 10px with inner scrollbars).
* **Cause:** the carrier's CSS was written for the old DOM and never applied on 0.46 until it was fixed. 0.46 wraps components such as `htmlRender` in an `ant-form-item`, so broad rules like `.x .ant-form-item-row{flex-direction:column}` now also match them.
* **Fix:** after reviving a carrier, re-check every page the form appears on, and narrow its rules to the elements they were meant for (e.g. `.ant-form-item:has(textarea)`).

## H32 Renamed framework entity types

* **Symptom:** an autocomplete or table bound to a framework entity shows nothing; the console shows `Metadata/Get?entityType=...` 404 and `Entities/GetAll` 500.
* **Cause:** 0.46 renamed framework entity classes: `Shesha.Domain.ConfigurationItems.Module` is `Shesha.Domain.Module`, and form references are `Shesha.Domain.FormConfiguration` (not `Shesha.Framework.ConfigurableComponent`).
* **Detect:** grep markup for `Shesha.Domain.ConfigurationItems.` and `Shesha.Framework.ConfigurableComponent`; confirm the target with `Metadata/GetProperties` (`entityType` + `entityModule` of the bound property) or `EntityConfig/GetMainDataList`.
* **Fix:** replace the type name in the `entityType` / `entityTypeShortAlias` values.

## H33 Empty status chip

* **Symptom:** a grey rounded box beside a record name where the status has no value; before 0.46 nothing rendered.
* **Cause:** `refListStatus` renders a placeholder chip when its value is null.
* **Fix:** give an always-visible `refListStatus` the visibility condition `return data?.<path> != null;` (optional chaining on every hop of a dotted property name).

## H34 Optional filter item sent as `null`

* **Symptom:** a table (`datatableContext` / `dataContext`) shows no rows; the `Entities/GetAll` call answers 400 `The binary operator AndAlso is not defined for the types 'System.Boolean' and 'System.Object'`; the request's filter is `{"and":[{...},null]}`. The same table loaded on 0.43.
* **Cause:** the 0.46 filter evaluator in `@shesha-io/reactjs`: an `and` / `or` item whose mustache `evaluate` is optional (`required: false`) and does not resolve is left in the array as `undefined`. The array is kept when at least one item is defined, and `JSON.stringify` turns the `undefined` into `null`, which the backend cannot turn into a boolean expression. 0.43 dropped the item.
* **Detect:** a stored filter (`permanentFilter` and similar) with an `and` / `or` item `{"==":[{"var":"<prop>"},{"evaluate":[{"expression":"...","required":false}]}]}`; typically an optional fallback beside a required item on the same variable (`<prop> == {{data.x.id}}` required + `<prop> == {{data.model.x.id}}` optional). Confirm in the browser: the `GetAll` request body contains `null`.
* **Fix:** drop the optional item when a required sibling compares the same variable (identical to 0.43 whenever the fallback is unresolved or equal). Report, and review by hand, any other optional item: dropping it changes the filter when it does resolve. Verify by comparing the request with the 0.43 environment's request for the same page (same filter, 200, same row count).
* **Fixed in:** Shesha 0.46.1 release notes report this fixed - verify on a running 0.46.1 before relying on it; the reconciler's retire command unwinds the workaround.

## H35 Custom dialog footer buttons ignore their scripts

* **Symptom:** a dialog opened with `footerButtons: "custom"` shows its buttons, but a button whose `editMode` (or `visible` / `hidden`) is a script never changes state: a Save that 0.43 disabled until a condition held is always enabled; a script `console.log` inside it never fires.
* **Cause:** the 0.46 dialog renders the action's `buttons` with the raw button-group renderer, which reads only static `visible`, `disabled` and permissions. Script evaluation happens only in the `buttonGroup` *form component*, which footer items never pass through. 0.43 evaluated them.
* **Detect:** a `Show Dialog` action with `footerButtons: "custom"` and any item whose `editMode` / `visible` / `hidden` / `disabled` has `_mode: "code"`.
* **Fix:** when the dialog form is opened by that one dialog, render the buttons inside the dialog form as an ordinary `buttonGroup` (a right-aligned row appended to the root container) and set `footerButtons: "none"`; the items are copied unchanged and `shesha.form` actions still act on the dialog form. When the dialog form is shared by several dialogs with different buttons, the buttons cannot move: enforce the button's condition inside its first `Execute Script` (warn and throw when the condition says disabled; fail open if the condition itself errors). The visual disabled state then needs a framework fix.
* **Fixed in:** Shesha 0.46.1 release notes report this fixed - verify on a running 0.46.1 before relying on it; the reconciler's retire command unwinds the workaround.

## H36 `[default]` reference-list column on a URL-sourced table

* **Symptom:** a table whose context has `sourceType: "Url"` shows a reference-list column as numbers (`12`, `20`) where 0.43 showed item names; sibling tables with an explicit dropdown display render names.
* **Cause:** the `[default]` display needs property metadata to know the value is a reference-list item; 0.46 does not resolve it for URL-sourced data even when the context names an `entityType`. 0.43 did.
* **Detect:** a `datatable` under a `datatableContext` with `sourceType: "Url"` and an `entityType`, a data column whose `displayComponent.type` is `[default]`, and whose property is a reference list in that entity's metadata (`Metadata/Get?entityType=`).
* **Fix:** give the column a dropdown display (`dataSourceType: "referenceList"`, `referenceListId` from the metadata), copied from a working dropdown display; read-only, stored values unchanged.

## H37 Reference-list dropdown search filters by value

* **Symptom:** typing in a searchable reference-list dropdown ("South" in a country list) shows "No matches" although the items exist; 0.43 filtered by the item text.
* **Cause:** the 0.46 reference-list select renders antd `Select` with `showSearch: true` and passes `filterOption` from its props, which the dropdown component never supplies; antd then matches the typed text against the option `value` (the numeric item value).
* **Detect:** any `dropdown` with `dataSourceType: "referenceList"` and numeric item values; type part of an item's text.
* **Not a fix:** the dropdown's *Binding Format* (Item value / Item label). With *Item label* the option value is the label, so search works, but the form then stores and sends the label string on save, which a numeric reference-list property rejects.
* **Fix:** none at configuration level. Framework fix: make the search always use the item label, independent of Binding Format (`optionFilterProp: "label"` or a label `filterOption`). Until then users scroll and click.
* **Fixed in:** Shesha 0.46.1 release notes are reported to cover this - verify on a running 0.46.1 before relying on it. There is no reconciler workaround to retire for this hazard.

## H38 Entity autocomplete without a sort

* **Symptom:** an entity autocomplete lists options in database order (a list of categories) where 0.43 listed them alphabetically.
* **Cause:** 0.43 sent `sorting=<displayPropName>` when none was stored; 0.46 sends no sorting.
* **Detect:** `autocomplete` with `dataSourceType: "entitiesList"`, no `sorting`, and a real `displayPropName` (compare the `GetAll` request on both versions: `&sorting=name` vs none).
* **Fix:** store the 0.43 default explicitly: `sorting: [{"id": "...", "propertyName": "<displayPropName>", "sorting": "asc", "itemType": "item"}]`. Leave `_displayName` / dotted display properties alone (not sortable columns).

## H39 `delete data.x` does nothing in an action script

* **Symptom:** a save that posts `{...data, ...}` from an `Execute Script` action fails with `Property '<helper>' not found for '<Entity>'` although the script deletes that helper field first; 0.43 saved.
* **Cause:** in 0.46 action scripts `data` is a proxy over the form values that ignores `delete`; spreading it afterwards still copies the "deleted" keys.
* **Detect:** an action script (`actionConfiguration...expression`, `_code`) containing `delete data.<x>` followed by a spread `...data`.
* **Fix:** copy first and work on the copy: `const payload = { ...data }; delete payload.x; ... {...payload, ...}`. Reads of `data.<x>` stay as they are.

## H40 URL table fetches with an empty id before the record loads

* **Symptom:** a table with `sourceType: "Url"` and an endpoint such as `...?parentId={{data.id}}` stays empty; the network shows one call with `parentId=` (400 `The value '' is invalid`) and no retry.
* **Cause:** the 0.46 context fetches when it mounts and does not refetch once the mustache value resolves; on 0.43 the first fetch came after the record had loaded.
* **Detect:** `datatableContext` / `dataContext` with `sourceType: "Url"` whose endpoint mustache parameters are all id-like (`data.id`, `data.<x>Id`) and whose visibility is static.
* **Fix:** make the context visible only once the ids exist (`visible` code `return !!data?.id;`), so it mounts and fetches with real values. Leave contexts whose parameters may legitimately be empty (filters) alone.

## H41 `globalState.<tableContext>` no longer holds table contexts

* **Symptom:** a script that refreshes or reads a table through `globalState.<contextName>.refreshTable()` / `.tableData` does nothing or throws `Cannot read properties of undefined`; the row list is not refreshed after an upload or add.
* **Cause:** 0.43 published every data table context into `globalState` under its component name; 0.46 exposes them through `contexts.<name>` (and the action system), not `globalState`.
* **Detect:** any `_code` / action expression containing `globalState.<name>.refreshTable`, `globalState.<name>.tableData` or `globalState?.<name>` where `<name>` is a `datatableContext` component name in the same form or its host.
* **Fix:** `contexts.<name>` holds the table *state* (`tableData`, `selectedRow`, `selectedRows`) but has no `refreshTable`. Read state through `contexts.<name>?.<prop>`; replace a script refresh with a chained `Refresh table` action (`{"_type": "action-config", "actionName": "Refresh table", "actionOwner": "<context component id>"}`) after the script, ahead of any existing `onSuccess`. Proven on a real upload: the list request fires again and the row updates without a reload. A context that lives in a hosting form needs its own browser proof before converting.

## H42 Read-only (calculated) properties rejected on save

* **Symptom:** saving a form fails with `Your request is not valid! Property '<x>' is readonly.`; 0.43 saved the same form.
* **Cause:** the 0.46 dynamic CRUD validates the payload against metadata and rejects properties marked `readonly`; 0.43 ignored them. A form that displays a calculated value, or hosts a subform whose entity is updated in cascade, posts them back.
* **Detect:** the form's model metadata (`Metadata/Get?entityType=`) has `readonly: true` properties, at the top level or under an entity reference with `cascadeUpdate: true`, and the form submits through the default endpoints.
* **Fix:** in `formSettings.onPrepareSubmitData`, before `return data;`, delete every read-only property from `data` (and from each cascade-updated reference). Deleting an absent key is a no-op; read-only values were never stored anyway. Verify by repeating the save: 200 and the record reloads.

## H43 Leftover filter on a URL-sourced table blocks the fetch

* **Symptom:** a URL-sourced table never issues its request (nothing in the network tab) and shows "No Data"; on 0.43 the same table listed rows.
* **Cause:** the context still carries a `permanentFilter` from when it was entity-sourced, with a required mustache value that can never resolve on this form (e.g. `{{data.parent.id}}` on a form whose data *is* the parent). 0.46 keeps the filter "not ready" and does not fetch; 0.43 fetched the URL without it.
* **Detect:** `sourceType: "Url"` plus a `permanentFilter` whose every mustache expression starts with `data.<prop>` where `<prop>` is neither `id` nor a property of the form's model.
* **Fix:** remove that permanent filter (the URL already scopes the data). Leave filters that resolve alone: 0.46 sends a resolvable filter to the URL endpoint. Proof: strip it in flight and the request fires.

## H44 `onAfterDataLoad` receives only the id as `data`

* **Symptom:** values that a page form's `formSettings.onAfterDataLoad` derives from the loaded record (totals, flags, page-context values) stay empty; the handler throws part-way (`Cannot read properties of undefined`), skipping everything after the throw.
* **Cause:** on 0.46 the page form runs `onAfterDataLoad` with `data` holding only the initial values (the `id` from the URL); the loaded record is in `form.data`. 0.43 passed the loaded record as `data`. Sub-form after-load scripts behave the same on both versions.
* **Detect:** an `onAfterDataLoad` that reads record fields through `data.<x>` (other than `data.id`). Confirm in the browser: log `Object.keys(data)` vs `Object.keys(form.data)` inside the handler.
* **Fix:** run the handler with `data` bound to `form.data` exactly when `data` holds nothing but the id and `form.data` holds more: `const d = (form?.data && only-id(data) && Object.keys(form.data).length > 1) ? form.data : data; return (async (data) => { <original> })(d);`. Elsewhere the handler runs unchanged. Leave handlers that write into `data` for review by hand.
* **Fixed in:** Shesha 0.46.1 release notes report this fixed - verify on a running 0.46.1 before relying on it; the reconciler's retire command unwinds the workaround.

## H45 Subform names a framework form 0.46 no longer ships

* **Symptom:** a tab that hosts a subform renders an empty dashed box with an info icon; the console shows `form '<module>/<name>' not found`.
* **Cause:** a framework module form that existed on 0.43 is not shipped by the 0.46 packages (absent on a fresh 0.46 environment too), while the application has its own copy with the same components.
* **Detect:** `subForm.formId` naming a framework module form that `ConfigurationItem/GetCurrent` cannot find on 0.46, and an application form with the same name and the same component list on 0.43.
* **Fix:** point the subform at the application's copy. Confirm the two are equivalent (same components) on the 0.43 environment first.

## H46 Subform expressions cannot see the host record

* **Symptom:** a list inside a subform that filters on the host record (`{{data.id}}`) never fetches; the tab shows its empty text while the pager shows a default count.
* **Cause:** a subform with `dataSource: "form"` bound to a property the host record does not have gets empty `data` on 0.46; its filter expressions also do not resolve `pageContext`, `query` or `parentFormValues`, so a required filter stays unresolved and the context never fetches. On 0.43 the subform's data proxy fell back to the host record.
* **Detect:** a `subForm` with `dataSource: "form"` whose `propertyName` is not a property of the host model, hosting a form whose `permanentFilter` uses `{{data.id}}`. A literal id in the filter makes it fetch (proof the evaluator, not the endpoint, is the blocker).
* **Fix:** no lever inside the subform. Proven design: place the subform's components directly in the host (ids made unique), where `{{data.id}}` is the host record. That turns one shared form into copies, so it is a design decision for the application owner; the alternative is a framework fix (subform expression context falls back to the host record).

## H47 A stale `parentId` makes the designer re-nest a component

* **Symptom:** a component that a merge or a script placed correctly renders in the wrong container after someone opens and saves the form in the designer: a side panel that was moved out of a tab pane jumps back into it and renders below the page content. Read-back equality, `forms changed 0` and component counts all pass while this is waiting to happen.
* **Cause:** 0.43 renders by NESTING and ignores `parentId`; the 0.46 designer rebuilds the tree from `parentId` on save. A package authored with the 0.43 designer can leave `parentId` pointing at the OLD parent although the component sits in the new container. Who re-saved the form is inferred (a designer open and save); the tree rebuild from `parentId` is the mechanism.
* **Detect:** for every component compare its `parentId` with the id of the container that actually holds it in the markup tree (the root holds children as `'root'`; any `components` list belongs to the nearest enclosing dict with an `id`: a component, a tab pane, a column, a wizard step, a panel part). A component with no `parentId` is left alone, and keys starting with `_` are not part of the tree. A markup diff between what you wrote and what the server holds minutes later shows the re-nest. `shrec.py detect` check `parent-id`. **[proven]**: a package's raw copy had a row's children `[mainColumn, sidePanel]` with `sidePanel.parentId` naming an old pane; a later read had the panel in the pane and nine components normalised by the designer (`hidden` to `visible`, `version` bumped, device blocks added).
* **Fix:** set `parentId` to the real nesting parent BEFORE the push (the reconciler rule `normparent` normalises every `parentId` to the tree; run it before and after every merge; it rewrites only the string and never moves a component). Re-read the form some minutes after the push and diff it. Tell the authors of the package: their source carries stale `parentId`s, and the trap recurs on every merge.

## H48 Flex-item sizing comes from the device block's `dimensions`

* **Symptom:** a two-column row (a main column and a fixed-width side column) clips or squeezes the side column when `flex` or `width` is set in the container's `style` code. A script that positions things by counting the row's DOM children (`row.children.length === 2`) silently bails because the row's inner element has extra zero-size `display:none` placeholder children.
* **Cause:** on 0.46 the flex items are the `sha-component` wrappers; their `width` / `min-width` / `max-width` / `min-height` come from `desktop.dimensions`. `style` (code) and top-level `dimensions` reach only the INNER element, so they do not size the flex item.
* **Detect:** a container used as a row whose children rely on `style` for width or flex, and any `htmlRender` script that counts `children`. Measure instead of guessing: `shrec.py dom-chain <page> --name <component>` prints width, display and flex per ancestor and the matched CSS rules. Read the computed CSS, not the markup. **[proven]** by computed CSS at one viewport (main column + gap + side column summed to the row width, nothing clipped); a static top margin used to align the side column was an approximation that was not verified at other widths.
* **Fix:** give the row `desktop = { display: 'flex', flexDirection: 'row', direction: 'horizontal', justifyContent: 'start', alignItems: 'start', flexWrap: 'nowrap', gap: 16 }`, the fixed column `desktop.dimensions = { width, minWidth, maxWidth }` (all the same value) and the flexible column `desktop.dimensions = { width: '100%', minWidth: 0 }`; keep the author's `style` strings. Do not depend on the number of DOM children of a row.

## H49 Scripts inside a sub-form run against the HOST page form

* **Symptom:** a Save button inside a sub-form reads `data.newEntry` and gets nothing (an "empty" validation message with text in the box); a request that needs a record id goes out with `undefined` or no id (a 500 "id must be supplied", a 400 `parentId=undefined`); `http.get(url, { params })` in a form script sends no query string.
* **Cause:** in a sub-form's (or a dialog-opened form's) Execute Script, `data` is `{}` and `form` is the HOST page form (read-only mode, `form.shaForm._formData` holds the host record, `getFieldValue('x')` is undefined, `form.getFormData()` is undefined, `pageContext` has no key for the sub-form's fields). `form.setFieldsValue(...)` there silently writes to the host form. The value lives only in the sub-form's own state; the DOM node is the only reachable handle. A custom component that evaluates a setting with a narrower scope (for example only `{ data, globalState, formMode }`) throws on `page.state` and loses the whole expression.
* **Detect:** any sub-form (embedded through `subForm` or a datalist row) whose scripts read `data.*` or call `form.getFieldValue` / `setFieldsValue` / `getFormData` for fields of the same sub-form; any `<id>: data.x` read in an action, `getUrl` or `queryParams` of a hosted or dialog form. `shrec.py detect` check `subform-script-scope` (a heuristic: review); confirm with `shrec.py probe-scope`, which adds a TEMPORARY dump of `data`, `form` (keys, `formMode`, `shaForm._formData`), `pageContext` and `contexts` to one script, prints it from a fresh browser, and always removes it afterwards. Confirm record ids with `shrec.py audit-requests` (hook `fetch` AND `XMLHttpRequest`). **[proven]** end to end: after the fix the Save request carried the parent id and entity type, and the stored row was read back.
* **Fix:** read and clear a sub-form's input through its stable component name (`document.querySelector('[data-sha-c-name="newEntry"] textarea')`, clear with the native value setter plus a bubbling `input` event) and let the list refresh through the button's `onSuccess: Refresh table`. For record ids, keep the ORIGINAL lookup first and append only fallbacks that exist in that scope: an id the host publishes in `page.state` (scripts, mustache) and in `globalState` (the only one a narrow-scope component can see); never rewrite a setter. How a sub-form button should read sibling fields on 0.46 is an open question for the framework team. The first attempt (`form.getFieldValue`) was a guess and wrong: probe first.

## H50 A Url data context drops the endpoint's query string (data leak)

* **Symptom:** a list that filters and sorts through query text in the context's `endpoint` shows ALL rows of the entity, unsorted: any user sees records that belong to other parents. With `sortMode: 'strict'` (or the Entity source), rows render empty (or with defaults) instead.
* **Cause:** the Url data context drops the endpoint's query text and rebuilds `filter`, `sorting` and `properties` from its own settings. With `sortMode: 'strict'` (and with the Entity source) the sort field is added to `properties` (`properties=<sortField> id`), so each row carries only `id` and the sort field. A Url context with NO `properties` returns whole objects.
* **Detect:** a `datatableContext` / `dataContext` with `sourceType: 'Url'` whose `endpoint` (a string or a code-mode `_code`) contains `filter=`, `sorting=` or `properties=`. `shrec.py detect` check `url-endpoint-query` (trap when it is a generic list endpoint such as `Crud/GetAll` or `Entities/GetAll` carrying `filter=` with no `permanentFilter`; review otherwise). Capture the real request with `shrec.py audit-requests` (flags NO FILTER, NO SORTING, TRIMMED PROPERTIES, PARENT MISMATCH). The strongest check compares the rendered set with the database. **[proven]** on the wire: the author's endpoint produced `GET .../Crud/GetAll?maxResultCount=100&skipCount=0`; with a plain-string `Entities/GetAll?...&filter=...` only `entityType` survived; after the fix the request carried `sorting=<sortField> desc` and a filter on the parent, and every returned row belonged to that parent.
* **Fix:** keep `sourceType: 'Url'`, `endpoint: '/api/dynamic/Shop/Order/Crud/GetAll'` (or the entity's own endpoint) and `entityType` set, and put the scope in settings: `permanentFilter: { and: [ { '==': [ {var: '<parent reference property>'}, {evaluate: [{expression: '{{page.state.<parent id key>}}', required: true}]} ] } ] }`, `sortMode: 'standard'`, `standardSorting: [{ id, propertyName: '<sortField>', sorting: 'desc', itemType: 'item' }]`. Use `standard` plus `standardSorting` rather than `strict` when the row needs more than the sort column.

## H51 Which id expression resolves inside a nested sub-form's `permanentFilter`

* **Symptom:** a list inside a sub-form inside a host form shows its empty text although records exist, and the network shows NO request.
* **Cause:** a `required: true` mustache that never resolves gives an EMPTY list, not an error. In a form nested two deep, `{{data.id}}` did not resolve and `{{pageContext.<key>}}` did not either; `{{page.state.<key>}}` resolved to the record id the host publishes (the pattern existing task and list sub-forms already use). How `page.state` and `pageContext` relate on 0.46 is unexplained: the key resolved at run time although no `page.state.<key> = ...` setter was found, only a legacy `pageContext.setFieldValue` write. An open question for the framework team.
* **Detect:** a `required: true` `{{data.*}}` or `{{pageContext.*}}` mustache in the `permanentFilter` of a form embedded two deep (a sub-form of a sub-form). `shrec.py detect` check `required-mustache-subform` (a heuristic: review). Confirm a request fires with `shrec.py audit-requests`. **[proven]** on the wire; the explanation is open.
* **Fix:** use `{{page.state.<key>}}` for an id the host page publishes (in its `onAfterDataLoad`). Negative control: `{{page.state.doesNotExist}}` must send no request. H46 is the same family for one level of nesting.

## H52 Hidden data-holder fields are not mounted; a list row sees only what is mounted directly under it

* **Symptom:** a list row's `htmlRender` prints a default value although the response holds the data.
* **Cause:** extends H6. Row data keys: bound fields with `hidden: true` (a trick to force fields into the row) give `[id, <sortField>]` only; `hidden: false` bound fields that are DIRECT children of the row root give the full keys; `hidden: false` fields nested inside a zero-height holder container give `[id, <sortField>]` again. A row only sees what is mounted directly under its root.
* **Detect:** a bound input with `hidden: true` inside a list row form, or a bound input wrapped in a zero-height container there. `shrec.py detect` check `hidden-row-field` (trap when a row script reads `data.<field>`, review otherwise). Dump `data` from inside the row's `htmlRender` with `shrec.py probe-scope`. Judge by a screenshot: `innerText` of the panel still contains the collapsed fields' values. **[proven]** by a temporary dump from inside the row's `htmlRender`.
* **Fix:** keep the data-holder fields mounted as DIRECT children of the row root and collapse each one on its own: `desktop` / `tablet` / `mobile` `dimensions` height, minHeight and maxHeight 0, `style` height 0 plus `overflow: hidden`, margin as the author had it. If a generic rule such as `layout` writes a margin on the same fields, make both agree (a collapse with `margin: 0` against the rule's `-3` kept reporting changes).

## H53 A datalist makes two requests, and the first load after a push can mislead

* **Symptom:** a list that looks complete on the first load after a push and is incomplete on later fresh loads; a row-level `visible` code such as `return !!data && data.bodyText !== undefined` leaves the list empty forever.
* **Cause:** a datalist makes TWO requests: the first with `properties=id` (plus the sort field), the second with the full projection (the task lists do the same). In some states the second response never reached the rows, and an `htmlRender` paints once. No Shesha-internal explanation was found (the bundles are minified, only `.d.ts` ships): the cause is inferred.
* **Detect:** a list that is complete after a push and incomplete on later fresh loads. Capture ALL requests without de-duplicating by path and load at least three times in fresh browser contexts: `shrec.py audit-requests <page> --loads 3` flags `LOAD DIFFERS`. **[proven]** misleading signal: twice the very first load after a push showed complete rows and every later fresh load did not.
* **Fix:** do not accept a result from the first load after a push. Prefer the Url-with-no-`properties` shape (H50), which avoids the question.

---

## Scanner

`scripts/scan-hazards.mjs` implements the predicates above that are decidable from markup alone (H3-H18 except H2; H1 is a tooling hazard, covered by `scripts/form-api.mjs`) and, with `--syntax`, the script syntax gate.

```bash
node scripts/scan-hazards.mjs staged/form.json            # report
node scripts/scan-hazards.mjs staged/form.json --json     # machine-readable
node scripts/scan-hazards.mjs staged/ --syntax            # a directory of forms + syntax-check every _code
```

Exit codes: 0 clean, 1 findings, 2 could not run. A hit is a **hypothesis**: confirm in the browser before rewriting a working form (the predicates are deliberately broad).
