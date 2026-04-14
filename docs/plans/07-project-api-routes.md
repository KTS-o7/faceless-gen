# Plan 07 — Project API Routes

> **Goal:** Expose all project operations as a clean REST API. These routes power the editorial wizard — creating projects, advancing stages, saving edits, triggering LLM editorial calls, and reading back full project state. All routes have integration tests using FastAPI's TestClient.

**Assumes:** Plans 01–06 complete. `pytest backend/tests/ -v` passes. `ProjectRepository` and all editorial functions available.

---

## Task 1: Pydantic Request/Response Schemas

**Actionables:**
- Create `backend/models/schemas.py` with request and response Pydantic models (separate from SQLModel table classes — do not mix table definitions with API schemas)
- Request schemas to define:
  - `CreateProjectRequest`: `name` (str, min_length=1), `source_doc` (str, min_length=100), `target_duration_minutes` (int, ge=1, le=30, default=5)
  - `UpdateProjectRequest`: all fields Optional — `name`, `stage`, `aspect_ratio`, `music_track`
  - `ReorderRequest`: `ordered_ids` (list[str], min_length=1)
  - `UpdateStoryBlockRequest`: `content` (str, min_length=1)
  - `UpdateSceneRequest`: all Optional — `title`, `dialog`, `image_prompt`, `video_prompt`
  - `ChooseAngleRequest`: `angle_id` (str)
  - `RegenerateFieldRequest`: `field_name` (Literal["image_prompt", "video_prompt"]), `story_context` (str, default ""), `source_doc_excerpt` (str, default "")`
    — Using `Literal` here enforces valid field names at Pydantic schema validation level before any LLM call is made
- Response schemas to define:
  - `ProjectSummary`: `id`, `name`, `stage`, `target_duration_minutes`, `created_at`, `updated_at`
  - `ProjectDetail`: all `ProjectSummary` fields plus `source_doc`, `aspect_ratio`, `music_track`, `final_output_path`, `error`, plus nested lists: `angles`, `story_blocks`, `scenes`
  - `AngleResponse`: `id`, `order`, `title`, `pitch`, `chosen`
  - `StoryBlockResponse`: `id`, `order`, `content`
  - `SceneResponse`: `id`, `order`, `title`, `dialog`, `image_prompt`, `video_prompt`, `audio_path`, `video_clip_path`, `thumbnail_path`

**Acceptance Criteria:**
- All schemas import cleanly from `backend.models.schemas`
- `CreateProjectRequest(name="x", source_doc="y"*100)` validates successfully
- `CreateProjectRequest(name="", source_doc="y"*100)` raises `ValidationError`
- `CreateProjectRequest(target_duration_minutes=31)` raises `ValidationError`
- `ProjectDetail` can be constructed from a `Project` + its child lists without type errors

---

## Task 2: Project CRUD Routes

**Actionables:**
- Create `backend/api/routes/projects.py`
- Register all routes under prefix `/projects` (the FastAPI app will mount this under `/api`)
- Implement the following endpoints:

  `POST /projects`
  — Body: `CreateProjectRequest`
  — Creates project via `ProjectRepository.create_project()`, advances stage to `angle_selection`
  — Returns `ProjectDetail` with empty angles/story_blocks/scenes lists
  — Response status: 201

  `GET /projects`
  — Returns `list[ProjectSummary]` ordered newest-first

  `GET /projects/{project_id}`
  — Returns `ProjectDetail` with all child lists populated
  — 404 if project not found

  `PATCH /projects/{project_id}`
  — Body: `UpdateProjectRequest`
  — Updates only the fields provided (partial update)
  — Returns updated `ProjectDetail`
  — 404 if not found

  `DELETE /projects/{project_id}`
  — Deletes project and all child rows via `ProjectRepository.delete_project()`
  — Also deletes the project's output directory (`outputs/{project_id}/`) if it exists
  — Returns 204 No Content

**Acceptance Criteria:**
- `POST /api/projects` with valid body returns 201 with `id` and `stage: "angle_selection"`
- `GET /api/projects` always returns a list (never 404)
- `GET /api/projects/{unknown_id}` returns 404 with descriptive detail
- `DELETE /api/projects/{id}` followed by `GET /api/projects/{id}` returns 404
- `PATCH /api/projects/{id}` with `{"music_track": "chill.mp3"}` updates only that field

---

## Task 3: Angle Routes

**Actionables:**
- Add the following endpoints to `backend/api/routes/projects.py`:

  `POST /projects/{project_id}/angles/generate`
  — This route calls a **synchronous blocking LLM function** (`generate_angles`). To avoid blocking the FastAPI async event loop, wrap the call:
    `result = await asyncio.get_event_loop().run_in_executor(None, generate_angles, project.source_doc, project.target_duration_minutes)`
  — Apply this `run_in_executor` pattern to **all routes that call LLM functions** (`generate_angles`, `generate_story`, `generate_scenes`, `regenerate_field`) — each can take 5–30 seconds and must not block other requests
  — Saves the 3 returned angles via `ProjectRepository.set_angles()`
  — Updates project stage to `angle_selection`
  — Returns `list[AngleResponse]`
  — 404 if project not found
  — 422 if LLM returns invalid structure (catch `ValueError`, return 422 with detail)

  `POST /projects/{project_id}/angles/{angle_id}/choose`
  — Calls `ProjectRepository.choose_angle()`
  — Updates project stage to `story_editing`
  — Returns the chosen `AngleResponse`

**Acceptance Criteria:**
- `POST /api/projects/{id}/angles/generate` returns a list of exactly 3 angle objects
- Each angle has `title`, `pitch`, `chosen: false`, `id`
- `POST /api/projects/{id}/angles/{angle_id}/choose` sets `chosen: true` only on that angle
- `GET /api/projects/{id}` after choose shows `stage: "story_editing"`
- LLM error (mocked `ValueError`) returns 422 not 500

---

## Task 4: Story Routes

**Actionables:**
- Add the following endpoints:

  `POST /projects/{project_id}/story/generate`
  — Fetches the chosen angle from the DB; returns 409 if no angle is chosen yet
  — Wraps LLM call in `run_in_executor`: `await asyncio.get_event_loop().run_in_executor(None, generate_story, ...)`
  — Saves returned blocks via `ProjectRepository.set_story_blocks()`
  — Updates project stage to `story_editing`
  — Returns `list[StoryBlockResponse]`

  `GET /projects/{project_id}/story`
  — Returns current story blocks ordered by `order` ascending
  — Returns empty list if no story generated yet

  `PATCH /projects/{project_id}/story/reorder`
  — Body: `ReorderRequest`
  — Calls `ProjectRepository.reorder_story_blocks()`
  — Returns updated `list[StoryBlockResponse]`

  `PATCH /projects/{project_id}/story/{block_id}`
  — Body: `UpdateStoryBlockRequest`
  — Updates content of a single story block
  — Returns updated `StoryBlockResponse`

  `DELETE /projects/{project_id}/story/{block_id}`
  — Deletes a single story block, re-numbers remaining
  — Returns 204 No Content

  `POST /projects/{project_id}/story/confirm`
  — Advances project stage to `scene_editing`
  — Returns updated `ProjectSummary`

**Acceptance Criteria:**
- `POST /story/generate` with no chosen angle returns 409 with descriptive message
- `PATCH /story/reorder` with reversed IDs correctly reverses `order` values in DB
- `DELETE /story/{block_id}` removes the block and re-numbers remaining blocks sequentially from 0
- `POST /story/confirm` sets `stage: "scene_editing"` in DB and response

---

## Task 5: Scene Routes

**Actionables:**
- Add the following endpoints:

  `POST /projects/{project_id}/scenes/generate`
  — Fetches current story blocks; returns 409 if story has fewer than 2 blocks
  — Wraps LLM call in `run_in_executor`: `await asyncio.get_event_loop().run_in_executor(None, generate_scenes, ...)`
  — Saves scenes via `ProjectRepository.set_scenes()`
  — Updates project stage to `scene_editing`
  — Returns `list[SceneResponse]`

  `GET /projects/{project_id}/scenes`
  — Returns all scenes ordered by `order` ascending
  — Returns empty list if no scenes generated yet

  `PATCH /projects/{project_id}/scenes/reorder`
  — Body: `ReorderRequest`
  — Calls `ProjectRepository.reorder_scenes()`
  — Returns updated `list[SceneResponse]`

  `PATCH /projects/{project_id}/scenes/{scene_id}`
  — Body: `UpdateSceneRequest` (partial update, only provided fields updated)
  — Returns updated `SceneResponse`

  `POST /projects/{project_id}/scenes/{scene_id}/regenerate`
  — Body: `RegenerateFieldRequest` — `field_name` is `Literal["image_prompt", "video_prompt"]`, validated at schema level
  — Wraps LLM call in `run_in_executor`: `await asyncio.get_event_loop().run_in_executor(None, regenerate_field, ...)`
  — On success: updates the specified field on the scene in the DB
  — Returns updated `SceneResponse`
  — 422 if `field_name` fails Pydantic Literal validation (automatic, no manual check needed)

  `POST /projects/{project_id}/scenes/confirm`
  — Advances project stage to `music_selection`
  — Returns updated `ProjectSummary`

**Acceptance Criteria:**
- `POST /scenes/generate` with fewer than 2 story blocks returns 409
- `PATCH /scenes/{id}` with `{"dialog": "new text"}` updates only the dialog field, leaves others unchanged
- `POST /scenes/{id}/regenerate` with `field_name: "aspect_ratio"` returns 422 not 500
- `GET /projects/{id}` after `/scenes/confirm` shows `stage: "music_selection"`

---

## Task 6: Register Routes + Update CORS

**Actionables:**
- In `backend/main.py`, import and register the projects router: `app.include_router(projects_router, prefix="/api")`
- Add `http://localhost:5173` and `http://localhost:4173` to the CORS allowed origins if not already present
- Verify `GET /api/docs` shows all new project routes

