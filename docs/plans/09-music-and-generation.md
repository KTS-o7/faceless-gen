# Plan 09 — Music Selection + Final Generation

> **Goal:** Add bundled royalty-free music track selection, update the LangGraph generation pipeline to work from an approved project's scenes (not a raw prompt), wire the full per-scene pipeline (audio → image → video → assembly with duration sync and music mixing), and build the generation + result UI as steps 4 and 5 of the wizard.

**Assumes:** Plans 01–08 complete. All backend tests pass. Wizard steps 1–3 working end-to-end. ComfyUI installed locally with Flux checkpoint. Persona files exist at `backend/assets/personas/default/`.

---

## Task 1: Bundle Royalty-Free Music Tracks + Persona Files

**Actionables:**
- Create directory `backend/assets/music/`
- Source 5–8 royalty-free background music tracks in MP3 format, each 2–3 minutes long. Suitable sources: pixabay.com/music, freemusicarchive.org, or similar CC0-licensed libraries. Download manually.
- Name files descriptively: e.g. `calm_acoustic.mp3`, `upbeat_corporate.mp3`, `cinematic_epic.mp3`, `soft_piano.mp3`, `ambient_tech.mp3`
- Create `backend/assets/music/tracks.json` — a list of objects each with: `filename`, `title`, `mood` (one of: calm, upbeat, cinematic, ambient, dramatic), `duration_seconds` (int)
- Mount `backend/assets/music/` as a static file directory in FastAPI at `/assets/music`
- Create the default persona directory: `backend/assets/personas/default/`
- Create `backend/assets/personas/default/personality.md` — must contain at minimum:
  - `Voice-ID: <elevenlabs_voice_id>` on the first line (parseable by `_load_persona()`)
  - A narration tone description (e.g. "dry, deadpan, factual — like a nature documentary about humans")
  - 2–3 example dialog lines showing the style
- Create `backend/assets/personas/default/character.md` — must contain:
  - A visual description of the stickman character (e.g. "a simple black line stickman figure with circular head, no facial features except two dot eyes, drawn in 2px stroke weight, always centered in frame")
  - Typical poses or expressions used
- Create `backend/assets/personas/default/seed.png` — a reference image of the stickman character on a white background. This is the img2img anchor for all image generation. Can be drawn in any tool (Keynote, Figma, MS Paint). Must be 512×512 or 1024×1024 PNG.
- Add `backend/assets/personas/*/seed.png` to `.gitignore` if the file is large — or commit it since it is small and critical
- Mount `backend/assets/personas/` as a static file directory in FastAPI at `/assets/personas` so the frontend can preview persona assets

**Acceptance Criteria:**
- `GET /assets/music/calm_acoustic.mp3` returns 200 with `audio/mpeg`
- `backend/assets/personas/default/personality.md` exists with `Voice-ID:` line and tone description
- `backend/assets/personas/default/character.md` exists with stickman visual description
- `backend/assets/personas/default/seed.png` exists and is a valid PNG
- All `.mp3` files are gitignored — only `tracks.json` committed
- `_load_persona()` from Plan 06 can load these files without error

---

## Task 2: Music Routes

**Actionables:**
- Create `backend/api/routes/music.py`
- Implement:

  `GET /music/tracks`
  — Reads `backend/assets/music/tracks.json`, returns parsed list
  — Never returns 404 — returns empty list if file is missing

  `POST /projects/{project_id}/music/select`
  — Body: `{"track_filename": "calm_acoustic.mp3"}` (or `null` to clear)
  — Validates that the filename exists in `tracks.json` — returns 422 if not found
  — Updates `project.music_track` via `ProjectRepository.update_project()`
  — Advances project `stage` to `generating` readiness — actually just updates `music_track` field; stage advances in Task 5 when generation starts
  — Returns updated `ProjectSummary`

- Register this router in `backend/main.py` under `/api` prefix

**Acceptance Criteria:**
- `GET /api/music/tracks` returns a list of track objects with `filename`, `title`, `mood`, `duration_seconds`
- `POST /api/projects/{id}/music/select` with a valid filename updates `project.music_track`
- `POST /api/projects/{id}/music/select` with an unknown filename returns 422
- `POST /api/projects/{id}/music/select` with `null` clears `music_track` to `None`

---

## Task 3: Update Generation Pipeline for Project-Based Input

