"""Reddit ingestion for Phase 1 (text-only)."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import asyncpraw
import yaml
from prawcore.exceptions import PrawcoreException, RateLimitExceeded

logger = logging.getLogger(__name__)

SUPPORTED_FEEDS = {"rising", "new", "hot", "top"}


class IngestionConfigError(RuntimeError):
	"""Raised when ingestion configuration is invalid or missing."""


@dataclass(frozen=True)
class IngestionDefaults:
	feed: str = "rising"
	post_limit: int = 25
	comment_limit: int = 5
	comment_sort: str = "best"
	include_comments: bool = True
	request_delay_seconds: float = 1.0


@dataclass(frozen=True)
class SubredditSource:
	name: str
	enabled: bool = True
	feed: str | None = None
	post_limit: int | None = None
	comment_limit: int | None = None
	comment_sort: str | None = None
	include_comments: bool | None = None


def load_subreddit_config(config_path: str | Path) -> tuple[IngestionDefaults, list[SubredditSource]]:
	path = Path(config_path)
	if not path.exists():
		raise IngestionConfigError(f"Config file not found: {path}")

	raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
	defaults_raw = raw.get("defaults", {})
	defaults = IngestionDefaults(
		feed=_validate_feed(defaults_raw.get("feed", "rising")),
		post_limit=int(defaults_raw.get("post_limit", 25)),
		comment_limit=int(defaults_raw.get("comment_limit", 5)),
		comment_sort=str(defaults_raw.get("comment_sort", "best")),
		include_comments=bool(defaults_raw.get("include_comments", True)),
		request_delay_seconds=float(defaults_raw.get("request_delay_seconds", 1.0)),
	)

	subreddits_raw = raw.get("subreddits", [])
	sources: list[SubredditSource] = []
	for entry in subreddits_raw:
		if isinstance(entry, str):
			name = entry.strip()
			if not name:
				continue
			sources.append(SubredditSource(name=name))
			continue

		if not isinstance(entry, dict):
			continue

		name = str(entry.get("name", "")).strip()
		if not name:
			continue
		sources.append(
			SubredditSource(
				name=name,
				enabled=bool(entry.get("enabled", True)),
				feed=_optional_feed(entry.get("feed")),
				post_limit=_optional_int(entry.get("post_limit")),
				comment_limit=_optional_int(entry.get("comment_limit")),
				comment_sort=_optional_str(entry.get("comment_sort")),
				include_comments=_optional_bool(entry.get("include_comments")),
			)
		)

	if not sources:
		raise IngestionConfigError("No subreddits configured.")

	return defaults, sources


async def ingest_reddit_posts(config_path: str | Path) -> list[dict[str, Any]]:
	defaults, sources = load_subreddit_config(config_path)
	reddit = _build_reddit_client()
	reddit.read_only = True

	results: list[dict[str, Any]] = []
	try:
		for source in sources:
			if not source.enabled:
				continue

			effective = _merge_defaults(defaults, source)
			try:
				subreddit = await reddit.subreddit(source.name)
				posts = await _fetch_subreddit_posts(subreddit, effective)
				results.extend(posts)
			except RateLimitExceeded as exc:
				delay = max(defaults.request_delay_seconds, float(getattr(exc, "sleep", 5)))
				logger.warning("Rate limit hit for r/%s, sleeping %s seconds", source.name, delay)
				await asyncio.sleep(delay)
			except PrawcoreException as exc:
				logger.warning("Reddit API error for r/%s: %s", source.name, exc)

			await _safe_sleep(defaults.request_delay_seconds)
	finally:
		await reddit.close()

	return results


async def _fetch_subreddit_posts(
	subreddit: asyncpraw.models.Subreddit,
	settings: IngestionDefaults,
) -> list[dict[str, Any]]:
	listing = _get_listing(subreddit, settings)
	posts: list[dict[str, Any]] = []

	async for submission in listing:
		if getattr(submission, "stickied", False):
			continue

		post = await _extract_submission(submission, settings)
		if post is not None:
			posts.append(post)

	return posts


def _get_listing(
	subreddit: asyncpraw.models.Subreddit,
	settings: IngestionDefaults,
):
	feed = settings.feed
	if feed == "rising":
		return subreddit.rising(limit=settings.post_limit)
	if feed == "new":
		return subreddit.new(limit=settings.post_limit)
	if feed == "hot":
		return subreddit.hot(limit=settings.post_limit)
	if feed == "top":
		return subreddit.top(time_filter="day", limit=settings.post_limit)

	raise IngestionConfigError(f"Unsupported feed: {feed}")


async def _extract_submission(
	submission: asyncpraw.models.Submission,
	settings: IngestionDefaults,
) -> dict[str, Any] | None:
	title = _clean_text(getattr(submission, "title", ""))
	selftext = _clean_text(getattr(submission, "selftext", ""))

	author = submission.author.name if submission.author else None
	permalink = f"https://www.reddit.com{submission.permalink}"

	comments: list[dict[str, Any]] = []
	if settings.include_comments and settings.comment_limit > 0:
		comments = await _fetch_top_comments(
			submission,
			limit=settings.comment_limit,
			sort=settings.comment_sort,
		)

	return {
		"source": "reddit",
		"subreddit": str(submission.subreddit),
		"post_id": submission.id,
		"post_fullname": submission.name,
		"title": title,
		"selftext": selftext,
		"url": submission.url,
		"permalink": permalink,
		"created_utc": submission.created_utc,
		"score": submission.score,
		"num_comments": submission.num_comments,
		"upvote_ratio": getattr(submission, "upvote_ratio", None),
		"is_self": submission.is_self,
		"over_18": submission.over_18,
		"author": author,
		"comments": comments,
		"comment_count_ingested": len(comments),
	}


async def _fetch_top_comments(
	submission: asyncpraw.models.Submission,
	limit: int,
	sort: str,
) -> list[dict[str, Any]]:
	submission.comment_sort = sort
	await submission.comments.replace_more(limit=0)

	comments: list[dict[str, Any]] = []
	for comment in submission.comments:
		if len(comments) >= limit:
			break
		body = _clean_text(getattr(comment, "body", ""))
		if not body:
			continue
		author = comment.author.name if comment.author else None
		comments.append(
			{
				"comment_id": comment.id,
				"body": body,
				"author": author,
				"score": comment.score,
				"created_utc": comment.created_utc,
			}
		)

	return comments


def _build_reddit_client() -> asyncpraw.Reddit:
	client_id = os.getenv("REDDIT_CLIENT_ID")
	client_secret = os.getenv("REDDIT_CLIENT_SECRET")
	user_agent = os.getenv("REDDIT_USER_AGENT")

	if not client_id or not client_secret or not user_agent:
		raise IngestionConfigError(
			"Missing Reddit API environment variables. "
			"Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT."
		)

	return asyncpraw.Reddit(
		client_id=client_id,
		client_secret=client_secret,
		user_agent=user_agent,
	)


def _merge_defaults(defaults: IngestionDefaults, source: SubredditSource) -> IngestionDefaults:
	return IngestionDefaults(
		feed=source.feed or defaults.feed,
		post_limit=source.post_limit or defaults.post_limit,
		comment_limit=source.comment_limit or defaults.comment_limit,
		comment_sort=source.comment_sort or defaults.comment_sort,
		include_comments=defaults.include_comments if source.include_comments is None else source.include_comments,
		request_delay_seconds=defaults.request_delay_seconds,
	)


def _validate_feed(feed: str) -> str:
	feed_normalized = str(feed).lower().strip()
	if feed_normalized not in SUPPORTED_FEEDS:
		raise IngestionConfigError(f"Unsupported feed: {feed}")
	return feed_normalized


def _optional_feed(value: Any) -> str | None:
	if value is None:
		return None
	return _validate_feed(value)


def _optional_int(value: Any) -> int | None:
	if value is None:
		return None
	return int(value)


def _optional_str(value: Any) -> str | None:
	if value is None:
		return None
	return str(value)


def _optional_bool(value: Any) -> bool | None:
	if value is None:
		return None
	return bool(value)


def _clean_text(text: str | None) -> str | None:
	if not text:
		return None
	cleaned = text.strip()
	if cleaned in {"[deleted]", "[removed]"}:
		return None
	return cleaned


async def _safe_sleep(seconds: float) -> None:
	if seconds and seconds > 0:
		await asyncio.sleep(seconds)
