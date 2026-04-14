# Plan 01 — Repo, Environment & Project Structure

> **Goal:** Get the git repo live on GitHub (private), Python 3.11 venv created with uv, all folders scaffolded, FFmpeg installed, and `.env.example` ready.

**Stack:** Python 3.11 (`/opt/homebrew/bin/python3.11`), uv, git, gh CLI  
**Assumes:** Nothing. This is the starting point.

---

## Task 1: Initialize Git Repo

**Actionables:**
- Run `git init` and set default branch to `main` in `/Users/krishnatejaswis/Documents/Personal/Faceless-gen`
- Create `.gitignore` covering: Python cache, `.venv/`, `.env`, `models/`, `outputs/`, `*.mp4`, `*.wav`, `*.mp3`, `*.gguf`, `node_modules/`, `frontend/dist/`, `.DS_Store`, `.vscode/`, `.uv/`
- Create a minimal `README.md` describing the project, stack, and pointing to `docs/plans/` for setup
- Run `gh repo create faceless-gen --private --source=. --remote=origin --push`

**Acceptance Criteria:**
- `git log --oneline` shows 1 commit
- `gh repo view` shows `KTS-o7/faceless-gen` as private
- `.env` is listed in `.gitignore` and `git check-ignore -v .env` confirms it

---

## Task 2: Install System Dependencies

**Actionables:**
- Check if `ffmpeg` is available: `ffmpeg -version`
- If missing, install via Homebrew: `brew install ffmpeg`
- Verify FFmpeg is on PATH after install

**Why:** MovieLite requires FFmpeg installed and available in PATH. It does not bundle its own.

**Acceptance Criteria:**
- `ffmpeg -version` prints version info without error
- `which ffmpeg` returns a path under `/opt/homebrew/bin/`

---

## Task 3: Python Environment with uv

**Actionables:**
- Check if `uv` is installed: `uv --version`. If missing, install via `curl -LsSf https://astral.sh/uv/install.sh | sh` and reload shell
- Create venv pinned to Python 3.11: `uv venv .venv --python /opt/homebrew/bin/python3.11`
- Activate the venv: `source .venv/bin/activate`
- Create `pyproject.toml` at project root with the following dependency groups:
  - **Core:** `langgraph>=0.2`, `langchain-openai>=0.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `sse-starlette>=2.0`, `httpx>=0.27`, `python-multipart>=0.0.9`, `elevenlabs>=2.0`, `movielite>=0.2.2`, `pydantic-settings>=2.0`, `python-dotenv>=1.0`, `pillow>=10.0`, `tqdm>=4.0`
  - **Dev:** `pytest>=8.0`, `pytest-asyncio>=0.23`, `ruff>=0.4`, `mypy>=1.0`
  - `requires-python = ">=3.11"`, build backend `hatchling`
  - `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `testpaths = ["backend/tests"]`
- Install all dependencies: `uv pip install -e ".[dev]"`

**Acceptance Criteria:**
- `python --version` (inside venv) prints `Python 3.11.x`
- `python -c "import langgraph; import fastapi; import movielite; import elevenlabs; print('ok')"` prints `ok`
- `uv pip list` shows all packages above with no resolution errors

---

## Task 4: Scaffold Project Folder Structure

**Actionables:**
- Create all backend directories: `backend/api/routes/`, `backend/pipeline/nodes/`, `backend/providers/`, `backend/models/`, `backend/storage/`, `backend/tests/`
- Create support directories: `docs/plans/`, `models/`, `outputs/`, `scripts/`, `external/`
- Add `__init__.py` to every Python package directory under `backend/`

**Acceptance Criteria:**
- `find backend -name "__init__.py" | sort` lists exactly 9 files (one per package directory)
- `ls backend/` shows: `api/`, `models/`, `pipeline/`, `providers/`, `storage/`, `tests/`, `__init__.py`

---

## Task 5: Environment Variables

