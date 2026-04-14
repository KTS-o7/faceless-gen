# Plan 02 — LangGraph Pipeline

> **Goal:** Build the complete Python pipeline: pydantic settings → LangGraph state → scripting node (bifrost LLM) → audio node (ElevenLabs) → video node (Wan 2.2 local) → assembly node (MovieLite) → CLI entrypoint. All nodes have unit tests with mocked dependencies.

**Assumes:** Plan 01 complete. Venv active. `.env` filled with real keys. `docs/lightx2v-invocation.md` written.

---

## Task 1: Config + Settings

**Actionables:**
- Create `backend/models/config.py` with a `pydantic-settings` `BaseSettings` subclass called `Settings`
- Fields to include: `bifrost_base_url`, `bifrost_api_key`, `bifrost_model` (default `glm-5`), `elevenlabs_api_key`, `elevenlabs_voice_id`, `video_backend` (default `local`), `cloud_video_api_key`, `cloud_video_base_url`, `wan_model_path`, `outputs_dir` (Path), `models_dir` (Path), `api_host`, `api_port` (int, default 8000)
- Set `env_file = ".env"` in the model config
- Export a module-level singleton `settings = Settings()`
- Write a unit test in `backend/tests/test_config.py` that imports `settings` and asserts key fields are correctly typed and have expected defaults

**Acceptance Criteria:**
- `pytest backend/tests/test_config.py -v` passes
- `settings.bifrost_base_url` is a string starting with `http`
- `settings.video_backend` is either `"local"` or `"cloud"`
- `settings.api_port` is `8000`
- Importing `settings` with a missing required field raises a `ValidationError`, not a silent default

---

## Task 2: LangGraph Pipeline State

**Actionables:**
- Create `backend/pipeline/state.py` with a `PipelineState` TypedDict
- Fields: `job_id` (str), `user_prompt` (str), `video_prompts` (list[str]), `voiceover_script` (str), `audio_path` (Optional[str]), `video_paths` (list[str]), `scene_thumbnails` (list[str]), `final_output` (Optional[str]), `progress_log` (list[str]), `error` (Optional[str])
- **Important — parallel safety:** Any field that two nodes may write concurrently must use `Annotated[list[str], operator.add]` as the type so LangGraph merges rather than overwrites. Apply this to `progress_log`, `video_paths`, and `scene_thumbnails`
- Create an `initial_state(job_id, user_prompt) -> PipelineState` factory function that returns a fully initialized state with empty collections and `None` for optional fields
- Write a unit test asserting all fields are present with correct empty/None defaults

**Acceptance Criteria:**
- `pytest backend/tests/test_state.py -v` passes
- `initial_state("abc", "test")` returns a dict with all keys defined
- `audio_path`, `final_output`, `error` are `None` in initial state
- All list fields default to `[]`

---

## Task 3: bifrost LLM Provider

**Actionables:**
- Create `backend/providers/llm.py` with a `get_llm(temperature=0.7)` factory function
- Use `ChatOpenAI` from `langchain-openai`, setting `model`, `api_key`, and `base_url` from `settings`
- The `base_url` must point to the bifrost gateway, never `api.openai.com`
- Write a unit test that calls `get_llm()` and asserts the returned object has a `base_url` that does not contain `openai.com`

**Acceptance Criteria:**
- `pytest backend/tests/test_providers.py -v` passes
- `get_llm().openai_api_base` does not contain `openai.com`
- Changing `BIFROST_MODEL` in `.env` changes `llm.model_name` without any code change

---

## Task 4: Scripting Node

