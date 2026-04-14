# Plan 06 — LLM Editorial Nodes

> **Goal:** Build the four on-demand LLM functions that power the editorial pipeline — angle generation, story generation, scene breakdown, and per-field regeneration. These are synchronous LangChain chains called directly from FastAPI route handlers, not LangGraph pipeline nodes.

**Assumes:** Plans 01–05 complete. bifrost LLM provider (`backend/providers/llm.py`) working.

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

**Acceptance Criteria:**
- `_parse_json_response('```json\n{"a": 1}\n```')` returns `{"a": 1}`
- `_parse_json_response('{"a": 1}')` returns `{"a": 1}`
- `_parse_json_response('not json')` raises `ValueError` with the bad content included
- `_build_system_prompt("do x")` returns a string containing both the preamble and "do x"

---

## Task 2: Angle Generation

**Actionables:**
- In `backend/pipeline/editorial.py`, implement `generate_angles(source_doc: str, target_duration_minutes: int) -> list[dict]`
- System prompt instructs the LLM to act as a video scriptwriter, read the provided document, and return exactly 3 story angle options
- Each angle must have: `title` (3–6 words), `pitch` (exactly 2 sentences: what the angle covers and why it's compelling)
- Expected JSON shape: `{"angles": [{"title": "...", "pitch": "..."}, ...]}`
- Validate that the response contains exactly 3 angles; raise `ValueError` if not
- User message to the LLM must include: the full `source_doc` text, and the `target_duration_minutes` so the LLM calibrates the scope appropriately
- Write unit tests covering: 3 valid angles parsed correctly, fewer than 3 angles raises ValueError, missing `pitch` field raises ValueError, fenced JSON is handled

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestGenerateAngles -v` → all tests pass
- Returns a list of exactly 3 dicts, each with `title` and `pitch` string keys
- Response with 2 angles raises `ValueError`
- Response with missing `pitch` on any angle raises `ValueError`

---

## Task 3: Story Generation

**Actionables:**
- Implement `generate_story(source_doc: str, chosen_angle: dict, target_duration_minutes: int) -> list[dict]`
- System prompt instructs the LLM to write a video narration story based on the chosen angle and the source document
- Target number of story blocks: `target_duration_minutes * 2` (i.e. ~2 blocks per minute, each ~30 seconds of narration)
- Each story block is a self-contained paragraph of narration — 2 to 4 sentences
- Expected JSON shape: `{"story_blocks": [{"order": 0, "content": "..."}, ...]}`
- Validate: at least 2 blocks returned, each has `order` (int) and `content` (non-empty string)
- User message must include: the full `source_doc`, the chosen angle title and pitch, target duration
- Write unit tests covering: valid story parsed, fewer than 2 blocks raises ValueError, missing `content` raises ValueError

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestGenerateStory -v` → all tests pass
- For `target_duration_minutes=5`, returns between 8 and 12 blocks
- Each block has `order` (int) and `content` (non-empty string)
- Single-block response raises `ValueError`

---

## Task 4: Scene Breakdown

**Actionables:**
- Implement `generate_scenes(story_blocks: list[dict], target_duration_minutes: int) -> list[dict]`
- `story_blocks` is a list of dicts with `order` and `content` — this is the user-approved (possibly reordered/edited) story
- System prompt instructs the LLM to break the story into scenes. Each scene corresponds to one video clip with a voiceover, a visual (image), and a motion layer (video).
- Target scene count: `target_duration_minutes * 1.5` rounded to nearest int (e.g. 5 min → 7–8 scenes)
- Each scene must have: `order` (int), `title` (3–5 words), `dialog` (the voiceover narration for this scene, extracted/condensed from story blocks), `image_prompt` (a detailed visual description for image generation — lighting, composition, mood, subject), `video_prompt` (a motion description for video generation — camera movement, action, atmosphere)
- Expected JSON shape: `{"scenes": [{"order": 0, "title": "...", "dialog": "...", "image_prompt": "...", "video_prompt": "..."}, ...]}`
- Validate: at least 2 scenes, all 5 fields present on each scene
- Write unit tests covering: valid scenes parsed, missing `video_prompt` field raises ValueError, fewer than 2 scenes raises ValueError

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestGenerateScenes -v` → all tests pass
- Each scene has all 5 required fields with non-empty string values
- Missing any required field on any scene raises `ValueError`
- Scene `dialog` is non-empty (not just whitespace)

---

## Task 5: Per-Field Regeneration

**Actionables:**
- Implement `regenerate_field(scene: dict, field_name: str, story_context: str, source_doc_excerpt: str) -> str`
- `field_name` must be one of: `dialog`, `image_prompt`, `video_prompt` — raise `ValueError` for any other value
- `story_context` is a brief summary of the overall story (passed by the caller — first 500 chars of the joined story blocks)
- `source_doc_excerpt` is the first 1000 chars of the source doc (to keep the LLM grounded in the research)
- System prompt instructs the LLM to regenerate only the specified field for the given scene, maintaining consistency with the story context and the other fields already set on that scene
- Expected JSON shape: `{"<field_name>": "new value"}`
- Validate: returned dict has exactly the requested field key
- Write unit tests covering: each of the 3 valid field names, invalid field name raises ValueError, missing key in response raises ValueError

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py::TestRegenerateField -v` → all tests pass
- `regenerate_field(..., field_name="image_prompt", ...)` returns a single non-empty string
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
- Commit `backend/pipeline/editorial.py` and `backend/tests/test_editorial.py` with message: `feat: LLM editorial nodes — angles, story, scenes, per-field regen`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/test_editorial.py -v` → minimum 14 tests pass
- `pytest backend/tests/ -v` → zero failures
- `git push` succeeds

---

## Plan 06 Checklist — Before Moving to Plan 07

- [ ] `pytest backend/tests/test_editorial.py -v` → 14+ tests pass
- [ ] `generate_angles()` returns exactly 3 angles
- [ ] `generate_scenes()` returns scenes with all 5 required fields
- [ ] `regenerate_field()` with invalid field name raises `ValueError` immediately
- [ ] All functions truncate source_doc to 12k chars before sending to LLM
- [ ] `pytest backend/tests/ -v` → zero failures

**Next:** `docs/plans/07-project-api-routes.md`
