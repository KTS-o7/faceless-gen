# Plan 03 — FastAPI Backend

> **Goal:** Wrap the LangGraph pipeline in a FastAPI server with REST endpoints and SSE (Server-Sent Events) for live progress streaming. Jobs are tracked in a thread-safe in-memory store. All endpoints have tests.

**Assumes:** Plan 01 + 02 complete. `pytest backend/tests/ -v` passes. Pipeline importable without error.

---

## Task 1: Job Model

**Actionables:**
- Create `backend/models/job.py` with:
  - A `JobStatus` string enum with values: `pending`, `running`, `done`, `failed`
  - A `Job` Pydantic model with fields: `job_id` (str), `status` (JobStatus, default pending), `user_prompt` (str), `progress_log` (list[str], default `[]`), `final_output` (Optional[str]), `scene_thumbnails` (list[str], default `[]`), `video_paths` (list[str], default `[]`), `error` (Optional[str]), `created_at` (datetime, default to `datetime.utcnow()`)
  - Use `use_enum_values = True` in model config so serialization produces strings not enum objects

**Acceptance Criteria:**
- `Job(job_id="x", user_prompt="y")` instantiates with `status = "pending"`, all lists empty, optionals `None`
- `job.model_dump_json()` produces valid JSON with `"status": "pending"` (string, not object)
- `created_at` is auto-populated and is a datetime instance

---

## Task 2: Thread-Safe In-Memory Job Store

**Actionables:**
- Create `backend/storage/job_store.py` with a `JobStore` class
- Internal storage: a `dict[str, Job]` protected by `threading.Lock`
- Methods:
  - `create(job: Job) -> Job` — store and return the job
  - `get(job_id: str) -> Optional[Job]` — return job or `None`
  - `update(job: Job) -> None` — overwrite existing entry
  - `append_log(job_id: str, message: str) -> None` — thread-safe append to `job.progress_log` without replacing the whole job object (acquire lock, append, release)
  - `all() -> list[Job]` — return all jobs sorted by `created_at` descending
- Export a module-level singleton `job_store = JobStore()`
- Write unit tests for all 5 methods including concurrent access safety on `append_log`

**Acceptance Criteria:**
- `pytest backend/tests/test_job_store.py -v` → all tests pass
- `get` on a missing job returns `None`
- `all()` returns jobs newest-first
- Two threads calling `append_log` concurrently produce two entries with no data loss (test with `threading.Thread`)

---

## Task 3: Real-Time Progress Bridge

**Actionables:**
- Add a `progress_queue: Optional[queue.Queue]` field to `PipelineState` in `backend/pipeline/state.py` (default `None`)
- Update `initial_state()` to accept an optional `progress_queue` argument and include it in the returned state
- Update each pipeline node (`scripting`, `audio`, `video`, `assembly`) to call `state["progress_queue"].put(message)` immediately after each significant step, in addition to appending to `progress_log`
- The queue is optional — nodes must guard with `if state.get("progress_queue"): ...` so existing tests that don't pass a queue still pass
- Update the FastAPI generate route (Task 4) to pass a `queue.Queue` into `initial_state` and use it for the SSE stream

**Why this matters:** Without this, the SSE stream only shows progress when a whole node completes. Video generation takes minutes per clip — users see nothing during that time. The queue allows the video node to push per-clip progress mid-execution.

**Acceptance Criteria:**
- Existing `pytest backend/tests/ -v` still passes after this change (no tests broken)
- When `progress_queue` is provided, each log message is put in the queue at the moment it is generated, not batched at node end
- When `progress_queue` is `None`, nodes behave identically to before

---

## Task 4: Generate Route (POST + SSE)

**Actionables:**
- Create `backend/api/routes/generate.py` with:
  - `POST /generate` endpoint accepting `{"user_prompt": str}` JSON body
    - Creates a `queue.Queue()` for live progress
    - Creates a `Job` in `job_store` with status `pending`
    - Starts the pipeline in a `threading.Thread` (daemon=True), passing the job_id, prompt, and queue
    - Returns immediately with `{"job_id": ..., "status": "pending"}`
  - A background function `_run_pipeline(job_id, user_prompt, queue)` that:
    - Sets job status to `running`
    - Calls `compiled_graph.invoke(initial_state(job_id, user_prompt, progress_queue=queue))`
    - On completion: updates job with final state fields (progress_log, final_output, scene_thumbnails, video_paths, error, status)
    - Puts a sentinel value (e.g., `None`) on the queue to signal completion
    - On unhandled exception: sets job status to `failed`, sets error, puts sentinel on queue
  - `GET /generate/{job_id}/stream` SSE endpoint using `sse-starlette` `EventSourceResponse`
    - Async generator that drains the queue using `asyncio` (use `loop.run_in_executor` to call `queue.get(timeout=0.5)` without blocking the event loop)
    - Emits `event: progress` with `data: <log line>` for each message
    - When sentinel is received: fetch final job from store, emit `event: done` with `data: <job JSON>`, return
    - If job not found: emit `event: error` and return
  - `GET /generate/{job_id}` endpoint — returns current job state as JSON, 404 if not found

