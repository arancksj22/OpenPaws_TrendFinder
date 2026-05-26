"""Schemas for raw and normalized post payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RawRedditComment(BaseModel):
	model_config = ConfigDict(extra="ignore")

	comment_id: str
	body: str | None = None
	author: str | None = None
	score: int | None = None
	created_utc: float | None = None


class RawRedditPost(BaseModel):
	model_config = ConfigDict(extra="ignore")

	source: str
	subreddit: str
	post_id: str
	post_fullname: str | None = None
	title: str | None = None
	selftext: str | None = None
	url: str | None = None
	permalink: str | None = None
	created_utc: float | None = None
	score: int | None = None
	num_comments: int | None = None
	upvote_ratio: float | None = None
	is_self: bool | None = None
	over_18: bool | None = None
	author: str | None = None
	comments: list[RawRedditComment] = Field(default_factory=list)
	comment_count_ingested: int | None = None


class RawBlueskyReply(BaseModel):
	model_config = ConfigDict(extra="ignore")

	comment_id: str
	body: str | None = None
	author: str | None = None
	score: int | None = None
	created_utc: float | None = None


class RawBlueskyPost(BaseModel):
	model_config = ConfigDict(extra="ignore")

	source: str
	community: str
	post_id: str
	post_cid: str | None = None
	text: str | None = None
	url: str | None = None
	permalink: str | None = None
	created_utc: float | None = None
	score: int | None = None
	num_comments: int | None = None
	repost_count: int | None = None
	author: str | None = None
	comments: list[RawBlueskyReply] = Field(default_factory=list)
	comment_count_ingested: int | None = None


class PostMetrics(BaseModel):
	score: int | None = None
	num_comments: int | None = None
	upvote_ratio: float | None = None


class PostFlags(BaseModel):
	is_self: bool | None = None
	over_18: bool | None = None


class NormalizedComment(BaseModel):
	source: str
	source_id: str
	body: str | None = None
	author: str | None = None
	score: int | None = None
	created_utc: float | None = None


class NormalizedPost(BaseModel):
	source: str
	source_id: str
	source_fullname: str | None = None
	community: str
	title: str | None = None
	body: str | None = None
	text: str | None = None
	author: str | None = None
	url: str | None = None
	permalink: str | None = None
	created_utc: float | None = None
	metrics: PostMetrics
	flags: PostFlags
	comments: list[NormalizedComment] = Field(default_factory=list)
	comment_count_ingested: int = 0
