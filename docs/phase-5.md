# Phase 5: Post-Batch Check

## Scope
Phase 5 evaluates each trend cluster as a single unit to omit hostile, sarcastic, or anti-advocacy angles before downstream steps.

## Implemented Module

### Post-batch filter
- Entry point: `post_batch_check(trends, rules, config)`
- Rule loader: `load_post_check_rules(config_path)`
- Source: `app/pipeline/post_check.py`
- Config file: `config/post_check.yaml`

#### Expected input
The post-batch check expects trend records returned by clustering, each containing:
- `trend_id`
- `example_post_ids` (top 5 post IDs stored in Supabase)

#### What it does
1. Fetches the top example posts from Supabase using `example_post_ids`.
2. Builds a combined cluster text from `text`, `title`, and `body` fields.
3. Runs sentiment consensus using VADER across example posts when advocacy keywords are present.
4. Drops trends that meet negative sentiment consensus.

#### Output shape
- Returns a tuple: `(kept_trends, blocked_trends)`.
- `blocked_trends` contains `{trend_id, reason}` entries only (no UI changes).

## Environment
The module reads:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Notes
- This step is cluster-level, not per-post.
- It does not modify database records yet; it only filters in-memory results.
- Sentiment uses `negative_threshold`, `negative_ratio`, and `min_posts` from `config/post_check.yaml`.
