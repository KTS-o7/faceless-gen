# Plan 05 — SQLite Project Persistence

> **Goal:** Introduce a local SQLite database to store video projects with all their stages — source doc, angles, story blocks, scenes, and generation results. Projects survive server restarts and let users continue exactly where they left off.

**Assumes:** Plans 01–04 complete. `pytest backend/tests/ -v` passes.  
**New dependency:** `aiosqlite>=0.20`, `sqlmodel>=0.0.18` (SQLModel wraps SQLAlchemy + Pydantic, gives typed tables without raw SQL)

---

## Task 1: Add Dependencies

**Actionables:**
- Add `sqlmodel>=0.0.18` and `aiosqlite>=0.20` to `pyproject.toml` under core dependencies
- Run `uv pip install -e ".[dev]"` to install
- Verify import: `python -c "import sqlmodel; import aiosqlite; print('ok')"`

**Acceptance Criteria:**
- `python -c "import sqlmodel; import aiosqlite; print('ok')"` prints `ok`
- `uv pip list` shows both packages at correct minimum versions

---

## Task 2: Define Enums

**Actionables:**
- Create `backend/models/project.py`
- Define a `ProjectStage` string enum with values: `angle_selection`, `story_editing`, `scene_editing`, `music_selection`, `generating`, `done`, `failed`
- Define an `AspectRatio` string enum with values: `16:9`, `9:16`, `1:1`

**Acceptance Criteria:**
- Both enums import cleanly from `backend.models.project`
- `ProjectStage("angle_selection")` succeeds; `ProjectStage("unknown")` raises `ValueError`
- Enum values are strings (not enum objects) when serialized to JSON

---

## Task 3: Define SQLModel Tables

**Actionables:**
- In `backend/models/project.py`, define the following SQLModel table classes. All use `table=True`. All have a `project_id` foreign key where appropriate.

**`Project` table** — fields:
  - `id`: str, primary key, default to `uuid4().hex`
  - `name`: str
  - `source_doc`: str (full markdown text)
  - `target_duration_minutes`: int, default 5
  - `stage`: str (ProjectStage value), default `angle_selection`
  - `aspect_ratio`: Optional[str], default `None`
  - `music_track`: Optional[str], default `None`
  - `final_output_path`: Optional[str], default `None`
  - `error`: Optional[str], default `None`
  - `created_at`: datetime, default `datetime.utcnow()`
  - `updated_at`: datetime, default `datetime.utcnow()`

**`Angle` table** — fields:
  - `id`: str, primary key, default `uuid4().hex`
  - `project_id`: str (FK to Project)
  - `order`: int
  - `title`: str
  - `pitch`: str (2-sentence description)
  - `chosen`: bool, default `False`

**`StoryBlock` table** — fields:
  - `id`: str, primary key, default `uuid4().hex`
  - `project_id`: str (FK to Project)
  - `order`: int
  - `content`: str (paragraph text)

**`Scene` table** — fields:
  - `id`: str, primary key, default `uuid4().hex`
  - `project_id`: str (FK to Project)
  - `order`: int
  - `title`: str
  - `dialog`: str
  - `image_prompt`: str
  - `video_prompt`: str
  - `image_path`: Optional[str], default `None` — path to the Flux/ComfyUI-generated scene image (PNG)
  - `audio_path`: Optional[str], default `None`
  - `audio_duration_seconds`: Optional[float], default `None` — duration of TTS audio measured via ffprobe after synthesis
  - `video_clip_path`: Optional[str], default `None`
  - `thumbnail_path`: Optional[str], default `None`

**Acceptance Criteria:**
- All 4 table classes import cleanly
- Each has a string primary key with `uuid4()` default
- `Scene` and `StoryBlock` and `Angle` all have `project_id` field
- `Scene` has `image_path` (Optional[str]) and `audio_duration_seconds` (Optional[float]) fields
- No raw SQL strings in this file

---

## Task 4: Database Initialization

**Actionables:**
- Create `backend/storage/database.py`
- Define `DATABASE_URL` using `settings.outputs_dir.parent / "faceless_gen.db"` (one directory up from outputs so the DB sits at project root level)
- Provide an async `init_db()` function that calls `SQLModel.metadata.create_all(engine)` — creates all tables if they don't exist, is safe to call on every startup
- Provide `get_session()` as an async context manager yielding a SQLModel `AsyncSession`
- Export an `engine` instance built from `DATABASE_URL` using `create_async_engine` from `sqlalchemy.ext.asyncio`
- Call `init_db()` in `backend/main.py` using a FastAPI `lifespan` context handler so it runs on server startup

**Acceptance Criteria:**
- Starting the FastAPI server creates `faceless_gen.db` on disk if it doesn't exist
- Re-starting the server with an existing DB does not raise an error or wipe data
- `ls` confirms the `.db` file exists after first server start
- `.db` file is listed in `.gitignore` (add it if missing)

---

## Task 5: Project Repository