**Actionables:**
- Create `backend/pipeline/nodes/scripting.py` with a `scripting_node(state)` function
- The node calls the bifrost LLM with a structured system prompt instructing it to output only valid JSON with two keys: `video_prompts` (list of 4–6 short cinematic scene descriptions) and `voiceover_script` (a 3–5 sentence narration)
- Parse the LLM response as JSON; strip any leading/trailing markdown code fences before parsing
- On success: populate `state["video_prompts"]` and `state["voiceover_script"]`, append a progress message to `state["progress_log"]`
- On `JSONDecodeError` or missing keys: set `state["error"]` with a descriptive message including the first 200 chars of the raw response
- Write unit tests covering: valid response parsed correctly, markdown fences stripped, bad JSON sets error, missing key sets error

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestScriptingNode -v` → 4 tests pass
- Valid LLM response → `video_prompts` is a non-empty list, `voiceover_script` is a non-empty string, `error` is `None`
- Malformed JSON response → `error` is set, `video_prompts` remains `[]`
- Markdown-fenced JSON is parsed correctly as if fences were absent

---

## Task 5: TTS Provider + Audio Node

**Actionables:**
- Create `backend/providers/tts.py` with:
  - An abstract base class `TTSProvider` with a single abstract method `synthesize(text, output_dir) -> str` that returns the absolute path to the saved audio file
  - A concrete `ElevenLabsTTSProvider` implementing `TTSProvider` using the `ElevenLabs` client from the `elevenlabs` SDK (v2+)
  - Use `client.text_to_speech.convert(voice_id, text, model_id, output_format)` — iterate the returned generator and write chunks to a `.mp3` file, skipping any non-bytes chunks
  - A `get_tts_provider() -> TTSProvider` factory that returns `ElevenLabsTTSProvider`
- Create `backend/pipeline/nodes/audio.py` with an `audio_node(state)` function
  - Skip (return state unchanged) if `state["error"]` is already set
  - Call `get_tts_provider().synthesize(state["voiceover_script"], output_dir)` where `output_dir = settings.outputs_dir / state["job_id"]`
  - On success: set `state["audio_path"]`, append progress log entry
  - On exception: set `state["error"]`
- Write unit tests covering: audio path is set on success, node is skipped when upstream error exists, exception sets error

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestAudioNode -v` → 3 tests pass
- On success: `state["audio_path"]` ends with `.mp3`, `state["error"]` is `None`
- If `state["error"]` is pre-set: `audio_node` returns without modifying `audio_path`
- The `TTSProvider` ABC cannot be instantiated directly

---

## Task 6: Video Backend + Video Node

**Actionables:**
- Read `docs/lightx2v-invocation.md` (written in Plan 01) to understand the confirmed LightX2V invocation interface before writing any code
- Create `backend/providers/video_backend.py` with:
  - An abstract base class `VideoBackend` with abstract method `generate_clip(prompt, output_path, duration_seconds=5) -> str`
  - A concrete `LocalWanBackend` that invokes LightX2V via `subprocess.run` using the **confirmed invocation pattern from `docs/lightx2v-invocation.md`** — do not guess CLI flags
  - Run each clip as a subprocess (not in-process) so the model fully unloads from MPS memory between clips
  - Set a subprocess timeout of 300 seconds per clip
  - A `CloudVideoBackend` stub that raises `NotImplementedError` with a clear message
  - A `get_video_backend() -> VideoBackend` factory that selects based on `settings.video_backend`
- Create `backend/pipeline/nodes/video.py` with a `video_node(state)` function
  - Skip if `state["error"]` is set
  - Iterate `state["video_prompts"]`, call `backend.generate_clip()` for each, collect output paths
  - After each successful clip, extract a JPEG thumbnail of the first frame using `ffmpeg` as a subprocess
  - Append per-clip progress messages to `state["progress_log"]`
  - On any clip failure: set `state["error"]` and return immediately (do not continue remaining clips)
  - On success: set `state["video_paths"]` and `state["scene_thumbnails"]`
