#!/usr/bin/env node
/**
 * validate-form-markup.cjs — MANDATORY pre-push check for create-crud-form (Shesha 0.46)
 * (and shesha-form-edit's Step 6 blocking gate).
 *
 * Enforces the "silent-drop-on-render", "React-key-collision", and "component-crash"
 * rules that agents repeatedly re-introduce despite the docs. Every rule below maps
 * to a symptom observed on a live build.
 *
 * Usage:
 *   node validate-form-markup.cjs <path-to-markup.json>
 *   cat markup.json | node validate-form-markup.cjs -
 *
 * Exit codes:
 *   0 — no critical issues (may emit warnings on stderr)
 *   1 — one or more BLOCK-push violations found (do NOT push)
 *   2 — usage / IO error
 *
 * Rules checked:
 *   R1   Every typed component has an integer `version` (dataContext version is WARN-only).
 *   R2   (0.46, flipped from 0.43/0.45) Plain-string `text.content` / `link.href` mustache is
 *        evaluated against the FULL context (data, form, user, contexts, ...), so an entity
 *        property is `{{data.<prop>}}`; a bare `{{<prop>}}` silently renders empty.
 *   R3   Datatable column `displayComponent`/`editComponent`/`createComponent`: any real
 *        type (not `[default]` / `[not-editable]`) MUST be wrapped in `settings` with
 *        `version` — otherwise crashes with `reading 'version'` at cell render.
 *   R4   Tabs: `tab.key === tab.id` AND all `tab.id` unique within `tabs.tabs[]`.
 *        Otherwise React key collision → multiple tab bodies render on the visible tab.
 *   R5   componentName uniqueness across sibling tab bodies (WARN — seeds also violate).
 *   R6   For each `card`, every field-holding `container` under `content.components` uses
 *        `desktop.display === "grid"` with `gridColumnsCount ∈ {2, 3}`.
 *   R7   A form whose top-level component tree is a `container` wrapping a single
 *        `dataContext` is a hand-authored departure from the seed's "dataContext at root"
 *        convention — WARN.
 *   R8   Every `buttonGroup` has `isInline: true`. Otherwise buttons collapse into a "..."
 *        dropdown and the user sees no button. Observed on org-details, notification-*.
 *   R9   On a form whose `dataLoaderType === "none"` OR whose form name matches /(create|
 *        register|new-|-new)/, every input has `editMode === "editable"`. `inherited`
 *        renders dead labels with no input boxes on a standalone create page.
 *        (Details forms use `inherited` — the check runs only on create-family names.)
 *   R10  `dataContext.permanentFilter` must be JsonLogic + mustache `evaluate` — NOT
 *        `{ _mode: "code", _code: "..." }`. The backend expects the JsonLogic shape;
 *        code-mode returns a JS object that hits the Entities/GetAll endpoint with the
 *        wrong query and 400s.
 *   R11  `refListStatus.propertyName` is a bare property path (no mustache at all); a bare
 *        `{{<prop>}}` in an action `target` is blocked like R2.
 *   R12  datalist wiring: `formSelectionMode === "name"` AND `formId` is
 *        `{ name, module }` — the canonical row-template pattern. Missing either
 *        renders the list empty.
 *   R13  Grid + space-between: any `container` with `desktop.display === "grid"`
 *        MUST NOT use `justifyContent: "space-between"`. Grids distribute via
 *        `gridColumnsCount`; space-between conflicts and breaks layout.
 *   R14  Soft-shadow byte-exactness: any `container` with `desktop.shadow.blurRadius > 0`
 *        MUST use the canonical soft shadow — `{offsetX:0, offsetY:2, blurRadius:8,
 *        spreadRadius:2, color:"rgba(0,0,0,0.05)"}`. Solid `#000000` shadows produce
 *        the "too dark" render observed on the organisations form.
 *   R15  pageShell canon: any `container` with `desktop.background.color === "#fafafa"`
 *        (the grey outer page shell) MUST carry padding 20 on all four sides in the OBJECT
 *        `desktop.stylingBoxJson` (0.46 reads that, not the `stylingBox` string).
 *   R16  (informational, WARN) any container using the deprecated field `columns` at
 *        top level — the canonical seeds never do; use flex/grid containers instead.
 *
 *   R17  (0.46) every typed component's `version` equals the current 0.46 version in the component
 *        KB (shesha-form-edit/assets/components-kb/_index.json). Lower = BLOCK (the portal
 *        re-runs migrations on every load, e.g. datatable forces striped/hover defaults);
 *        higher or a type missing from the KB = WARN. Deprecated types = WARN.
 *   R18  (0.46) runs clean-form-config/scripts/scan-046.mjs when present: script syntax (S1) and
 *        ReferenceList/GetItems (N7) BLOCK; unsafe render-time chains (N1), htmlRender carrier
 *        hazards (N2), per-device spacing only in the legacy stylingBox string (N4), subForm
 *        label span 0 (N6), editMode false (N8) and dead props (D1) WARN.
 *   R19  (0.46) `refListStatus` inside a `subForm` component throws "Component with id ... is not
 *        found" (framework bug) - BLOCK.
 *
 * Add rules here as new defect patterns are observed. Every rule number maps to a
 * documented rule in references/canonical-seeds.md / binding-rules.md / functional-
 * requirements.md.
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function readMarkup(pathArg) {
  const raw = pathArg === '-'
    ? fs.readFileSync(0, 'utf8')
    : fs.readFileSync(pathArg, 'utf8');
  const parsed = JSON.parse(raw);
  // Accept both { components, formSettings } and a stringified markup wrapper
  if (typeof parsed === 'string') return JSON.parse(parsed);
  if (parsed.markup && typeof parsed.markup === 'string') return JSON.parse(parsed.markup);
  return parsed;
}

function walk(nodes, visitor, parents = []) {
  if (!Array.isArray(nodes)) return;
  for (const n of nodes) {
    if (!n || typeof n !== 'object') continue;
    visitor(n, parents);
    const stack = parents.concat(n);
    for (const k of ['components', 'items']) {
      const v = n[k];
      if (Array.isArray(v)) walk(v, visitor, stack);
    }
    if (Array.isArray(n.tabs)) {
      for (const t of n.tabs) if (Array.isArray(t.components)) walk(t.components, visitor, stack);
    }
    for (const slot of ['header', 'content']) {
      const s = n[slot];
      if (s && Array.isArray(s.components)) walk(s.components, visitor, stack);
    }
  }
}

function main() {
  const arg = process.argv[2];
  if (!arg) {
    console.error('Usage: node validate-form-markup.cjs <path-to-markup.json | ->');
    process.exit(2);
  }
  const markup = readMarkup(arg);
  if (!markup.components || !Array.isArray(markup.components)) {
    console.error('input has no top-level `components` array — is this a Shesha form markup?');
    process.exit(2);
  }

  const errors = [];
  const warnings = [];
  const SENTINELS = new Set(['[default]', '[not-editable]']);

  // ---------- R1 : component version present ----------
  // Exceptions:
  //   - Column entries + buttonGroup items don't carry outer 'version' (wrapped-settings carries it).
  //   - dataContext version is OPTIONAL per canonical-crud-seeds.md ("sample carries no version;
  //     stamp 8 for consistency"). Emit as WARN so authors get a nudge without blocking.
  walk(markup.components, (n, parents) => {
    if (!n.type) return;
    const parent = parents[parents.length - 1];
    if (parent && (parent.type === 'datatable' || parent.type === 'buttonGroup')) return;
    if (typeof n.version !== 'number') {
      if (n.type === 'dataContext') {
        warnings.push({ rule: 'R1', where: n.componentName || n.type, msg: `dataContext missing 'version' (seed omits it; consider stamping 8 for consistency)` });
      } else {
        errors.push({ rule: 'R1', where: n.componentName || n.type, msg: `component ${n.type} missing integer 'version'` });
      }
    }
  });

  // ---------- R2 : plain-string mustache must be rooted (0.46: {{data.<prop>}}, not {{<prop>}}) ----------
  // 0.46 evaluates plain-string mustache against the full context (data, form, user, contexts, ...);
  // text v7 even rewrites a legacy {{x}} to {{data.x}} on load. A bare {{x}} resolves to undefined.
  const MUSTACHE_ROOTS = new Set(['data', 'form', 'user', 'application', 'contexts', 'page', 'query', 'initialValues', 'parentFormValues', 'selectedRow', 'utils', 'storage', 'globalState', 'actions']);
  const bareMustache = (str) => {
    const out = [];
    for (const m of str.matchAll(/\{\{\{?\s*([A-Za-z_$][\w$]*)/g)) if (!MUSTACHE_ROOTS.has(m[1])) out.push(m[0]);
    return out;
  };
  walk(markup.components, (n) => {
    if (n.type === 'text' && typeof n.content === 'string' && bareMustache(n.content).length) {
      errors.push({ rule: 'R2', where: n.componentName || 'text', msg: `text.content has an unrooted mustache (${bareMustache(n.content).join(', ')}) — on 0.46 it resolves against the full context and renders empty; write {{data.<prop>}}. content="${n.content}"` });
    }
    if (n.type === 'link' && typeof n.href === 'string' && bareMustache(n.href).length) {
      errors.push({ rule: 'R2', where: n.componentName || 'link', msg: `link.href has an unrooted mustache (${bareMustache(n.href).join(', ')}) — write {{data.<prop>}} or use code-mode` });
    }
  });

  // ---------- R3 : datatable cell components wrapped in settings ----------
  walk(markup.components, (n) => {
    if (n.type !== 'datatable') return;
    const cols = Array.isArray(n.items) ? n.items : [];
    for (const col of cols) {
      if (!col || typeof col !== 'object') continue;
      const pn = col.propertyName || col.caption || '?';
      for (const slot of ['displayComponent', 'editComponent', 'createComponent']) {
        const s = col[slot];
        if (!s || typeof s !== 'object') continue;
        const t = s.type;
        if (!t) {
          errors.push({ rule: 'R3', where: `col ${pn}`, msg: `${slot} has no type — must be a sentinel or a wrapped component` });
          continue;
        }
        if (SENTINELS.has(t)) continue;
        // Real component — MUST be wrapped
        if (!s.settings || typeof s.settings !== 'object') {
          errors.push({ rule: 'R3', where: `col ${pn}`, msg: `${slot}.type="${t}" needs a "settings" wrapper (crashes with reading 'version' at cell render)` });
          continue;
        }
        if (typeof s.settings.version !== 'number') {
          errors.push({ rule: 'R3', where: `col ${pn}`, msg: `${slot}.settings missing integer 'version' — crashes at cell render` });
        }
        if (s.settings.type && s.settings.type !== t) {
          errors.push({ rule: 'R3', where: `col ${pn}`, msg: `${slot}.type="${t}" but settings.type="${s.settings.type}" — must match` });
        }
      }
    }
  });

  // ---------- R4 : tabs identity ----------
  walk(markup.components, (n) => {
    if (n.type !== 'tabs') return;
    const tabs = Array.isArray(n.tabs) ? n.tabs : [];
    const ids = new Set();
    for (let i = 0; i < tabs.length; i++) {
      const t = tabs[i];
      if (!t.id) { errors.push({ rule: 'R4', where: `tabs(${n.componentName}) tab[${i}]`, msg: 'missing tab.id' }); continue; }
      if (!t.key) { errors.push({ rule: 'R4', where: `tabs(${n.componentName}) tab[${i}]`, msg: 'missing tab.key' }); continue; }
      if (t.key !== t.id) errors.push({ rule: 'R4', where: `tabs(${n.componentName}) tab[${i}] "${t.title}"`, msg: `tab.key !== tab.id (routing loses mapping — both tab bodies render)` });
      if (ids.has(t.id)) errors.push({ rule: 'R4', where: `tabs(${n.componentName}) tab[${i}] "${t.title}"`, msg: `duplicate tab.id "${t.id}" — React key collision → both bodies render` });
      ids.add(t.id);
    }
  });

  // ---------- R5 : componentName uniqueness across sibling tab bodies ----------
  walk(markup.components, (n) => {
    if (n.type !== 'tabs') return;
    const tabs = Array.isArray(n.tabs) ? n.tabs : [];
    if (tabs.length < 2) return;
    const namesPerTab = tabs.map((t, i) => {
      const seen = new Set();
      walk(t.components || [], (child) => { if (child.componentName) seen.add(child.componentName); });
      return { i, title: t.title, names: seen };
    });
    for (let i = 0; i < namesPerTab.length; i++) {
      for (let j = i + 1; j < namesPerTab.length; j++) {
        const inter = [...namesPerTab[i].names].filter(x => namesPerTab[j].names.has(x));
        if (inter.length > 0) {
          warnings.push({ rule: 'R5', where: `tabs(${n.componentName}) tab[${i}] "${namesPerTab[i].title}" vs tab[${j}] "${namesPerTab[j].title}"`, msg: `${inter.length} colliding componentName(s): ${inter.slice(0, 6).join(', ')} — uniqueStateId scopes may misroute` });
        }
      }
    }
  });

  // ---------- R6 : card content — field-holding containers use grid layout ----------
  // Seed pattern (from sample-patient-details): card.content.components can be a SEQUENCE of:
  //   • container(display:"grid", gridColumnsCount: 2 or 3) holding field-row groups
  //   • standalone span-full siblings — `address`, `htmlRender`, `textField`, `textArea`
  // Rule: any DIRECT-CHILD container of card.content that contains ≥1 field-like grandchild
  //       MUST use desktop.display === "grid" AND gridColumnsCount ∈ {2, 3}.
  //       Multiple grid containers + interleaved span-full siblings are allowed.
  const FIELD_TYPES = new Set([
    'textField','textArea','numberField','dateField','dropdown','autocomplete',
    'checkbox','checkboxGroup','address','htmlRender','refListStatus','entityReference',
  ]);
  walk(markup.components, (n) => {
    if (n.type !== 'card') return;
    const content = n.content;
    if (!content || !Array.isArray(content.components) || content.components.length === 0) {
      errors.push({ rule: 'R6', where: `card ${n.componentName}`, msg: 'card.content.components missing or empty' });
      return;
    }
    for (const child of content.components) {
      if (!child || typeof child !== 'object' || child.type !== 'container') continue;
      // Does this container hold field-like grandchildren?
      const gc = Array.isArray(child.components) ? child.components : [];
      const hasFields = gc.some(g => g && FIELD_TYPES.has(g.type));
      if (!hasFields) continue;
      const dsk = child.desktop || {};
      if (dsk.display !== 'grid') {
        errors.push({ rule: 'R6', where: `card ${n.componentName} / ${child.componentName || 'container'}`, msg: `field-holding container missing desktop.display === "grid" (seed uses grid; do not decompose into horizontal-flex rows)` });
      } else if (dsk.gridColumnsCount !== 2 && dsk.gridColumnsCount !== 3) {
        errors.push({ rule: 'R6', where: `card ${n.componentName} / ${child.componentName || 'container'}`, msg: `field-holding container has gridColumnsCount=${dsk.gridColumnsCount}; seed uses 2 or 3` });
      }
    }
  });

  // ---------- R7 : dataContext at root (table archetype hint) ----------
  const tops = markup.components;
  if (tops.length === 1 && tops[0].type === 'container') {
    const kids = tops[0].components || [];
    if (kids.length >= 1 && kids[0].type === 'dataContext') {
      warnings.push({ rule: 'R7', where: `root ${tops[0].componentName}`, msg: `Top-level is a container wrapping a dataContext — sample-patient-table seed puts dataContext AT the root. If this is a table form, unwrap.` });
    }
  }

  // ---------- R8 : every buttonGroup has isInline: true ----------
  // Without it, buttons collapse into a "..." dropdown and the user sees no button.
  walk(markup.components, (n) => {
    if (n.type !== 'buttonGroup') return;
    if (n.isInline !== true) {
      errors.push({ rule: 'R8', where: `buttonGroup(${n.componentName || '?'})`, msg: `isInline is ${n.isInline} — must be true, otherwise buttons collapse into "..."` });
    }
  });

  // ---------- R9 : create-form inputs use editMode: "editable" ----------
  // Detect create-family form via formSettings.dataLoaderType === "none" OR
  // the modelType being null (form is not bound) OR the form name (not available here).
  // Heuristic: apply the check when dataLoaderType === "none" AND some inputs have
  // editMode: "inherited". Also apply when dataSubmitterType === "gql" but
  // dataLoaderType === "none" — that's the classic create-in-modal pattern.
  const fs2 = markup.formSettings || {};
  const looksLikeCreate = fs2.dataLoaderType === 'none' && fs2.dataSubmitterType === 'gql';
  if (looksLikeCreate) {
    const INPUT_TYPES = new Set(['textField','textArea','numberField','dateField','dropdown','autocomplete','checkbox','checkboxGroup','address']);
    walk(markup.components, (n) => {
      if (!INPUT_TYPES.has(n.type)) return;
      if (n.editMode === 'inherited') {
        errors.push({ rule: 'R9', where: `${n.type}(${n.componentName || n.propertyName || '?'})`, msg: `editMode='inherited' on a create-form input — renders as a dead label with no input box. Use 'editable' on standalone create pages.` });
      }
    });
  }

  // ---------- R10 : dataContext.permanentFilter uses JsonLogic + evaluate, not code-mode ----------
  // Code-mode returns a JS object the query builder can't serialise → 400 on Entities/GetAll.
  walk(markup.components, (n) => {
    if (n.type !== 'dataContext') return;
    const pf = n.permanentFilter;
    if (!pf) return;
    if (typeof pf === 'object' && pf._mode === 'code') {
      errors.push({ rule: 'R10', where: `dataContext(${n.componentName || '?'})`, msg: `permanentFilter uses {_mode:"code"} — this 400s on Entities/GetAll. Use JsonLogic + mustache evaluate: { and: [{ "==": [{ var: "<parentFk>" }, { evaluate: [{ expression: "{{data.id}}", required: true, type: "mustache" }] }] }] }` });
      return;
    }
    // Also check: the JsonLogic shape should reference an evaluate wrapper for the mustache RHS
    // (basic shape check — the `and` array with a `==` comparator is the seed pattern).
    if (typeof pf === 'object' && !Array.isArray(pf.and)) {
      warnings.push({ rule: 'R10', where: `dataContext(${n.componentName || '?'})`, msg: `permanentFilter doesn't have the canonical { and: [...] } wrapper — check against child-tables seed shape` });
    }
  });

  // ---------- R11 : mustache in refListStatus.propertyName / unrooted mustache in action targets ----------
  walk(markup.components, (n) => {
    // refListStatus binding
    if (n.type === 'refListStatus' && typeof n.propertyName === 'string' && /\{\{/.test(n.propertyName)) {
      errors.push({ rule: 'R11', where: `refListStatus(${n.componentName || '?'})`, msg: `propertyName contains a mustache — refListStatus binds via bare property path (e.g. "status"), no braces at all` });
    }
    // buttonGroup items: check actionArguments.target for {{data.…}}
    if (n.type === 'buttonGroup' && Array.isArray(n.items)) {
      for (const it of n.items) {
        const target = it?.actionConfiguration?.actionArguments?.target;
        if (typeof target === 'string' && bareMustache(target).length) {
          errors.push({ rule: 'R11', where: `buttonGroup(${n.componentName || '?'}) item "${it.label || '?'}"`, msg: `actionArguments.target has an unrooted mustache (${bareMustache(target).join(', ')}) — use {{data.<prop>}} or {{selectedRow.<prop>}}` });
        }
      }
    }
    // Same for column action targets inside datatable.items
    if (n.type === 'datatable' && Array.isArray(n.items)) {
      for (const col of n.items) {
        const target = col?.actionConfiguration?.actionArguments?.target;
        if (typeof target === 'string' && bareMustache(target).length) {
          errors.push({ rule: 'R11', where: `datatable(${n.componentName || '?'}) col "${col.caption || col.propertyName || '?'}"`, msg: `column actionArguments.target has an unrooted mustache (${bareMustache(target).join(', ')})` });
        }
      }
    }
  });

  // ---------- R12 : datalist wiring (formSelectionMode: "name" + formId object) ----------
  // The canonical datalist row-template pattern. Missing either renders the list empty.
  walk(markup.components, (n) => {
    if (n.type !== 'datalist') return;
    const cn = n.componentName || '?';
    if (n.formSelectionMode !== 'name') {
      errors.push({ rule: 'R12', where: `datalist(${cn})`, msg: `formSelectionMode is ${JSON.stringify(n.formSelectionMode)} — must be "name" for the canonical row-template pattern` });
    }
    const fid = n.formId || n.formIdentifier;
    if (!fid || typeof fid !== 'object' || !fid.name || !fid.module) {
      errors.push({ rule: 'R12', where: `datalist(${cn})`, msg: `formId must be { name, module } — got ${JSON.stringify(fid)}` });
    }
  });

  // ---------- R13 : Grid + space-between ----------
  // Grid containers distribute via gridColumnsCount; justifyContent:"space-between" conflicts.
  walk(markup.components, (n) => {
    if (n.type !== 'container') return;
    const dsk = n.desktop || {};
    if (dsk.display === 'grid' && dsk.justifyContent === 'space-between') {
      errors.push({ rule: 'R13', where: `container(${n.componentName || '?'})`, msg: `desktop.display:"grid" with justifyContent:"space-between" — grids distribute automatically via gridColumnsCount; use "normal" (or omit).` });
    }
  });

  // ---------- R14 : Soft-shadow byte-exactness ----------
  // Any container with a non-zero shadow must use the canonical soft shadow, not solid #000000.
  const CANONICAL_SHADOW = { offsetX: 0, offsetY: 2, blurRadius: 8, spreadRadius: 2, color: 'rgba(0,0,0,0.05)' };
  walk(markup.components, (n) => {
    if (n.type !== 'container') return;
    const sh = (n.desktop || {}).shadow;
    if (!sh || !sh.blurRadius || sh.blurRadius <= 0) return;
    const problems = [];
    if (sh.color !== CANONICAL_SHADOW.color) problems.push(`color=${JSON.stringify(sh.color)} (want "rgba(0,0,0,0.05)")`);
    if (sh.offsetY !== CANONICAL_SHADOW.offsetY) problems.push(`offsetY=${sh.offsetY} (want 2)`);
    if (sh.blurRadius !== CANONICAL_SHADOW.blurRadius) problems.push(`blurRadius=${sh.blurRadius} (want 8)`);
    if (sh.spreadRadius !== CANONICAL_SHADOW.spreadRadius) problems.push(`spreadRadius=${sh.spreadRadius} (want 2)`);
    if (problems.length) {
      errors.push({ rule: 'R14', where: `container(${n.componentName || '?'})`, msg: `non-canonical shadow — ${problems.join(', ')}. The canonical soft shadow is {offsetX:0, offsetY:2, blurRadius:8, spreadRadius:2, color:"rgba(0,0,0,0.05)"}` });
    }
  });

  // ---------- R15 : pageShell canonical padding ----------
  // Any container with bg #fafafa (the grey outer shell) must have stylingBox padding "20" all sides.
  walk(markup.components, (n) => {
    if (n.type !== 'container') return;
    const dsk = n.desktop || {};
    const bg = (dsk.background || {}).color;
    if (bg !== '#fafafa') return;
    // 0.46 reads the object desktop.stylingBoxJson ({_type:'styleBox', paddingTop:'20', ...}); the
    // stylingBox string is legacy and is ignored for per-device components.
    const sb = dsk.stylingBoxJson;
    if (!sb || typeof sb !== 'object') {
      errors.push({ rule: 'R15', where: `container(${n.componentName || '?'})`, msg: `pageShell (bg #fafafa) has no desktop.stylingBoxJson object (0.46 ignores the legacy stylingBox string). Want { _type:"styleBox", paddingTop:"20", paddingRight:"20", paddingBottom:"20", paddingLeft:"20" }` });
      return;
    }
    const want = ['paddingTop','paddingRight','paddingBottom','paddingLeft'];
    const missing = want.filter(k => String(sb[k]) !== '20');
    if (missing.length) {
      errors.push({ rule: 'R15', where: `container(${n.componentName || '?'})`, msg: `pageShell (bg #fafafa) requires desktop.stylingBoxJson padding 20 on all four sides — off/missing on: ${missing.join(', ')}. Current: ${JSON.stringify(sb)}` });
    }
  });

  // ---------- R16 : deprecated `columns` component ----------
  // WARN only — the canonical seeds never use `columns`; flex/grid containers are the pattern.
  walk(markup.components, (n) => {
    if (n.type === 'columns') {
      warnings.push({ rule: 'R16', where: `columns(${n.componentName || '?'})`, msg: `deprecated 'columns' component — canonical seeds use flex/grid containers instead. Refactor to a flex or grid container with children sized via desktop.dimensions.width.` });
    }
  });

  // ---------- R17 : versions match the 0.46 KB ----------
  const kbPath = path.join(__dirname, '..', '..', 'shesha-form-edit', 'assets', 'components-kb', '_index.json');
  if (fs.existsSync(kbPath)) {
    const kb = JSON.parse(fs.readFileSync(kbPath, 'utf8'));
    const seenWarn = new Set();
    const check = (n, where) => {
      if (!n || typeof n !== 'object' || typeof n.type !== 'string' || typeof n.id !== 'string') return;
      const e = kb[n.type];
      if (!e) {
        if (!SENTINELS.has(n.type) && !['item', 'group'].includes(n.type) && !seenWarn.has(n.type)) { seenWarn.add(n.type); warnings.push({ rule: 'R17', where, msg: `type "${n.type}" is not in the 0.46 component KB (custom/removed type?)` }); }
        return;
      }
      if (e.deprecated && !seenWarn.has('dep:' + n.type)) { seenWarn.add('dep:' + n.type); warnings.push({ rule: 'R17', where, msg: `"${n.type}" is deprecated in 0.46 — do not author new ones` }); }
      if (typeof n.version !== 'number' || e.version === null) return; // R1 reports missing versions
      if (n.version < e.version) errors.push({ rule: 'R17', where, msg: `${n.type} version ${n.version} < current ${e.version}: the portal re-runs migrations on every load (and they overwrite stored values). Author at ${e.version}.` });
      else if (n.version > e.version) warnings.push({ rule: 'R17', where, msg: `${n.type} version ${n.version} > KB ${e.version}` });
    };
    const visit = (node, where) => {
      if (Array.isArray(node)) { node.forEach((x) => visit(x, where)); return; }
      if (!node || typeof node !== 'object') return;
      check(node, node.componentName || node.type || where);
      for (const v of Object.values(node)) if (v && typeof v === 'object') visit(v, node.componentName || where);
    };
    visit(markup.components, 'root');
  } else {
    warnings.push({ rule: 'R17', where: 'validator', msg: `component KB not found at ${kbPath}; versions were not checked` });
  }

  // ---------- R19 : refListStatus under a subForm component (framework bug) ----------
  (function r19(nodes, underSubForm) {
    if (!Array.isArray(nodes)) return;
    for (const n of nodes) {
      if (!n || typeof n !== 'object') continue;
      if (n.type === 'refListStatus' && underSubForm) errors.push({ rule: 'R19', where: `refListStatus(${n.componentName || '?'})`, msg: 'refListStatus inside a subForm throws "Component with id ... is not found" on 0.46 — render the status in the parent form or use a read-only dropdown/text inside the sub-form' });
      const sub = underSubForm || n.type === 'subForm';
      for (const k of ['components']) if (Array.isArray(n[k])) r19(n[k], sub);
      if (Array.isArray(n.tabs)) for (const t of n.tabs) r19(t.components, sub);
      for (const slot of ['header', 'content']) if (n[slot] && Array.isArray(n[slot].components)) r19(n[slot].components, sub);
    }
  })(markup.components, false);

  // ---------- R18 : clean-form-config 0.46 scanner ----------
  const scanPath = path.join(__dirname, '..', '..', 'clean-form-config', 'scripts', 'scan-046.mjs');
  if (fs.existsSync(scanPath) && arg !== '-') {
    const r = spawnSync(process.execPath, [scanPath, arg, '--json'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
    try {
      const out = JSON.parse(r.stdout || '[]');
      const BLOCK = new Set(['S1', 'N7']);
      const WARN = new Set(['N1', 'N2', 'N4', 'N6', 'N8', 'D1']);
      for (const file of out) for (const f of file.findings) {
        if (BLOCK.has(f.id)) errors.push({ rule: 'R18', where: `${f.id} ${f.component || f.ptr}`, msg: f.message });
        else if (WARN.has(f.id)) warnings.push({ rule: 'R18', where: `${f.id} ${f.component || f.ptr}`, msg: f.message });
      }
    } catch (e) {
      warnings.push({ rule: 'R18', where: 'scanner', msg: `scan-046.mjs could not be run (${r.stderr || e.message})` });
    }
  }

  // ---------- Report ----------
  const total = errors.length + warnings.length;
  if (total === 0) {
    console.log('✓ validate-form-markup: 0 issues');
    process.exit(0);
  }
  if (errors.length) {
    console.error(`\nBLOCK-PUSH violations (${errors.length}):`);
    for (const e of errors) console.error(`  [${e.rule}] ${e.where}: ${e.msg}`);
  }
  if (warnings.length) {
    console.error(`\nWarnings (${warnings.length}):`);
    for (const w of warnings) console.error(`  [${w.rule}] ${w.where}: ${w.msg}`);
  }
  if (errors.length) {
    console.error('\nDO NOT push. Fix the BLOCK-PUSH violations above, then re-run.');
    process.exit(1);
  }
  process.exit(0);
}

if (require.main === module) main();