**Actionables:**
- Create `backend/storage/project_repo.py` with a `ProjectRepository` class
- All methods are async and accept a SQLModel `AsyncSession` as first argument
- Methods to implement:

  `create_project(session, name, source_doc, target_duration_minutes) -> Project`
  — Creates and persists a new Project, returns it

  `get_project(session, project_id) -> Optional[Project]`
  — Returns project by id or None

  `list_projects(session) -> list[Project]`
  — Returns all projects ordered by `created_at` descending

  `update_project(session, project_id, **kwargs) -> Project`
  — Updates any subset of fields on a project, sets `updated_at = datetime.utcnow()`, raises `ValueError` if project not found

  `delete_project(session, project_id) -> None`
  — Deletes project and all its child rows (angles, story blocks, scenes)

  `set_angles(session, project_id, angles: list[dict]) -> list[Angle]`
  — Deletes existing angles for project, inserts new ones, returns inserted list

  `choose_angle(session, project_id, angle_id) -> Angle`
  — Sets `chosen=True` for the given angle, `chosen=False` for all others on that project

  `set_story_blocks(session, project_id, blocks: list[dict]) -> list[StoryBlock]`
  — Deletes existing story blocks for project, inserts new ones ordered by `order` field

  `reorder_story_blocks(session, project_id, ordered_ids: list[str]) -> list[StoryBlock]`
  — Updates `order` field of each StoryBlock to match position in `ordered_ids`

  `update_story_block(session, project_id, block_id, content) -> StoryBlock`
  — Updates content of a single story block

  `delete_story_block(session, project_id, block_id) -> None`
  — Deletes a single story block, re-numbers remaining blocks to fill gap

  `set_scenes(session, project_id, scenes: list[dict]) -> list[Scene]`
  — Deletes existing scenes for project, inserts new ones

  `update_scene(session, project_id, scene_id, **kwargs) -> Scene`
  — Updates any subset of fields on a single scene, including `image_path`, `audio_path`, `audio_duration_seconds`, `video_clip_path`, `thumbnail_path`

  `reorder_scenes(session, project_id, ordered_ids: list[str]) -> list[Scene]`
  — Updates `order` field of each Scene to match position in `ordered_ids`

  `get_scenes(session, project_id) -> list[Scene]`
  — Returns all scenes for project ordered by `order` ascending

**Acceptance Criteria:**
- `pytest backend/tests/test_project_repo.py -v` → all method tests pass
- `delete_project` also removes all child Angle, StoryBlock, and Scene rows (no orphaned rows)
- `reorder_story_blocks` with ids in reverse order correctly flips the order values
- `update_project` with unknown `project_id` raises `ValueError`
- `update_scene` correctly persists `image_path` and `audio_duration_seconds` fields

---

## Task 6: Write Repository Tests

**Actionables:**
- Create `backend/tests/test_project_repo.py`
- Use an in-memory SQLite database for tests: configure a test `AsyncSession` using `sqlite+aiosqlite:///:memory:`
- Create a pytest async fixture `db_session` that creates all tables, yields the session, and drops all tables after the test
- Write tests for every repository method listed in Task 5
- Include tests for:
  - Creating a project and reading it back
  - Listing projects returns newest-first
  - `delete_project` cascades to all child tables
  - `reorder_story_blocks` correctly reorders
  - `choose_angle` unsets previous chosen angle

**Acceptance Criteria:**
- `pytest backend/tests/test_project_repo.py -v` → all tests pass
- Tests use in-memory DB — no `.db` file created during test run
- Full suite `pytest backend/tests/ -v` still passes (no regressions)

---

## Task 7: Migrate In-Memory Job Store to SQLite

**Actionables:**
- The existing `backend/storage/job_store.py` uses an in-memory dict. The generation job lifecycle (pending → running → done/failed) should now also be persisted so jobs survive server restarts.
- Add a `GenerationJob` SQLModel table to `backend/models/job.py` with fields matching the existing `Job` Pydantic model: `id`, `project_id` (FK to Project, nullable — jobs can exist without a project for the old quick-generate flow), `status`, `user_prompt`, `progress_log` (stored as JSON string), `final_output`, `error`, `created_at`
- Update `backend/storage/job_store.py` to use async SQLite via the session instead of the in-memory dict. Keep the same public method signatures so existing code does not break.
- `progress_log` is stored as a JSON-encoded string in SQLite. Serialize on write, deserialize on read.

**Acceptance Criteria:**
- Existing `pytest backend/tests/test_job_store.py -v` passes after this change (adapt mocks if needed)
- Restarting the server preserves jobs from the previous session (`GET /api/history` still returns them)
- `append_log` still works without race conditions (use a database transaction per append)

---

## Task 8: Commit

**Actionables:**
- Run `pytest backend/tests/ -v` — all tests must pass
- Commit all new files (`backend/models/project.py` updates, `backend/storage/database.py`, `backend/storage/project_repo.py`, test file, updated `pyproject.toml`)
- Confirm `faceless_gen.db` and `*.db` are in `.gitignore`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/ -v` → zero failures
- No `.db` file committed
- `git push` succeeds

---

## Plan 05 Checklist — Before Moving to Plan 06

- [ ] `python -c "import sqlmodel; import aiosqlite"` → no error
- [ ] Starting server creates `faceless_gen.db` on disk
- [ ] Re-starting server does not wipe existing data
- [ ] `pytest backend/tests/ -v` → all tests pass including `test_project_repo.py`
- [ ] `faceless_gen.db` is gitignored
- [ ] `Scene` table has `image_path` (Optional[str]) and `audio_duration_seconds` (Optional[float]) columns
- [ ] `update_scene` persists both new fields correctly

**Next:** `docs/plans/06-editorial-llm-nodes.md`
