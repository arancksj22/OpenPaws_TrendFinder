"""Phase 10: Closed-Loop Production Storage.

Receives the scored, serialised output from Phase 9 (plus the GenerationResult
from Phase 8 which carries the raw image bytes) and persists everything to
Supabase:

  1. Text variations (brief + 3 scored drafts) → ``generated_content`` table.
  2. Trend infographic image (PNG bytes)        → Supabase Storage bucket
                                                  ``trend-images``.

All records and storage paths are namespaced under the caller's ``user_id``
so that users can only see their own generation history.

Public API
----------
    result: StorageResult = store_generation(
        user_id, generation_result, scored_payload, config
    )

``scored_payload`` is the dict produced by ``serialise_result()`` (Phase 9).
``generation_result`` is the ``GenerationResult`` object from Phase 8 (holds
``image_bytes`` and ``trend_id``).

Required Supabase SQL
---------------------
Run once in the Supabase SQL editor:

    CREATE TABLE IF NOT EXISTS generated_content (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id         text        NOT NULL,
        trend_id        text        NOT NULL,
        advocacy_brief  text,
        positioning_angle text,
        suggested_hashtags jsonb,
        scored_drafts   jsonb       NOT NULL,
        recommended_index integer,
        image_url       text,
        image_prompt    text,
        total_prompt_tokens   integer,
        total_completion_tokens integer,
        created_at      timestamptz NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS generated_content_user_idx
        ON generated_content (user_id, created_at DESC);

    CREATE INDEX IF NOT EXISTS generated_content_trend_idx
        ON generated_content (trend_id);
"""

from __future__ import annotations

import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from app.pipeline.generation import GenerationResult

logger = logging.getLogger(__name__)

# Supabase Storage bucket name — create this in your project dashboard.
_BUCKET_NAME = "trend-images"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StorageConfig:
	"""Configuration for Phase 10.

	Attributes
	----------
	supabase_url:
	    Supabase project REST URL. Reads ``SUPABASE_URL`` from env if not set.
	supabase_service_role_key:
	    Service-role key (full write access). Reads ``SUPABASE_SERVICE_ROLE_KEY``.
	table_name:
	    Name of the Supabase table for generated content records.
	storage_bucket:
	    Name of the Supabase Storage bucket for trend images.
	"""

	supabase_url: str | None = None
	supabase_service_role_key: str | None = None
	table_name: str = "generated_content"
	storage_bucket: str = _BUCKET_NAME


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class StorageResult:
	"""Return value from ``store_generation``."""

	record_id: str          # UUID of the inserted ``generated_content`` row
	user_id: str
	trend_id: str
	image_url: str | None   # Public storage URL, or None if no image was stored
	storage_path: str | None  # e.g. "{user_id}/{trend_id}/2024-01-15T12-00-00.png"
	table: str              # Name of the table written to


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_generation(
	user_id: str,
	generation_result: GenerationResult,
	scored_payload: dict[str, Any],
	config: StorageConfig | None = None,
) -> StorageResult:
	"""Persist a complete generation run to Supabase.

	Parameters
	----------
	user_id:
	    Caller's identifier — used as the storage namespace.  All records and
	    storage objects are scoped to this value.  Use your auth system's user
	    UUID here; pass ``"anonymous"`` for unauthenticated MVP usage.
	generation_result:
	    The ``GenerationResult`` from Phase 8.  Carries ``trend_id``,
	    ``brief``, ``image_bytes``, and ``image_prompt_used``.
	scored_payload:
	    The dict produced by ``revalidation.serialise_result()``.  Contains
	    the scored drafts with all five individual scores and composite.
	config:
	    Optional ``StorageConfig``; reads env-vars if not provided.

	Returns
	-------
	``StorageResult`` with the inserted record ID and public image URL.

	Raises
	------
	``RuntimeError`` if Supabase credentials are missing.
	``RuntimeError`` if the database insert fails.
	"""
	config = config or StorageConfig()
	client = _create_client(config)

	trend_id = generation_result.trend_id

	# ── 1. Upload image to Storage (non-fatal if it fails) ────────────────
	image_url: str | None = None
	storage_path: str | None = None

	if generation_result.image_bytes:
		try:
			storage_path, image_url = _upload_image(
				client=client,
				user_id=user_id,
				trend_id=trend_id,
				image_bytes=generation_result.image_bytes,
				config=config,
			)
		except Exception:
			logger.exception(
				"Image upload failed for user_id=%s trend_id=%s (non-fatal)",
				user_id, trend_id,
			)

	# ── 2. Insert text record into generated_content table ────────────────
	record_id = _insert_record(
		client=client,
		user_id=user_id,
		trend_id=trend_id,
		generation_result=generation_result,
		scored_payload=scored_payload,
		image_url=image_url,
		config=config,
	)

	logger.info(
		"Phase 10 stored: user_id=%s trend_id=%s record_id=%s image=%s",
		user_id, trend_id, record_id, image_url or "none",
	)

	return StorageResult(
		record_id=record_id,
		user_id=user_id,
		trend_id=trend_id,
		image_url=image_url,
		storage_path=storage_path,
		table=config.table_name,
	)


