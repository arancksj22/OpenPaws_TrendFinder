# Phase 2: Normalization

## Scope
Phase 2 normalizes the raw Reddit payloads into a platform-agnostic JSON schema. FastAPI uses Pydantic to strip platform-specific metadata and serialize core textual fields into a unified shape.

## Implemented Module

### Normalization
- Entry point: `normalize_reddit_posts(raw_posts)`
- Source: `app/pipeline/normalization.py`
- Schemas: `app/schemas/post.py`

#### What it does
- Validates raw Reddit payloads with Pydantic models (`RawRedditPost`, `RawRedditComment`).
- Ignores extra platform-specific keys (extra fields are dropped).
- Emits a normalized payload that is platform-agnostic and consistent for later stages.

#### Normalized post shape
Each normalized post includes:
- `source`, `source_id`, `source_fullname`, `community`
- `title`, `body`, `text` (merged title + body)
- `author`, `url`, `permalink`, `created_utc`
- `metrics` (`score`, `num_comments`, `upvote_ratio`)
- `flags` (`is_self`, `over_18`)
- `comments` (normalized list) and `comment_count_ingested`

## Known Constraints
- Only Reddit inputs are supported for now.
- Output schema is platform-agnostic for future sources.
