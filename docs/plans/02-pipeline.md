# Plan 02 — LangGraph Pipeline

> **Goal:** Build the complete Python pipeline: pydantic settings → LangGraph state → scripting node (bifrost LLM) → audio node (ElevenLabs) → image node (Flux/ComfyUI img2img) → video node (LightX2V I2V) → assembly node (MovieLite + FFmpeg duration sync) → CLI entrypoint. All nodes have unit tests with mocked dependencies.

**Assumes:** Plan 01 complete. Venv active. `.env` filled with real keys. `docs/lightx2v-invocation.md` written. ComfyUI installed locally with Flux checkpoint available.

---

## Task 1: Config + Settings

**Actionables:**
- Create `backend/models/config.py` with a `pydantic-settings` `BaseSettings` subclass called `Settings`
- Fields to include: `bifrost_base_url`, `bifrost_api_key`, `bifrost_model` (default `glm-5`), `elevenlabs_api_key`, `elevenlabs_voice_id`, `video_backend` (default `local`), `cloud_video_api_key`, `cloud_video_base_url`, `wan_model_path`, `outputs_dir` (Path), `models_dir` (Path), `api_host`, `api_port` (int, default 8000), `comfyui_base_url` (default `http://127.0.0.1:8188`), `personas_dir` (Path, default `backend/assets/personas`), `active_persona` (str, default `default`)
- Set `env_file = ".env"` in the model config
- Export a module-level singleton `settings = Settings()`
- Write a unit test in `backend/tests/test_config.py` that imports `settings` and asserts key fields are correctly typed and have expected defaults

**Acceptance Criteria:**
- `pytest backend/tests/test_config.py -v` passes
- `settings.bifrost_base_url` is a string starting with `http`
- `settings.video_backend` is either `"local"` or `"cloud"`
- `settings.api_port` is `8000`
- `settings.comfyui_base_url` defaults to `http://127.0.0.1:8188`
- `settings.active_persona` defaults to `"default"`
- Importing `settings` with a missing required field raises a `ValidationError`, not a silent default

---

## Task 2: LangGraph Pipeline State

**Actionables:**
- Create `backend/pipeline/state.py` with a `PipelineState` TypedDict
- Fields: `job_id` (str), `user_prompt` (str), `video_prompts` (list[str]), `voiceover_script` (str), `audio_path` (Optional[str]), `audio_duration_seconds` (Optional[float]), `image_paths` (list[str]), `video_paths` (list[str]), `scene_thumbnails` (list[str]), `final_output` (Optional[str]), `progress_log` (list[str]), `error` (Optional[str])
- **Important — parallel safety:** Any field that two nodes may write concurrently must use `Annotated[list[str], operator.add]` as the type so LangGraph merges rather than overwrites. Apply this to `progress_log`, `video_paths`, `image_paths`, and `scene_thumbnails`
- Create an `initial_state(job_id, user_prompt) -> PipelineState` factory function that returns a fully initialized state with empty collections and `None` for optional fields
- Write a unit test asserting all fields are present with correct empty/None defaults

**Acceptance Criteria:**
- `pytest backend/tests/test_state.py -v` passes
- `initial_state("abc", "test")` returns a dict with all keys defined
- `audio_path`, `audio_duration_seconds`, `final_output`, `error` are `None` in initial state
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
- Create `backend/providers/audio_utils.py` with a `get_audio_duration(audio_path: str) -> float` function:
  - Runs `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 <path>` as a subprocess
  - Returns duration as a float in seconds
  - Raises `RuntimeError` if ffprobe returns a non-zero exit code
- Create `backend/pipeline/nodes/audio.py` with an `audio_node(state)` function
  - Skip (return state unchanged) if `state["error"]` is already set
  - Call `get_tts_provider().synthesize(state["voiceover_script"], output_dir)` where `output_dir = settings.outputs_dir / state["job_id"]`
  - After synthesis, call `get_audio_duration(audio_path)` and store the result in `state["audio_duration_seconds"]`
  - On success: set `state["audio_path"]` and `state["audio_duration_seconds"]`, append progress log entry
  - On exception: set `state["error"]`
