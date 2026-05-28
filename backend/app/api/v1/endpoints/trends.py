"""Trend review and explainer endpoints (Phase 6: Human in the Loop)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import AuthContext, get_auth_context
from app.pipeline.cybersec_check import load_cybersec_rules, sanitize_trend_payload
from app.pipeline.generation import ContentBrief, GenerationConfig, generate_content, generate_standalone_image
from app.pipeline.humanintheloop import (
	HumanInTheLoopConfig,
	build_trend_payload,
	fetch_trends_for_review,
	generate_explainer,
)
from app.pipeline.production_storage import StorageConfig, store_generation, fetch_generation_by_trend, update_generation_image, update_draft_text
from app.pipeline.revalidation import RevalidationConfig, revalidate_and_score, serialise_result, _score_text
from app.schemas.content import GenerateContentResponse, StorageSummary, RegenerateImageResponse, UpdateDraftRequest, UpdateDraftResponse
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


@router.post("/{trend_id}/generate", response_model=GenerateContentResponse)
def generate_content_for_trend(
	trend_id: str,
	auth: AuthContext = Depends(get_auth_context),
) -> GenerateContentResponse:
	"""Chain Phases 7-10 for a single trend.

	Steps: payload -> cybersec -> Gemini -> revalidation -> storage.
	"""
	try:
		payload = build_trend_payload(
			trend_id=trend_id,
			config=HumanInTheLoopConfig(),
			ensure_explainer=True,
		)
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(exc),
		) from exc

	try:
		rules = load_cybersec_rules("config/cybersec.yaml")
		sanitized = sanitize_trend_payload(payload, rules)
		if sanitized.blocked:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Trend blocked by cybersecurity checks",
			)

		generation_result = generate_content(
			sanitized.payload,
			GenerationConfig(),
		)
		revalidation_result = revalidate_and_score(
			generation_result,
			RevalidationConfig(),
		)
		scored_payload = serialise_result(revalidation_result)
		storage_result = store_generation(
			user_id=auth.user_id,
			generation_result=generation_result,
			scored_payload=scored_payload,
			config=StorageConfig(user_jwt=auth.token),
		)
	except HTTPException:
		raise
	except RuntimeError as exc:
		logger.exception("Generate pipeline failed for trend_id=%s", trend_id)
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"Pipeline error: {exc}",
		) from exc

	return GenerateContentResponse(
		trend_id=trend_id,
		generation=scored_payload,
		storage=StorageSummary(
			record_id=storage_result.record_id,
			image_url=storage_result.image_url,
			table=storage_result.table,
		),
	)


@router.post("/{trend_id}/regenerate-image", response_model=RegenerateImageResponse)
def regenerate_image_for_trend(
	trend_id: str,
	auth: AuthContext = Depends(get_auth_context),
) -> RegenerateImageResponse:
	"""Regenerates the artwork for a given trend and updates the existing record."""
	# Fetch the existing generation record
	existing = fetch_generation_by_trend(user_id=auth.user_id, trend_id=trend_id)
	if not existing:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="No existing generation found to regenerate image for.",
		)

	# Reconstruct ContentBrief
	brief = ContentBrief(
		advocacy_brief=existing.get("advocacy_brief", ""),
		positioning_angle=existing.get("positioning_angle", ""),
		suggested_hashtags=existing.get("suggested_hashtags", []),
		prompt_tokens=0,
		completion_tokens=0,
	)

	# Call generation for image only
	image_bytes, image_prompt = generate_standalone_image(brief)
	if not image_bytes:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to regenerate image.",
		)

	# Upload and update record
	new_url = update_generation_image(
		user_id=auth.user_id,
		trend_id=trend_id,
		record_id=str(existing["id"]),
		image_bytes=image_bytes,
		image_prompt=image_prompt or "",
	)

	return RegenerateImageResponse(
		trend_id=trend_id,
		image_url=new_url,
	)


@router.patch("/{trend_id}/draft/{draft_index}", response_model=UpdateDraftResponse)
def update_draft_text_for_trend(
	trend_id: str,
	draft_index: int,
	payload: UpdateDraftRequest,
	auth: AuthContext = Depends(get_auth_context),
) -> UpdateDraftResponse:
	"""Updates the text of a specific generated draft for a trend and re-scores it."""
	# Re-score the newly edited text
	try:
		new_scores_obj = _score_text(payload.text, RevalidationConfig())
		new_scores_dict = {
			"advocacy_preference": new_scores_obj.advocacy_preference,
			"potential_influence": new_scores_obj.potential_influence,
			"emotional_impact": new_scores_obj.emotional_impact,
			"animal_alignment": new_scores_obj.animal_alignment,
			"composite": new_scores_obj.composite,
		}
	except Exception as e:
		logger.exception("Failed to re-score updated draft text")
		new_scores_dict = None

	updated_draft = update_draft_text(
		user_id=auth.user_id,
		trend_id=trend_id,
		draft_index=draft_index,
		new_text=payload.text,
		scores=new_scores_dict,
	)
	
	if not updated_draft:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Draft not found or invalid index.",
		)

	return UpdateDraftResponse(
		trend_id=trend_id,
		draft_index=draft_index,
		text=updated_draft["text"],
		char_count=updated_draft["char_count"],
		scores=updated_draft.get("scores"),
	)
