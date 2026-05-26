"""Trend review and explainer endpoints (Phase 6: Human in the Loop)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.pipeline.humanintheloop import (
	HumanInTheLoopConfig,
	fetch_trends_for_review,
	generate_explainer,
)
from app.schemas.trend import (
	ExplainerResponse,
	TrendListResponse,
	TrendSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=TrendListResponse)
def list_trends(
	status_filter: str | None = Query(
		default="pending_review",
		alias="status",
		description="Filter trends by status. Pass empty string or omit for all.",
	),
	limit: int = Query(default=20, ge=1, le=100, description="Page size."),
	offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> TrendListResponse:
	"""List trends that survived post-batch check, with example posts.

	Intended for the dashboard review screen where a social media manager
	inspects trend clusters before requesting an AI explainer.
	"""
	effective_status = status_filter if status_filter else None

	try:
		raw_trends = fetch_trends_for_review(
			config=HumanInTheLoopConfig(),
			status_filter=effective_status,
			limit=limit,
			offset=offset,
		)
	except RuntimeError as exc:
		logger.exception("Failed to fetch trends for review")
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"Database error: {exc}",
		) from exc

	trends = [TrendSummary(**t) for t in raw_trends]
	return TrendListResponse(trends=trends, count=len(trends))


@router.post("/{trend_id}/explainer", response_model=ExplainerResponse)
def request_explainer(trend_id: str) -> ExplainerResponse:
	"""Generate a short AI explainer for a single trend.

	Calls Gemini 2.5 Flash to produce a 2-3 sentence summary explaining the
	trend's relevance to animal rights advocacy. The explainer is written back
	to the trends table and the status is updated to ``explainer_ready``.
	"""
	try:
		result = generate_explainer(
			trend_id=trend_id,
			config=HumanInTheLoopConfig(),
		)
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(exc),
		) from exc
	except RuntimeError as exc:
		logger.exception("Gemini explainer generation failed for trend_id=%s", trend_id)
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"AI service error: {exc}",
		) from exc

	return ExplainerResponse(**result)
