"""History endpoints (Phase 10)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import AuthContext, get_auth_context
from app.pipeline.production_storage import StorageConfig, fetch_user_history
from app.schemas.content import HistoryResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=HistoryResponse)
def get_history(
	auth: AuthContext = Depends(get_auth_context),
	limit: int = Query(default=20, ge=1, le=100),
	offset: int = Query(default=0, ge=0),
) -> HistoryResponse:
	try:
		records = fetch_user_history(
			user_id=auth.user_id,
			config=StorageConfig(user_jwt=auth.token),
			limit=limit,
			offset=offset,
		)
	except RuntimeError as exc:
		logger.exception("Failed to fetch history")
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail=f"Database error: {exc}",
		) from exc

	return HistoryResponse(items=records)
