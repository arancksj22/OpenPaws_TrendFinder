"""Post-batch check: evaluate trend clusters as a single unit."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from supabase import Client, create_client

logger = logging.getLogger(__name__)


@dataclass
class PostCheckRules:
	blocked_terms: list[str]
	term_patterns: list[re.Pattern[str]] = field(default_factory=list)


@dataclass(frozen=True)
class PostCheckConfig:
	supabase_url: str | None = None
	supabase_service_role_key: str | None = None
	posts_table: str = "posts"
	select_fields: str = "id,title,body,text,permalink,url,community"


def load_post_check_rules(config_path: str | Path) -> PostCheckRules:
	path = Path(config_path)
	if not path.exists():
		raise FileNotFoundError(f"Post-check config not found: {path}")

	raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
	blocked_terms = _normalize_list(raw.get("blocked_terms", []))
	patterns = [re.compile(term, re.IGNORECASE) for term in blocked_terms]

	return PostCheckRules(blocked_terms=blocked_terms, term_patterns=patterns)


def post_batch_check(
	trends: Iterable[dict[str, Any]],
	rules: PostCheckRules,
	config: PostCheckConfig | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	config = config or PostCheckConfig()
	client = _create_supabase_client(config)

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
		if cluster_text and _matches_terms(cluster_text, rules.term_patterns):
			logger.warning("Post-check drop: trend_id=%s matched blocked terms", trend_id)
			blocked.append({"trend_id": trend_id, "reason": "blocked_terms"})
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


def _matches_terms(text: str, patterns: Iterable[re.Pattern[str]]) -> bool:
	return any(pattern.search(text) for pattern in patterns)


def _normalize_list(items: Iterable[Any]) -> list[str]:
	normalized: list[str] = []
	for item in items or []:
		value = str(item).strip()
		if value:
			normalized.append(value)
	return normalized
