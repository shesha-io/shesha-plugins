# Semantic Search — Entities, Modules, Forms, Reference Lists

When the user names a resource fuzzily (`"the person entity"`, `"customer form"`, `"gender list"`, `"membership module"`), an exact-name lookup fails and the skill needs to surface the best matches. This is the skill's stand-in for the MCP's FAISS + Claude-Haiku rerank — but **without** the embedding store. The technique is **two-tier**:

1. **String-similarity shortlist** — fetch the resource list, score every candidate against the query with a cheap deterministic metric, keep the top ≤10.
2. **Calling-model rerank** — pass the shortlist to Claude (the model already running this skill) and let it pick. **Skipped** when string score is already high-confidence.

No embeddings, no API keys, no persistent index. The whole flow is bash + node + the existing tool loop.

---

## Resource registry

The same algorithm applies to four resource types. Only the endpoint and the fields that get scored differ:

| Resource | List endpoint | Score these fields | Display fields |
|---|---|---|---|
| **Entity** | `GET /api/services/app/EntityConfig/GetMainDataList?MaxResultCount=500` | `className`, `namespace`, `friendlyName`, `typeShortAlias` | `className`, `namespace`, `id`, `source` |
| **Module** | `GET /api/services/app/Module/GetAll?MaxResultCount=500` | `name`, `friendlyName`, `description` | `name`, `id`, `isEnabled`, `isEditable` |
| **Form** | `GET /api/services/Shesha/FormConfiguration/GetAll?MaxResultCount=500` | `name`, `label`, `description` | `name`, `module.name` / `module._displayName`, `id`, `modelType` |
| **Reference list** | `GET /api/dynamic/Shesha/ReferenceList/Crud/GetAll?MaxResultCount=500` | `name`, `namespace`, `description` | `name`, `namespace`, `module`, `id` |

> ⚠ **ReferenceList endpoint quirk** — on stock recent-build Shesha, `/api/services/app/ReferenceList/GetAll` returns 404. The working route is the dynamic-CRUD form above (`/api/dynamic/Shesha/ReferenceList/Crud/GetAll`). The MCP has the old route hardcoded in `reference_list_api.py`; on this build it would fail. Use the dynamic-CRUD path.

All four endpoints take a bearer token (`Authorization: Bearer $ACCESS_TOKEN`) and return the ABP envelope `{ result: { items: [...], totalCount }, success, ... }`. Increase `MaxResultCount` or paginate via `SkipCount` if the install has more entries.

---

## Scoring algorithm

Save the fetched list to disk, run the following node script against it. The script is self-contained (no deps), portable across Windows/macOS/Linux, and runs in well under a second on stock Shesha (~150 entities, ~50 forms, ~30 ref lists).

```bash
node - <<'EOF' "$QUERY" "$RESOURCE_LIST_PATH" "$FIELDS_CSV"
const [, , query, listPath, fieldsCsv] = process.argv;
const items = JSON.parse(require('fs').readFileSync(listPath, 'utf8')).result.items;
const fields = fieldsCsv.split(',');

const norm = s => (s == null ? '' : String(s)).toLowerCase().trim();
const tokens = s => norm(s).split(/[^a-z0-9]+/).filter(Boolean);

// Jaro-Winkler — handles typos and reorderings, returns 0..1
function jaroWinkler(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  const m = Math.max(a.length, b.length);
  const matchWindow = Math.floor(m / 2) - 1;
  const aMatches = new Array(a.length).fill(false);
  const bMatches = new Array(b.length).fill(false);
  let matches = 0;
  for (let i = 0; i < a.length; i++) {
    const start = Math.max(0, i - matchWindow);
    const end = Math.min(i + matchWindow + 1, b.length);
    for (let j = start; j < end; j++) {
      if (bMatches[j] || a[i] !== b[j]) continue;
      aMatches[i] = bMatches[j] = true;
      matches++;
      break;
    }
  }
  if (!matches) return 0;
  let transpositions = 0, k = 0;
  for (let i = 0; i < a.length; i++) {
    if (!aMatches[i]) continue;
    while (!bMatches[k]) k++;
    if (a[i] !== b[k]) transpositions++;
    k++;
  }
  const jaro = (matches / a.length + matches / b.length + (matches - transpositions / 2) / matches) / 3;
  let prefix = 0;
  for (let i = 0; i < Math.min(4, a.length, b.length); i++) {
    if (a[i] === b[i]) prefix++; else break;
  }
  return jaro + prefix * 0.1 * (1 - jaro);
}

// Token-overlap (Jaccard) — handles paraphrasing and word reordering
function tokenOverlap(q, c) {
  const qt = new Set(tokens(q));
  const ct = new Set(tokens(c));
  if (!qt.size || !ct.size) return 0;
  const inter = [...qt].filter(t => ct.has(t)).length;
  return inter / new Set([...qt, ...ct]).size;
}

const q = norm(query);
const scored = items.map(item => {
  let best = 0;
  for (const field of fields) {
    const raw = field.split('.').reduce((o, k) => (o == null ? null : o[k]), item);
    const value = typeof raw === 'object' && raw ? (raw._displayName || raw.displayName || '') : raw;
    const v = norm(value);
    if (!v) continue;
    // Exact match → 1.0; substring → 0.85 weighted by length ratio; otherwise max of JW + Jaccard
    let s = 0;
    if (v === q) s = 1.0;
    else if (v.includes(q) || q.includes(v)) s = 0.85 * Math.min(q.length, v.length) / Math.max(q.length, v.length);
    else s = Math.max(jaroWinkler(q, v) * 0.9, tokenOverlap(query, value) * 0.85);
    if (s > best) best = s;
  }
  return { score: best, item };
}).filter(x => x.score > 0.3).sort((a, b) => b.score - a.score).slice(0, 10);

console.log(JSON.stringify(scored, null, 2));
EOF
```

