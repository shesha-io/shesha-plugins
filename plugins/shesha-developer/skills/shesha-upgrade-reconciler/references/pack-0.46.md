# Rule pack 0.46

Contents: how to read the table | rule table | framework behaviours and revert markers | withdrawn approaches

The pack in `scripts/packs/v0_46/` reconciles forms authored for the 0.43 line on a Shesha 0.46 target. It applies to targets `>=0.46.0 <0.47.0` with a source below 0.46.0
(`shrec.py versions` prints the match and the hazard catalogue). `H<n>` points to `shesha-developer-0-46:shesha-form-edit` `references/render-hazards-046.md`, which holds each
hazard's symptom, cause, detection predicate and fix; this page is the packaged answer. Every rule is anchored, idempotent and syntax-gated where it writes a script
([rule-authoring.md](rule-authoring.md)); `shrec.py plan` prints each rule's fate for the target version. Rules run in the order of the table.

How to read it:

- **kind**: `fleet` runs on every form it applies to; `targeted` needs measured inputs or form-specific anchors and is run by name (`shrec.py apply --rules <id> --only ...`);
  `opt-in` runs only when enabled in `project.json` (`rules.enable`) or named in `--rules`.
- **options**: the `project.json` `options` keys the rule reads ([tracking.md](tracking.md)); a rule whose fix is a project decision is a no-op without them.
- **fixed in**: the framework version whose release notes report the bug fixed. **Release notes are claims, not proofs**: a rule marked this way is still applied
  (`apply-claimed-fixed`) until the fix is verified on a running instance of that version; then `shrec.py retire` unwinds the workaround for the rules that ship a retire function (`textvis`, `editmode`, `afterload`, `dialogfooter`).

## Rule table

The first block of rows (`scripts` to `normparent`) are the fleet and opt-in groups in pack order; the last six are the targeted rules, run by name on measured inputs or named forms (`shrec.py apply --rules <id> --only <forms>`, dry run first).

