# Phase 6: Human in the Loop Trend Explainer

## Scope
Phase 6 is triggered on dashboard interaction by a social media manager. It fetches trends that survived the post-batch check from Supabase and uses a low-cost Gemini 2.5 Flash call to produce a short AI summary explaining each trend's relevance to animal rights advocacy. This explainer is displayed on the frontend so the human can decide whether to approve the trend for full content generation.

## Implemented Modules

### Pipeline logic
- Trend fetcher: `fetch_trends_for_review(config, status_filter, limit, offset)`
- Explainer generator: `generate_explainer(trend_id, config)`
- Source: `app/pipeline/humanintheloop.py`

### API endpoints
- `GET /api/v1/trends/` — list trends with example posts
- `POST /api/v1/trends/{trend_id}/explainer` — generate AI explainer
- Source: `app/api/v1/endpoints/trends.py`

### Schemas
- `TrendSummary`, `TrendListResponse`, `ExplainerResponse`, `ExamplePostSummary`
- Source: `app/schemas/trend.py`

## Expected Input (from Supabase — Phase 5 output)

Phase 6 reads persisted data written by Phase 4 (clustering) and filtered by Phase 5 (post-batch check). It does **not** receive in-memory data from the previous step.

### Supabase tables queried
- `trends` — trend rows with `id`, `cluster_key`, `representative_count`, `status`, `explainer`, `created_at`
- `trend_examples` — join table linking `trend_id` → `post_id` with `rank`
- `posts` — post data with `id`, `title`, `body`, `text`, `community`, `permalink`, `url`, `score`, `num_comments`

### Contract alignment with Phase 5
Phase 5 `post_batch_check()` returns `(kept_trends, blocked_trends)` where each trend dict contains:
- `trend_id` — matches `trends.id` in Supabase
- `example_post_ids` — matches post IDs linked via `trend_examples`

Phase 6 reads the same `trends` and `trend_examples` tables, filtered by `status = 'pending_review'`. The `status` column must be updated by the Phase 5 worker after filtering.

## What it does

### GET /api/v1/trends/
1. Queries the `trends` table filtered by `status` (default `pending_review`).
2. For each trend, fetches example posts via `trend_examples` → `posts` join.
3. Returns a paginated list of `TrendSummary` objects with nested `ExamplePostSummary` items.

### POST /api/v1/trends/{trend_id}/explainer
1. Fetches the trend row from `trends` by ID.
2. Fetches example posts via `trend_examples` → `posts`.
3. Builds a prompt from example post titles, text snippets, communities, and scores (capped at ~1500 chars).
4. Calls Gemini 2.5 Flash with a system prompt, low temperature (0.3), and tight output token limit (300).
5. Writes the explainer text to `trends.explainer`.
6. Updates `trends.status` to `explainer_ready`.
7. Returns the explainer text with token usage metadata.

## Output Shape

### GET response (`TrendListResponse`)
```json
{
  "trends": [
    {
      "trend_id": "uuid",
      "cluster_key": "uuid",
      "representative_count": 5,
      "status": "pending_review",
      "created_at": "2026-05-26T...",
      "explainer": null,
      "example_posts": [
        {
          "id": "uuid",
          "title": "...",
          "body": "...",
          "text": "...",
          "community": "vegan",
          "permalink": "/r/vegan/...",
          "url": "https://...",
          "score": 42,
          "num_comments": 7
        }
      ]
    }
  ],
  "count": 1
}
```

### POST response (`ExplainerResponse`)
```json
{
  "trend_id": "uuid",
  "explainer": "This trend captures growing public concern about...",
  "model_used": "gemini-2.5-flash",
  "prompt_tokens": 312,
  "completion_tokens": 87
}
```

## Environment
The module reads:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GEMINI_API_KEY`

## Required Supabase Schema Changes
The `trends` table needs two columns added beyond what Phase 4 created:
```sql
ALTER TABLE trends ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending_review';
ALTER TABLE trends ADD COLUMN IF NOT EXISTS explainer TEXT;
```

## Notes
- This phase is **not** part of the automated pipeline flow. It is triggered by human dashboard interaction.
- The Gemini call is deliberately cheap: Flash model, 300 max output tokens, low temperature.
- The prompt is capped at ~1500 characters to minimize input token cost.
- Error handling: 404 if trend not found, 502 if Supabase or Gemini fails.
- The `status` lifecycle is: `pending_review` → `explainer_ready` → (Phase 7+ handles `approved` / `rejected`).
