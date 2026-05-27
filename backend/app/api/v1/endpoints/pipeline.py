"""Pipeline trigger endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.queue import RedisQueue, RedisQueueConfig
from app.pipeline.clustering import ClusteringConfig, cluster_posts
from app.pipeline.ingestion import ingest_bluesky_posts
from app.pipeline.normalization import normalize_bluesky_posts
from app.pipeline.post_check import load_post_check_rules, post_batch_check, update_trend_statuses
from app.pipeline.pre_check import filter_posts, load_pre_check_rules

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


class DiscoveryRunnerRequest(BaseModel):
	discovery_stream_name: str = "trendfinder:discovery"
	pre_check_config_path: str = "config/pre_check.yaml"
	post_check_config_path: str = "config/post_check.yaml"
	batch_size: int = 100
	max_batches: int = 5
	drain: bool = True


from app.schemas.content import DiscoveryRunnerResponse


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


@router.post("/discover", response_model=DiscoveryRunnerResponse)
async def run_discovery_pipeline(request: DiscoveryRunnerRequest) -> DiscoveryRunnerResponse:
	queue = await RedisQueue.create(RedisQueueConfig(stream_name=request.discovery_stream_name))
	messages = []
	message_ids: list[str] = []
	try:
		for _ in range(max(1, request.max_batches)):
			batch = await queue.dequeue(count=request.batch_size)
			if not batch:
				break
			messages.extend(batch)
			message_ids.extend([msg.message_id for msg in batch])
			if not request.drain:
				break
	finally:
		await queue.close()

	if not messages:
		return DiscoveryRunnerResponse(
			status="empty",
			dequeued_count=0,
			kept_posts=0,
			clustered_trends=0,
			blocked_trends=0,
			acknowledged=0,
			stream_name=request.discovery_stream_name,
		)

	try:
		posts = [msg.payload for msg in messages]
		pre_rules = load_pre_check_rules(request.pre_check_config_path)
		filtered_posts = filter_posts(posts, pre_rules)

		trends = cluster_posts(filtered_posts, ClusteringConfig()) if filtered_posts else []
		post_rules = load_post_check_rules(request.post_check_config_path)
		kept_trends, blocked_trends = post_batch_check(trends, post_rules)

		blocked_ids = [trend.get("trend_id") for trend in blocked_trends if trend.get("trend_id")]
		kept_ids = [trend.get("trend_id") for trend in kept_trends if trend.get("trend_id")]

		if blocked_ids:
			update_trend_statuses(blocked_ids, "blocked")
		if kept_ids:
			update_trend_statuses(kept_ids, "pending_review")

		queue = await RedisQueue.create(RedisQueueConfig(stream_name=request.discovery_stream_name))
		try:
			ack_count = await queue.ack(message_ids)
		finally:
			await queue.close()

		return DiscoveryRunnerResponse(
			status="completed",
			dequeued_count=len(messages),
			kept_posts=len(filtered_posts),
			clustered_trends=len(trends),
			blocked_trends=len(blocked_trends),
			acknowledged=ack_count,
			stream_name=request.discovery_stream_name,
		)
	except Exception as exc:
		logger.exception("Discover pipeline failed")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Discover pipeline crashed: {exc}"
		) from exc


async def _run_discovery_pipeline(
	bluesky_config_path: str,
	discovery_stream_name: str,
	task_id: str | None,
) -> dict[str, int]:
	import google.generativeai as genai
	genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

	try:
		raw_posts = await ingest_bluesky_posts(bluesky_config_path)
		normalized_posts = normalize_bluesky_posts(raw_posts)

		# Generate embeddings using Gemini
		for post in normalized_posts:
			text = post.get("text", "")
			if not text:
				post["embedding"] = [0.0] * 1024
				continue
			try:
				result = genai.embed_content(
					model="models/text-embedding-004",
					content=text,
					task_type="clustering"
				)
				vector = result['embedding']
				# Pad 768-dim vector to 1024 to match DB schema
				if len(vector) < 1024:
					vector.extend([0.0] * (1024 - len(vector)))
				post["embedding"] = vector[:1024]
			except Exception as e:
				logger.warning("Failed to generate embedding for post: %s", e)
				post["embedding"] = [0.0] * 1024

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