**Acceptance Criteria:**
- `POST /api/generate` with a valid prompt returns 200 with `job_id` and `status: "pending"` within < 100ms (no blocking)
- `GET /api/generate/{job_id}/stream` returns `text/event-stream` content-type
- SSE events arrive progressively as the pipeline runs — not all at once at the end
- `GET /api/generate/{unknown_id}` returns 404
- SSE stream for an unknown job emits `event: error` and closes

---

## Task 5: History Route

**Actionables:**
- Create `backend/api/routes/history.py` with:
  - `GET /history` — returns all jobs from `job_store.all()` as a JSON array, newest-first
  - `GET /history/{job_id}` — returns a single job, 404 if not found

**Acceptance Criteria:**
- `GET /api/history` always returns a list (empty list if no jobs, not 404)
- `GET /api/history/{job_id}` returns full job JSON including `progress_log`, `scene_thumbnails`, and `video_paths`
- `GET /api/history/{unknown_id}` returns 404 with `{"detail": "Job <id> not found"}`

---

## Task 6: Main FastAPI App

**Actionables:**
- Create `backend/main.py` as the FastAPI application entry point
- Load `.env` via `python-dotenv` before any settings imports
- Create the `FastAPI` app with title and version
- Add `CORSMiddleware` allowing origins: `http://localhost:5173` (Vite dev), `http://localhost:4173` (Vite preview), `http://localhost:8000` (same-origin)
- Register both routers under `/api` prefix: `generate.router`, `history.router`
- Mount the `outputs/` directory as static files at `/outputs` (create the dir if it doesn't exist)
- Add a `GET /health` endpoint returning `{"status": "ok", "service": "faceless-gen"}`

**Acceptance Criteria:**
- `uvicorn backend.main:app --reload --port 8000` starts without import errors
- `http://localhost:8000/docs` shows all 6 endpoints
- `http://localhost:8000/health` returns `{"status": "ok", ...}`
- `http://localhost:8000/outputs/<job_id>/final.mp4` serves files from the `outputs/` directory

---

## Task 7: API Tests

**Actionables:**
- Create `backend/tests/test_api.py` using FastAPI's `TestClient`
- Tests to include:
  - `GET /health` returns 200 with `status: ok`
  - `POST /api/generate` with valid body returns 200 with `job_id` and `status: pending`; the background thread must be patched so the test does not actually run the pipeline
  - `GET /api/generate/{job_id}` after a POST returns 200 with the correct `job_id`
  - `GET /api/generate/{unknown_id}` returns 404
  - `GET /api/history` returns 200 with a list
  - `GET /api/history/{unknown_id}` returns 404
  - `GET /api/generate/{job_id}/stream` — assert response content-type is `text/event-stream`

**Acceptance Criteria:**
- `pytest backend/tests/test_api.py -v` → all 7 tests pass
- Background thread is patched in generate tests so test suite does not block or run the real pipeline
- Full test suite `pytest backend/tests/ -v` still passes (no regressions from prior plans)

---

## Task 8: Manual End-to-End Verification

**Actionables:**
- Start the server: `uvicorn backend.main:app --reload --port 8000`
- Post a generate request via curl: `curl -X POST http://localhost:8000/api/generate -H "Content-Type: application/json" -d '{"user_prompt": "a quick test"}'` — capture the `job_id`
- Open an SSE stream: `curl -N http://localhost:8000/api/generate/<job_id>/stream` — observe progress events streaming in
- After completion: `curl http://localhost:8000/api/generate/<job_id>` — verify status is `done` or `failed` with populated fields
- Check `curl http://localhost:8000/api/history` — verify the job appears

**Acceptance Criteria:**
- Server starts without error
- POST returns a job_id immediately (< 200ms)
- SSE stream emits at least one `progress` event before the `done` event
- Completed job is visible in history with non-empty `progress_log`

---

## Task 9: Commit

**Actionables:**
- Run `pytest backend/tests/ -v` — all tests must pass before committing
- Commit all new backend files with message: `feat: FastAPI backend — generate endpoint, SSE streaming, history, job store`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/ -v` → zero failures
- `git push` succeeds with no untracked secrets

---

## Plan 03 Checklist — Before Moving to Plan 04

- [ ] `pytest backend/tests/ -v` → all tests pass (19+ tests)
- [ ] `uvicorn backend.main:app --reload` starts without error
- [ ] `http://localhost:8000/docs` shows all 6 endpoints
- [ ] `curl -X POST /api/generate` returns `job_id` in < 200ms
- [ ] SSE stream emits incremental progress events (not all at end)
- [ ] `GET /api/history` returns a list

**Next:** `docs/plans/04-frontend.md`