- Write unit tests covering: audio path is set on success, duration is measured via ffprobe after synthesis, node is skipped when upstream error exists, exception sets error

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestAudioNode -v` → 4 tests pass
- On success: `state["audio_path"]` ends with `.mp3`, `state["audio_duration_seconds"]` is a positive float, `state["error"]` is `None`
- If `state["error"]` is pre-set: `audio_node` returns without modifying `audio_path`
- The `TTSProvider` ABC cannot be instantiated directly
- `get_audio_duration` is called exactly once after synthesis (verify via mock call count)

---

---

## Task 6: Image Generation Provider + Image Node

**Actionables:**
- Create `backend/providers/image_backend.py` with:
  - An abstract base class `ImageBackend` with abstract method `generate_image(prompt: str, seed_image_path: str, output_path: str) -> str`
  - A concrete `ComfyUIImageBackend` implementing `ImageBackend`:
    - Sends an HTTP POST to `{settings.comfyui_base_url}/prompt` with a ComfyUI workflow JSON payload
    - The workflow must use img2img conditioning: load `seed_image_path` as the reference image, apply `prompt` as the positive text prompt, apply the style constraints string as an additional positive prompt
    - Style constraints to always append to the positive prompt: `"flat 2D vector art, unshaded, solid #FFFFFF white background, black lines, zero shadows, minimal character motion, zero camera movement"`
    - Poll `{settings.comfyui_base_url}/history/{prompt_id}` every 2 seconds until the job completes (max 120 seconds timeout)
    - Download the output image from `{settings.comfyui_base_url}/view?filename={output_filename}` and save to `output_path`
    - Raise `RuntimeError` on timeout or non-200 response
  - A `get_image_backend() -> ImageBackend` factory returning `ComfyUIImageBackend`
- Create `backend/pipeline/nodes/image_gen.py` with an `image_gen_node(state)` function:
  - Skip if `state["error"]` is set
  - Load the active persona's seed image path from `settings.personas_dir / settings.active_persona / "seed.png"` — raise `FileNotFoundError` if missing
  - Load `character.md` from `settings.personas_dir / settings.active_persona / "character.md"` — append the first 500 chars of its visual description to each `image_prompt` before passing to ComfyUI
  - Iterate `state["video_prompts"]` (or `state["scenes"]` when project-based), call `backend.generate_image(image_prompt, seed_image_path, output_path)` per scene
  - Save output images as `outputs/{job_id}/scene_{n:02d}.png`
  - Append per-scene progress messages to `state["progress_log"]`
  - On success: set `state["image_paths"]`
  - On any failure: set `state["error"]`, return immediately
- Write unit tests covering: all images generated, seed file missing raises error and sets state error, ComfyUI timeout sets error, upstream error skips node, character.md visual description appended to prompt

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestImageGenNode -v` → 5 tests pass
- `len(state["image_paths"]) == len(state["video_prompts"])` on success
- Each image path ends with `.png`
- If `seed.png` does not exist: `state["error"]` is set, no ComfyUI call is made
- Style constraints string is present in every prompt sent to ComfyUI (verify via mock call args)
- character.md visual description prefix is present in every prompt (verify via mock call args)

---

## Task 7: Video Backend + Video Node

**Actionables:**
- Read `docs/lightx2v-invocation.md` (written in Plan 01) to understand the confirmed LightX2V invocation interface before writing any code
- Create `backend/providers/video_backend.py` with:
  - An abstract base class `VideoBackend` with abstract method `generate_clip(prompt: str, first_frame_image_path: str, output_path: str, duration_seconds: int = 5) -> str`
  - A concrete `LocalWanBackend` that invokes LightX2V via `subprocess.run` in **Image-to-Video (I2V) mode** using the confirmed invocation from `docs/lightx2v-invocation.md`
  - The `first_frame_image_path` argument must be passed as the I2V anchor frame — LightX2V uses this as frame 0 to ensure character appearance is locked
  - Run each clip as a subprocess (not in-process) so the model fully unloads from MPS memory between clips
  - Set a subprocess timeout of 300 seconds per clip
  - A `CloudVideoBackend` stub that raises `NotImplementedError` with a clear message
  - A `get_video_backend() -> VideoBackend` factory that selects based on `settings.video_backend`
