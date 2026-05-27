# Phase 2: Normalization

## Scope
Phase 2 normalizes raw Bluesky payloads into a platform-agnostic JSON schema. Pydantic validates and strips all platform-specific metadata, serializing core textual fields into a unified `NormalizedPost` shape that every downstream phase (Phase 3 onwards) consumes without any knowledge of the source platform.

## Implemented Module

### Normalization
- Entry point: `normalize_bluesky_posts(raw_posts)`
- Source: `app/pipeline/normalization.py`
- Schemas: `app/schemas/post.py`

#### What it does
- Validates raw Bluesky payloads with Pydantic models (`RawBlueskyPost`, `RawBlueskyReply`).
- Drops all platform-specific keys via `extra="ignore"` on each model.
- Maps Bluesky-specific fields to the platform-agnostic `NormalizedPost` contract:
  - `post_id` (AT URI) → `source_id`
  - `post_cid` → `source_fullname`
  - `community` (hashtag-derived) → `community`
  - `text` → both `body` and `text` (`title` is always `None` for Bluesky)
  - `score` (like count) → `metrics.score`
  - `num_comments` (reply count) → `metrics.num_comments`
  - `upvote_ratio` → `None` (not available on Bluesky)
  - `is_self` → `True` (all Bluesky posts are text-self posts)
  - `over_18` → `False` (Bluesky has no NSFW flag at the post level)
- Normalizes reply threads into `NormalizedComment` objects.
- Emits a `NormalizedPost` dict that is identical in shape regardless of source platform.

> **Note:** `normalize_reddit_posts()` is retained for backward compatibility but is not part of the active pipeline.

#### Normalized post shape (`NormalizedPost`)
Each normalized post dict passed to Phase 3 includes:
- `source` — `"bluesky"`
- `source_id` — AT URI of the post
- `source_fullname` — CID of the post (or `null`)
- `community` — hashtag or author handle (e.g. `"animalrights"`)
- `title` — `null` (Bluesky has no title field)
- `body` — full post text
- `text` — full post text (same as `body`; used by pre-check regex and clustering)
- `author`, `url`, `permalink`, `created_utc`
- `metrics` — `{ score, num_comments, upvote_ratio: null }`
- `flags` — `{ is_self: true, over_18: false }`
- `comments` — list of `NormalizedComment` dicts
- `comment_count_ingested` — integer

#### `NormalizedComment` shape
Each reply in the `comments` list includes:
- `source` — `"bluesky"`
- `source_id` — AT URI of the reply post
- `body` — reply text
- `author`, `score`, `created_utc`

## Contract with Phase 3 (Pre-Batch Check)
Phase 3 (`pre_check.py`) reads `source`, `community`, `title`, `text`, and `body` from each normalized dict and `body` from each comment dict. All of these fields are populated by the Bluesky normalizer. The `title` field being `null` is safe — the pre-check iterates a list of keys and skips missing ones.

## Known Constraints
- `upvote_ratio` is always `null` for Bluesky posts. Phase 4 clustering uses `score + num_comments` for engagement ranking, so this has no effect downstream.
- Output schema is platform-agnostic and ready for any future source.
