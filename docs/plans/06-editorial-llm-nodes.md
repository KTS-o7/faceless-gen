# Plan 06 — LLM Editorial Nodes

> **Goal:** Build the four on-demand LLM functions that power the editorial pipeline — angle generation, story generation, scene breakdown, and per-field regeneration. These are synchronous LangChain chains called directly from FastAPI route handlers, not LangGraph pipeline nodes. All LLM calls are conditioned on the active persona's personality and character description for voice and visual consistency.

**Assumes:** Plans 01–05 complete. bifrost LLM provider (`backend/providers/llm.py`) working. Persona files exist at `backend/assets/personas/default/personality.md` and `backend/assets/personas/default/character.md`.

---

## Task 1: Shared LLM Chain Utilities

**Actionables:**
- Create `backend/pipeline/editorial.py` as the single file for all editorial LLM functions
- Import `get_llm()` from `backend/providers/llm.py` for all LLM calls
- Create a private helper `_parse_json_response(raw: str) -> dict` that:
  - Strips leading/trailing whitespace
  - Strips markdown code fences (` ```json ... ``` ` and ` ``` ... ``` `) if present
  - Calls `json.loads()` on the cleaned string
  - Raises a descriptive `ValueError` if parsing fails, including the first 300 chars of the raw response in the error message
- Create a private helper `_build_system_prompt(instructions: str) -> str` that wraps instructions in a consistent system prompt preamble emphasizing: output only valid JSON, no prose outside JSON, no markdown fences
- Create a private helper `_load_persona() -> dict` that:
  - Reads `settings.personas_dir / settings.active_persona / "personality.md"` — raises `FileNotFoundError` if missing
  - Reads `settings.personas_dir / settings.active_persona / "character.md"` — raises `FileNotFoundError` if missing
  - Returns `{"personality": <str content of personality.md>, "character": <str content of character.md>}`
  - Results are cached after the first load (use a module-level `_persona_cache` dict) — re-reads on first call only
- Define the style constraints as a module-level constant:
  `STYLE_CONSTRAINTS = "flat 2D vector art, unshaded, solid #FFFFFF white background, black lines, zero shadows, minimal character motion, zero camera movement"`

**Acceptance Criteria:**
- `_parse_json_response('```json\n{"a": 1}\n```')` returns `{"a": 1}`
- `_parse_json_response('{"a": 1}')` returns `{"a": 1}`
- `_parse_json_response('not json')` raises `ValueError` with the bad content included
- `_build_system_prompt("do x")` returns a string containing both the preamble and "do x"
- `_load_persona()` returns a dict with `personality` and `character` string keys
- `_load_persona()` raises `FileNotFoundError` when persona directory is missing
- `STYLE_CONSTRAINTS` constant is importable from `backend.pipeline.editorial`

---

## Task 2: Angle Generation

**Actionables:**
- In `backend/pipeline/editorial.py`, implement `generate_angles(source_doc: str, target_duration_minutes: int) -> list[dict]`
- Call `_load_persona()` at the start — include the `personality` content in the system prompt so the LLM understands the channel's narration style and tone when evaluating angle options
- System prompt instructs the LLM to act as a video scriptwriter for this persona, read the provided document, and return exactly 3 story angle options
- Each angle must have: `title` (3–6 words), `pitch` (exactly 2 sentences: what the angle covers and why it's compelling for this persona's audience)
- Expected JSON shape: `{"angles": [{"title": "...", "pitch": "..."}, ...]}`
- Validate that the response contains exactly 3 angles; raise `ValueError` if not
- User message to the LLM must include: the full `source_doc` text, and the `target_duration_minutes` so the LLM calibrates the scope appropriately
- Write unit tests covering: 3 valid angles parsed correctly, fewer than 3 angles raises ValueError, missing `pitch` field raises ValueError, fenced JSON is handled, persona personality is included in system prompt (verify via mock call args)

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestGenerateAngles -v` → all tests pass
- Returns a list of exactly 3 dicts, each with `title` and `pitch` string keys
- Response with 2 angles raises `ValueError`
- Response with missing `pitch` on any angle raises `ValueError`
- System prompt passed to LLM contains the persona's `personality` content

---

## Task 3: Story Generation

**Actionables:**
- Implement `generate_story(source_doc: str, chosen_angle: dict, target_duration_minutes: int) -> list[dict]`
- Call `_load_persona()` — include the `personality` content in the system prompt so the LLM writes narration in the persona's established voice and tone
- System prompt instructs the LLM to write a video narration story in the persona's voice, based on the chosen angle and the source document
- Target number of story blocks: `target_duration_minutes * 2` (i.e. ~2 blocks per minute, each ~30 seconds of narration)
- Each story block is a self-contained paragraph of narration — 2 to 4 sentences
- Expected JSON shape: `{"story_blocks": [{"order": 0, "content": "..."}, ...]}`
- Validate: at least 2 blocks returned, each has `order` (int) and `content` (non-empty string)
- User message must include: the full `source_doc`, the chosen angle title and pitch, target duration
- Write unit tests covering: valid story parsed, fewer than 2 blocks raises ValueError, missing `content` raises ValueError, persona personality is in system prompt (verify via mock)

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestGenerateStory -v` → all tests pass
- For `target_duration_minutes=5`, returns between 8 and 12 blocks
- Each block has `order` (int) and `content` (non-empty string)
- Single-block response raises `ValueError`
- System prompt contains persona's `personality` content

