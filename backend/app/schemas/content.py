"""Schemas for generation and history endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class StorageSummary(BaseModel):
	record_id: str
	image_url: str | None = None
	table: str


class GenerateContentResponse(BaseModel):
	trend_id: str
	generation: dict[str, Any]
	storage: StorageSummary


class HistoryResponse(BaseModel):
	items: list[dict[str, Any]]


class DiscoveryRunnerResponse(BaseModel):
	status: str
	dequeued_count: int
	kept_posts: int
	clustered_trends: int
	blocked_trends: int
	acknowledged: int
	stream_name: str