**Actionables:**
- Create `.env.example` at project root with clearly commented variables for:
  - `BIFROST_BASE_URL`, `BIFROST_API_KEY`, `BIFROST_MODEL` (default: `glm-5`)
  - `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (default: Rachel voice ID)
  - `VIDEO_BACKEND` (default: `local`; options: `local`, `cloud`)
  - `CLOUD_VIDEO_API_KEY`, `CLOUD_VIDEO_BASE_URL` (blank defaults, only needed if `VIDEO_BACKEND=cloud`)
  - `OUTPUTS_DIR` (default: `./outputs`), `MODELS_DIR` (default: `./models`)
  - `WAN_MODEL_PATH` (path to `.gguf` file, set after model download)
  - `API_HOST` (default: `0.0.0.0`), `API_PORT` (default: `8000`)
- Copy `.env.example` to `.env` and fill in real API keys

**Acceptance Criteria:**
- `.env.example` is committed and visible in the repo
- `.env` is NOT committed (`git status` does not show it)
- All required keys are present in `.env.example` with explanatory comments

---

## Task 6: Video Inference Setup — LightX2V + MPS Decision

**CRITICAL FINDING — Read before proceeding:**
LightX2V (`https://github.com/ModelTC/lightx2v`) is **CUDA-only**. Its platform directory contains: `nvidia.py`, `amd_rocm.py`, `ascend_npu.py`, `intel_xpu.py`, `mthreads_musa.py`, `cambricon_mlu.py` — **there is no Apple MPS platform file**. The README announces NVIDIA, AMD ROCm, Ascend, Intel AIPC support — never Apple Silicon. Running LightX2V on this MacBook M3 Pro will either fail at import or fall back to CPU (extremely slow — hours per clip).

**Decision required before writing any video node code:**

Option A — **Use llama.cpp with the Wan GGUF model directly**
- The model (`QuantStack/Wan2.2-TI2V-5B-GGUF`, file `Wan2.2-TI2V-5B-Q4_K_S.gguf`) is confirmed on HuggingFace
- llama.cpp has Metal (MPS) support on Apple Silicon via `CMAKE_ARGS="-DLLAMA_METAL=on"`
- However, llama.cpp's video generation support is unverified — llama.cpp is primarily for LLMs not diffusion models
- **Risk: Medium** — llama.cpp may not support the Wan video model architecture

Option B — **Use diffusers + PyTorch MPS backend**
- Wan 2.1/2.2 models are available in full-precision safetensors format on HuggingFace
- `diffusers>=0.32` has `WanImageToVideoPipeline` with `torch_dtype=torch.float16` and `device="mps"`
- PyTorch MPS is confirmed available on M-series chips (`torch.backends.mps.is_available()`)
- Memory constraint: 18GB unified RAM — 5B model in float16 is ~10GB, leaves 8GB for inference
- **Risk: Low** — diffusers + MPS is a proven path for Apple Silicon video generation

Option C — **Cloud video API as the local backend** (fall back if both above fail)
- `VIDEO_BACKEND=cloud` path is already stubbed in the plan
- Use Replicate, fal.ai, or RunwayML API for video generation during development
- Switch to local once MPS path is confirmed
- **Risk: Zero** — works immediately, costs money per clip

**Recommended path: Option B (diffusers + MPS)**

**Actionables:**
- Do NOT clone LightX2V — it will not run on Apple Silicon
- Remove `external/lightx2v` from the project structure
- Install: `pip install torch torchvision torchaudio` (MPS support is built-in since PyTorch 2.0)
- Install: `pip install diffusers>=0.32 transformers>=4.40 accelerate>=0.30`
- Create `scripts/verify_mps.py`:
  - Imports `torch`, asserts `torch.backends.mps.is_available()` is `True`
  - Creates a small test tensor on MPS device and runs a matmul — confirms MPS compute works
  - Prints: `MPS available: True, device: mps`
- Create `scripts/download_model.sh`:
  - Creates `./models/wan2.2-i2v-5b/` directory
  - Downloads Wan 2.2 I2V 5B in diffusers format from HuggingFace: `huggingface-cli download Wan-AI/Wan2.2-I2V-5B-480P --local-dir ./models/wan2.2-i2v-5b`
  - **Note:** This is ~20GB. Only run when ready to test video generation. The rest of the pipeline (audio, image, assembly) can be developed and tested without downloading this model.
  - Prints the expected `WAN_MODEL_PATH` value on completion
- Document the confirmed diffusers invocation in `docs/wan-invocation.md`:
  - Record the exact Python API: `WanImageToVideoPipeline.from_pretrained(...)`, `.to("mps")`, `pipeline(image=..., prompt=..., ...)`
  - Record expected output format, duration control, resolution
  - Record memory requirements and any `enable_model_cpu_offload()` flags needed for 18GB
- Update `.env.example`: change `WAN_MODEL_PATH` comment to reference the diffusers model directory, add `VIDEO_BACKEND=local`