Invocation per resource type:

```bash
# Entities — score by className, namespace, friendlyName, typeShortAlias
node ... "$QUERY" "$ENTITIES_JSON" "className,namespace,friendlyName,typeShortAlias"

# Modules — score by name, friendlyName, description
node ... "$QUERY" "$MODULES_JSON"  "name,friendlyName,description"

# Forms — score by name, label, description
node ... "$QUERY" "$FORMS_JSON"    "name,label,description"

# Reference lists — score by name, namespace, description
node ... "$QUERY" "$REFLISTS_JSON" "name,namespace,description"
```

Output is a JSON array of `{score, item}` ordered descending — top 10, all with score > 0.3.

---

## Confidence tiers — when to skip the rerank

Inspect the top result's score and the gap to second place:

| Tier | Condition | Action |
|---|---|---|
| **High** | `top.score >= 0.95` AND (`results.length === 1` OR `top.score - second.score >= 0.15`) | **Skip rerank.** Use the top match directly. |
| **Medium** | `top.score >= 0.7` | Hand the shortlist (top 5-10) back to the calling model with the original query. Claude picks the right one based on context (the rest of the conversation, the user's intent). |
| **Low** | `top.score < 0.7` | No confident match. Surface the top 3 to the user verbatim and ask which one they meant — or whether the resource exists at all. |

**Why this works without embeddings:** the calling model is already a frontier LLM with the conversation context. The shortlist gives it 5-10 plausible candidates and a query — that's exactly the rerank task Claude Haiku does inside the MCP, but done for free by the model already running the skill. The string-similarity stage exists to keep the rerank context small (10 items, not 150).

---

## Recipe — full flow

For an entity query (other resources are identical, just swap the endpoint + score fields):

```bash
# 1. Fetch the list (cache to temp if you'll do multiple searches in a session)
TMPF="${TEMP:-/tmp}/entities.json"
curl -s -G "$BASE_URL/api/services/app/EntityConfig/GetMainDataList" \
  --data-urlencode "MaxResultCount=500" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -o "$TMPF"

# 2. Score (using the node block above)
RESULTS=$(node ... "$QUERY" "$TMPF" "className,namespace,friendlyName,typeShortAlias")

# 3. Inspect confidence and branch
node -e "
const r = $RESULTS;
if (!r.length) { console.log('NO_MATCH'); process.exit(0); }
const top = r[0], second = r[1];
const gap = top.score - (second ? second.score : 0);
if (top.score >= 0.95 && (r.length === 1 || gap >= 0.15)) {
  console.log('HIGH', JSON.stringify(top));
} else if (top.score >= 0.7) {
  console.log('MEDIUM', JSON.stringify(r.slice(0, 5)));
} else {
  console.log('LOW', JSON.stringify(r.slice(0, 3)));
}
"
```

Interpret the marker:

- `HIGH <one item>` — use it. No user / no rerank.
- `MEDIUM <shortlist>` — let Claude (you) pick the right one from the shortlist using conversation context. If still ambiguous, surface to the user.
- `LOW <top 3>` — ask the user to confirm or rephrase.
- `NO_MATCH` — tell the user the resource doesn't seem to exist; offer to create it (entity create flow, form Step 3b create branch, etc.).

---

## Caching

The four list endpoints are read-mostly and rarely change mid-session. Cache strategy when token-caching is added (see `mcp-parity-inventory.md`):

- Cache each list to disk keyed by `$BASE_URL` and resource type.
- TTL: 1 hour for entities / modules / reference lists (rarely added in a working session); 5 minutes for forms (often added by the same session that's searching).
- Bust the form cache on every successful `Create` / `UpdateMarkup` from this skill.
- `--no-cache` escape hatch for the user who just added something via the admin UI and wants fresh data.

Until then, fetching ~500 records adds ~200–500ms per search — acceptable for interactive use.

---

## Gotchas

1. **Module field is often a dict, not a string.** Forms come back with `module: {id, _displayName, _className}`. The script reads `_displayName` / `displayName` when the value is an object — same as `reference/model-configurations.md` gotcha #1 for `entityType`.
2. **`friendlyName` is often null.** Don't treat its absence as a problem — fall back to the other scored fields.
3. **`description` is the secret weapon for forms.** The MCP semantic search uses form description heavily; if your team writes good descriptions, paraphrased queries ("the form for managing customer orders") will match without rerank.
4. **`source: 1` is code-defined, `source: 2` is user-defined** (entities and modules). Useful when the user says "the entity I just added" — filter to `source === 2` before scoring.
5. **Modules where `isEnabled === false` or `isEditable === false`** — still return them in search, but flag them in the display. The user may be hitting "module not editable" precisely because they picked a disabled one.
6. **`typeShortAlias` is null for non-framework entities.** It only exists for entities exposed via Shesha's discriminator-based aliasing.
7. **MaxResultCount=500 is enough for stock Shesha** (138 entities, ~40 modules, ~50 forms, ~30 ref lists). For larger installs, paginate.

---

## When to use this in the skill

- **Step 3a (Edit branch)** — when `GetByName` returns null, fall back to form search before asking the user.
- **Step 3b (Create branch)** — when the user names a module that doesn't exact-match, search modules. Same for `modelType` (entity search). Same for any `referenceListName` the user references on a dropdown.
- **Anywhere a script binds to a `referenceListName`** — verify the list exists; if not, search for the closest match.

Read this file **before** doing any fuzzy lookup. Don't reimplement the algorithm inline — copy-paste the node block.
