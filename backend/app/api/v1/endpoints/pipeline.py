"""Pipeline trigger endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.queue import RedisQueue, RedisQueueConfig
from app.pipeline.ingestion import ingest_bluesky_posts
from app.pipeline.normalization import normalize_bluesky_posts

logger = logging.getLogger(__name__)

router = APIRouter()


class PipelineTriggerRequest(BaseModel):
	trigger: Literal["cron", "ui"] = "cron"
	bluesky_config_path: str = "config/bluesky.yaml"
	discovery_stream_name: str = "trendfinder:discovery"
	async_run: bool = True


class PipelineTriggerResponse(BaseModel):
	status: str
	trigger: str
	task_id: str | None = None
	ingested_count: int | None = None
	normalized_count: int | None = None
	enqueued_count: int | None = None
	stream_name: str | None = None


@router.post("/trigger")
async def trigger_pipeline(request: PipelineTriggerRequest) -> JSONResponse:
	if request.async_run:
		task_id = uuid4().hex
		asyncio.create_task(
			_run_discovery_pipeline(
				bluesky_config_path=request.bluesky_config_path,
				discovery_stream_name=request.discovery_stream_name,
				task_id=task_id,
			)
		)
		response = PipelineTriggerResponse(
			status="accepted",
			trigger=request.trigger,
			task_id=task_id,
			stream_name=request.discovery_stream_name,
		)
		return JSONResponse(
			content=response.model_dump(exclude_none=True),
			status_code=status.HTTP_202_ACCEPTED,
		)

	results = await _run_discovery_pipeline(
		bluesky_config_path=request.bluesky_config_path,
		discovery_stream_name=request.discovery_stream_name,
		task_id=None,
	)
	response = PipelineTriggerResponse(
		status="completed",
		trigger=request.trigger,
		stream_name=request.discovery_stream_name,
		**results,
	)
	return JSONResponse(
		content=response.model_dump(exclude_none=True),
		status_code=status.HTTP_200_OK,
	)


async def _run_discovery_pipeline(
	bluesky_config_path: str,
	discovery_stream_name: str,
	task_id: str | None,
) -> dict[str, int]:
	try:
		raw_posts = await ingest_bluesky_posts(bluesky_config_path)
		normalized_posts = normalize_bluesky_posts(raw_posts)
		queue = await RedisQueue.create(
			RedisQueueConfig(stream_name=discovery_stream_name)
		)
		try:
			await queue.enqueue_many(normalized_posts)
		finally:
			await queue.close()
		return {
			"ingested_count": len(raw_posts),
			"normalized_count": len(normalized_posts),
			"enqueued_count": len(normalized_posts),
		}
	except Exception:
		logger.exception("Pipeline run failed for task_id=%s", task_id)
		return {
			"ingested_count": 0,
			"normalized_count": 0,
			"enqueued_count": 0,
		}