def fetch_user_history(
	user_id: str,
	config: StorageConfig | None = None,
	limit: int = 20,
	offset: int = 0,
) -> list[dict[str, Any]]:
	"""Return previous generation runs for a user, newest first.

	Each record includes the scored drafts and image URL so the frontend can
	render a full history view without additional lookups.

	Parameters
	----------
	user_id:
	    The user whose history to retrieve.
	config:
	    Optional ``StorageConfig``.
	limit / offset:
	    Pagination controls (max 100).

	Returns
	-------
	List of row dicts from ``generated_content``, ordered by ``created_at DESC``.
	"""
	config = config or StorageConfig()
	client = _create_client(config)

	response = (
		client.table(config.table_name)
		.select("*")
		.eq("user_id", user_id)
		.order("created_at", desc=True)
		.range(offset, offset + min(limit, 100) - 1)
		.execute()
	)
	return response.data or []


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------


def _create_client(config: StorageConfig) -> Client:
	url = config.supabase_url or os.getenv("SUPABASE_URL")
	key = config.supabase_service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
	if not url or not key:
		raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
	return create_client(url, key)


def _upload_image(
	client: Client,
	user_id: str,
	trend_id: str,
	image_bytes: bytes,
	config: StorageConfig,
) -> tuple[str, str]:
	"""Upload image bytes to Supabase Storage.

	Returns ``(storage_path, public_url)``.

	Storage path is namespaced per user:
	    ``{user_id}/{trend_id}/{timestamp}.png``
	"""
	timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
	# Sanitise user_id for safe path usage (strip slashes / dots).
	safe_user = _sanitise_path_segment(user_id)
	safe_trend = _sanitise_path_segment(trend_id)
	storage_path = f"{safe_user}/{safe_trend}/{timestamp}.png"

	client.storage.from_(config.storage_bucket).upload(
		path=storage_path,
		file=image_bytes,
		file_options={"content-type": "image/png", "upsert": "true"},
	)

	# Build the public URL using the Supabase storage URL pattern.
	supabase_url = (config.supabase_url or os.getenv("SUPABASE_URL") or "").rstrip("/")
	# Strip /rest/v1 suffix if present — storage URL uses a different path.
	supabase_base = supabase_url.replace("/rest/v1", "")
	public_url = (
		f"{supabase_base}/storage/v1/object/public/{config.storage_bucket}/{storage_path}"
	)

	logger.info("Image uploaded to storage path=%s", storage_path)
	return storage_path, public_url


def _insert_record(
	client: Client,
	user_id: str,
	trend_id: str,
	generation_result: GenerationResult,
	scored_payload: dict[str, Any],
	image_url: str | None,
	config: StorageConfig,
) -> str:
	"""Insert a generated_content row and return its UUID."""
	brief = generation_result.brief

	row: dict[str, Any] = {
		"user_id":                user_id,
		"trend_id":               trend_id,
		"advocacy_brief":         brief.advocacy_brief,
		"positioning_angle":      brief.positioning_angle,
		"suggested_hashtags":     brief.suggested_hashtags,
		# The full scored drafts JSON is stored as-is — all 5 individual scores
		# and the composite are present, ready for the frontend history view.
		"scored_drafts":          scored_payload.get("scored_drafts", []),
		"recommended_index":      scored_payload.get("recommended_index"),
		"image_url":              image_url,
		"image_prompt":           generation_result.image_prompt_used,
		"total_prompt_tokens":    generation_result.total_prompt_tokens,
		"total_completion_tokens": generation_result.total_completion_tokens,
	}

	response = client.table(config.table_name).insert(row).execute()
	rows = response.data or []
	if not rows:
		raise RuntimeError(
			f"Supabase insert into {config.table_name!r} returned no data"
		)
	return str(rows[0]["id"])


def _sanitise_path_segment(value: str) -> str:
	"""Remove characters unsafe in a Supabase Storage path segment."""
	import re
	# Keep alphanumerics, hyphens, underscores.  Replace everything else.
	return re.sub(r"[^a-zA-Z0-9_\-]", "_", value)[:80]
