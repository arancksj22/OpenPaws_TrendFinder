"""Schemas for trend review and explainer endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExamplePostSummary(BaseModel):
	"""Lightweight post fields for dashboard display."""

	model_config = ConfigDict(extra="ignore")

	id: str
	title: str | None = None
	body: str | None = None
	text: str | None = None
	community: str | None = None
	permalink: str | None = None
	url: str | None = None
	score: int | None = None
	num_comments: int | None = None


class TrendSummary(BaseModel):
	"""Single trend listing item for the review dashboard."""

	model_config = ConfigDict(extra="ignore")

	trend_id: str
	cluster_key: str | None = None
	representative_count: int | None = None
	status: str | None = None
	created_at: str | None = None
	explainer: str | None = None
	example_posts: list[ExamplePostSummary] = []


class TrendListResponse(BaseModel):
	"""Wrapper for paginated trend listing."""

	trends: list[TrendSummary]
	count: int


class ExplainerRequest(BaseModel):
	"""POST body for requesting an explainer (unused when trend_id is a path param)."""

	trend_id: str


class ExplainerResponse(BaseModel):
	"""Response after generating an AI explainer for a trend."""

	trend_id: str
	explainer: str
	model_used: str
	prompt_tokens: int | None = None
	completion_tokens: int | None = None
