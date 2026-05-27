"""Bluesky ingestion for Phase 1 (text-only).

Polls Bluesky via the AT Protocol Lexicon search API to fetch posts matching
configured hashtags, then retrieves reply threads for each post.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from atproto import Client

logger = logging.getLogger(__name__)


class IngestionConfigError(RuntimeError):
	"""Raised when ingestion configuration is invalid or missing."""


SUPPORTED_SORTS = {"latest", "top"}


@dataclass(frozen=True)
class IngestionDefaults:
	sort: str = "latest"
	post_limit: int = 25
	reply_depth: int = 1
	max_replies: int = 5
	request_delay_seconds: float = 1.0


@dataclass(frozen=True)
class HashtagSource:
	tags: list[str] = field(default_factory=list)
	enabled: bool = True
	sort: str | None = None
	post_limit: int | None = None
	reply_depth: int | None = None
	max_replies: int | None = None


def load_bluesky_config(
	config_path: str | Path,
) -> tuple[IngestionDefaults, list[HashtagSource]]:
	path = Path(config_path)
	if not path.exists():
		raise IngestionConfigError(f"Config file not found: {path}")

	raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
	defaults_raw = raw.get("defaults", {})
	defaults = IngestionDefaults(
		sort=_validate_sort(defaults_raw.get("sort", "latest")),
		post_limit=int(defaults_raw.get("post_limit", 25)),
		reply_depth=int(defaults_raw.get("reply_depth", 1)),
		max_replies=int(defaults_raw.get("max_replies", 5)),
		request_delay_seconds=float(
			defaults_raw.get("request_delay_seconds", 1.0)
		),
	)

	hashtag_groups_raw = raw.get("hashtag_groups", [])
	sources: list[HashtagSource] = []
	for entry in hashtag_groups_raw:
		if not isinstance(entry, dict):
			continue

		tags = _normalize_tag_list(entry.get("tags", []))
		if not tags:
			continue

		sources.append(
			HashtagSource(
				tags=tags,
				enabled=bool(entry.get("enabled", True)),
				sort=_optional_sort(entry.get("sort")),
				post_limit=_optional_int(entry.get("post_limit")),
				reply_depth=_optional_int(entry.get("reply_depth")),
				max_replies=_optional_int(entry.get("max_replies")),
			)
		)

	if not sources:
		raise IngestionConfigError("No hashtag groups configured.")

	return defaults, sources


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ingest_bluesky_posts(
	config_path: str | Path,
) -> list[dict[str, Any]]:
	"""Fetch Bluesky posts matching configured hashtags with reply threads.

	This is the main entry point for the ingestion phase. It mirrors the
	public API of the former ``ingest_reddit_posts`` function: accepts a
	config path and returns a flat list of raw post dicts.
	"""
	defaults, sources = load_bluesky_config(config_path)
	client = _build_bluesky_client()

	results: list[dict[str, Any]] = []
	seen_uris: set[str] = set()

	for source in sources:
		if not source.enabled:
			continue

		effective = _merge_defaults(defaults, source)

		try:
			posts = _search_posts(client, source.tags, effective)
			for post in posts:
				uri = post.get("post_id")
				if uri in seen_uris:
					continue
				seen_uris.add(uri)
				results.append(post)
		except Exception as exc:
			logger.exception(
				"Bluesky search error for tags %s", source.tags
			)

		await _safe_sleep(defaults.request_delay_seconds)

	return results


# ---------------------------------------------------------------------------
# Bluesky client helpers
# ---------------------------------------------------------------------------


def _build_bluesky_client() -> Client:
	handle = os.getenv("BLUESKY_HANDLE")
	app_password = os.getenv("BLUESKY_APP_PASSWORD")

	if not handle or not app_password:
		raise IngestionConfigError(
			"Missing Bluesky environment variables. "
			"Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD."
		)

	client = Client()
	client.login(handle, app_password)
	return client


def _search_posts(
	client: Client,
	tags: list[str],
	settings: IngestionDefaults,
) -> list[dict[str, Any]]:
	"""Search Bluesky for posts matching the given hashtags, with pagination."""
	query_str = " OR ".join(tags)
	posts: list[dict[str, Any]] = []
	cursor: str | None = None
	remaining = settings.post_limit

	while remaining > 0:
		batch_size = min(remaining, 100)  # Bluesky API hard cap per request
		params: dict[str, Any] = {
			"q": query_str,
			"sort": settings.sort,
			"limit": batch_size,
		}
		if cursor:
			params["cursor"] = cursor

		try:
			response = client.app.bsky.feed.search_posts(params=params)
		except Exception as exc:
			logger.warning("Bluesky search_posts error (stopping pagination): %s", exc)
			break

		page_posts = response.posts or []
		if not page_posts:
			break  # No more results

		for post_view in page_posts:
			post = _extract_post(client, post_view, settings)
			if post is not None:
				posts.append(post)

		remaining -= len(page_posts)

		# Stop if no cursor returned (last page)
		cursor = getattr(response, "cursor", None)
		if not cursor:
			break

		logger.debug("Bluesky pagination: fetched %d so far, cursor=%s", len(posts), cursor)

	return posts


def _extract_post(
	client: Client,
	post_view: Any,
	settings: IngestionDefaults,
) -> dict[str, Any] | None:
	"""Extract a raw post dict from a Bluesky PostView object."""
	record = post_view.record
	if record is None:
		return None

	text = _clean_text(getattr(record, "text", ""))
	author_handle = post_view.author.handle if post_view.author else None
	post_uri = post_view.uri
	post_cid = post_view.cid

	# Parse created_at into a UTC float timestamp for downstream compat.
	created_utc = _parse_created_at(getattr(record, "created_at", None))

	# Extract engagement metrics from the post_view.
	like_count = getattr(post_view, "like_count", None) or 0
	reply_count = getattr(post_view, "reply_count", None) or 0
	repost_count = getattr(post_view, "repost_count", None) or 0

	# Derive community from hashtags or author handle.
	community = _derive_community(record, author_handle)

	# Build the Bluesky permalink.
	permalink = _build_permalink(author_handle, post_uri)

	# Fetch reply thread.
	comments: list[dict[str, Any]] = []
	if settings.reply_depth > 0 and settings.max_replies > 0:
		comments = _fetch_replies(
			client,
			post_uri,
			depth=settings.reply_depth,
			max_replies=settings.max_replies,
		)

	return {
		"source": "bluesky",
		"community": community,
		"post_id": post_uri,
		"post_cid": post_cid,
		"text": text,
		"url": permalink,
		"permalink": permalink,
		"created_utc": created_utc,
		"score": like_count,
		"num_comments": reply_count,
		"repost_count": repost_count,
		"author": author_handle,
		"comments": comments,
		"comment_count_ingested": len(comments),
	}


def _fetch_replies(
	client: Client,
	post_uri: str,
	depth: int,
	max_replies: int,
) -> list[dict[str, Any]]:
	"""Fetch reply thread for a post."""
	try:
		thread_response = client.get_post_thread(
			uri=post_uri,
			depth=depth,
			parent_height=0,
		)
	except Exception as exc:
		logger.warning("Failed to fetch thread for %s: %s", post_uri, exc)
		return []

	thread = thread_response.thread
	if not hasattr(thread, "replies") or not thread.replies:
		return []

	comments: list[dict[str, Any]] = []
	for reply_node in thread.replies:
		if len(comments) >= max_replies:
			break

		reply_post = getattr(reply_node, "post", None)
		if reply_post is None:
			continue

		reply_record = reply_post.record
		if reply_record is None:
			continue

		body = _clean_text(getattr(reply_record, "text", ""))
		if not body:
			continue

		reply_author = (
			reply_post.author.handle if reply_post.author else None
		)
		reply_like_count = getattr(reply_post, "like_count", None) or 0
		reply_created = _parse_created_at(
			getattr(reply_record, "created_at", None)
		)

		comments.append(
			{
				"comment_id": reply_post.uri,
				"body": body,
				"author": reply_author,
				"score": reply_like_count,
				"created_utc": reply_created,
			}
		)

	return comments


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _derive_community(record: Any, author_handle: str | None) -> str:
	"""Best-effort community derivation from hashtags embedded in the post.

	Bluesky has no "subreddit" concept. We use the first facet hashtag
	found in the record as the community label. Falls back to the
	author's handle domain.
	"""
	facets = getattr(record, "facets", None)
	if facets:
		for facet in facets:
			features = getattr(facet, "features", None)
			if not features:
				continue
			for feature in features:
				tag = getattr(feature, "tag", None)
				if tag:
					return tag.lower()

	# Fallback: use the author handle minus .bsky.social suffix.
	if author_handle:
		return author_handle.replace(".bsky.social", "")
	return "bluesky"


def _build_permalink(author_handle: str | None, post_uri: str) -> str:
	"""Build a human-readable Bluesky web URL from an AT URI.

	AT URIs look like: at://did:plc:abc123/app.bsky.feed.post/3abcdef
	Web URLs look like: https://bsky.app/profile/handle/post/3abcdef
	"""
	if author_handle and "/app.bsky.feed.post/" in post_uri:
		rkey = post_uri.split("/app.bsky.feed.post/")[-1]
		return f"https://bsky.app/profile/{author_handle}/post/{rkey}"
	return post_uri


def _parse_created_at(value: Any) -> float | None:
	"""Convert an ISO-8601 datetime string to a UTC float timestamp."""
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return float(value)

	try:
		dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
		return dt.timestamp()
	except (ValueError, TypeError):
		return None


def _merge_defaults(
	defaults: IngestionDefaults, source: HashtagSource
) -> IngestionDefaults:
	return IngestionDefaults(
		sort=source.sort or defaults.sort,
		post_limit=source.post_limit or defaults.post_limit,
		reply_depth=(
			source.reply_depth
			if source.reply_depth is not None
			else defaults.reply_depth
		),
		max_replies=source.max_replies or defaults.max_replies,
		request_delay_seconds=defaults.request_delay_seconds,
	)


def _validate_sort(sort: str) -> str:
	sort_normalized = str(sort).lower().strip()
	if sort_normalized not in SUPPORTED_SORTS:
		raise IngestionConfigError(f"Unsupported sort: {sort}")
	return sort_normalized


def _optional_sort(value: Any) -> str | None:
	if value is None:
		return None
	return _validate_sort(value)


def _optional_int(value: Any) -> int | None:
	if value is None:
		return None
	return int(value)


def _normalize_tag_list(items: Any) -> list[str]:
	"""Normalize a list of hashtag strings, stripping '#' prefixes."""
	if not items:
		return []
	result: list[str] = []
	for item in items:
		tag = str(item).strip().lstrip("#")
		if tag:
			result.append(tag)
	return result


def _clean_text(text: str | None) -> str | None:
	if not text:
		return None
	cleaned = text.strip()
	if not cleaned:
		return None
	return cleaned


async def _safe_sleep(seconds: float) -> None:
	if seconds and seconds > 0:
		await asyncio.sleep(seconds)
