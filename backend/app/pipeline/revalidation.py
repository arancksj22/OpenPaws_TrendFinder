"""Phase 9: Revalidation and Scoring.

Receives the GenerationResult from Phase 8 and scores every draft post
against five hosted OpenPaws prediction models:

    open-paws/animal_advocate_preference_prediction_shortform
    open-paws/text_performance_prediction_shortform
    open-paws/potential_influence_prediction_shortform
    open-paws/emotional_impact_prediction_shortform
    open-paws/animal_alignment_prediction_shortform

Two backends are supported, selected automatically:

  1. HuggingFace Inference API  — used when OPENPAWS_HUGGINGFACE_API_URL is set.
     Sends HTTP POST requests; no GPU/local model weights required.

  2. Local transformers          — fallback when the env var is not set.
     Uses AutoModel + AutoTokenizer; models are cached process-wide so they
     are only downloaded and loaded once per server process.

A programmatic text boundary pass is also applied to each draft before
scoring: empty texts, char-limit violations, and bare [REDACTED]-only posts
are flagged and excluded from the recommended selection.

Public API
----------
    result: RevalidationResult = revalidate_and_score(generation_result, config)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.pipeline.generation import DraftPost, GenerationResult

logger = logging.getLogger(__name__)

# Bluesky hard char limit — mirrors the constant in generation.py.
BLUESKY_MAX_CHARS = 300

# ---------------------------------------------------------------------------
# The five OpenPaws scoring models
# Each key becomes a field name on PostScores.
# ---------------------------------------------------------------------------

SCORING_MODELS: dict[str, str] = {
	"advocacy_preference":   "open-paws/animal_advocate_preference_prediction_shortform",
	"potential_influence":   "open-paws/potential_influence_prediction_shortform",
	"emotional_impact":      "open-paws/emotional_impact_prediction_shortform",
	"animal_alignment":      "open-paws/animal_alignment_prediction_shortform",
}

# Weights used to compute the composite score (must sum to 1.0).
_WEIGHTS: dict[str, float] = {
	"advocacy_preference":  0.30,
	"potential_influence":  0.25,
	"emotional_impact":     0.25,
	"animal_alignment":     0.20,
}

# Process-level cache: model_name → (model, tokenizer)
_MODEL_CACHE: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevalidationConfig:
	"""Configuration for Phase 9.

	Attributes
	----------
	hf_api_url:
	    Base URL of the hosted OpenPaws HuggingFace Inference endpoint.
	    If ``None`` the module falls back to loading models locally via
	    the ``transformers`` library.
	    Reads ``OPENPAWS_HUGGINGFACE_API_URL`` from the environment by default.
	hf_api_token:
	    Optional bearer token for the HuggingFace Inference API.
	    Reads ``HF_API_TOKEN`` from the environment if not provided.
	device:
	    PyTorch device for local model inference (``"cpu"`` or ``"cuda"``).
	    Ignored when using the HTTP backend.
	cache_dir:
	    Optional directory for HuggingFace model weight cache.
	    Ignored when using the HTTP backend.
	"""

	hf_api_url: str | None = None
	hf_api_token: str | None = None
	device: str = "cpu"
	cache_dir: str | None = None

	def resolved_api_url(self) -> str | None:
		return self.hf_api_url or os.getenv("OPENPAWS_HUGGINGFACE_API_URL") or "https://router.huggingface.co/hf-inference/models"

	def resolved_api_token(self) -> str | None:
		return self.hf_api_token or os.getenv("HF_API_TOKEN") or None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PostScores:
	"""Four individual model scores plus a weighted composite for one draft post."""

	advocacy_preference: float   # open-paws/animal_advocate_preference_prediction_shortform
	potential_influence: float   # open-paws/potential_influence_prediction_shortform
	emotional_impact: float      # open-paws/emotional_impact_prediction_shortform
	animal_alignment: float      # open-paws/animal_alignment_prediction_shortform
	composite: float             # weighted average of the above four


@dataclass
class ScoredDraft:
	"""A draft post from Phase 8 with its Phase 9 scores attached."""

	draft: DraftPost
	scores: PostScores
	passed_boundary_check: bool  # False → post fails structural validation
	boundary_issues: list[str]   # Human-readable list of issues found


@dataclass
class RevalidationResult:
	"""Full output of Phase 9."""

	trend_id: str
	scored_drafts: list[ScoredDraft]   # Always length 3, ordered factual/emotional/cta
	recommended_index: int             # Index into scored_drafts with highest composite
	                                   # among drafts that passed boundary checks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def revalidate_and_score(
	generation_result: GenerationResult,
	config: RevalidationConfig | None = None,
) -> RevalidationResult:
	"""Score all draft posts from Phase 8 against the OpenPaws model suite.

	Parameters
	----------
	generation_result:
	    The ``GenerationResult`` from Phase 8.
	config:
	    Optional ``RevalidationConfig``; falls back to env-var defaults.

	Returns
	-------
	``RevalidationResult`` containing scored drafts and a recommended index.
	"""
	config = config or RevalidationConfig()

	scored_drafts: list[ScoredDraft] = []
	for draft in generation_result.draft_posts:
		# Step 1: structural boundary check.
		passed, issues = _boundary_check(draft)

		if not passed:
			# Assign zero scores for drafts that fail boundary checks.
			scores = _zero_scores()
			logger.warning(
				"Boundary check FAILED for tone=%s issues=%s",
				draft.tone, issues,
			)
		else:
			# Step 2: score against all five OpenPaws models.
			scores = _score_text(draft.text, config)

		scored_drafts.append(
			ScoredDraft(
				draft=draft,
				scores=scores,
				passed_boundary_check=passed,
				boundary_issues=issues,
			)
		)

	# Pick the recommended draft: highest composite among passing ones.
	recommended_index = _pick_recommended(scored_drafts)

	return RevalidationResult(
		trend_id=generation_result.trend_id,
		scored_drafts=scored_drafts,
		recommended_index=recommended_index,
	)


# ---------------------------------------------------------------------------
# Boundary (structural) check
# ---------------------------------------------------------------------------


_REDACTED_ONLY_RE = re.compile(r"^(\s*\[REDACTED\]\s*)+$")


def _boundary_check(draft: DraftPost) -> tuple[bool, list[str]]:
	"""Run structural validation on a draft post before scoring.

	Checks:
	- Text is non-empty.
	- Text does not exceed Bluesky's 300-char limit.
	- Text is not purely composed of [REDACTED] markers (i.e. nothing survived
	  Phase 7 scrubbing and the draft is therefore meaningless).

	Returns (passed: bool, issues: list[str]).
	"""
	issues: list[str] = []
	text = draft.text or ""

	if not text.strip():
		issues.append("empty text")

	if len(text) > BLUESKY_MAX_CHARS:
		issues.append(
			f"exceeds {BLUESKY_MAX_CHARS} char limit ({len(text)} chars)"
		)

	if text.strip() and _REDACTED_ONLY_RE.match(text):
		issues.append("text consists entirely of [REDACTED] markers")

	return len(issues) == 0, issues


# ---------------------------------------------------------------------------
# Scoring — dispatches to HTTP or local backend
# ---------------------------------------------------------------------------


def _score_text(text: str, config: RevalidationConfig) -> PostScores:
	"""Score ``text`` against all five OpenPaws models."""
	api_url = config.resolved_api_url()

	if api_url:
		raw = _score_via_api(text, api_url, config.resolved_api_token())
	else:
		raw = _score_via_local(text, config)

	return _build_post_scores(raw)


def _build_post_scores(raw: dict[str, float]) -> PostScores:
	"""Assemble a PostScores object from a raw {metric: score} dict."""
	composite = sum(
		_WEIGHTS[metric] * raw.get(metric, 0.0)
		for metric in _WEIGHTS
	)
	return PostScores(
		advocacy_preference=raw.get("advocacy_preference", 0.0),
		potential_influence=raw.get("potential_influence", 0.0),
		emotional_impact=raw.get("emotional_impact", 0.0),
		animal_alignment=raw.get("animal_alignment", 0.0),
		composite=round(float(np.clip(composite, 0.0, 1.0)), 4),
	)


def _zero_scores() -> PostScores:
	return PostScores(
		advocacy_preference=0.0,
		potential_influence=0.0,
		emotional_impact=0.0,
		animal_alignment=0.0,
		composite=0.0,
	)


# ---------------------------------------------------------------------------
# Backend A: HuggingFace Inference API (HTTP)
# ---------------------------------------------------------------------------


def _score_via_api(
	text: str,
	base_url: str,
	token: str | None,
) -> dict[str, float]:
	"""Call the hosted OpenPaws endpoint for each model via HTTP POST."""
	try:
		import httpx
	except ImportError as exc:
		raise RuntimeError(
			"httpx is required for the HuggingFace API backend. "
			"Install it with: pip install httpx"
		) from exc

	headers: dict[str, str] = {"Content-Type": "application/json"}
	if token:
		headers["Authorization"] = f"Bearer {token.strip()}"

	raw: dict[str, float] = {}
	base_url = base_url.strip().rstrip("/")

	with httpx.Client(timeout=30) as client:
		for metric, model_name in SCORING_MODELS.items():
			url = f"{base_url}/{model_name}"
			try:
				response = client.post(url, json={"inputs": text}, headers=headers)
				response.raise_for_status()
				data = response.json()
				# HuggingFace text-classification pipeline returns:
				# [[{"label": "LABEL_0", "score": 0.856}]]
				score = _extract_api_score(data)
				raw[metric] = float(np.clip(score, 0.0, 1.0))
				logger.debug("API score %s=%s for model %s", metric, raw[metric], model_name)
			except Exception:
				logger.exception("Failed to score metric=%s via API; defaulting to 0.0", metric)
				raw[metric] = 0.0

	return raw


def _extract_api_score(data: Any) -> float:
	"""Extract the numeric score from a HuggingFace Inference API response.

	Handles both pipeline-style ([[{label, score}]]) and plain float responses.
	"""
	if isinstance(data, (int, float)):
		return float(data)
	if isinstance(data, list) and data:
		inner = data[0]
		if isinstance(inner, list) and inner:
			return float(inner[0].get("score", 0.0))
		if isinstance(inner, dict):
			return float(inner.get("score", 0.0))
	return 0.0


# ---------------------------------------------------------------------------
# Backend B: Local transformers (no API required)
# ---------------------------------------------------------------------------


def _score_via_local(
	text: str,
	config: RevalidationConfig,
) -> dict[str, float]:
	"""Score text using locally loaded AutoModel + AutoTokenizer.

	Models are cached in ``_MODEL_CACHE`` so they are only downloaded
	and loaded once per process lifetime.
	"""
	try:
		import torch
		from transformers import AutoModelForSequenceClassification, AutoTokenizer
	except ImportError as exc:
		raise RuntimeError(
			"torch and transformers are required for local scoring. "
			"Install them with: pip install torch transformers"
		) from exc

	raw: dict[str, float] = {}

	for metric, model_name in SCORING_MODELS.items():
		try:
			model, tokenizer = _load_model(model_name, config, AutoModelForSequenceClassification, AutoTokenizer)
			inputs = tokenizer(
				text,
				return_tensors="pt",
				truncation=True,
				max_length=512,
			)
			# Move inputs to the configured device.
			inputs = {k: v.to(config.device) for k, v in inputs.items()}
			with torch.no_grad():
				logits = model(**inputs).logits
			score = float(logits.squeeze().item())
			raw[metric] = float(np.clip(score, 0.0, 1.0))
			logger.debug(
				"Local score %s=%.4f for model %s", metric, raw[metric], model_name
			)
		except Exception:
			logger.exception(
				"Failed to score metric=%s locally; defaulting to 0.0", metric
			)
			raw[metric] = 0.0

	return raw


def _load_model(
	model_name: str,
	config: RevalidationConfig,
	AutoModelClass: Any,
	AutoTokenizer: Any,
) -> tuple[Any, Any]:
	"""Return (model, tokenizer) from cache, downloading on first access."""
	if model_name in _MODEL_CACHE:
		return _MODEL_CACHE[model_name]

	logger.info("Loading OpenPaws model: %s (first use — downloading weights)", model_name)
	kwargs: dict[str, Any] = {}
	if config.cache_dir:
		kwargs["cache_dir"] = config.cache_dir

	tokenizer = AutoTokenizer.from_pretrained(model_name, **kwargs)
	model = AutoModelClass.from_pretrained(model_name, **kwargs)
	model.to(config.device)
	model.eval()

	_MODEL_CACHE[model_name] = (model, tokenizer)
	logger.info("Model cached: %s", model_name)
	return model, tokenizer


# ---------------------------------------------------------------------------
# Recommendation helper
# ---------------------------------------------------------------------------


def _pick_recommended(scored_drafts: list[ScoredDraft]) -> int:
	"""Return the index of the draft with the highest composite score
	among those that passed the boundary check.

	Falls back to index 0 if no drafts passed.
	"""
	passing = [
		(i, sd.scores.composite)
		for i, sd in enumerate(scored_drafts)
		if sd.passed_boundary_check
	]
	if not passing:
		logger.warning("No draft posts passed boundary checks; defaulting to index 0")
		return 0
	return max(passing, key=lambda item: item[1])[0]


# ---------------------------------------------------------------------------
# Serialization — frontend-ready JSON dict
# ---------------------------------------------------------------------------


# Human-readable labels for each scoring metric.
_SCORE_LABELS: dict[str, str] = {
	"advocacy_preference": "Advocacy Preference",
	"potential_influence": "Potential Influence",
	"emotional_impact":    "Emotional Impact",
	"animal_alignment":    "Animal Alignment",
}

# Weights re-exposed for the frontend tooltip / legend.
SCORE_WEIGHTS: dict[str, float] = dict(_WEIGHTS)


def serialise_result(result: RevalidationResult) -> dict[str, Any]:
	"""Convert a ``RevalidationResult`` into a JSON-serialisable dict.

	Produces a structure that exposes every individual model score, the
	composite, and the recommended index so the frontend can render:
	  - Per-draft score breakdowns (bar charts / radar)
	  - Composite score prominently
	  - Boundary check status and issues
	  - Which draft is recommended

	Structure
	---------
	::

	    {
	      "trend_id": "...",
	      "recommended_index": 1,
	      "score_meta": {
	        "metrics": [
	          {"key": "advocacy_preference", "label": "Advocacy Preference", "weight": 0.25},
	          ...
	        ]
	      },
	      "scored_drafts": [
	        {
	          "index": 0,
	          "tone": "factual",
	          "text": "...",
	          "char_count": 280,
	          "hashtags": ["AnimalRights"],
	          "passed_boundary_check": true,
	          "boundary_issues": [],
	          "is_recommended": false,
	          "scores": {
	            "advocacy_preference": 0.82,
	            "potential_influence": 0.68,
	            "emotional_impact":    0.61,
	            "animal_alignment":    0.91,
	            "composite":           0.754
	          }
	        },
	        ...
	      ]
	    }
	"""
	score_meta = {
		"metrics": [
			{
				"key":    key,
				"label":  _SCORE_LABELS[key],
				"weight": _WEIGHTS[key],
			}
			for key in SCORING_MODELS
		]
	}

	scored_drafts_out: list[dict[str, Any]] = []
	for i, sd in enumerate(result.scored_drafts):
		scored_drafts_out.append(
			{
				"index":                 i,
				"tone":                  sd.draft.tone,
				"text":                  sd.draft.text,
				"char_count":            sd.draft.char_count,
				"hashtags":              sd.draft.hashtags,
				"passed_boundary_check": sd.passed_boundary_check,
				"boundary_issues":       sd.boundary_issues,
				"is_recommended":        i == result.recommended_index,
				"scores": {
					"advocacy_preference": sd.scores.advocacy_preference,
					"potential_influence": sd.scores.potential_influence,
					"emotional_impact":    sd.scores.emotional_impact,
					"animal_alignment":    sd.scores.animal_alignment,
					"composite":           sd.scores.composite,
				},
			}
		)

	return {
		"trend_id":          result.trend_id,
		"recommended_index": result.recommended_index,
		"score_meta":        score_meta,
		"scored_drafts":     scored_drafts_out,
	}
