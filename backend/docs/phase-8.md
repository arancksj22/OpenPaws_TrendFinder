# Phase 8: Gemini Generation

## Scope
Phase 8 generates tailored advocacy content from a sanitized social media trend payload. It sits between the Cybersecurity Check (Phase 7) and Revalidation (Phase 9). Operating exclusively on the XML-isolated, prompt-injection-scrubbed payload from Phase 7, it performs five AI calls to produce a strategic content brief, three Bluesky post drafts, and one trend infographic image.

## Implemented Module

### Generation
- Entry point: `generate_content(sanitized_payload, config)`
- Source: `app/pipeline/generation.py`
- Configuration: `GenerationConfig` dataclass

#### What it does
It executes **five** AI calls in sequence:

| Call | Model | Task |
|------|-------|------|
| 1 | `gemini-2.0-flash` | Content brief + positioning angle (structured JSON) |
| 2 | `gemini-2.0-flash` | Draft Bluesky post — Factual tone |
| 3 | `gemini-2.0-flash` | Draft Bluesky post — Emotional tone |
| 4 | `gemini-2.0-flash` | Draft Bluesky post — Call-to-Action tone |
| 5 | `imagen-3.0-fast-generate-001` | One infographic-style PNG image |

---

**Call 1: Content Brief & Angle (JSON)**
- **Input**: The AI explainer and up to 5 sanitized example posts (with Phase 7 XML `<untrusted_social_media_data>` boundary tags).
- **Task**: Produce a 2-4 sentence advocacy brief, a single strategic positioning angle, and 3 suggested hashtags.
- **Settings**: Temperature `0.3` (factual consistency), forced JSON structure.

**Calls 2–4: Draft Bluesky Posts (Text)**
- **Input**: The brief, positioning angle, and hashtags from Call 1.
- **Task**: Three distinct posts — Factual, Emotional, Call-to-Action.
- **Settings**: Temperature `0.7` (creative variety), hard 300-char limit enforced programmatically.

**Call 5: Trend Infographic Image (Imagen)**
- **Model**: `imagen-3.0-fast-generate-001` — the cheapest Imagen tier.
- **Input**: Advocacy brief + positioning angle + top 3 hashtags.
- **Prompt style**: Flat design, warm earthy tones, no text overlays, Bluesky-suitable 1:1 aspect ratio.
- **Output**: Raw PNG bytes stored in `GenerationResult.image_bytes`.
- **Failure policy**: **Non-fatal.** If Imagen fails for any reason (quota, safety filter, network), `image_bytes` is `None` and the pipeline continues. Phase 10 will simply omit the image upload.

---

#### Security & Validation Features
- **Prompt Injection Defence**: System prompt instructs the LLM to treat all `<untrusted_social_media_data>` content as data to analyze, never as executable instructions.
- **Hard Character Limits**: Every draft post is programmatically truncated to Bluesky's 300-character limit at the last word boundary.
- **JSON Recovery**: Automatically strips accidental markdown fences (` ```json `) from the brief response before parsing.

---

#### Input
The `payload` dict from Phase 7's `SanitizeResult.payload`.
```json
{
  "trend_id": "uuid",
  "explainer": "<untrusted_social_media_data>\nAI Summary...\n</untrusted_social_media_data>",
  "example_posts": [
    {
      "text": "<untrusted_social_media_data>\nRaw post text...\n</untrusted_social_media_data>",
      "community": "animalrights",
      "score": 42
    }
  ]
}
```

#### Output (`GenerationResult`)
```python
GenerationResult(
    trend_id="uuid",
    brief=ContentBrief(
        advocacy_brief="Factory farming causes immense suffering...",
        positioning_angle="Focus on the scale of the problem.",
        suggested_hashtags=["FactoryFarming", "AnimalRights", "vegan"],
        prompt_tokens=450,
        completion_tokens=85
    ),
    draft_posts=[
        DraftPost(text="Factual post...",  hashtags=["..."], char_count=280, tone="factual"),
        DraftPost(text="Emotional post...", hashtags=["..."], char_count=295, tone="emotional"),
        DraftPost(text="CTA post...",      hashtags=["..."], char_count=250, tone="call_to_action"),
    ],
    total_prompt_tokens=1050,
    total_completion_tokens=220,
    image_bytes=b"\x89PNG...",   # Raw PNG from Imagen; None if generation failed
    image_prompt_used="Create a clean, modern infographic..."
)
```

---

## Contract with Phase 9 (Revalidation)
Phase 9 receives the full `GenerationResult` object. It scores `DraftPost.text` fields against the five OpenPaws models, performs boundary checks, and passes the scored payload to Phase 10.

## Contract with Phase 10 (Production Storage)
Phase 10 receives both the `GenerationResult` (for `image_bytes` and `image_prompt_used`) and the Phase 9 `serialise_result()` dict (for scored drafts). It uploads the image and writes all text + score data to Supabase.

## Known Constraints
- Requires a valid `GEMINI_API_KEY` environment variable for both text and image generation.
- The `imagen-3.0-fast-generate-001` model is subject to Gemini API image quota. Non-fatal on failure.
- Relies on `gemini-2.0-flash` outputting valid JSON for the brief. A `ValueError` is raised if the JSON is structurally broken beyond what the markdown-fence stripper can fix.
- All five calls run sequentially. Future optimization can parallelize Calls 2–4 with `asyncio.gather`.
