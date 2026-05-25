# Phase 1: Reddit Ingestion

## Scope
Phase 1 is the ingestion stage only: a scheduled background script polls target communities to fetch raw batches of posts from Reddit via asyncpraw. Normalization happens in Phase 2.

## Implemented Module

### Ingestion
- Entry point: `ingest_reddit_posts(config_path)`
- Source: `app/pipeline/ingestion.py`
- Config file: `config/subreddits.yaml`

#### What it does
- Reads subreddit configuration (defaults + per-subreddit overrides).
- Pulls posts from the `/rising` feed by default (supports `rising`, `new`, `hot`, `top`).
- Skips stickied posts.
- Captures text-only fields from each post plus top-level comments.
- Applies a small delay between subreddits and handles rate-limit sleeps.

#### Required environment variables
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

#### Raw post payload fields
The ingestion stage outputs a raw Reddit-shaped dict with keys like:
- `source`, `subreddit`, `post_id`, `post_fullname`
- `title`, `selftext`, `url`, `permalink`
- `created_utc`, `score`, `num_comments`, `upvote_ratio`
- `is_self`, `over_18`, `author`
- `comments` (top-level only) and `comment_count_ingested`

#### Comments behavior
- Uses Reddit comment sorting configured in YAML (default `best`).
- Calls `replace_more(limit=0)` and iterates top-level comments only.
- Drops deleted or removed comment bodies.
- Limits comment count per post (default `5`).

## Known Constraints
- Only Reddit is supported in Phase 1.
- Text-only ingestion (no media extraction).
- Scheduling/cron orchestration is external to this module.
