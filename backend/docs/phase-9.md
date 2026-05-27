# Phase 9: Revalidation and Scoring

## Scope
Phase 9 receives the `GenerationResult` from Phase 8 and performs two tasks in sequence for every draft post:

1. **Structural Boundary Pass** — programmatic validation before scoring (empty text, character limit violation, fully-redacted content).
2. **OpenPaws Model Scoring** — five separate text-regression models score the draft on distinct advocacy dimensions. A weighted composite score is calculated and the best-scoring draft is flagged as recommended.

The full result is serialised via `serialise_result()` into a JSON structure that exposes all individual scores, the composite, and the score metadata (labels + weights), so the frontend can render per-metric breakdowns alongside the composite without any additional backend work.

## Implemented Module

### Revalidation
- Entry point: `revalidate_and_score(generation_result, config)`
- Serializer: `serialise_result(result)`
- Source: `app/pipeline/revalidation.py`
- Config: `RevalidationConfig` dataclass

---

## Step 1: Structural Boundary Check

Applied to every draft before it is sent to any model. A draft **fails** if any of the following are true:

| Check | Condition |
|-------|-----------|
| Empty text | `text.strip()` is falsy |
| Character limit exceeded | `len(text) > 300` |
| Fully redacted | Text consists entirely of `[REDACTED]` markers |

Drafts that fail boundary checks are assigned zero scores across all metrics and are excluded from recommendation consideration. Their `boundary_issues` list is preserved in the output for the frontend to display.

---

## Step 2: OpenPaws Scoring Models

Five text-regression models from HuggingFace are called for each passing draft:

| Key | Model | Weight |
|-----|-------|--------|
| `advocacy_preference` | `open-paws/animal_advocate_preference_prediction_shortform` | 25% |
| `text_performance` | `open-paws/text_performance_prediction_shortform` | 20% |
| `potential_influence` | `open-paws/potential_influence_prediction_shortform` | 20% |
| `emotional_impact` | `open-paws/emotional_impact_prediction_shortform` | 20% |
| `animal_alignment` | `open-paws/animal_alignment_prediction_shortform` | 15% |

All raw logit outputs are clipped to `[0.0, 1.0]` as recommended in the OpenPaws documentation to handle out-of-range regression predictions.

The **composite score** is the weighted average of the five individual scores, also clipped to `[0.0, 1.0]` and rounded to 4 decimal places.

### Scoring Backends

Two backends are supported and selected automatically at runtime:

**Backend A — HuggingFace Inference API** *(preferred)*
- Activated when `OPENPAWS_HUGGINGFACE_API_URL` is set in the environment.
- Sends HTTP `POST` requests via `httpx`. No local GPU or model weights required.
- Requires `pip install httpx`.

**Backend B — Local `transformers`** *(fallback)*
- Used when `OPENPAWS_HUGGINGFACE_API_URL` is not set.
- Uses `AutoModel` + `AutoTokenizer` from HuggingFace `transformers`.
- Models are cached process-wide in `_MODEL_CACHE` — downloaded once on first use and reused for all subsequent requests in the same server process.
- Requires `pip install torch transformers`.

---

## Result Types

### `PostScores`
```python
@dataclass
class PostScores:
    advocacy_preference: float   # 0.0 – 1.0
    text_performance:    float   # 0.0 – 1.0
    potential_influence: float   # 0.0 – 1.0
    emotional_impact:    float   # 0.0 – 1.0
    animal_alignment:    float   # 0.0 – 1.0
    composite:           float   # weighted average, clipped to [0.0, 1.0]
```

### `ScoredDraft`
```python
@dataclass
class ScoredDraft:
    draft:                 DraftPost   # Phase 8 draft post object
    scores:                PostScores
    passed_boundary_check: bool
    boundary_issues:       list[str]  # e.g. ["exceeds 300 char limit (312 chars)"]
```

### `RevalidationResult`
```python
@dataclass
class RevalidationResult:
    trend_id:          str
    scored_drafts:     list[ScoredDraft]  # always length 3
    recommended_index: int                # index of highest-composite passing draft
```

---

## Frontend JSON Shape (`serialise_result`)

Call `serialise_result(result)` before returning from any API endpoint. It produces a flat, fully frontend-ready dict:

```json
{
  "trend_id": "uuid",
  "recommended_index": 1,
  "score_meta": {
    "metrics": [
      { "key": "advocacy_preference", "label": "Advocacy Preference", "weight": 0.25 },
      { "key": "text_performance",    "label": "Text Performance",    "weight": 0.20 },
      { "key": "potential_influence", "label": "Potential Influence", "weight": 0.20 },
      { "key": "emotional_impact",    "label": "Emotional Impact",    "weight": 0.20 },
      { "key": "animal_alignment",    "label": "Animal Alignment",    "weight": 0.15 }
    ]
  },
  "scored_drafts": [
    {
      "index": 0,
      "tone": "factual",
      "text": "Every year, billions of animals...",
      "char_count": 271,
      "hashtags": ["AnimalRights", "FactoryFarming"],
      "passed_boundary_check": true,
      "boundary_issues": [],
      "is_recommended": false,
      "scores": {
        "advocacy_preference": 0.82,
        "text_performance":    0.74,
        "potential_influence": 0.68,
        "emotional_impact":    0.61,
        "animal_alignment":    0.91,
        "composite":           0.7548
      }
    },
    { "index": 1, "tone": "emotional",      "is_recommended": true,  "scores": { ... } },
    { "index": 2, "tone": "call_to_action", "is_recommended": false, "scores": { ... } }
  ]
}
```

### Frontend rendering guide

| Field | Suggested UI element |
|-------|---------------------|
| `composite` | Large circular gauge / ring score per draft card |
| `advocacy_preference` … `animal_alignment` | Horizontal bar per metric (labelled from `score_meta.metrics`) |
| `score_meta.metrics[n].weight` | Tooltip on each bar: *"Weighted at 25% of composite"* |
| `is_recommended` | Highlighted border / star badge on the recommended draft card |
| `passed_boundary_check: false` | Greyed-out card with `boundary_issues` shown as warning |

---

## Contract with Phase 8 and Phase 10

### Input from Phase 8
Receives `GenerationResult` directly — `trend_id`, `brief`, and `draft_posts` (list of 3 `DraftPost` objects).

### Output to Phase 10 (Closed-Loop Storage)
Phase 10 should receive the `serialise_result()` dict. It will write all three scored drafts and their individual scores to the Supabase `generated_content` table, and use `is_recommended` to pre-select the default variant on the dashboard.

---

## Known Constraints
- Local backend downloads ~500MB+ of model weights on first use per model. In production, set `OPENPAWS_HUGGINGFACE_API_URL` to use the hosted endpoint.
- Individual model calls are sequential. With 5 models × 3 drafts = 15 calls total, latency is dominated by network round-trips on the API backend or inference time on the local backend. A future optimization could parallelize per-model calls with `asyncio` or `ThreadPoolExecutor`.
- The composite score weights are hardcoded. They can be tuned in the `_WEIGHTS` dict in `revalidation.py` and are re-exposed via `SCORE_WEIGHTS` for any config/admin tooling that needs to read them at runtime.
