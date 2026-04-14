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

## Task 6: LightX2V Setup

**Actionables:**
- Clone the LightX2V repo into `external/lightx2v`: `git clone https://github.com/ModelTC/lightx2v.git external/lightx2v`
- Install LightX2V into the active venv from the cloned directory: `pip install -e external/lightx2v`
- Read `external/lightx2v/README.md` and `external/lightx2v/scripts/` to understand the actual inference invocation interface (config file vs CLI flags — do not assume)
- Document the confirmed invocation pattern in a new file: `docs/lightx2v-invocation.md` — record the exact command/config format, required arguments, output path behavior, and supported device flags for Apple Silicon MPS
- Create `scripts/download_model.sh` that:
  - Creates `./models/wan2.2-5b-q4/` directory
  - Uses `huggingface-cli download` to fetch the Wan 2.2 5B Q4_K_S GGUF weight file
  - Prints the expected `WAN_MODEL_PATH` value on completion
  - Is idempotent (re-running skips already-downloaded files)
- Make the script executable: `chmod +x scripts/download_model.sh`
- Run the download: `bash scripts/download_model.sh`

**Acceptance Criteria:**
- `ls external/lightx2v/` shows the cloned repo
- `python -c "import lightx2v"` succeeds inside the venv
- `docs/lightx2v-invocation.md` exists and describes the confirmed inference invocation
- `ls models/wan2.2-5b-q4/` shows the `.gguf` weight file
- `WAN_MODEL_PATH` in `.env` points to the correct file path

---

## Task 7: Commit Everything

**Actionables:**
- Stage all non-ignored files: `.gitignore`, `README.md`, `pyproject.toml`, `backend/` scaffold, `.env.example`, `scripts/`, `docs/`, `opencode.json`, `.opencode/`
- Commit with message: `chore: scaffold repo, venv, folder structure, env config, LightX2V setup`
- Push to origin main

**Acceptance Criteria:**
- `git log --oneline` shows a clean commit history
- `gh repo view` shows the repo is up to date with remote
- No secrets are committed (`git show HEAD` does not contain any API keys)

---

## Plan 01 Checklist — Before Moving to Plan 02

- [ ] `gh repo view` → shows `faceless-gen` (private) under KTS-o7
- [ ] `ffmpeg -version` → prints version without error
- [ ] `.venv/bin/python --version` → `Python 3.11.x`
- [ ] `python -c "import langgraph; import fastapi; import movielite; print('ok')"` → `ok`
- [ ] `find backend -name "__init__.py" | wc -l` → `9`
- [ ] `.env` exists with real API keys and is gitignored
- [ ] `ls models/wan2.2-5b-q4/` → shows the `.gguf` file
- [ ] `docs/lightx2v-invocation.md` exists with confirmed invocation details
- [ ] `git log --oneline` → clean commit, no secrets

**Next:** `docs/plans/02-pipeline.md`