- Write unit tests covering: all clips succeed, first clip failure stops and sets error, upstream error skips node, thumbnails are extracted for each clip

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestVideoNode -v` → 4 tests pass
- When all clips succeed: `len(state["video_paths"]) == len(state["video_prompts"])` and same for thumbnails
- When a clip fails: `state["error"]` is set, subsequent clips are not attempted
- If upstream `state["error"]` exists: node returns without calling backend

---

## Task 7: Assembly Node (MovieLite)

**Actionables:**
- Create `backend/pipeline/nodes/assembly.py` with an `assembly_node(state)` function
- Skip if `state["error"]` is set
- Use the real MovieLite API — concatenation is done via chaining clips with `start=previous_clip.end`, not via any `concatenate()` function
- Create a `VideoWriter` targeting `outputs_dir / job_id / final.mp4`
- Add all video clips to the writer using `writer.add_clips([...])`
- If `state["audio_path"]` is set: create an `AudioClip` from it (start=0) and add it to the writer via `writer.add_clip(audio)`
- Call `writer.write()` to produce the final MP4
- Call `.close()` on all opened `VideoClip` objects in a `finally` block
- On success: set `state["final_output"]` to the absolute path of `final.mp4`, append progress log entry
- On exception: set `state["error"]`
- Write unit tests covering: final output path is set on success, audio clip is added when audio_path is present, node skipped when upstream error exists
- Tests must mock `movielite.VideoClip`, `movielite.AudioClip`, `movielite.VideoWriter` — do not actually invoke MovieLite in unit tests

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestAssemblyNode -v` → 3 tests pass
- On success: `state["final_output"]` ends with `final.mp4`, `state["error"]` is `None`
- Clips are closed even if an exception occurs during write (verify via mock `.close()` call count)
- If upstream error exists: `final_output` remains `None`

---

## Task 8: LangGraph Graph Wiring

**Actionables:**
- Create `backend/pipeline/graph.py` with a `build_graph()` function that returns a compiled `StateGraph`
- Wire nodes in this order: `START → scripting → audio → video → assembly → END`
- **Do not use parallel fan-out for audio and video.** Run them sequentially: scripting → audio → video → assembly. This avoids TypedDict state merge complexity on the single-machine MPS setup where video generation already saturates the hardware
- Export `compiled_graph = build_graph()` as a module-level singleton
- Write tests asserting: graph compiles without error, all 4 node names are present, the graph can be invoked with a mock state that has pre-set `video_prompts` and `voiceover_script`

**Acceptance Criteria:**
- `pytest backend/tests/test_graph.py -v` → all tests pass
- `compiled_graph` is not None
- All 4 nodes (`scripting`, `audio`, `video`, `assembly`) are in `g.nodes`
- Invoking the graph with a fully-mocked state (all nodes patched) completes without exception

---

## Task 9: CLI Entrypoint

**Actionables:**
- Create `main.py` at project root as the CLI entrypoint
- Accept `--prompt` (required) and `--job-id` (optional, default to a random 12-char hex) as CLI arguments via `argparse`
- Load `.env` via `python-dotenv` before any imports that use settings
- Build initial state via `initial_state()`, invoke `compiled_graph.invoke(state)`, print the progress log, and print the final output path or error message
- Exit with code `1` on pipeline error, `0` on success
- This is a smoke-test entrypoint — it requires real API keys and the Wan model; it is not meant to be run in CI

**Acceptance Criteria:**
- `python main.py --help` prints usage without error
- `python main.py --prompt "test"` runs without `ImportError` or `AttributeError` (pipeline may fail due to missing model — that is acceptable at this stage)
- With real API keys and model: full run produces a `final.mp4` in `outputs/<job_id>/`

---

## Task 10: Run All Tests + Commit

**Actionables:**
- Run the full test suite: `pytest backend/tests/ -v`
- Fix any failures before committing
- Commit all backend files with message: `feat: complete LangGraph pipeline — scripting, audio, video, assembly nodes + CLI`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/ -v` → all tests pass, zero failures
- `git push` succeeds
- No API keys or `.env` content in the commit

---

## Plan 02 Checklist — Before Moving to Plan 03

- [ ] `pytest backend/tests/ -v` → all tests pass (12+ tests)
- [ ] `python main.py --help` prints usage without error
- [ ] `python -c "from backend.pipeline.graph import compiled_graph"` imports cleanly
- [ ] `backend/pipeline/graph.py` uses sequential wiring (scripting → audio → video → assembly)
- [ ] Assembly node uses real MovieLite API (`VideoWriter`, `add_clips`, `writer.write()`)
- [ ] `docs/lightx2v-invocation.md` was consulted and `LocalWanBackend` uses the confirmed invocation

**Next:** `docs/plans/03-backend-api.md`
