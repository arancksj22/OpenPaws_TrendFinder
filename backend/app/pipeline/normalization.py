"""Normalization layer: unify raw ingestion into platform-agnostic JSON."""

from __future__ import annotations

from typing import Any, Iterable, TypeVar

from pydantic import BaseModel

from app.schemas.post import (
	NormalizedComment,
	NormalizedPost,
	PostFlags,
	PostMetrics,
	RawBlueskyPost,
	RawBlueskyReply,
	RawRedditComment,
	RawRedditPost,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


# ---------------------------------------------------------------------------
# Bluesky normalization (primary)
# ---------------------------------------------------------------------------


def normalize_bluesky_posts(raw_posts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
	normalized: list[dict[str, Any]] = []
	for raw in raw_posts:
		parsed = _validate_model(RawBlueskyPost, raw)
		normalized_post = _normalize_bluesky_post(parsed)
		normalized.append(_model_dump(normalized_post))
	return normalized


def _normalize_bluesky_post(raw: RawBlueskyPost) -> NormalizedPost:
	# Bluesky posts have no title — text field is the full body.
	text = raw.text
	comments = [
		_normalize_bluesky_reply(raw.source, reply)
		for reply in raw.comments
		if _has_text(reply.body)
	]
	normalized_comments = [c for c in comments if c is not None]

	return NormalizedPost(
		source=raw.source,
		source_id=raw.post_id,
		source_fullname=raw.post_cid,
		community=raw.community,
		title=None,
		body=raw.text,
		text=text,
		author=raw.author,
		url=raw.url,
		permalink=raw.permalink,
		created_utc=raw.created_utc,
		metrics=PostMetrics(
			score=raw.score,
			num_comments=raw.num_comments,
			upvote_ratio=None,
		),
		flags=PostFlags(
			is_self=True,
			over_18=False,
		),
		comments=normalized_comments,
		comment_count_ingested=len(normalized_comments),
	)


def _normalize_bluesky_reply(
	source: str, reply: RawBlueskyReply,
) -> NormalizedComment | None:
	if not _has_text(reply.body):
		return None
	return NormalizedComment(
		source=source,
		source_id=reply.comment_id,
		body=reply.body,
		author=reply.author,
		score=reply.score,
		created_utc=reply.created_utc,
	)


# ---------------------------------------------------------------------------
# Reddit normalization (kept for backward compatibility)
# ---------------------------------------------------------------------------


def normalize_reddit_posts(raw_posts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
	normalized: list[dict[str, Any]] = []
	for raw in raw_posts:
		parsed = _validate_model(RawRedditPost, raw)
		normalized_post = _normalize_reddit_post(parsed)
		normalized.append(_model_dump(normalized_post))
	return normalized


def _normalize_reddit_post(raw: RawRedditPost) -> NormalizedPost:
	text = _merge_text(raw.title, raw.selftext)
	comments = [
		_normalize_reddit_comment(raw.source, comment)
		for comment in raw.comments
		if _has_text(comment.body)
	]
	normalized_comments = [comment for comment in comments if comment is not None]

	return NormalizedPost(
		source=raw.source,
		source_id=raw.post_id,
		source_fullname=raw.post_fullname,
		community=raw.subreddit,
		title=raw.title,
		body=raw.selftext,
		text=text,
		author=raw.author,
		url=raw.url,
		permalink=raw.permalink,
		created_utc=raw.created_utc,
		metrics=PostMetrics(
			score=raw.score,
			num_comments=raw.num_comments,
			upvote_ratio=raw.upvote_ratio,
		),
		flags=PostFlags(
			is_self=raw.is_self,
			over_18=raw.over_18,
		),
		comments=normalized_comments,
		comment_count_ingested=len(normalized_comments),
	)


def _normalize_reddit_comment(
	source: str, comment: RawRedditComment,
) -> NormalizedComment | None:
	if not _has_text(comment.body):
		return None
	return NormalizedComment(
		source=source,
		source_id=comment.comment_id,
		body=comment.body,
		author=comment.author,
		score=comment.score,
		created_utc=comment.created_utc,
	)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _merge_text(title: str | None, body: str | None) -> str | None:
	title_clean = title.strip() if title else ""
	body_clean = body.strip() if body else ""
	if title_clean and body_clean:
		return f"{title_clean}\n\n{body_clean}"
	if title_clean:
		return title_clean
	if body_clean:
		return body_clean
	return None


def _has_text(value: str | None) -> bool:
	return bool(value and value.strip())


def _model_dump(model: BaseModel) -> dict[str, Any]:
	if hasattr(model, "model_dump"):
		return model.model_dump(exclude_none=True)
	return model.dict(exclude_none=True)


def _validate_model(model_cls: type[ModelT], data: Any) -> ModelT:
	if hasattr(model_cls, "model_validate"):
		return model_cls.model_validate(data)
	return model_cls.parse_obj(data)
