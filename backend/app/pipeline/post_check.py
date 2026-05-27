"""Post-batch check: evaluate trend clusters as a single unit."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml
from supabase import Client, create_client
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


DEFAULT_ADVOCACY_KEYWORDS = [
	"animal",
	"animals",
	"animal rights",
	"animal welfare",
	"vegan",
	"veganism",
	"plant-based",
	"factory farm",
	"fur",
	"sanctuary",
	"rescue",
	"adoption",
	"wildlife",
]


@dataclass
class PostCheckRules:
	advocacy_keywords: list[str]
	negative_threshold: float
	negative_ratio: float
	min_posts: int


@dataclass(frozen=True)
class PostCheckConfig:
	supabase_url: str | None = None
	supabase_service_role_key: str | None = None
	posts_table: str = "posts"
	trends_table: str = "trends"
	select_fields: str = "id,title,body,text,permalink,url,community"


def load_post_check_rules(config_path: str | Path) -> PostCheckRules:
	path = Path(config_path)
	if not path.exists():
		raise FileNotFoundError(f"Post-check config not found: {path}")

	raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
	advocacy_keywords = _normalize_list(raw.get("advocacy_keywords", DEFAULT_ADVOCACY_KEYWORDS))
	negative_threshold = float(raw.get("negative_threshold", -0.4))
	negative_ratio = float(raw.get("negative_ratio", 0.6))
	min_posts = int(raw.get("min_posts", 3))

	return PostCheckRules(
		advocacy_keywords=advocacy_keywords,
		negative_threshold=negative_threshold,
		negative_ratio=negative_ratio,
		min_posts=min_posts,
	)


def post_batch_check(
	trends: Iterable[dict[str, Any]],
	rules: PostCheckRules,
	config: PostCheckConfig | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	config = config or PostCheckConfig()
	client = _create_supabase_client(config)

	analyzer = SentimentIntensityAnalyzer()
	kept: list[dict[str, Any]] = []
	blocked: list[dict[str, Any]] = []
	for trend in trends:
		trend_id = trend.get("trend_id")
		example_ids = trend.get("example_post_ids") or []
		if not example_ids:
			kept.append(trend)
			continue

		posts = _fetch_posts_by_id(client, example_ids, config)
		cluster_text = _collect_cluster_text(posts)
		if _is_negative_trend(posts, cluster_text, rules, analyzer):
			logger.warning("Post-check drop: trend_id=%s negative sentiment consensus", trend_id)
			blocked.append({"trend_id": trend_id, "reason": "negative_sentiment"})
			continue

		kept.append(trend)

	return kept, blocked


def _create_supabase_client(config: PostCheckConfig) -> Client:
	url = config.supabase_url or os.getenv("SUPABASE_URL")
	key = config.supabase_service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
	if not url or not key:
		raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
	return create_client(url, key)


def _fetch_posts_by_id(client: Client, post_ids: list[str], config: PostCheckConfig) -> list[dict[str, Any]]:
	response = (
		client.table(config.posts_table)
		.select(config.select_fields)
		.in_("id", post_ids)
		.execute()
	)
	return response.data or []


def _collect_cluster_text(posts: Iterable[dict[str, Any]]) -> str:
	parts: list[str] = []
	for post in posts:
		for key in ("text", "title", "body"):
			value = post.get(key)
			if value:
				parts.append(str(value))
	return "\n".join(parts)


def _is_negative_trend(
	posts: list[dict[str, Any]],
	cluster_text: str,
	rules: PostCheckRules,
	analyzer: SentimentIntensityAnalyzer,
) -> bool:
	if not cluster_text:
		return False
	if not _has_advocacy_context(cluster_text, rules.advocacy_keywords):
		return False
	if len(posts) < max(1, rules.min_posts):
		return False

	negative_hits = 0
	considered = 0
	for post in posts:
		post_text = _collect_post_text(post)
		if not post_text:
			continue
		considered += 1
		compound = analyzer.polarity_scores(post_text).get("compound", 0.0)
		if compound <= rules.negative_threshold:
			negative_hits += 1

	if considered == 0:
		return False
	return (negative_hits / considered) >= rules.negative_ratio


def _collect_post_text(post: dict[str, Any]) -> str:
	parts: list[str] = []
	for key in ("text", "title", "body"):
		value = post.get(key)
		if value:
			parts.append(str(value))
	return "\n".join(parts)


def _has_advocacy_context(text: str, keywords: Iterable[str]) -> bool:
	text_lower = text.lower()
	return any(keyword.lower() in text_lower for keyword in keywords)


def _normalize_list(items: Iterable[Any]) -> list[str]:
	normalized: list[str] = []
	for item in items or []:
		value = str(item).strip()
		if value:
			normalized.append(value)
	return normalized


def update_trend_statuses(
	trend_ids: Iterable[str],
	status_value: str,
	config: PostCheckConfig | None = None,
) -> int:
	config = config or PostCheckConfig()
	client = _create_supabase_client(config)
	ids = [trend_id for trend_id in trend_ids if trend_id]
	if not ids:
		return 0
	response = (
		client.table(config.trends_table)
		.update({"status": status_value})
		.in_("id", ids)
		.execute()
	)
	return len(response.data or [])