**Actionables:**
- Update `backend/pipeline/state.py`: add `project_id` (Optional[str]), `scenes` (list[dict]), `music_track` (Optional[str]), and `persona` (Optional[dict]) fields to `PipelineState`
- Add a `load_persona_node(state)` as the first node in the project-based flow:
  - Calls `_load_persona()` from `backend/pipeline/editorial.py`
  - Sets `state["persona"]` with the loaded `{"personality": ..., "character": ...}` dict
  - On `FileNotFoundError`: sets `state["error"]` with a clear message about missing persona files
- Update `backend/pipeline/graph.py`: the existing `scripting_node` must be bypassed when `project_id` is set and `scenes` is non-empty
  - Add a router function at the start of the graph: if `scenes` is populated, run `load_persona_node` then skip directly to `audio_node`; otherwise run `scripting_node` as before
  - This preserves backward compatibility with the old prompt-only flow
- Update `backend/pipeline/nodes/audio.py`:
  - When `project_id` is set, iterate `state["scenes"]` and generate TTS audio for each scene's `dialog` field individually
  - Use the persona's `elevenlabs_voice_id` if set in `personality.md` (parse as `Voice-ID: <id>` line in the file); fall back to `settings.elevenlabs_voice_id`
  - Save each to `outputs/{project_id}/audio_{order:02d}.mp3`
  - After each synthesis, measure duration via `get_audio_duration()` and update the scene's `audio_duration_seconds` in the SQLite DB via `ProjectRepository.update_scene()`
  - Update each scene's `audio_path` in the DB after each TTS call — allows partial progress recovery
  - Still use `state["voiceover_script"]` for the old single-file path when no scenes are present
- Update `backend/pipeline/nodes/image_gen.py`:
  - When `project_id` is set, use each scene's `image_prompt` (already has `STYLE_CONSTRAINTS` appended from Plan 06)
  - Pass `state["persona"]["character"]` visual description as additional conditioning prefix to ComfyUI
  - Save each image to `outputs/{project_id}/scene_{order:02d}.png`
  - Update each scene's `image_path` in the DB after each generation
- Update `backend/pipeline/nodes/video.py`:
  - When `scenes` is populated, use each scene's `video_prompt` zipped with the generated `image_paths`
  - Pass the scene's generated image as the I2V first-frame anchor to `LocalWanBackend`
  - Save each clip to `outputs/{project_id}/clip_{order:02d}.mp4`
  - Update each scene's `video_clip_path` and `thumbnail_path` in the DB after each clip
- Update `backend/pipeline/nodes/assembly.py`:
  - When `scenes` is populated: for each clip, read the scene's `audio_duration_seconds` from state to drive FFmpeg freeze/trim sync
  - Concatenate duration-synced clips in scene `order`
  - Mix in music if `state.get("music_track")` is set: use `ffmpeg` subprocess to overlay music at -18dB under the assembled video's audio track. Loop the music track if shorter than the video.
  - Save final output to `outputs/{project_id}/final.mp4`

**Acceptance Criteria:**
- Old single-prompt flow (`python main.py --prompt "..."`) still works — `pytest backend/tests/ -v` passes
- When `scenes` is provided: `scripting_node` is skipped (verify via unit test with mocked graph)
- `load_persona_node` runs before audio when in project mode — `state["persona"]` is set (verify via unit test)
- Each scene's `audio_path`, `audio_duration_seconds`, `image_path`, `video_clip_path` in the DB are updated as generation progresses (not only at the end)
- Assembly with `music_track` set produces a file — verify via test that the ffmpeg command includes the music overlay flag
- Assembly applies per-scene freeze/trim: verify via mock that FFmpeg `tpad` or trim command is called based on mocked duration values

---

## Task 4: Project-Based Generation Route

**Actionables:**
- Add the following endpoint to `backend/api/routes/projects.py`:

  `POST /projects/{project_id}/generate`
  — Validates: project stage is `music_selection` — returns 409 if not (prevents double-trigger)
  — Validates: project has at least 2 scenes confirmed — returns 409 if not
  — Updates project stage to `generating`
  — Creates a `GenerationJob` in the DB with `project_id` set
  — Creates a `queue.Queue()` for SSE progress
  — Starts pipeline in a `threading.Thread`, passing: `job_id`, `project_id`, all scenes as dicts, `music_track`, `aspect_ratio`, and the progress queue
  — Returns `{"job_id": ..., "project_id": ..., "status": "pending"}` immediately