---

## Task 4: Scene Breakdown

**Actionables:**
- Implement `generate_scenes(story_blocks: list[dict], target_duration_minutes: int) -> list[dict]`
- `story_blocks` is a list of dicts with `order` and `content` — this is the user-approved (possibly reordered/edited) story
- Call `_load_persona()` — include both `personality` and `character` content in the system prompt:
  - `personality` to ensure dialog is written in the correct voice
  - `character` to ensure image and video prompts describe the stickman character consistently with `character.md`
- System prompt instructs the LLM to:
  - Break the story into scenes where each scene corresponds to one video clip
  - Write dialog as **1 to 2 short, punchy sentences only** — never more. Pacing must be fast to accommodate minimal visual changes
  - Write `image_prompt` describing the scene layout with the stickman character performing a specific action — must be compatible with the character described in `character.md`
  - Write `video_prompt` describing subtle motion only — consistent with stickman animation
  - The system prompt must **explicitly forbid** adding shadows, 3D rendering, gradients, or camera movement in any prompt
  - The system prompt must **explicitly require** appending `STYLE_CONSTRAINTS` to both `image_prompt` and `video_prompt`
- Target scene count: `target_duration_minutes * 1.5` rounded to nearest int (e.g. 5 min → 7–8 scenes)
- Each scene must have: `order` (int), `title` (3–5 words), `dialog` (1–2 sentences), `image_prompt` (visual description), `video_prompt` (motion description)
- After receiving the LLM response, **always append `STYLE_CONSTRAINTS`** to the end of every `image_prompt` and every `video_prompt` in Python — regardless of whether the LLM already included it. This is a hard post-processing step.
- Expected JSON shape: `{"scenes": [{"order": 0, "title": "...", "dialog": "...", "image_prompt": "...", "video_prompt": "..."}, ...]}`
- Validate: at least 2 scenes, all 5 fields present on each scene
- Write unit tests covering: valid scenes parsed, `STYLE_CONSTRAINTS` appended to every `image_prompt` and `video_prompt` after LLM call (even if LLM didn't include it), missing `video_prompt` field raises ValueError, fewer than 2 scenes raises ValueError, character content in system prompt (verify via mock), dialog field is non-empty

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestGenerateScenes -v` → all tests pass
- Each scene has all 5 required fields with non-empty string values
- `STYLE_CONSTRAINTS` string is present at the end of every `image_prompt` in the returned list (verify in test without mocking LLM — test the post-processing directly)
- `STYLE_CONSTRAINTS` string is present at the end of every `video_prompt` in the returned list
- Missing any required field on any scene raises `ValueError`
- Scene `dialog` is non-empty (not just whitespace)
- System prompt contains persona's `character` description

---

## Task 5: Per-Field Regeneration

**Actionables:**
- Implement `regenerate_field(scene: dict, field_name: str, story_context: str, source_doc_excerpt: str) -> str`
- `field_name` must be one of: `image_prompt`, `video_prompt` — raise `ValueError` for any other value including `dialog` (dialog is editorial-only, no LLM regeneration)
- `story_context` is a brief summary of the overall story (passed by the caller — first 500 chars of the joined story blocks)
- `source_doc_excerpt` is the first 1000 chars of the source doc (to keep the LLM grounded in the research)
- Call `_load_persona()` — include `personality` and `character` in the system prompt so regenerated prompts remain consistent with the persona
- System prompt must:
  - Instruct the LLM to regenerate only the specified field for the given scene
  - Explicitly require appending `STYLE_CONSTRAINTS` to the regenerated value
  - Explicitly forbid camera movement, shadows, 3D rendering, gradients
  - Reference the persona's `character` description so the regenerated visual prompts are consistent
- Expected JSON shape: `{"<field_name>": "new value"}`
- Validate: returned dict has exactly the requested field key
- After receiving the LLM response, **always append `STYLE_CONSTRAINTS`** to the returned string in Python — regardless of LLM compliance
- Write unit tests covering: `image_prompt` regeneration returns string with `STYLE_CONSTRAINTS` appended, `video_prompt` regeneration returns string with `STYLE_CONSTRAINTS` appended, `dialog` field name raises ValueError immediately (no LLM call), invalid field name raises ValueError, missing key in response raises ValueError, persona character in system prompt (verify via mock)

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestRegenerateField -v` → all tests pass
- `regenerate_field(..., field_name="image_prompt", ...)` returns a single non-empty string ending with `STYLE_CONSTRAINTS`
- `regenerate_field(..., field_name="video_prompt", ...)` returns a single non-empty string ending with `STYLE_CONSTRAINTS`
- `regenerate_field(..., field_name="dialog", ...)` raises `ValueError` immediately (no LLM call made)
- `regenerate_field(..., field_name="aspect_ratio", ...)` raises `ValueError` immediately (no LLM call)
- Returned value is the string content of the field, not a dict

---

## Task 6: Token Budget Guard

**Actionables:**
- Add a private helper `_truncate_doc(doc: str, max_chars: int = 12000) -> str` in `backend/pipeline/editorial.py`
- If `len(doc) > max_chars`, truncate to `max_chars` characters and append `"\n\n[Document truncated for context window]"`
- Apply this helper to `source_doc` before constructing any LLM user message in all 4 functions above
- Add a unit test asserting that a 20,000-char doc is truncated to 12,000 chars with the truncation notice appended

**Why:** Research docs can be very long. Sending 50k-char docs into the context window will hit rate limits on some models and produce inconsistent outputs.

**Acceptance Criteria:**
- `_truncate_doc("x" * 20000)` returns a string of length 12,000 + the truncation notice
- `_truncate_doc("short doc")` returns the original string unchanged
- All 4 LLM functions call `_truncate_doc` on `source_doc` before building the user message

---

## Task 7: Run All Tests + Commit

**Actionables:**
- Run `pytest backend/tests/test_editorial.py -v` — all tests must pass
- Run full suite `pytest backend/tests/ -v` — no regressions
- Commit `backend/pipeline/editorial.py` and `backend/tests/test_editorial.py` with message: `feat: LLM editorial nodes — angles, story, scenes, per-field regen with persona injection and style constraints`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py -v` → minimum 18 tests pass
- `pytest backend/tests/ -v` → zero failures
- `git push` succeeds

---

## Plan 06 Checklist — Before Moving to Plan 07

- [ ] `pytest backend/tests/test_editorial.py -v` → 18+ tests pass
- [ ] `generate_angles()` returns exactly 3 angles; system prompt contains persona personality
- [ ] `generate_scenes()` returns scenes with all 5 required fields
- [ ] `generate_scenes()` always appends `STYLE_CONSTRAINTS` to every `image_prompt` and `video_prompt` in Python post-processing
- [ ] `regenerate_field()` with `dialog` field name raises `ValueError` immediately (no LLM call)
- [ ] `regenerate_field()` always appends `STYLE_CONSTRAINTS` to returned string
- [ ] All functions inject persona `personality` into system prompt; scene/regen functions also inject `character`
- [ ] All functions truncate source_doc to 12k chars before sending to LLM
- [ ] `backend/assets/personas/default/personality.md` and `character.md` exist and are non-empty
- [ ] `pytest backend/tests/ -v` → zero failures

**Next:** `docs/plans/07-project-api-routes.md`
