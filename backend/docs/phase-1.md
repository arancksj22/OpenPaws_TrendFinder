# Phase 1: Bluesky Ingestion

## Scope
Phase 1 is the ingestion stage only: a scheduled background script polls target hashtag communities to fetch raw batches of posts from Bluesky via the AT Protocol Lexicon search API (`app.bsky.feed.search_posts`). Normalization happens in Phase 2.

## Implemented Module

### Ingestion
- Entry point: `ingest_bluesky_posts(config_path)`
- Source: `app/pipeline/ingestion.py`
- Config file: `config/bluesky.yaml`

#### What it does
- Reads hashtag group configuration (defaults + per-group overrides).
- Searches posts by hashtag using the Lexicon search API (supports `latest` and `top` sort).
- Deduplicates posts by AT URI across hashtag groups so the same post is not ingested twice.
- Fetches reply threads for each post using `get_post_thread` (configurable depth and max replies).
- Applies a small delay between hashtag group queries.
- Derives `community` from the first hashtag facet in the post record, falling back to the author handle.
- Builds a human-readable `https://bsky.app/profile/handle/post/rkey` permalink from the AT URI.

#### Required environment variables
- `BLUESKY_HANDLE`
- `BLUESKY_APP_PASSWORD`

#### Raw post payload fields
The ingestion stage outputs a raw Bluesky-shaped dict with keys:
- `source` (always `"bluesky"`), `community` (derived from hashtags)
- `post_id` (AT URI, e.g. `at://did:plc:.../app.bsky.feed.post/...`), `post_cid`
- `text` (Bluesky posts have no title field — full body is in `text`)
- `url`, `permalink` (human-readable `bsky.app` URL)
- `created_utc` (UTC float), `score` (like count), `num_comments` (reply count), `repost_count`
- `author` (handle)
- `comments` (thread replies) and `comment_count_ingested`

#### Comments behavior
- Replies are fetched with `get_post_thread(depth=N, parent_height=0)`.
- Limits reply count per post via `max_replies` (default `5`).
- Maps reply `like_count` to `score`.
- Drops empty reply bodies.

## Known Constraints
- Only Bluesky is supported in Phase 1.
- Text-only ingestion (no media, images, or video extraction).
- Scheduling/cron orchestration is external to this module.
