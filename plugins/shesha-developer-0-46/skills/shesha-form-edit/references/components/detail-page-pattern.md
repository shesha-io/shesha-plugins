# Detail page anatomy: header band, KIB, labels

The canonical `<entity>-details` page layout. Read before building or normalizing any detail form. Subtable tabs are covered in [junction-subtables.md](junction-subtables.md); add dialogs in [add-dialogs.md](add-dialogs.md); the four style channels in `style-channels.md` (in `shesha-design-system`).

"KIB" below = the key-info-bar **built from plain `container`s** (a `flexDirection:"row"` container of stat columns). Do NOT use the `KeyInformationBar` component — deprecated in this pattern (see [containers.md](containers.md)).

---

## Surfaces: every content group is a CARD, not a container

Stated first because this file previously never mentioned `card` once, and the result was a
detail page built from **56 containers and zero cards** — flat, borderless groups where the
design clearly wanted surfaces.

- **A group of fields the user reads as a unit is a `card`.** Passenger details, Payment,
  Itinerary, each tab's content — cards. Compose [`card-with-header-strip`](../block-library.md).
- **Heading when the group needs a title, headless when it doesn't.** `hideHeading: true` turns a
  card into a plain surface (background, hairline, radius) with no title row — that is the whole
  trick, and it is what makes a headless card strictly better than a bare container.
- **`container` belongs INSIDE a card**, for layout only — flex rows, two-cell field rows, spacing.
  A container is not a surface: it has no background, border or radius by convention.
- **The page shell is also a card** ([containers.md](containers.md) "page shell").

**The trap that causes containers-everywhere:** a card's children go in **`content.components`**
(and `header.components`), while every other grouping component uses `components`. A generic
`mk(type, props, children)` builder that pushes children into `components` therefore cannot emit a
card without a special case — so the component with the irregular shape becomes the one that gets
skipped, and the whole page degrades to containers. If you are writing a build script, give it a
card emitter **before** you start, not after you notice the page looks flat.

## Canonical anatomy

```text
.sha-page root
├─ header band            container: display:"flex", flexDirection:"row", justifyContent:"space-between", alignItems:"stretch"
│  ├─ banner              container: legacy style string carries flex:'1 1 auto' (leave it — identical across forms)
│  │  ├─ title row        container: dimensions.minHeight:"fit-content"
│  │  │  ├─ title         text: contentDisplay:"name", propertyName:"<titleProp>", textType:"paragraph", fontSize:"text-xl"
│  │  │  └─ status chip   refListStatus bound to <statusProp> (style: h24/auto, 1px #d9d9d9 border, radius 4; FILL is data-driven per reflist item — never force it)
│  │  └─ subtitle wrap    container → text: contentType:"custom", font.color:"#c7c7c7", size 12.5
│  └─ KIB                 container: flexDirection:"row", alignItems/alignSelf:"stretch", gap:0, flexWrap:"nowrap"
│     └─ column ×N        container per stat: label text + value component (see next section)
├─ sectionSeparator       (orange via theme accent)
├─ page-heading toolbar   container: Edit/Cancel/Save buttonGroup, justifyContent:"left" (NOT right/flex-end)
├─ sectionSeparator
├─ detail tabs            tabs: "Details" (+ optional grouped tabs) — 50/50 columns grid (section 5)
├─ sectionSeparator
└─ subtable tabs          tabs: one per child/junction collection → junction-subtables.md
                          (toolbar containers there carry className "sha-index-table-control")
```

**`sha-page-content` rule:** if the detail-tabs + subtable-tabs sit inside a wrapper carrying `className:"sha-page-content"`, that wrapper MUST also carry `no-padding` → `"sha-page-content no-padding"` on the base `className` AND `desktop.className`/`tablet.className`/`mobile.className` (whichever contain it). The framework stylesheet defines `.sha-page-content:not(.no-padding){ padding:12px }` — without the modifier, content insets 12px off the header grid. Don't hand-tune `stylingBox`; the class is the intended escape hatch. Find the wrapper **by className, not by name**.

**Detail-area tabs:** when one "Details" tab is cramped, bucket fields into 2+ tabs (e.g. Details / DevOps Details / Specification): extract leaf field components preserving full config (reflists, FK `entityType`, `editMode`), rebuild on the 50/50 grid, omit empty tabs. **Count fields before/after — field loss is the #1 re-layout risk.**

---

## KIB columns + dividers

