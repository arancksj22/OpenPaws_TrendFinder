"""Phase 6: Human in the Loop Trend Explainer.

Triggered on dashboard interaction. Fetches trends that survived post-batch
check from Supabase and generates a low-cost Gemini 2.5 Flash summary
explaining each trend's relevance to animal rights advocacy.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import openai
from supabase import Client, create_client
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HumanInTheLoopConfig:
	supabase_url: str | None = None
	supabase_service_role_key: str | None = None
	cerebras_api_key: str | None = None
	text_model: str = "llama3.1-8b"
	trends_table: str = "trends"
	trend_examples_table: str = "trend_examples"
	posts_table: str = "posts"
	posts_select_fields: str = "id,title,body,text,community,permalink,url,score,num_comments"
	max_prompt_posts: int = 5
	max_explainer_tokens: int = 300


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_trends_for_review(
	config: HumanInTheLoopConfig | None = None,
	*,
	status_filter: str | None = "pending_review",
	limit: int = 20,
	offset: int = 0,
) -> list[dict[str, Any]]:
	"""Return trends with their example posts, ready for dashboard display.

	Each returned dict matches the ``TrendSummary`` schema shape:
	``trend_id``, ``cluster_key``, ``representative_count``, ``status``,
	``created_at``, ``explainer``, and ``example_posts`` (list of post dicts).
	"""
	config = config or HumanInTheLoopConfig()
	client = _create_supabase_client(config)

	# Build the trends query.
	query = client.table(config.trends_table).select("*")
	if status_filter:
		query = query.eq("status", status_filter)
	query = query.order("representative_count", desc=True).order("created_at", desc=True).range(offset, offset + limit - 1)

	trends_response = query.execute()
	trend_rows = trends_response.data or []

	results: list[dict[str, Any]] = []
	for trend in trend_rows:
		trend_id = trend.get("id")
		example_posts = _fetch_example_posts(client, trend_id, config)
		results.append(
			{
				"trend_id": trend_id,
				"cluster_key": trend.get("cluster_key"),
				"representative_count": trend.get("representative_count"),
				"status": trend.get("status"),
				"created_at": trend.get("created_at"),
				"explainer": trend.get("explainer"),
				"example_posts": example_posts,
			}
		)

	return results


def generate_explainer(
	trend_id: str,
	config: HumanInTheLoopConfig | None = None,
) -> dict[str, Any]:
	"""Generate a short AI explainer for a single trend.

	Steps:
	1. Fetch the trend row and its example posts from Supabase.
	2. Build a concise prompt from example post text.
	3. Call Gemini 2.5 Flash with a tight output-token limit.
	4. Write the explainer back to the ``trends`` table.
	5. Update the trend status to ``explainer_ready``.

	Returns a dict matching the ``ExplainerResponse`` schema shape.

	Raises ``ValueError`` if the trend is not found.
	"""
	config = config or HumanInTheLoopConfig()
	client = _create_supabase_client(config)

	# 1. Fetch trend row.
	trend_row = _fetch_trend_by_id(client, trend_id, config)
	if trend_row is None:
		raise ValueError(f"Trend not found: {trend_id}")

	# 2. Fetch example posts.
	example_posts = _fetch_example_posts(client, trend_id, config)

	# 3. Build prompt and call Cerebras.
	prompt = _build_explainer_prompt(example_posts)
	cerebras_result = _call_cerebras(prompt, config)

	explainer_text = cerebras_result["text"]
	model_used = cerebras_result["model"]
	prompt_tokens = cerebras_result.get("prompt_tokens")
	completion_tokens = cerebras_result.get("completion_tokens")

	# 4. Write explainer back to Supabase and update status.
	_update_trend_explainer(client, trend_id, explainer_text, config)

	return {
		"trend_id": trend_id,
		"explainer": explainer_text,
		"model_used": model_used,
		"prompt_tokens": prompt_tokens,
		"completion_tokens": completion_tokens,
	}


def build_trend_payload(
	trend_id: str,
	config: HumanInTheLoopConfig | None = None,
	*,
	ensure_explainer: bool = True,
) -> dict[str, Any]:
	"""Return a Phase 6 payload for downstream phases.

	Payload keys: ``trend_id``, ``explainer``, ``example_posts``.
	"""
	config = config or HumanInTheLoopConfig()
	client = _create_supabase_client(config)

	trend_row = _fetch_trend_by_id(client, trend_id, config)
	if trend_row is None:
		raise ValueError(f"Trend not found: {trend_id}")

	explainer = trend_row.get("explainer")
	if ensure_explainer and not explainer:
		result = generate_explainer(trend_id=trend_id, config=config)
		explainer = result.get("explainer")

	example_posts = _fetch_example_posts(client, trend_id, config)
	return {
		"trend_id": trend_id,
		"explainer": explainer or "",
		"example_posts": example_posts,
	}


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------


def _create_supabase_client(config: HumanInTheLoopConfig) -> Client:
	url = config.supabase_url or os.getenv("SUPABASE_URL")
	key = config.supabase_service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
	if not url or not key:
		raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
	return create_client(url, key)


def _fetch_trend_by_id(
	client: Client, trend_id: str, config: HumanInTheLoopConfig
) -> dict[str, Any] | None:
	response = (
		client.table(config.trends_table)
		.select("*")
		.eq("id", trend_id)
		.limit(1)
		.execute()
	)
	rows = response.data or []
	return rows[0] if rows else None


def _fetch_example_posts(
	client: Client, trend_id: str, config: HumanInTheLoopConfig
) -> list[dict[str, Any]]:
	"""Fetch example posts for a trend via the trend_examples join table."""
	# Get the linked post IDs ordered by rank.
	examples_response = (
		client.table(config.trend_examples_table)
		.select("post_id")
		.eq("trend_id", trend_id)
		.order("rank")
		.limit(config.max_prompt_posts)
		.execute()
	)
	example_rows = examples_response.data or []
	post_ids = [row["post_id"] for row in example_rows if row.get("post_id")]

	if not post_ids:
		return []

	# Fetch actual post data.
	posts_response = (
		client.table(config.posts_table)
		.select(config.posts_select_fields)
		.in_("id", post_ids)
		.execute()
	)
	posts = posts_response.data or []

	# Preserve rank ordering.
	posts_by_id = {post["id"]: post for post in posts}
	return [posts_by_id[pid] for pid in post_ids if pid in posts_by_id]


def _update_trend_explainer(
	client: Client, trend_id: str, explainer_text: str, config: HumanInTheLoopConfig
) -> None:
	client.table(config.trends_table).update(
		{"explainer": explainer_text, "status": "explainer_ready"}
	).eq("id", trend_id).execute()


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------


_EXPLAINER_SYSTEM_PROMPT = (
	"You are an animal rights advocacy analyst working for a nonprofit. "
	"Your job is to evaluate social media trend clusters and explain their "
	"relevance to animal welfare advocacy in concise, actionable language. "
	"Your output MUST be strictly 2 sentences long. No lists, no bullet points, no line breaks."
)

_EXPLAINER_USER_TEMPLATE = (
	"Given the following cluster of social media posts that form a trend, "
	"write exactly a 2-sentence summary explaining what this trend is about, "
	"why it is relevant to animal rights advocacy, and whether it represents "
	"an opportunity or a risk for advocacy content.\n\n"
	"Trend posts:\n{post_text}"
)


def _build_explainer_prompt(example_posts: list[dict[str, Any]]) -> str:
	"""Concatenate example post snippets into a single prompt string."""
	parts: list[str] = []
	char_budget = 1500

	for i, post in enumerate(example_posts, start=1):
		title = post.get("title") or ""
		text = post.get("text") or post.get("body") or ""
		community = post.get("community") or ""
		score = post.get("score")
		snippet = f"[Post {i}] Community: {community} (score: {score})\n{title}"
		if text and text != title:
			snippet += f"\n{text[:300]}"
		parts.append(snippet)

	combined = "\n\n".join(parts)
	if len(combined) > char_budget:
		combined = combined[:char_budget] + "..."

	return _EXPLAINER_USER_TEMPLATE.format(post_text=combined)


@retry(
	stop=stop_after_attempt(5),
	wait=wait_exponential(multiplier=1, min=2, max=10),
	retry=retry_if_exception_type(openai.RateLimitError)
)
def _call_cerebras(prompt: str, config: HumanInTheLoopConfig) -> dict[str, Any]:
	"""Call Cerebras Inference API and return the text response with token usage."""
	api_key = config.cerebras_api_key or os.getenv("CEREBRAS_API_KEY")
	if not api_key:
		raise RuntimeError("Missing CEREBRAS_API_KEY")

	client = openai.OpenAI(
		base_url="https://api.cerebras.ai/v1",
		api_key=api_key
	)

	response = client.chat.completions.create(
		model=config.text_model,
		messages=[
			{"role": "system", "content": _EXPLAINER_SYSTEM_PROMPT},
			{"role": "user", "content": prompt}
		],
		max_tokens=config.max_explainer_tokens,
		temperature=0.3,
	)

	text = response.choices[0].message.content or ""
	prompt_tokens = response.usage.prompt_tokens if response.usage else None
	completion_tokens = response.usage.completion_tokens if response.usage else None

	return {
		"text": text,
		"model": config.text_model,
		"prompt_tokens": prompt_tokens,
		"completion_tokens": completion_tokens,
	}
