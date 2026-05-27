# Phase 8: Gemini Generation

## Scope
Phase 8 generates tailored advocacy content from a sanitized social media trend payload. It sits between the Cybersecurity Check (Phase 7) and Revalidation (Phase 9). Operating exclusively on the XML-isolated, prompt-injection-scrubbed payload from Phase 7, it performs lightweight AI calls to produce a strategic content brief and multiple ready-to-publish Bluesky post drafts.

## Implemented Module

### Generation
- Entry point: `generate_content(sanitized_payload, config)`
- Source: `app/pipeline/generation.py`
- Configuration: `GenerationConfig` dataclass (configurable via env vars or code)

#### What it does
It executes four distinct, low-cost calls to the `gemini-2.0-flash` model:

**Call 1: Content Brief & Angle (JSON)**
- **Input**: The AI explainer and up to 5 sanitized example posts (complete with Phase 7 XML `<untrusted_social_media_data>` tags).
- **Task**: Produce a 2-4 sentence advocacy brief, a single strategic positioning angle, and 3 suggested hashtags.
- **Settings**: Temperature `0.3` (for factual consistency), forced JSON structure.

**Calls 2-4: Draft Bluesky Posts (Text)**
- **Input**: The generated advocacy brief, positioning angle, and hashtags from Call 1.
- **Task**: Draft three distinct Bluesky posts with different tones:
  - **Factual**: Evidence-led, clear issue statement.
  - **Emotional**: Empathy-driven, vivid human language.
  - **Call to Action**: Action-oriented, ending with a specific directive (share/sign/donate).
- **Settings**: Temperature `0.7` (for creative variety), hard character limit enforcement.

#### Security & Validation Features
- **Prompt Injection Defense**: The system prompt explicitly instructs the LLM that any content within the Phase 7 XML tags is raw, untrusted data to be analyzed, not instructions to be executed.
- **Hard Character Limits**: Every generated post is programmatically truncated to Bluesky's `300` character limit, breaking cleanly on the last word boundary to ensure no malformed URLs or cut-off words.
- **JSON Recovery**: Automatically strips accidental markdown fences (`` ` ` `json ``) from the LLM's structured output before parsing.

#### Input
The `payload` dictionary from Phase 7's `SanitizeResult`.
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
        advocacy_brief="Summary of the issue...",
        positioning_angle="Focus on the environmental impact.",
        suggested_hashtags=["FactoryFarming", "AnimalRights"],
        prompt_tokens=450,
        completion_tokens=85
    ),
    draft_posts=[
        DraftPost(text="Factual post...", hashtags=["..."], char_count=280, tone="factual", ...),
        DraftPost(text="Emotional post...", hashtags=["..."], char_count=295, tone="emotional", ...),
        DraftPost(text="CTA post...", hashtags=["..."], char_count=250, tone="call_to_action", ...)
    ],
    total_prompt_tokens=1050,
    total_completion_tokens=220
)
```

## Contract with Phase 9 (Revalidation)
Phase 9 expects the `GenerationResult` object. It will take the generated `DraftPost.text` fields and perform revalidation (checking for text boundaries, profanity, or brand-safety issues) before moving the final approved text variations to Phase 10 (Closed-Loop Storage).

## Known Constraints
- Requires a valid `GEMINI_API_KEY` environment variable.
- Relies on the `gemini-2.0-flash` model's ability to consistently output JSON for the brief. If the model severely hallucinates the JSON structure beyond simple markdown fences, the pipeline will raise a `ValueError`.
- The draft calls run sequentially. While `gemini-2.0-flash` is extremely fast, future optimizations could use `asyncio.gather` to execute the three draft calls concurrently to reduce overall latency.
