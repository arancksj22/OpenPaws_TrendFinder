"""Vector clustering using Supabase pgvector."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable

from supabase import Client, create_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClusteringConfig:
	supabase_url: str | None = None
	supabase_service_role_key: str | None = None
	embedding_dim: int = 1024
	match_threshold: float = 0.45
	match_count: int = 50
	top_k: int = 5
	posts_table: str = "posts"
	embeddings_table: str = "post_embeddings"
	trends_table: str = "trends"
	trend_examples_table: str = "trend_examples"
	match_rpc: str = "match_posts"


def cluster_posts(
	normalized_posts: Iterable[dict[str, Any]],
	config: ClusteringConfig | None = None,
) -> list[dict[str, Any]]:
	config = config or ClusteringConfig()
	posts = list(normalized_posts)
	if not posts:
		return []

	client = _create_supabase_client(config)
	embeddings_by_key = _collect_embeddings(posts, config.embedding_dim)
	post_ids = _upsert_posts(client, posts, config)
	_upsert_embeddings(client, embeddings_by_key, post_ids, config)

	post_by_id = _map_posts_by_id(posts, post_ids)
	unassigned = set(post_by_id.keys())
	trends: list[dict[str, Any]] = []

	while unassigned:
		seed_id = next(iter(unassigned))
		seed_post = post_by_id[seed_id]
		seed_key = _post_key(seed_post)
		seed_embedding = embeddings_by_key.get(seed_key)
		if seed_embedding is None:
			unassigned.remove(seed_id)
			continue

		matched_ids = _match_posts(client, seed_embedding, config)
		cluster_ids = (matched_ids | {seed_id}) & unassigned
		if not cluster_ids:
			cluster_ids = {seed_id}

		trend_id = _create_trend(client, seed_id, len(cluster_ids), config)
		examples = _select_top_examples(cluster_ids, post_by_id, config.top_k)
		_insert_trend_examples(client, trend_id, examples, config)

		unassigned -= cluster_ids
		trends.append(
			{
				"trend_id": trend_id,
				"cluster_key": seed_id,
				"post_ids": list(cluster_ids),
				"example_post_ids": examples,
			}
		)

	return trends


def _create_supabase_client(config: ClusteringConfig) -> Client:
	url = config.supabase_url or os.getenv("SUPABASE_URL")
	key = config.supabase_service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
	if not url or not key:
		raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
	return create_client(url, key)


def _collect_embeddings(posts: list[dict[str, Any]], embedding_dim: int) -> dict[tuple[str, str], list[float]]:
	embeddings: dict[tuple[str, str], list[float]] = {}
	for post in posts:
		embedding = post.get("embedding")
		if not isinstance(embedding, list):
			raise ValueError("Missing embedding list on normalized post")
		if len(embedding) != embedding_dim:
			raise ValueError(f"Embedding must be length {embedding_dim}")
		key = _post_key(post)
		embeddings[key] = embedding
	return embeddings


def _upsert_posts(client: Client, posts: list[dict[str, Any]], config: ClusteringConfig) -> dict[tuple[str, str], str]:
	rows = [_post_row_from_normalized(post) for post in posts]
	response = client.table(config.posts_table).upsert(rows, on_conflict="source,source_id").execute()
	data = response.data or []
	if not data:
		raise RuntimeError("Supabase returned no post rows from upsert")

	return {(row["source"], row["source_id"]): row["id"] for row in data}


def _upsert_embeddings(
	client: Client,
	embeddings_by_key: dict[tuple[str, str], list[float]],
	post_ids: dict[tuple[str, str], str],
	config: ClusteringConfig,
) -> None:
	rows: list[dict[str, Any]] = []
	for key, post_id in post_ids.items():
		embedding = embeddings_by_key.get(key)
		if embedding is None:
			continue
		rows.append({"post_id": post_id, "embedding": embedding})

	if rows:
		client.table(config.embeddings_table).upsert(rows).execute()


def _match_posts(client: Client, embedding: list[float], config: ClusteringConfig) -> set[str]:
	response = client.rpc(
		config.match_rpc,
		{
			"query_embedding": embedding,
			"match_threshold": config.match_threshold,
			"match_count": config.match_count,
		},
	).execute()
	rows = response.data or []
	return {row["post_id"] for row in rows if "post_id" in row}


def _create_trend(client: Client, cluster_key: str, size: int, config: ClusteringConfig) -> str:
	response = client.table(config.trends_table).insert(
		{
			"cluster_key": cluster_key,
			"representative_count": min(size, config.top_k),
			"status": "pending_review",
		}
	).execute()
	rows = response.data or []
	if not rows:
		raise RuntimeError("Supabase returned no trend rows from insert")
	return rows[0]["id"]


def _insert_trend_examples(
	client: Client,
	trend_id: str,
	examples: list[str],
	config: ClusteringConfig,
) -> None:
	rows = [
		{"trend_id": trend_id, "post_id": post_id, "rank": index + 1}
		for index, post_id in enumerate(examples)
	]
	if rows:
		client.table(config.trend_examples_table).insert(rows).execute()


def _select_top_examples(
	post_ids: Iterable[str],
	post_by_id: dict[str, dict[str, Any]],
	top_k: int,
) -> list[str]:
	scored = []
	for post_id in post_ids:
		post = post_by_id.get(post_id, {})
		scored.append((post_id, _engagement_score(post)))
	scored.sort(key=lambda item: item[1], reverse=True)
	return [post_id for post_id, _score in scored[:top_k]]


def _engagement_score(post: dict[str, Any]) -> int:
	metrics = post.get("metrics") or {}
	score = metrics.get("score") if isinstance(metrics, dict) else None
	if score is None:
		score = post.get("score")
	num_comments = metrics.get("num_comments") if isinstance(metrics, dict) else None
	if num_comments is None:
		num_comments = post.get("num_comments")
	return int(score or 0) + int(num_comments or 0)


def _post_row_from_normalized(post: dict[str, Any]) -> dict[str, Any]:
	metrics = post.get("metrics") or {}
	return {
		"source": post.get("source"),
		"source_id": post.get("source_id"),
		"source_fullname": post.get("source_fullname"),
		"community": post.get("community"),
		"title": post.get("title"),
		"body": post.get("body"),
		"text": post.get("text"),
		"author": post.get("author"),
		"url": post.get("url"),
		"permalink": post.get("permalink"),
		"created_utc": post.get("created_utc"),
		"score": metrics.get("score") if isinstance(metrics, dict) else post.get("score"),
		"num_comments": metrics.get("num_comments") if isinstance(metrics, dict) else post.get("num_comments"),
		"upvote_ratio": metrics.get("upvote_ratio") if isinstance(metrics, dict) else post.get("upvote_ratio"),
	}


def _post_key(post: dict[str, Any]) -> tuple[str, str]:
	source = str(post.get("source"))
	source_id = str(post.get("source_id"))
	if not source or not source_id:
		raise ValueError("Normalized post missing source or source_id")
	return source, source_id


def _map_posts_by_id(
	posts: Iterable[dict[str, Any]],
	post_ids: dict[tuple[str, str], str],
) -> dict[str, dict[str, Any]]:
	mapped: dict[str, dict[str, Any]] = {}
	for post in posts:
		key = _post_key(post)
		post_id = post_ids.get(key)
		if post_id:
			mapped[post_id] = post
	return mapped