| rule | hazard | symptom on 0.46 | what it writes | kind | options | fixed in |
|---|---|---|---|---|---|---|
| `scripts` | H10 | thousands of script errors on render; components that should be hidden show, because a throwing visibility expression now means visible | optional chaining on every hop of render-time scripts (`data?.a?.b`), never on assignment targets; syntax-gated | fleet | - | - |
| `textvis` | H19 | conditional `text` components (hints, notes, "this field is required") always show: `text` ignores `hidden` / `visible` | keeps the visibility setting and also drives `display:none` from the same expression through the component's `style` (root and device blocks); marker `/*reconciler:046-visibility-style*/`; `retire` unwraps it | fleet | - | 0.46.1 (release notes, not verified) |
| `textsize` | H8 | titles and texts 12.5% smaller, preset padding gone (the v5 migration converts size presets against a 14px root; v7 ignores the legacy padding preset) | `desktop.font.size` = preset rem x 16 and the preset padding into `desktop.stylingBoxJson`, only where the stored values are the migration's own output | fleet | - | - |
| `carriers` | H3, H6 | existing `htmlRender` CSS carriers inject nothing and show "Please, provide some content"; HTML built by renders shrinks to its content | carrier mounted (visible), `contentType: jsx`, renderer prefixed with `<span hidden></span>` so the sanitiser keeps the `<style>`, plus a rule restoring full width for htmlRenders in their own form; marker `/*reconciler:046-carrier*/` (opt-out `/*reconciler:nonempty*/`); existing carriers only, never adds new ones | fleet | - | - |
| `rlshidden` | H13 | `Component with id ... is not found` thrown by a hidden `refListStatus` inside a hosted form | a statically hidden `refListStatus` in a form another form hosts becomes a hidden `textField` (binding kept); the original is kept under `_reconcilerOriginal` | fleet | - | - |
| `layout` | H22, H16, H21 | blank 32px bands for hidden or empty containers; fields inset by gutter/2; rows 35px instead of 32 (pitch 40) | container Min height `0px` (skipped where the author stored one or the reference form stored a real floor); columns Margin left `-(gutterX/2)` only (a right margin adds scrollbars, H23); field Margin bottom `-3` where none is stored | fleet | - | - |
| `tabs` | H7, H9 | grey inactive tabs, black active label, bordered and padded tab body | values equal to the migration defaults are reset (transparent card, primary colour weight 400, zero borders with `hideBorder`, zero padding); tabs saved below v4 are seeded with the 0.43 framework tab look (primary-colour label, transparent card, no borders), marked `_reconciler046` | fleet | - | - |
| `status` | H10 | blank 37px status buttons (0.43 hid them because their label expression threw); section separators lost their bottom gap | with option `statusLabelPattern` set (required for this part, no default): the button gets `visible: data?.X?.status != null`; the separator's `wrapperStyle` marginBottom 8 where none is stored; a container holding only that button takes its condition; markers `/*reconciler:046-status-button*/`, `/*reconciler:046-separator-gap*/` | fleet | `statusLabelPattern` | - |
| `hints` | H22 | an empty strip (margin and cell padding) where a conditional hint text is hidden | a `visible: true` columns block whose only child is a `text` with a visibility code takes a copy of that code | fleet | - | - |
| `labelcol` | H14 | wrapped labels, or labels that disappear, in hosted subforms (the migration default is `labelCol 8 / wrapperCol 16`) | a subForm stored 8/16 (or unset) gets the configured spans; a no-op without the option | opt-in | `subformLabelCol` | 0.46.1 (release notes claim a subform `labelCol` / `wrapperCol` migration fix, not verified) |
| `subfetch` | H28 | a value the host shows from a subform-loaded object disappears once the subform loads (for example a status tag goes blank) | host-bound top-level fields are appended to the api subForm's `properties` list | fleet | - | - |
| `rowgap` | H29 | horizontal rows and table toolbars with gap 0, controls touching | `gap` in each device block that has none (top level when there are no blocks); containers with their own gap are left alone | fleet | `rowGap` | - |
| `tabgap` | H24 | the first field sits right under the tab bar | top-positioned tabs with a stored top padding of 0 or unset get `paddingTop` 16 | fleet | - | - |
| `tablectl` | - | a vertical table header (`sha-index-table-control`) is squeezed into one row: the title overlaps the search box | `display: flex`, column, stretch in each device block (the 0.46 class defaults force a nowrap row); horizontal headers and author-owned layouts are untouched | fleet | - | - |
| `tagnull` | H33 | an empty grey chip beside a record's name for a status tag with no value | an always-visible `refListStatus` gets `visible: data?.<path> != null`; marker `/*reconciler:046-tag-null*/` | fleet | - | - |
| `types` | H32 | lookups blank: 0.43 framework entity type names answer 404 / 500 on 0.46 | in every string value, `Shesha.Domain.ConfigurationItems.Module` becomes `Shesha.Domain.Module` and `Shesha.Framework.ConfigurableComponent` becomes `Shesha.Domain.FormConfiguration`, plus the project's extra entries | fleet | `typeMapExtra` | - |
| `panels` | H30 | collapsible panel headers 52-56px tall with 8px padding all round (the migration writes the default into every device block) | a header padding still exactly 8/8/8/8 is replaced by the configured padding; an author's own padding is kept | opt-in | `panelHeaderPadding` | - |
| `optfilter` | H34 | a table shows no rows; `Entities/GetAll` answers 400 `The binary operator AndAlso is not defined ...`; the request filter is `{"and":[{...},null]}` because an optional `evaluate` item that does not resolve is sent as `null` | in a `permanentFilter` `and` / `or`, drops an optional (`required: false`) `evaluate` item when a required sibling compares the same variable; any other optional item is reported for review, never changed; no `retire` (the dropped item is not stored anywhere) | fleet | - | 0.46.1 (release notes, not verified) |
| `editmode` | H15 | controls render greyed or disabled after Edit; read-only buttons stay clickable: 0.46 maps only `true` / `'editable'`, `'readOnly'`, `'disabled'`, `'inherited'`, and anything else (`'edit'`, `'readonly'`, `false`) means disabled, and a button honours only `disabled` | wraps every `editMode` script that can return a non-canonical value so the result maps back to the 0.43 meaning; canonical results pass through; scripts whose every return is canonical are left alone; button read-only or `false` becomes `'disabled'`; marker `/*reconciler:046-editmode*/` (`retire` unwraps the scripts; the static button change has no marker and is not reverted) | fleet | - | 0.46.1 (release notes, not verified) |
| `acsort` | H38 | entity autocomplete options in database order (0.43 sent `sorting=<display property>` by default) | for `entitiesList` autocompletes with no stored sorting and a real display column, `sorting: [{propertyName: <display>, sorting: 'asc'}]`; marker: the `-s046` id suffix | fleet | - | - |
| `payload` | H39 | an action script that deletes helper fields from `data` and then spreads `data` still posts them: dynamic CRUD rejects `Property 'x' not found for '<Entity>'` and nothing saves | `data` is copied into `__payload046` before the first `delete data.`; deletes go to the copy and the copy is spread; marker `/*reconciler:046-payload-copy*/` | fleet | - | - |
| `urlwait` | H40 | URL-sourced tables stay empty: one request goes out with an empty id (400) and there is no retry | a static-visibility URL context whose mustache parameters are all id-like gets a `visible` code true only once those ids exist; marker `/*reconciler:046-url-wait*/` | fleet | - | - |
| `afterload` | H44 | values a page form derives in `onAfterDataLoad` stay empty and the handler throws part-way: `data` holds only the id, the record is `form.data` | the handler runs with `data` bound to `form.data` exactly when `data` holds only the id; handlers that write into `data` are reported and left alone; syntax-gated; marker `/*reconciler:046-afterload-data*/` (`retire` restores the original) | fleet | - | 0.46.1 (release notes, not verified) |
| `formref` | H45 | a tab hosting a subform renders an empty dashed box (`form <module>/<name> not found`) because 0.46 no longer ships the framework form | the subForm's `formId` is pointed at the project's replacement copy; a no-op without the map | fleet | `formRefMap` | - |
| `gsrefresh` | H41 | a script that refreshes a table through `globalState.<ctx>.refreshTable()` does nothing, so the list is stale until reload | the dead call is removed and a chained `Refresh table` action (action owner = the same-form context id) follows the script; contexts in a host form are reported; marker `/*reconciler:046-refresh-chain*/` | fleet | - | - |
| `normparent` | H47 | after someone opens and saves the form in the designer, a component jumps into a different container: its `parentId` still names an old parent | only the `parentId` string is rewritten to the container that holds the component in the tree; never moves, copies or deletes a component and never adds a missing `parentId` | fleet | - | - |
| `split_labels` | H20 | a field label that wraps to two or more lines overlaps the next row: the label element is fixed at the form label height, set on the label column itself | for each non-required field whose label was MEASURED as wrapping: a row container (takes the field's visibility) holding a `text` label (label-column share wide, right-aligned, 14px / 400 / theme font by default, `labelSplitFont` overrides) and a holder container holding the field with `hideLabel: true` (its label kept in `_reconcilerLabel`); required fields are skipped (their red mark would be lost) and reported; no `retire` (structural rewrite) | targeted | `labelSplit`, `labelSplitFont` | 0.46.1 (release notes, not verified) |
| `hide_empty_buttons` | H26 | a button with an empty code label renders as a blank 32px button and pushes the rows of its column down | such button containers are moved, unchanged and in order, into one row container after the columns block, with `visible: false` (kept for functionality, not shown) | targeted | - | - |
| `dialogfooter` | H35 | custom dialog footer buttons ignore their `editMode` / visibility scripts: a Save that 0.43 disabled until a condition held is always enabled | dialog form opened by one dialog: the footer items are copied into the dialog form as a right-aligned `buttonGroup` row, `footerButtons` becomes `none`, originals kept in `_reconcilerFooterButtons046`; shared dialog form: the button's condition is enforced inside its first Execute Script (warn and throw; fails open on a guard error; the button still looks enabled); markers `/*reconciler:046-footer-guard*/`, the `-ftr046` id suffixes and `_reconcilerFooterButtons046`; the first run adds the footer row and the second clears the host, so include both forms in `--only` or run twice; `retire` removes the row, restores the host's footer and removes the guard | targeted | `footerGuardMessage` | 0.46.1 (release notes, not verified) |
| `url_reflist_columns` | H36 | a column bound to a reference list on a URL-sourced table shows the raw number | a `[default]` column on a `sourceType: Url` table whose property is a reference list in the context entity's metadata gets a read-only dropdown display bound to that list (template copied from a working dropdown display in the form, else the option, else a bundled one); marker: the `-rl046` id suffix | targeted | `refListDisplayTemplate` | - |
| `readonly_strip` | H42 | saves rejected: `Property '<x>' is readonly` (calculated properties posted back; 0.46 CRUD validates the payload against metadata) | `onPrepareSubmitData` deletes the model's read-only properties and those of cascade-updated references before `return data;`; marked block `/*reconciler:046-readonly-strip*/ ... /*end:046-readonly-strip*/`; only forms on the default submit endpoints | targeted | `entityNamespacePatterns` | - |
| `urlfilter` | H43 | a URL-sourced table never requests its data ("No Data"): a leftover entity `permanentFilter` has a required mustache value that can never resolve | removes that permanent filter when every mustache starts with `data.<prop>` where `<prop>` is neither `id` nor a property of the form's model | targeted | - | - |

Not yet in this pack (found later, written per form as anchored project rules; see `render-hazards-046.md` H47-H53): sub-form script scope and record ids (H49), the Url context
dropping the endpoint's query text (H50), nested id expressions (H51), hidden row data holders (H52), the datalist double request and the first-load trap (H53), and flex-item
sizing from the device block's `dimensions` (H48). H47 is in the pack (`normparent`). `shrec.py detect` statically reports H47 and
H49-H52 (it never writes); H48 and H53 are found by measuring (`dom-chain`, `audit-requests`).

## Framework behaviours and revert markers

Framework behaviours behind the rules, the workaround, and what to REMOVE once the framework fix is deployed. The reconciler never edits framework code; do not add new workarounds
for rows marked "do not work around". Describe a new finding for the PM or repo owner to raise with the framework team; never submit or create a work item yourself.

| Framework behaviour on 0.46 | Workaround (rule) | Revert when fixed |
|---|---|---|
| `text` ignores `hidden` / `visible` | `textvis` (visibility also in the style) | remove the wrapped style (`retire` unwraps it) |
| `refListStatus` inside a subForm throws "Component with id ... is not found" (H13) | `rlshidden`; visible ones swapped for a read-only dropdown | restore `_reconcilerOriginal` |
| a throwing visibility script now means VISIBLE | `scripts` (optional chaining on render-time scripts) | none needed (harmless) |
| antd 6 fixes the form label height: wrapped labels overlap | `split_labels` (measured wrapping labels only; skips required) | undo with `_reconcilerLabel` |
| container `min-height` default and hidden components keep wrappers | `layout` (container min height 0) | - |
| `text` v5 to v7 migration shrinks fonts 12.5% and drops padding presets | `textsize` | - |
| tabs v4+ migration persists card background and border | `tabs`, `tabgap` | - |
| `htmlRender` sanitiser drops a leading `<style>`; hidden carriers are never mounted; empty output shows a placeholder | `carriers`, try/catch and hidden-span wrappers | - |
| `sectionSeparator` bottom spacing 2px (10px on 0.43) | explicit margin on each separator (`status`) | - |
| `FormConfiguration/UpdateMarkup` overwrites `modelType` (null if omitted) | the push layer always sends the stored value | - |
| `ReferenceList/GetItems` and `FormConfiguration/GetByName` removed (404) | use `ReferenceList/GetByName` and `ConfigurationItem/GetCurrent` | - |
| `editMode` `'edit'` / `true` / `'readonly'` / `false` render DISABLED; a read-only button stays clickable | `editmode` | remove the wrapper marker `/*reconciler:046-editmode*/` |
| an unresolved optional filter item is sent as `null` and answers 400 | `optfilter` | - |
| custom dialog footer buttons never evaluate scripts | `dialogfooter` | restore `_reconcilerFooterButtons046` |
| `[default]` column on a URL-sourced table shows reference-list numbers | `url_reflist_columns` | - |
| entity autocompletes send no `sorting` | `acsort` | - |
| **searchable reference-list dropdown filters by item VALUE; Binding Format = Item label stores a string** | **none: do not work around** (Item label makes search work but stores a label string that a numeric reference-list property rejects) | framework fix (`optionFilterProp: 'label'`) |
| startup sync soft-deletes reference-list items the enum lacks | data restore only | - |
| `delete data.x` is ignored in action scripts | `payload` | remove `/*reconciler:046-payload-copy*/` |
| **subform expressions cannot see the host record (`data`, `pageContext`, `query`, `parentFormValues`)**: filters never resolve and no request is sent | anchor on an id the host publishes into `page.state` (per form, a project rule) | harmless to keep; revert only if `data.id` is reliable again |
| table contexts are not in `globalState`; `contexts.<name>` has no `refreshTable` | `gsrefresh` (chained Refresh table); read `contexts` first | remove `/*reconciler:046-refresh-chain*/` |
| dynamic CRUD rejects read-only properties in the payload | `readonly_strip` | remove the marked block |
| a leftover required filter keeps a URL table from fetching | `urlfilter` | - |
| `onAfterDataLoad` gets `data = {id}`; the record is `form.data` | `afterload` | remove `/*reconciler:046-afterload-data*/` |
| a framework form the application referenced is not shipped | `formref` to the project's copy | repoint back |
| FileUpload falls back to the form's own id when `ownerId` resolves empty, then answers 400 | hide read-only lists until the parent exists; fetch the parent; uploads untouched | - |

Temporary items that must be reverted when the matching framework fix ships: `afterload`, `gsrefresh`, `formref`, `textvis`, `editmode`, `dialogfooter`; a component that never subscribes to an event it should
needs a code fix, and any configuration nudge written for it is temporary; a global CSS carrier written for table cell chrome
would be dropped by a core fix to `.sha-data-cell .ant-form-item` margins and the column mapper's `width: undefined`; a framework fix for the datatable `min-height: 44px` rule would
make a row-geometry theme setting unnecessary. Priority wording used when describing findings for the framework team: P1 prevents an important feature from functioning, P2
important UX enhancement, P3 developer experience, P4 nice-to-have polish.

## Withdrawn approaches

Do not repeat these. The lessons are generic.

| Approach | Why it was withdrawn |
|---|---|
| application or framework CSS (editing the portal's global stylesheet for labels and container heights) | rejected in review: configuration level only (theme settings, form configuration, per-component settings, negative margins and paddings) |
| a hidden stylesheet component per form for scoped CSS | rejected in review: use each component's own settings; every such component was removed. The one exception is a single global carrier approved in writing in `decisions.md` for chrome no component setting can reach |
| a negative margin on BOTH sides of `columns` | horizontal scrollbars in `overflow: auto` containers and tab bodies; the `layout` rule restores the left inset only (H23) |
| container `minHeight 0px` on every container from the 0.46 defaults | reverted fleet-wide: replaced by the `layout` rule, which skips floors the author or the reference stored |
| field margin bottom `2` | no effect: it collapses with the form row's own margin; `-3` is the working value (H21) |
| theme defaults for tabs, text, container and htmlRender | no effect: migrations write `desktop` values that beat the theme |
| working around the searchable reference-list dropdown with `Binding Format = Item label` | search works but the form then stores and sends a label string that a numeric reference-list property rejects |
| splitting labels that render on one line | false positives add height; measure first, then split only labels measured as wrapping (undo with `_reconcilerLabel`) |