**NEVER build dividers as separate elements.** Two failed mechanisms, both deleted from production:

| Divider element | Why it fails |
|---|---|
| Empty border-only container | Collapses to **0×0**: an empty `width:auto` + `height:100%` child of a `height:auto` + `alignItems:flex-start` parent resolves zero-size — a border on a zero-size box paints nothing (percentage heights need a definite-height or stretching parent) |
| `sectionSeparator` vertical line | Needs a hard-coded `lineHeight` (e.g. `"150px"`) that sets the line LENGTH independently of content and drags the whole band taller |

**Correct pattern — stretch + border-left, flush by construction:**

| Element | Stamp (base + desktop + tablet + mobile) |
|---|---|
| Band + KIB container | `alignItems:"stretch"`; KIB also `alignSelf:"stretch"`, `gap:0`, `flexWrap:"nowrap"`, all height caps (`minHeight`/`maxHeight`) → `"auto"` |
| Every column | `alignSelf:"stretch"`, `justifyContent:"flex-start"`, `alignItems:"flex-start"`, `flexDirection:"column"`, padding `16/16/2/8` (top/right/bottom/left via stylingBox) |
| Columns 2+ | `border.borderType:"custom"` + `border.border.left = {"width":"1px","style":"solid","color":"#d9d9d9"}` |

- The last column's 16px right padding IS the edge spacing — don't add margin.
- Border sub-shape is a composite object — `clean-form-config` may flag it as a false positive; do NOT strip.
- Intermediate wrappers between band and KIB: stamp the stretch chain up THROUGH them until the `justifyContent:"space-between"` header — conditional on `type === 'container'` (some forms hold label text + value directly in the column, no wrapper).
- Verify computed, not visually: column height must equal KIB height, `border-left: 1px solid rgb(217,217,217)`.

---

## Dead-space checklist

Three independent causes of header dead space — **all hide on breakpoint objects** (`desktop`/`tablet`/`mobile`), invisible at base level. Check every one:

1. **Column `dimensions.minHeight`** hard-coded (e.g. `"150px"` when content is ~84px) → set `"auto"`.
2. **`sectionSeparator` `lineHeight` prop** — NOT `dimensions.height` (that's a red herring) — sets the vertical line's LENGTH and drags the band to its value regardless of column height. Rendered element: `div.vertical-separator`. (Moot once dividers are deleted per section above.)
3. **`alignSelf:"center"` on columns + mixed label `font.align`** → different-height columns centre at different label tops. Fix: `alignSelf`/`alignItems` → `"flex-start"`, all label `font.align` → `"left"`, normalize `paddingTop` across columns.

Also uncap `maxHeight` (`"150px"` → `"auto"`) on banner + KIB so compacted content isn't clipped.

**Title-row scrollbars** (titles "become scrollable"): every v7 container inner renders `overflow:auto` HARD-CODED — the markup `overflow` prop is a no-op in view mode. A stretched band squeezes banner flex children (flex-shrink defaults to 1). Fix: `dimensions.minHeight:"fit-content"` (+ `height`/`maxHeight` `"auto"`) on title wrap, title row, AND subtitle wrap, all breakpoints — `dimensions` is the only channel reaching the container's outer div. See `style-channels.md` (in `shesha-design-system`).

**When a stamped prop doesn't render at all**, or padding appears that no stylingBox explains: grep the component and every ancestor for a truthy legacy `style` / `desktop.style` JS-string FIRST — it renders as inline styles that override everything (`style-channels.md` (in `shesha-design-system`)).

---

## Text component binding traps

| Goal | Recipe | Trap avoided |
|---|---|---|
| Title bound to entity prop | `contentDisplay:"name"` + `propertyName:"<titleProp>"` (+ `content:"{{data.<titleProp>}}"`, `textType:"paragraph"`, `fontSize:"text-xl"`, `strong:true` (runtime-verified; not in the groups index — clean-form-config may flag it; do NOT strip), base `font.size` 15.5 + breakpoint `font.size` 17.5) | A plain mustache string in `content` with `contentDisplay:"content"` renders **EMPTY** |
| Transform a bound value (e.g. truncate to 100 chars) | `contentDisplay:"content"` + code-mode content: `"content": {"_mode":"code","_code":"...return ...;"}` — `content` is `jsSetting:true`, evaluated with `data` in scope | Truncate the **STRING**, not CSS `ellipsis` — a non-wrapping long text sets the flex item's min-width floor to full text width and pushes the KIB out |
| Gray subtitle | `contentType:"custom"` + `font.color:"#c7c7c7"` | Without `contentType:"custom"`, `font.color` is **IGNORED** (renders antd default `rgba(0,0,0,0.88)`); `font.size` works regardless |

**Pixel parity = COMPONENT TRANSPLANT, not property tweaks.** Designer-output components carry bloat (~167 keys vs a clean ~35-key template) with hidden extras like `font.color:"#000000"` that render visibly different despite identical-looking font size/weight. A one-directional diff misses extra keys — do a **bidirectional full-key diff** and compare **COMPUTED styles in-browser**. Transplant the template's whole text component, preserving target `id`/`parentId`/`componentName`/`propertyName` (for subtitles also keep `content`).

---

## Labels and columns

- **Field-level `labelCol` is silently IGNORED** — the renderer applies form-level `formSettings.labelCol`/`wrapperCol` (e.g. 8/16) to **every** field. (The server stores the field-level value; it just never renders.)
- Consequence: a full-width field's label column is 8/24 = 33% of page width; with default `labelAlign:"right"` the label looks centered/indented and falls off the 2-column grid.
- **Fix: put the lone field in a 50% LEFT column** — `width:"50%"`, `minWidth:"200px"`, `maxWidth:"50%"` — keeping `labelAlign:"right"`. Verified: label/value edges then exactly match the left-column fields.
- **NEVER `labelAlign:"left"`** on full-width fields — it pushes the label to the far page edge, which is not "align with the grid".
- **Net rule: every detail field lives in a 50% column** (100% width only for true full-span textAreas). Detail rows = explicit v7 width containers (`width:50%`/`minWidth:200px`/`maxWidth:50%`, `gap:0`) — NOT v6 `flex:1 1 0` + `gap:16` inline `style` strings.

---

## Locating elements structurally

Container names vary across forms (`container60` vs `hdrBand`, `pageContent` vs an auto-generated name). **Find by shape, never by name:**

| Element | Locator |
|---|---|
| Header band | `components[0]` of the form |
| Banner | First `container` child of the band |
| Status chip | The `refListStatus` component |
| Title | The `text` with `contentDisplay:"name"` |
| Subtitle | The gray `#c7c7c7` text |
| KIB | The `flexDirection:"row"` container (may be nested one wrapper deeper — walk through single-child containers) |
| KIB divider (legacy, to delete) | KIB child whose subtree has NO content leaf (only containers/sectionSeparators); columns = the rest |
| Content wrapper | The container whose `className` contains `sha-page-content` |
| Subtable toolbar / add wrapper | By subtree content (has quickSearch/pager vs has the buttonGroup) — see [junction-subtables.md](junction-subtables.md) |

When deleting/inserting nodes in a transform, guard with a component-count delta (e.g. delta must equal nodes removed). Clone repeated structure with fresh GUID ids AND fresh componentNames — never mutate the template's originals.

Verify with `getBoundingClientRect`/`getComputedStyle`, never screenshots (scaling makes 0px offsets look like 10–15px). The frontend caches form configs in IndexedDB — clear from a static page like `/favicon.ico`, not in-app (`deleteDatabase` blocks while the app holds connections). See [../verification.md](../verification.md).

---

### Worked example (project-specific)

`module-definition-details` (module `Shesha.RequirementsStudio`) is the live reference — all 17 RS detail forms were normalized to it:

- Band `container60` > [banner `container61`, KIB `mddKibCtr`]; 13 other forms use `hdrBand`/`hdrLeft` naming — same shape.
- Title binds `name`; status chip = `refListStatus` on `RsStatus`; subtitle gray `#c7c7c7`.
- KIB: Licensing Model dropdown + Front End / Back End switches; columns 2+ carry the `#d9d9d9` border-left; verified computed column height == KIB height (84px), `border-left 1px solid rgb(217,217,217)`.
- Toolbar `mddPageHeading` `justifyContent:"left"` (Edit at x=70 on every form); `formSettings.labelCol:8`/`wrapperCol:16`, layout `horizontal`.
- Known parasites fixed during normalization: VDD/BPD `container60` legacy `style` string (10px vertical pad + 25px left indent) nulled; `container52` KIB wrapper deleted and `mddKibCtr` re-parented; `pageContent`/`container001d3d` wrappers got `no-padding`.
