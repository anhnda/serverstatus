# Making n8n read config from the `config` table

The old **Load Config** node hardcoded everything. Now it reads from Postgres.
A plain Code node can't query Postgres, so use one of the two options below.
Downstream nodes are untouched — they still reference
`$('Load Config').first().json.keywordQuery`, `.authors`, `.openreviewVenues`, etc.
Both options keep that exact shape.

---

## Option A (recommended) — Postgres node + tiny Code node

Replace the single **Load Config** code node with two nodes:

### A1. Postgres node — "Load Config (DB)"
- Operation: **Execute Query**
- Credential: your existing **Postgres account** (`LvTeoXHnDyhIEnZe`)
- Query — folds every row back into one JSON object:

```sql
SELECT jsonb_object_agg(key, value) AS cfg FROM config;
```

This returns one item: `{ cfg: { keywordQuery: "...", authors: [...], ... } }`.

### A2. Code node — "Derive Config" (typeVersion 2)
Wire **Load Config (DB) → Derive Config**, then point the old
`Schedule Trigger → Load Config` link to `Schedule Trigger → Load Config (DB)`,
and everything that read from **Load Config** now reads from **Derive Config**.

> Easiest rename trick: name the Code node **exactly** `Load Config`
> (rename the old one first). Then every existing `$('Load Config')...`
> reference keeps working with zero edits elsewhere.

```js
// Pull the aggregated config object from the Postgres node.
const cfg = $input.first().json.cfg || {};

// Derive openreviewVenues from orConfs × [thisYear, lastYear],
// exactly like the original node did.
const _y = new Date().getFullYear();
const confs = cfg.orConfs || ["ICML", "ICLR", "NeurIPS"];
const openreviewVenues = [];
for (const y of [_y, _y - 1]) {
  for (const c of confs) openreviewVenues.push(`${c}.cc/${y}/Conference`);
}

return [{ json: {
  keywordQuery:      cfg.keywordQuery,
  fields:            cfg.fields,
  KEYWORD_MIN_SCORE: cfg.KEYWORD_MIN_SCORE,
  AUTHOR_MIN_SCORE:  cfg.AUTHOR_MIN_SCORE,
  daysBack:          cfg.daysBack,
  venueWhitelist:    cfg.venueWhitelist,
  authors:           cfg.authors,
  openreviewVenues,
} }];
```

---

## Option B — single Code node using the Postgres pool

If you'd rather keep exactly one node, a Code node **can** reach Postgres via
n8n's helpers only in some setups; the robust cross-version path is still
Option A. Use B only if you know your n8n exposes `this.helpers`. Skipped here
on purpose to avoid version-specific breakage.

---

## Notes
- `daysBack` is stored in the table (default **400**, the original TEST value).
  Set it to **2** for production straight from the pconfig UI.
- `topics` is **not** consumed by the workflow — it only powers the author
  topic droplist in the editor. Author rows still carry their own `topic`
  string, which flows through `Split Authors` unchanged.
- First run auto-seeds defaults via `schema.sql`. After that, the UI is the
  source of truth; n8n just reads.
