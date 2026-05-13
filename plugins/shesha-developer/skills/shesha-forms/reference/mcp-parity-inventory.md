# MCP Parity Inventory

Running tracker for bringing the `shesha-forms` skill up to feature parity with the Shesha MCP server (`C:\Code\automation-jan\Updated\Shesha-Mcp-Server`). Updated as work progresses.

**Strategy**: keep the skill JSON-first and LLM-free. The calling model (Claude) is the intelligence — no need for embedded `FormGenerator` LLM pipelines or FAISS embeddings. Cherry-pick the capabilities the MCP has and the skill doesn't, port them as direct-API recipes that fit the skill's progressive-disclosure shape.

---

## ✅ Done

- [x] **Fix broken reference links** — `api.md` → `reference/api.md`, `components.md` → `reference/components.md`, `assets/component-properties.json` → `reference/assets/component-properties.json`. The skill body had pointed at the wrong directory after the earlier `reference/` reorganization.
- [x] **Add Step 3 branch — explicit edit vs create** — introduced sub-steps 3a (edit) and 3b (create) with three seed strategies (template / inline-markup / blank) and explicit routing into Steps 4-8.
- [x] **Skip-conditions for Step 4 (Fetch)** — blank and inline-markup create seeds skip the GetJson round-trip.
- [x] **Create-flow note on Step 8 (Push)** — initial body push for blank/inline seeds; second `UpdateMarkup` with `access: 5` for anonymous forms.
- [x] **Remove MCP dependency from Step 9** — URL is now derived from `formSettings.access` (`/no-auth/<m>/<f>` if anonymous, `/dynamic/<m>/<f>` otherwise) instead of asking the MCP for a test URL.
- [x] **Remove "MCP unreliable" gotcha** — no longer mentioning the MCP at all.
- [x] **Correct module endpoint** — `/api/services/app/Module/GetAll` (verified against running backend; matches MCP's `module_api.py:252`). Earlier draft had `/api/services/Shesha/Module/GetAll` which is wrong.
- [x] **Add ModelConfigurations property-lookup reference** — `reference/model-configurations.md`. Two-step recipe (EntityConfig/GetMainDataList → ModelConfigurations/{id}), property → component mapping table, gotchas for dict-shaped `entityType` and the by-name 404. Not yet wired into the skill body.
- [x] **Semantic search across entities / modules / forms / reference lists** — `reference/semantic-search.md`. Two-tier algorithm: string-similarity (Jaro-Winkler + Jaccard + substring) shortlist, then calling-model rerank, with skip-on-high-confidence (`score >= 0.95` AND clear gap → use directly). Self-contained node block, no embeddings, no API keys. Replaces the MCP's FAISS + Claude-Haiku stack with the calling-model's context. Cross-linked from `model-configurations.md`.
  - **Bonus** — discovered that `/api/services/app/ReferenceList/GetAll` (the MCP's hardcoded route in `reference_list_api.py`) **404s on stock recent Shesha**. The working endpoint is `/api/dynamic/Shesha/ReferenceList/Crud/GetAll`. Documented in `semantic-search.md`.
- [x] **Wire ModelConfigurations + semantic-search into the SKILL.md body** — Step 3a gains a fallback to form-search when `GetByName` returns null. Step 3b inserts a new point 2 ("Resolve `modelType` if entity-bound") that combines fuzzy entity resolution + property-list fetch + filtered field proposal; existing points 2-5 renumber to 3-6 and the routing paragraph mentions using the property list for blank seeds. Step 6 gains three new core-principle bullets: property-reference verification against the bound entity, reference-list-binding verification, and a cross-cutting fuzzy-resolution rule.
- [x] **get_form_test_url equivalent** — `reference/form-test-url.md`. Step 9 now auto-fetches a sample entity id via `/api/services/app/Entities/GetAll?entityType=<modelType>&properties=id&MaxResultCount=1` for entity-bound forms, builds `/dynamic/<m>/<f>?id=<guid>` (authenticated) or `/no-auth/<m>/<f>?id=<guid>` (anonymous, `access === 5`). Handles empty-table case gracefully with a clear note. **Improves on the MCP** — the MCP's `FormUrlGenerator._build_url_path` only ever emits `/dynamic/`, never handles anonymous forms.
- [x] **Mandatory entity binding when `modelType` is set** — Step 3b.2's property-list output is no longer "drives the default field set for blank-seed forms"; it's now **mandatory for all seed strategies**. Step 6 gains a new core principle: every bindable input on an entity-bound form must have a real `propertyName`, never a placeholder. Rebinding strategy for template seeds: (1) label exact match → property label/name, (2) semantic-search fallback on the property list, (3) ask user on remaining ambiguity, (4) leave non-bindable components (buttons, layout) alone. Reference-list-item properties also copy `referenceListName` + `referenceListModule` onto dropdowns.
- [x] **Template placeholder substitution (`//*NAME*//` slots)** — `reference/template-placeholders.md`. Catalogues the verified placeholders on `Shesha/details-view` (`//*TITLE*//`, `//*KEYINFOBAR*//`, `//*DETAILSPANEL*//`, `//*CHILDTABLES*//`) and `Shesha/table-view` (`//*TABLEFILTER*//`, `//*TABLECOLUMNS*//`) with replacement strategies, the detection regex `/^\/\/\*[A-Z]+\*\/\/$/`, the substitution algorithm (walk → swap → re-scan), a worked example for Person, and gotchas around id preservation and dual-field markers. Step 6 in SKILL.md now opens with a "if template seed → substitute first" callout before the core principles.
- [x] **Template-placeholder catalog refinement** — `template-placeholders.md` and `components.md` updated based on canonical examples at `/examples/key-info-bar.json` and `/examples/table-view-selector.json`. Closed-catalog declaration (six placeholders, no unknown branch). Catalog corrections: `//*CHILDTABLES*//` filter is `dataType: "array"` AND `dataFormat: "entity"` (not "many-entity"); array-of-entity `entityType` is the flat `{fullClassName, name, module}` shape, not the FK `{_displayName, ...}` shape; child tables use `dataTableContext` + supporting datatable components (not a non-existent `childTable` component); 2+ child tables wrap in `tabs` with property's `label` as tab label; `//*TABLEFILTER*//` → single `tableViewSelector` (not generic filter inputs); `//*TABLECOLUMNS*//` → just a `datatable` (supporting `quickSearch`/`filter`/`pager` already exist as siblings in the template). New `components.md` sections for `KeyInformationBar` (PascalCase, columns-as-array idiom with container[text-label] + readOnly+hideLabel value) and `tableViewSelector` (`filters[]` with id/name/sortOrder/optional-expression, Default entry omits expression, JsonLogic with `var` + `evaluate`/`mustache`).
- [x] **Natural-language template inference** — `reference/templates.md`. Two templates are first-class: `Shesha/details-view` (view/edit one record) and `Shesha/table-view` (browse a collection). Everything else → blank seed (login/anonymous, dashboards, create-only forms, custom layouts). Decision table maps user intent ("details", "edit X" → details-view; "list of Xs", "browse Xs", plural → table-view; "login", "dashboard", explicit "from scratch" → blank). Three classification rules: intent matches + entity-bound + no explicit blank override. Explicit user naming always wins over inference. Template ids resolved at runtime via `GetByName` (no hardcoded ids). SKILL.md Step 3b.3 rewritten to put the explicit-name flow first, then intent inference via templates.md.
- [x] **Tighten skill to be API-first, not filesystem-exploratory** — new "Operating principles" callout inserted before Step 1 in SKILL.md. Explicit do-NOT list (grep codebase, read DTOs/.csproj/swagger artefacts, `ls`/Glob folders to discover what's "available") and do list (read skill's own references, read component-properties index, ask user when blocked). Step 1 retooled around a single targeted Glob (`src/*.Web.Host/Properties/launchSettings.json`) — removed the PBF-specific hardcoded path that was both project-specific and inadvertently licensing broader filesystem exploration. Triggered by an actual run where the model grep'd for "Organisation", read `obj/Debug/EndpointInfo/OrganisationCrud.json`, and `ls`ed multiple directories before finding the canonical `EntityConfig` + `ModelConfigurations` API path it should have used immediately. Feedback also saved to user memory.

## 🟡 In progress

_(nothing currently in progress)_

## ⏳ To do — high value

- [ ] **Module pre-validation in Step 3b.1** — before sending Create, check the resolved module has `isEnabled: true` and `isEditable: true`. Avoids the cryptic "Form is not editable" backend error. MCP does this at `validators.py:104-168`.
- [ ] **Form name kebab-case validation** — regex `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` check before sending Create. Matches MCP's `validators.py:232`. Catches typos like `Member-Create` (capitalized) or `member create` (spaces) before they hit the backend.
- [ ] **Form name uniqueness pre-check** — query `GetAll` with `module.name === X && name === Y` filter before sending Create. Surfaces a friendlier "already exists" error than the backend's generic duplicate response.
- [ ] **Versioning operations** — document `CreateNewVersion`, `CancelVersion`, `UpdateStatus` for published forms. The skill currently assumes `versionStatus: 3 (Draft)` and modifies in place; this silently fails for `versionStatus: 4 (Live)` forms. Needs detection in Step 4 ("this form is Live, do you want to create a new version?") plus the API recipes.

## ⏳ To do — lower value / optional

- [ ] **Stricter Step 7 validation** — port these MCP component-level checks:
  - `EntityPicker.entityType` required (MCP `validators.py:376-377`)
  - `Dropdown` / `radio` / `checkboxGroup` with `dataSourceType: referenceList` → `referenceListId` required (MCP `validators.py:379-381`)
  - `DatatableContext` requires `dataSourceEntity` or `entityType` (MCP `validators.py:383-387`)
- [ ] **Document `type` + `isTemplate` fields on Create DTO** — MCP includes them ([form_configurations_api.py:177-180]); skill omits. Likely optional but worth confirming what `type` controls (FormType enum?) and whether `isTemplate: true` makes the form show up in the template picker.
- [ ] **Token cache** — disk-backed, short TTL. Saves ~300ms per skill invocation. Discussed, not yet committed.
- [ ] **Module list cache** — disk-backed, 24h TTL, keyed by `baseUrl`. Lower value than token cache; introduces staleness risk if a module is added mid-session.
- [ ] **`getJson` for unauthenticated forms** — verify the GetJson endpoint works on `access: 5` forms with the bearer token, or whether a separate anonymous fetch path is needed.

## ❌ Won't do — out of scope

- [ ] **XML representation / round-trip** — the skill works in JSON. The MCP needs XML because its embedded LLMs author XML more reliably than nested JSON with `IPropertySetting` wrappers. Claude (the calling model in our setup) writes JSON directly, so no intermediate is needed.
- [ ] **FAISS / embeddings-based semantic search** — too heavyweight for a SKILL.md. Use a `GetAll` with `Contains` filter as a poor-man's substitute (see "search_forms equivalent" above).
- [ ] **Embedded LLM form generation** — the MCP's `FormGenerator.generate()` makes 4+ LLM calls (Claude Sonnet for analysis + design, Azure OpenAI for related entities). Claude does all of this natively when given the property index and `reference/components.md`. No need to re-host an LLM pipeline inside the skill.
- [ ] **`'dict' object has no attribute 'lower'` crash defense** — this was a Python-specific data-model bug in the MCP's `EntityConfigDto.from_dict`. The skill doesn't have an analogous serialization layer; it just handles dict-shaped `entityType` correctly per `reference/model-configurations.md` gotcha #1.

---

## Endpoint reference — verified against running backend

| Purpose | Path | Method | Status |
|---|---|---|---|
| Auth | `/api/TokenAuth/Authenticate` | POST | ✅ verified |
| Module list | `/api/services/app/Module/GetAll` | GET | ✅ verified, in `api.md §7` |
| Entity list | `/api/services/app/EntityConfig/GetMainDataList` | GET | ✅ verified, in `model-configurations.md` |
| Entity properties (by id) | `/api/ModelConfigurations/{id}` | GET | ✅ verified, in `model-configurations.md` |
| Entity properties (by name) | `/api/ModelConfigurations?name=&namespace=` | GET | ⚠ unreliable — 404s for code-defined entities |
| Sample entity row | `/api/services/app/Entities/GetAll?entityType=<full>&properties=id&MaxResultCount=1` | GET | ✅ verified, in `form-test-url.md` |
| Reference list list | `/api/dynamic/Shesha/ReferenceList/Crud/GetAll` | GET | ✅ verified — MCP's `/api/services/app/ReferenceList/GetAll` 404s on this build |
| Form by name | `/api/services/Shesha/FormConfiguration/GetByName` | GET | ✅ in `api.md §3` |
| Form markup | `/api/services/Shesha/FormConfiguration/GetJson` | GET | ✅ in `api.md §4` |
| Form create | `/api/services/Shesha/FormConfiguration/Create` | POST | ✅ in `api.md §7` |
| Form update markup | `/api/services/Shesha/FormConfiguration/UpdateMarkup` | PUT | ✅ in `api.md §5` |
| Form import (multipart) | `/api/services/Shesha/FormConfiguration/ImportJson` | POST | ✅ in `api.md §6` |
| Form list (browse) | `/api/services/Shesha/FormConfiguration/GetAll` | GET | ✅ in `api.md §8` |
| Form new version | `/api/services/Shesha/FormConfiguration/CreateNewVersion` | POST | ⏳ not yet documented |
| Form cancel version | `/api/services/Shesha/FormConfiguration/CancelVersion` | POST | ⏳ not yet documented |
| Form update status | `/api/services/Shesha/FormConfiguration/UpdateStatus` | PUT | ⏳ not yet documented |

---

## Release checklist (before pushing to `shesha-io/shesha-plugins`)

- [ ] Bump `plugin.json` version — current `1.6.5`, target `1.6.6` (patch — enhancements to existing skill).
- [ ] Verify all in-body links resolve (no `](api.md)` etc. — should all be `](reference/api.md)`).
- [ ] Confirm grep on `MCP`, `mcp`, `localhost:8000` returns zero matches in the skill folder.
- [ ] Commit with `[fix]- shesha-forms: remove MCP dependency, add create branch, fix references` (or split into multiple commits per the change set).
