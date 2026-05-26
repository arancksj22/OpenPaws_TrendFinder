# Phase 3: Pre-Batch Check

## Scope
Phase 3 performs a lightning-fast local filter on each normalized post to drop explicit gore or abuse trigger words and blocked sources before any embeddings are computed.

## Implemented Module

### Pre-batch filter
- Entry point: `filter_posts(posts, rules)`
- Rule loader: `load_pre_check_rules(config_path)`
- Source: `app/pipeline/pre_check.py`
- Config file: `config/pre_check.yaml`

#### What it does
- Loads blocked terms, subreddits, and sources from YAML.
- Compiles regex patterns (case-insensitive).
- Scans normalized post text and comments.
- Drops matching posts, returns a filtered list.

#### Expected input shape
This module expects normalized post dictionaries, with fields like:
- `source` (e.g., `reddit`)
- `community` (normalized subreddit name)
- `text`, `title`, `body` (core textual fields)
- `comments` (list of dicts with `body`)

#### Output shape
- Returns the same post dictionaries, unmodified, minus those that match a blocked rule.
- No queue integration is performed here; it is intended to be called by a queue worker.

## Notes
- The filter is intentionally cheap and local (regex only).
- It does not mutate payloads, preserving the queue contracts.