- Create `backend/pipeline/nodes/video.py` with a `video_node(state)` function
  - Skip if `state["error"]` is set
  - Requires `state["image_paths"]` to be non-empty — if empty, set `state["error"]` and return
  - Iterate `state["video_prompts"]` zipped with `state["image_paths"]`, call `backend.generate_clip(prompt, image_path, output_path)` for each
  - After each successful clip, extract a JPEG thumbnail of the first frame using `ffmpeg` as a subprocess
  - Append per-clip progress messages to `state["progress_log"]`
  - On any clip failure: set `state["error"]` and return immediately
  - On success: set `state["video_paths"]` and `state["scene_thumbnails"]`
- Write unit tests covering: all clips succeed with correct image anchors, empty `image_paths` sets error, first clip failure stops and sets error, upstream error skips node, thumbnails extracted per clip, I2V mode flag is passed in subprocess call (verify via mock)

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestVideoNode -v` → 6 tests pass
- When all clips succeed: `len(state["video_paths"]) == len(state["video_prompts"])` and same for thumbnails
- `first_frame_image_path` is passed to every `generate_clip` call (verify via mock)
- LightX2V subprocess is called in I2V mode (verify via mock subprocess args)
- When a clip fails: `state["error"]` is set, subsequent clips are not attempted
- If upstream `state["error"]` exists: node returns without calling backend

---

## Task 8: Assembly Node (MovieLite + FFmpeg Duration Sync)

**Actionables:**
- Create `backend/pipeline/nodes/assembly.py` with an `assembly_node(state)` function
- Skip if `state["error"]` is set
- **Per-scene duration sync before assembly:** For each video clip in `state["video_paths"]`:
  - Measure the clip's duration using `ffprobe` (same utility as `get_audio_duration` in Task 5)
  - Measure the corresponding scene's audio duration from `state["audio_duration_seconds"]` (or per-scene audio durations when in project-based mode)
  - If `video_duration < audio_duration`: run an FFmpeg subprocess using the `tpad` filter to freeze the last frame: `ffmpeg -i clip.mp4 -vf "tpad=stop_mode=clone:stop_duration=<gap>" -y padded_clip.mp4`
  - If `video_duration > audio_duration`: run an FFmpeg subprocess to trim: `ffmpeg -i clip.mp4 -t <audio_duration> -y trimmed_clip.mp4`
  - Replace the clip path in the list with the duration-synced version
- Use the real MovieLite API — concatenation is done via chaining clips with `start=previous_clip.end`, not via any `concatenate()` function
- Create a `VideoWriter` targeting `outputs_dir / job_id / final.mp4`
- Add all duration-synced video clips to the writer using `writer.add_clips([...])`
- If `state["audio_path"]` is set: create an `AudioClip` from it (start=0) and add it to the writer via `writer.add_clip(audio)`
- Call `writer.write()` to produce the final MP4
- Call `.close()` on all opened `VideoClip` objects in a `finally` block
- On success: set `state["final_output"]` to the absolute path of `final.mp4`, append progress log entry
- On exception: set `state["error"]`
- Write unit tests covering: final output path set on success, freeze applied when video shorter than audio, trim applied when video longer than audio, audio clip added when audio_path present, node skipped on upstream error, clips closed in finally block
- Tests must mock `movielite.VideoClip`, `movielite.AudioClip`, `movielite.VideoWriter`, and `subprocess.run` — do not actually invoke MovieLite or FFmpeg in unit tests

**Acceptance Criteria:**
- `pytest backend/tests/test_nodes.py::TestAssemblyNode -v` → 6 tests pass
- On success: `state["final_output"]` ends with `final.mp4`, `state["error"]` is `None`
- FFmpeg `tpad` command is called when mock video duration < mock audio duration (verify via subprocess mock args)
- FFmpeg trim command is called when mock video duration > mock audio duration (verify via subprocess mock args)
- Clips are closed even if an exception occurs during write (verify via mock `.close()` call count)
- If upstream error exists: `final_output` remains `None`

---

## Task 9: LangGraph Graph Wiring

**Actionables:**
- Create `backend/pipeline/graph.py` with a `build_graph()` function that returns a compiled `StateGraph`
- Wire nodes in this order: `START → scripting → audio → image_gen → video → assembly → END`
- **Do not use parallel fan-out.** Run all nodes sequentially. This avoids TypedDict state merge complexity on the single-machine MPS setup where video and image generation already saturate the hardware
- Export `compiled_graph = build_graph()` as a module-level singleton
- Write tests asserting: graph compiles without error, all 5 node names are present (`scripting`, `audio`, `image_gen`, `video`, `assembly`), the graph can be invoked with a mock state that has pre-set `video_prompts` and `voiceover_script`

**Acceptance Criteria:**
- `pytest backend/tests/test_graph.py -v` → all tests pass
- `compiled_graph` is not None
- All 5 nodes (`scripting`, `audio`, `image_gen`, `video`, `assembly`) are in `g.nodes`
- Invoking the graph with a fully-mocked state (all nodes patched) completes without exception

---

## Task 10: CLI Entrypoint

**Actionables:**
- Create `main.py` at project root as the CLI entrypoint
- Accept `--prompt` (required) and `--job-id` (optional, default to a random 12-char hex) as CLI arguments via `argparse`
- Load `.env` via `python-dotenv` before any imports that use settings
- Build initial state via `initial_state()`, invoke `compiled_graph.invoke(state)`, print the progress log, and print the final output path or error message
- Exit with code `1` on pipeline error, `0` on success
- This is a smoke-test entrypoint — it requires real API keys, ComfyUI running, and the Wan model; it is not meant to be run in CI

**Acceptance Criteria:**
- `python main.py --help` prints usage without error
- `python main.py --prompt "test"` runs without `ImportError` or `AttributeError` (pipeline may fail due to missing model — that is acceptable at this stage)
- With real API keys, ComfyUI running, and model: full run produces a `final.mp4` in `outputs/<job_id>/`

---

## Task 11: Run All Tests + Commit

**Actionables:**
- Run the full test suite: `pytest backend/tests/ -v`
- Fix any failures before committing
- Commit all backend files with message: `feat: complete LangGraph pipeline — scripting, audio, image_gen (ComfyUI I2V), video (LightX2V I2V), assembly (FFmpeg duration sync) nodes + CLI`
- Push to origin

**Acceptance Criteria:**
- `pytest backend/tests/ -v` → all tests pass, zero failures
- `git push` succeeds
- No API keys or `.env` content in the commit

---

## Plan 02 Checklist — Before Moving to Plan 03

- [ ] `pytest backend/tests/ -v` → all tests pass (18+ tests)
- [ ] `python main.py --help` prints usage without error
- [ ] `python -c "from backend.pipeline.graph import compiled_graph"` imports cleanly
- [ ] `backend/pipeline/graph.py` uses sequential wiring (scripting → audio → image_gen → video → assembly)
- [ ] Image node uses ComfyUI img2img with seed.png anchor and appends style constraints to every prompt
- [ ] Video node invokes LightX2V in I2V mode, passing generated scene image as first-frame anchor
- [ ] Assembly node applies FFmpeg freeze/trim per scene to sync video duration to TTS audio duration
- [ ] Assembly node uses real MovieLite API (`VideoWriter`, `add_clips`, `writer.write()`)
- [ ] `docs/lightx2v-invocation.md` was consulted and `LocalWanBackend` uses the confirmed invocation
- [ ] `backend/assets/personas/default/seed.png`, `personality.md`, `character.md` exist

**Next:** `docs/plans/03-backend-api.md`