**Acceptance Criteria:**
- `http://localhost:8000/docs` shows all routes: POST/GET/PATCH/DELETE for projects, plus sub-routes for angles, story, scenes
- `OPTIONS /api/projects` returns CORS headers including `Access-Control-Allow-Origin: http://localhost:5173`

---

## Task 7: API Integration Tests

**Actionables:**
- Create `backend/tests/test_projects_api.py` using FastAPI `TestClient`
- Use a test database (in-memory SQLite) via a dependency override on `get_async_session`:
  ```
  app.dependency_overrides[get_async_session] = override_get_async_session
  ```
  Where `override_get_async_session` yields an `AsyncSession` backed by `sqlite+aiosqlite:///:memory:`
- All LLM functions (`generate_angles`, `generate_story`, `generate_scenes`, `regenerate_field`) must be patched with `unittest.mock.patch` in every test that triggers them — no real API calls in tests
- Tests to cover:
  - `POST /api/projects` creates project and returns 201
  - `GET /api/projects` returns list
  - `GET /api/projects/{id}` returns full detail
  - `GET /api/projects/{unknown}` returns 404
  - `DELETE /api/projects/{id}` returns 204, subsequent GET returns 404
  - `POST /api/projects/{id}/angles/generate` with mocked `generate_angles` returns 3 angles
  - `POST /api/projects/{id}/angles/{angle_id}/choose` sets `chosen: true`, advances stage
  - `POST /api/projects/{id}/story/generate` with mocked `generate_story` returns blocks, advances stage
  - `POST /api/projects/{id}/story/generate` with no chosen angle returns 409
  - `PATCH /api/projects/{id}/story/reorder` with reversed IDs reverses order
  - `POST /api/projects/{id}/scenes/generate` with mocked `generate_scenes` returns scenes
  - `POST /api/projects/{id}/scenes/{scene_id}/regenerate` with mocked `regenerate_field` updates field
  - `POST /api/projects/{id}/scenes/{scene_id}/regenerate` with `field_name: "dialog"` returns 422 (Pydantic Literal rejects it)
  - `POST /api/projects/{id}/story/confirm` advances stage to `scene_editing`
  - `POST /api/projects/{id}/scenes/confirm` advances stage to `music_selection`

**Acceptance Criteria:**
- `pytest backend/tests/test_projects_api.py -v` → 15+ tests pass
- All LLM calls are mocked — no real API calls in tests
- Tests use in-memory DB — no `.db` files written during test run
- `pytest backend/tests/ -v` → zero failures

---

## Task 8: Commit

**Actionables:**
- Run `pytest backend/tests/ -v` — all tests pass
- Commit all new files with message: `feat: project API routes — CRUD, angle, story, scene endpoints with full test coverage`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/ -v` → zero failures (25+ tests total)
- `http://localhost:8000/docs` shows all routes
- `git push` succeeds

---

## Plan 07 Checklist — Before Moving to Plan 08

- [ ] `pytest backend/tests/ -v` → 25+ tests, zero failures
- [ ] `POST /api/projects` returns 201 with `stage: "angle_selection"`
- [ ] All stage advancement routes (`/angles/{id}/choose`, `/story/confirm`, `/scenes/confirm`) correctly update `stage` in DB
- [ ] LLM `ValueError` returns 422, not 500
- [ ] `DELETE /api/projects/{id}` removes project and child rows
- [ ] `http://localhost:8000/docs` shows all routes

**Next:** `docs/plans/08-frontend-editorial-wizard.md`
