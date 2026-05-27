# Phase 10: Closed-Loop Production Storage

## Scope
Phase 10 is the terminal stage of the generation pipeline. It receives the scored, serialised output from Phase 9 and the raw `GenerationResult` from Phase 8, and durably persists everything to Supabase:

1. **Text variations + scores** → `generated_content` Supabase table (all 3 drafts with individual scores and composite, brief, positioning angle, hashtags).
2. **Trend infographic image** → `trend-images` Supabase Storage bucket (PNG uploaded at a user-namespaced path).

All records and storage objects are namespaced under the caller's `user_id`, so users can only ever read their own generation history. The `fetch_user_history()` function returns the full paginated history for the frontend history view.

## Implemented Module

### Production Storage
- Entry points: `store_generation(user_id, generation_result, scored_payload, config)` and `fetch_user_history(user_id, ...)`
- Source: `app/pipeline/production_storage.py`
- Configuration: `StorageConfig` dataclass

---

## What it does

### Step 1: Image Upload (non-fatal)
If `generation_result.image_bytes` is present, the PNG is uploaded to the `trend-images` Supabase Storage bucket at a user-namespaced path:
```
{user_id}/{trend_id}/{timestamp}.png
```
A public URL is constructed and stored alongside the text record. If upload fails for any reason (quota, network, missing bucket), the failure is logged and Phase 10 continues, storing `image_url = null` in the database record.

### Step 2: Database Insert
A single row is inserted into the `generated_content` table containing:
- The advocacy brief and positioning angle from Phase 8.
- All 3 scored drafts as a JSONB column (includes all 5 individual scores + composite per draft, so the history view never needs a separate scoring call).
- The recommended draft index.
- The image public URL and the Imagen prompt used (audit trail).
- Token usage totals from Phase 8.

---

## User Namespacing

Every piece of storage is scoped to `user_id`:

| Layer | Namespace |
|-------|-----------|
| Supabase table row | `WHERE user_id = '{user_id}'` |
| Storage path | `{user_id}/{trend_id}/{timestamp}.png` |

Path segments are sanitised (only alphanumerics, hyphens, and underscores allowed; max 80 chars) to prevent directory traversal.

> **Note**: There is no auth enforcement inside Phase 10 itself — the `user_id` is trusted from the caller. Apply Row-Level Security (RLS) in Supabase to enforce access control at the database layer (see SQL section below).

---

## Result Types

### `StorageResult`
```python
@dataclass
class StorageResult:
    record_id:    str        # UUID of the inserted generated_content row
    user_id:      str
    trend_id:     str
    image_url:    str | None # Public storage URL; None if no image was stored
    storage_path: str | None # e.g. "user123/trend-abc/2024-01-15T12-00-00.png"
    table:        str        # "generated_content"
```

---

## Config

```python
@dataclass(frozen=True)
class StorageConfig:
    supabase_url:               str | None = None  # reads SUPABASE_URL
    supabase_service_role_key:  str | None = None  # reads SUPABASE_SERVICE_ROLE_KEY
    table_name:                 str = "generated_content"
    storage_bucket:             str = "trend-images"
```

---

## How to call it

```python
from app.pipeline.generation import generate_content
from app.pipeline.revalidation import revalidate_and_score, serialise_result
from app.pipeline.production_storage import store_generation, fetch_user_history

# Phase 8
gen_result = generate_content(sanitized_payload)

# Phase 9
rev_result  = revalidate_and_score(gen_result)
scored_dict = serialise_result(rev_result)

# Phase 10
storage = store_generation(
    user_id="user-uuid-from-auth",
    generation_result=gen_result,
    scored_payload=scored_dict,
)
print(storage.record_id)   # UUID of stored row
print(storage.image_url)   # Public Supabase Storage URL

# History view (paginated)
history = fetch_user_history(user_id="user-uuid-from-auth", limit=20, offset=0)
```

---

## Contract with Phase 9 (Revalidation)
Phase 10 receives:
- `GenerationResult` from Phase 8 directly (for `image_bytes`, `image_prompt_used`, `trend_id`, `brief`, token counts).
- `dict` from `serialise_result(RevalidationResult)` (for `scored_drafts`, `recommended_index`, and score metadata).

## Known Constraints
- Requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` environment variables.
- Supabase Storage bucket `trend-images` must be created manually in the Supabase dashboard before first use.
- Image upload uses `upsert: true` — re-running generation for the same trend + user + timestamp will overwrite the existing image (in practice, timestamps ensure uniqueness).
- `fetch_user_history()` returns a maximum of 100 rows per call (capped internally).

---

## Required SQL

Run these statements in the Supabase SQL editor before first use.

```sql
-- Main table: stores every generation run, namespaced by user.
CREATE TABLE IF NOT EXISTS generated_content (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 text        NOT NULL,
    trend_id                text        NOT NULL,
    advocacy_brief          text,
    positioning_angle       text,
    suggested_hashtags      jsonb,
    -- Full scored_drafts JSON from Phase 9 serialise_result().
    -- Includes all 5 individual scores + composite per draft.
    scored_drafts           jsonb       NOT NULL,
    recommended_index       integer,
    image_url               text,
    image_prompt            text,
    total_prompt_tokens     integer,
    total_completion_tokens integer,
    created_at              timestamptz NOT NULL DEFAULT now()
);

-- Index for fast user history queries (newest first).
CREATE INDEX IF NOT EXISTS generated_content_user_idx
    ON generated_content (user_id, created_at DESC);

-- Index for looking up all generations linked to a specific trend.
CREATE INDEX IF NOT EXISTS generated_content_trend_idx
    ON generated_content (trend_id);

-- Row-Level Security: each user can only read and insert their own records.
-- Enable RLS on the table first, then apply the policies.
ALTER TABLE generated_content ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own records"
    ON generated_content
    FOR SELECT
    USING (user_id = auth.uid()::text);

CREATE POLICY "Users can insert own records"
    ON generated_content
    FOR INSERT
    WITH CHECK (user_id = auth.uid()::text);
```