- The background pipeline thread:
  — Calls `compiled_graph.invoke(initial_state(..., project_id=project_id, scenes=scenes, music_track=music_track))`
  — On success: updates project stage to `done`, sets `project.final_output_path`
  — On failure: updates project stage to `failed`, sets `project.error`
  — Puts sentinel on the queue

**Acceptance Criteria:**
- `POST /api/projects/{id}/generate` returns within 200ms (non-blocking)
- Calling it twice on the same project at `generating` stage returns 409
- Calling it when stage is `scene_editing` (not `music_selection`) returns 409
- Background thread correctly reads scenes from the DB and passes them to the pipeline

---

## Task 5: Step 4 — Music Selection UI

**Actionables:**
- Create `frontend/src/components/wizard/MusicStep.tsx`
- On mount: call `GET /api/music/tracks` and render all tracks
- Each track rendered as a card showing: `title`, `mood` badge, duration formatted as `M:SS`
- Each track card has a "Preview" play/pause button — uses the browser's native `<audio>` element pointed at `/assets/music/{filename}`. Only one track plays at a time (pausing the previous when a new one is started).
- "Select" button on each track — highlights the selected track with a colored border, calls `POST /api/projects/{id}/music/select`
- "No Music" option at the top — a card that clears the selection (`POST` with null)
- The currently selected track (from `project.music_track`) is pre-highlighted on load
- "Continue to Generate" button at the bottom — navigates to step 5 without any API call (music selection is already saved per track click)

**Acceptance Criteria:**
- All tracks render with title, mood badge, and formatted duration
- Preview plays the track; clicking another track stops the first and starts the second
- Selected track has a distinct visual highlight
- Reloading the page with a previously selected track shows it as selected
- "No Music" option clears the selection and removes the highlight from all tracks
- `bun run build` passes

---

## Task 6: Step 5 — Generate + Result UI

**Actionables:**
- Create `frontend/src/components/wizard/GenerateStep.tsx`
- Pre-generation state (project at `music_selection` stage): show a summary of the project configuration — number of scenes, aspect ratio, selected music track (or "No music"), estimated duration from `target_duration_minutes`. A prominent "Generate Video" button.
- On "Generate Video" click:
  - Call `POST /api/projects/{id}/generate`
  - Transition to the in-progress state: show the SSE progress log (reuse `ProgressLog` component from Plan 04), disable the generate button, show a "Generating..." status
  - Connect SSE stream to `GET /api/generate/{job_id}/stream`
- Post-generation state (project `stage === "done"`): show:
  - An HTML5 `<video>` player with `controls` pointing to `/outputs/{project_id}/final.mp4`
  - A horizontal scrollable thumbnail strip — one thumbnail per scene, sourced from each scene's `thumbnail_path`
  - A "Download MP4" anchor link pointing to the same URL with the `download` attribute set
  - A "Start New Project" button that navigates back to the Projects list
- Failed state (project `stage === "failed"`): show the `project.error` in a red box and a "Retry Generation" button that re-calls `POST /api/projects/{id}/generate`
- On mount: if project stage is already `done` or `failed`, show the appropriate state immediately without waiting for a new generate call

**Acceptance Criteria:**
- Pre-generation summary correctly shows scene count, aspect ratio, and music track
- "Generate Video" triggers SSE stream and progress log fills in
- SSE progress events arrive incrementally (not all at once)
- Completed video player renders and plays the final MP4
- Thumbnail strip renders with one image per scene
- "Download MP4" link downloads the file (not just opens it in the browser)
- Failed state shows the error and allows retry
- Revisiting a `done` project shows the video player immediately without re-generating
- `bun run build` passes

---

## Task 7: Persist Scene Generation Progress in UI

**Actionables:**
- When a project is at `generating` stage and the user refreshes or navigates away and back, the wizard should show the in-progress state with any already-completed progress from the DB
- On mount of `GenerateStep`, if `project.stage === "generating"`: check `GET /api/projects/{id}` for an active `job_id` (store `job_id` on the `Project` model in the DB — add this field in `backend/models/project.py`), then re-connect to the SSE stream for that job
- If the SSE stream is no longer active (job already done/failed), show the final state based on `project.stage`

**Acceptance Criteria:**
- Refreshing the page during active generation reconnects to the SSE stream
- Refreshing after generation completes shows the video player, not the generating spinner
- `project.active_job_id` is persisted to the DB when generation starts and cleared when it finishes

---

## Task 8: Add `active_job_id` to Project + Extend Client

