"""Pre-batch check: fast local regex filters for normalized posts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclass
class PreCheckRules:
	blocked_terms: list[str]
	blocked_subreddits: list[str]
	blocked_sources: list[str]
	term_patterns: list[re.Pattern[str]] = field(default_factory=list)


def load_pre_check_rules(config_path: str | Path) -> PreCheckRules:
	path = Path(config_path)
	if not path.exists():
		raise FileNotFoundError(f"Pre-check config not found: {path}")

	raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
	blocked_terms = _normalize_list(raw.get("blocked_terms", []))
	blocked_subreddits = [value.lower() for value in _normalize_list(raw.get("blocked_subreddits", []))]
	blocked_sources = [value.lower() for value in _normalize_list(raw.get("blocked_sources", []))]
	patterns = [re.compile(term, re.IGNORECASE) for term in blocked_terms]

	return PreCheckRules(
		blocked_terms=blocked_terms,
		blocked_subreddits=blocked_subreddits,
		blocked_sources=blocked_sources,
		term_patterns=patterns,
	)


def filter_posts(posts: Iterable[dict[str, Any]], rules: PreCheckRules) -> list[dict[str, Any]]:
	kept: list[dict[str, Any]] = []
	for post in posts:
		if _is_blocked(post, rules):
			continue
		kept.append(post)
	return kept


def _is_blocked(post: dict[str, Any], rules: PreCheckRules) -> bool:
	source = str(post.get("source", "")).lower()
	if source and source in rules.blocked_sources:
		return True

	community = str(post.get("community") or post.get("subreddit") or "").lower()
	if community and community in rules.blocked_subreddits:
		return True

	text = _collect_text(post)
	if text and _matches_terms(text, rules.term_patterns):
		return True

	return False


def _collect_text(post: dict[str, Any]) -> str:
	parts: list[str] = []
	for key in ("text", "title", "body", "selftext"):
		value = post.get(key)
		if value:
			parts.append(str(value))

	for comment in post.get("comments", []) or []:
		if not isinstance(comment, dict):
			continue
		body = comment.get("body")
		if body:
			parts.append(str(body))

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