**Acceptance Criteria:**
- `python scripts/verify_mps.py` prints `MPS available: True`
- `docs/wan-invocation.md` documents the confirmed diffusers I2V Python API
- `scripts/download_model.sh` is executable and idempotent
- **No LightX2V anywhere in the project** — `ls external/` should not contain `lightx2v`
- `python -c "import diffusers; import torch; print(torch.backends.mps.is_available())"` prints `True`

---

## Task 7: ComfyUI Setup for Image Generation

**Actionables:**
- Clone ComfyUI into `external/comfyui`: `git clone https://github.com/comfyanonymous/ComfyUI.git external/comfyui`
- Install ComfyUI dependencies into the venv: `pip install -r external/comfyui/requirements.txt`
- Download a Flux checkpoint (fp8 variant for memory efficiency on 18GB): `huggingface-cli download black-forest-labs/FLUX.1-dev --include "flux1-dev.safetensors" --local-dir external/comfyui/models/checkpoints/`
- Download the Flux VAE: `huggingface-cli download black-forest-labs/FLUX.1-dev --include "ae.safetensors" --local-dir external/comfyui/models/vae/`
- Download the CLIP text encoder: `huggingface-cli download comfyanonymous/flux_text_encoders --local-dir external/comfyui/models/text_encoders/`
  - **Note:** FLUX.1-dev is ~24GB total. Only download when ready for image generation. The scripting, TTS audio, and assembly nodes can all be developed without it.
  - Alternative: Use `black-forest-labs/FLUX.1-schnell` (Apache 2.0, faster, 4-step inference) to reduce download size and generation time.
- Start ComfyUI server to verify: `python external/comfyui/main.py --port 8188 --listen 127.0.0.1`
- In the ComfyUI UI at `http://127.0.0.1:8188`, build and export an img2img workflow:
  - Nodes needed: `LoadImage` → `VAEEncode` → `KSampler` (with positive/negative `CLIPTextEncode`) → `VAEDecode` → `SaveImage`
  - Set denoise strength to `0.65` (preserves seed image structure while applying prompt)
  - Export the workflow as API JSON: **Workflow menu → Save (API format)** → save to `backend/assets/comfyui_img2img_workflow.json`
- Document the ComfyUI API payload format in `docs/comfyui-workflow.md`:
  - Record how to inject `image`, `positive_prompt`, `negative_prompt`, and `seed` into the workflow JSON at runtime
  - Record the polling endpoint: `GET /history/{prompt_id}` and the output image download endpoint: `GET /view?filename=...`

**Acceptance Criteria:**
- `curl http://127.0.0.1:8188/system_stats` returns 200 (ComfyUI server running)
- `backend/assets/comfyui_img2img_workflow.json` exists and is valid JSON
- `docs/comfyui-workflow.md` documents runtime injection points and polling API
- `python -c "import folder_paths"` succeeds (ComfyUI importable from venv)
- A test image can be generated via `POST http://127.0.0.1:8188/prompt` with the workflow JSON

**Actionables:**
- Stage all non-ignored files: `.gitignore`, `README.md`, `pyproject.toml`, `backend/` scaffold, `.env.example`, `scripts/`, `docs/`, `opencode.json`, `.opencode/`
- Commit with message: `chore: scaffold repo, venv, folder structure, env config, diffusers+MPS video setup, ComfyUI setup`
- Push to origin main

**Acceptance Criteria:**
- `git log --oneline` shows a clean commit history
- `gh repo view` shows the repo is up to date with remote
- No secrets are committed (`git show HEAD` does not contain any API keys)

---

## Plan 01 Checklist — Before Moving to Plan 02

- [ ] `gh repo view` → shows `faceless-gen` under KTS-o7
- [ ] `ffmpeg -version` → prints version without error
- [ ] `.venv/bin/python --version` → `Python 3.11.x`
- [ ] `python -c "import langgraph; import fastapi; import movielite; print('ok')"` → `ok`
- [ ] `python scripts/verify_mps.py` → `MPS available: True`
- [ ] `python -c "import diffusers; import torch; print(torch.backends.mps.is_available())"` → `True`
- [ ] `curl http://127.0.0.1:8188/system_stats` → 200 (ComfyUI running)
- [ ] `backend/assets/comfyui_img2img_workflow.json` exists
- [ ] `docs/wan-invocation.md` documents confirmed diffusers I2V API
- [ ] `docs/comfyui-workflow.md` documents ComfyUI API payload and polling
- [ ] `find backend -name "__init__.py" | wc -l` → `9`
- [ ] `.env` exists with real API keys and is gitignored
- [ ] `git log --oneline` → clean commit, no secrets

**Next:** `docs/plans/02-pipeline.md`