**Actionables:**
- Add `active_job_id: Optional[str] = None` field to the `Project` SQLModel table in `backend/models/project.py`
- Update `ProjectDetail` response schema in `backend/models/schemas.py` to include `active_job_id`
- Set `project.active_job_id = job_id` when generation starts
- Clear `project.active_job_id = None` when the job reaches `done` or `failed`
- Add `active_job_id` to the `ProjectDetail` TypeScript interface in `frontend/src/types.ts`
- Update `GenerateStep` to use `project.active_job_id` for SSE reconnection

**Acceptance Criteria:**
- `GET /api/projects/{id}` response includes `active_job_id` field
- `active_job_id` is set to the job ID when generation starts, `null` after completion
- Frontend `ProjectDetail` type has `active_job_id: string | null`

---

## Task 9: Full Stack End-to-End Test

**Actionables:**
- Start backend: `uvicorn backend.main:app --reload --port 8000`
- Start frontend: `cd frontend && bun run dev`
- Complete the full wizard flow:
  1. Create a new project with a real research doc (can be short, 200+ words of markdown)
  2. Generate and choose an angle
  3. Generate story, drag one block to reorder, edit one block's text
  4. Confirm story, generate scenes, expand a scene, regenerate one image prompt
  5. Set aspect ratio to `16:9`
  6. Confirm scenes, select a music track, preview it
  7. Click "Generate Video" — observe SSE progress streaming
  8. Wait for completion — verify video player and thumbnails appear
  9. Download the MP4
  10. Navigate to Projects list — verify the project shows `stage: done`
  11. Re-open the project — verify it shows the video player immediately

**Acceptance Criteria:**
- All 11 steps complete without console errors or server 500s
- Progress log shows at least one entry per scene during generation
- Final MP4 plays in the browser video player
- Downloaded file is a valid MP4 (plays in QuickTime or VLC)
- Project history shows correct stage for each project

---

## Task 10: Final Cleanup + Commit

**Actionables:**
- Run `pytest backend/tests/ -v` — all tests pass
- Run `bun run build` — exits 0
- Remove any temporary test files or debug print statements
- Update `README.md` to reflect the new editorial flow — add a brief "How to Use" section describing the 5-step wizard
- Commit all changes with message: `feat: music selection, project-based generation pipeline, generate + result UI (complete editorial flow)`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/ -v` → zero failures
- `bun run build` → exits 0
- No debug prints or TODO comments in committed code
- `git push` succeeds

---

## Plan 09 Checklist — All Plans Complete

- [ ] `pytest backend/tests/ -v` → zero failures
- [ ] `bun run build` → exits 0
- [ ] Music track preview plays in the browser
- [ ] Full 5-step wizard completes end-to-end without errors
- [ ] SSE progress streams incrementally during generation
- [ ] Final video player works with thumbnails
- [ ] Download link downloads the MP4
- [ ] Re-opening a completed project shows video player immediately
- [ ] Old prompt-only flow (`python main.py --prompt`) still works
- [ ] `backend/assets/personas/default/personality.md`, `character.md`, `seed.png` all exist
- [ ] Per-scene pipeline runs in order: audio → image (ComfyUI img2img with seed.png) → video (LightX2V I2V with scene image) → assembly (FFmpeg duration sync + music mix)
- [ ] Each scene's `audio_duration_seconds` is measured and stored in DB
- [ ] Assembly applies FFmpeg freeze/trim per scene to sync clip length to TTS audio

---

## Complete Project Map (All 9 Plans)

```
Plan 01 — Repo, venv, FFmpeg, ComfyUI setup, folder scaffold, LightX2V setup
Plan 02 — LangGraph pipeline: scripting, audio, image_gen (ComfyUI I2V), video (LightX2V I2V), assembly (FFmpeg duration sync)
Plan 03 — FastAPI backend: job store, SSE, history routes
Plan 04 — React frontend: basic dashboard, form, progress log, history
Plan 05 — SQLite persistence: project, angle, story block, scene tables (with image_path + audio_duration_seconds)
Plan 06 — LLM editorial nodes: angles, story, scene breakdown, per-field regen (persona injection + style constraints)
Plan 07 — Project API routes: full CRUD + all editorial endpoints
Plan 08 — Frontend wizard: angle selection, story editing, scene editing
Plan 09 — Persona files, music selection, project-based generation (per-scene audio→image→video→assembly), generate + result UI
```
