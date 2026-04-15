# Faceless-Gen

A local-only automated AI video studio for faceless YouTube channels. Takes a research document, guides you through a 5-step editorial wizard, and produces a finished MP4 — no cloud storage, no auth, no subscriptions.

**Stack:** Python 3.11 · FastAPI · LangGraph · LangChain · SQLite · React 18 · TypeScript · Vite · Bun · Tailwind v4

---

## How It Works

```
Research Doc (Markdown)
        │
        ▼
  ┌─────────────────────────────────────────────────────┐
  │              5-Step Editorial Wizard                │
  │                                                     │
  │  1. Angles    — LLM proposes 3 story angles         │
  │  2. Story     — LLM writes full narration blocks    │
  │  3. Scenes    — LLM breaks story into video scenes  │
  │  4. Music     — Choose background track             │
  │  5. Generate  — Pipeline runs, MP4 produced         │
  └─────────────────────────────────────────────────────┘
        │
        ▼
  Per-scene pipeline (runs for each scene):
  TTS Audio → ComfyUI Image → Wan I2V Video → Assembly
        │
        ▼
  Final MP4 (voiceover + stickman animation + music)
```

### Visual Style

All generated videos use a locked stickman character style enforced at every stage:

> `flat 2D vector art, unshaded, solid #FFFFFF white background, black lines, zero shadows, minimal character motion, zero camera movement`

Character consistency is achieved via a **two-stage img2img pipeline**: a seed image of the stickman is passed to Flux/ComfyUI for img2img conditioning, and the generated scene image is used as the first-frame anchor for Wan 2.2 I2V.

---

## Architecture

```
faceless-gen/
├── backend/
│   ├── api/routes/         # FastAPI route handlers
│   │   ├── generate.py     # Prompt-based generation (legacy)
│   │   ├── history.py      # Job history
│   │   ├── music.py        # Music track selection
│   │   └── projects.py     # Full project CRUD + editorial endpoints
│   ├── assets/
│   │   ├── music/          # MP3 tracks (gitignored) + tracks.json
│   │   └── personas/
│   │       └── default/
│   │           ├── personality.md   # Narrator voice + tone
│   │           ├── character.md     # Visual character description
│   │           └── seed.png         # Stickman reference image
│   ├── models/             # Pydantic + SQLModel schemas
│   ├── pipeline/
│   │   ├── editorial.py    # LLM functions (angles, story, scenes, regen)
│   │   ├── graph.py        # LangGraph StateGraph (5 nodes)
│   │   ├── nodes/          # scripting, audio, image_gen, video, assembly, persona
│   │   └── state.py        # PipelineState TypedDict
│   ├── providers/          # TTS, image, video, LLM abstractions
│   ├── storage/            # SQLite DB, sessions, job store, project repo
│   └── tests/              # 218 tests, all passing
├── frontend/
│   └── src/
│       ├── components/
│       │   └── wizard/     # AnglesStep, StoryStep, ScenesStep, MusicStep, GenerateStep
│       ├── hooks/          # useGenerate, useHistory
│       ├── lib/api.ts      # Full typed API client
│       └── types.ts        # Shared TypeScript interfaces
├── docs/plans/             # 9 implementation plans
├── scripts/
│   ├── verify_mps.py       # Verify PyTorch MPS works on Apple Silicon
│   └── download_model.sh   # Download Wan 2.2 I2V model (~20GB)
└── main.py                 # CLI entrypoint (prompt-only mode)
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| macOS | Apple Silicon (M1/M2/M3) | MPS required for local video generation |
| Python | 3.11 | `/opt/homebrew/bin/python3.11` |
| Bun | latest | `curl -fsSL https://bun.sh/install \| bash` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| FFmpeg | 6+ | `brew install ffmpeg` |
| ComfyUI | latest | For image generation (see setup below) |
| Wan 2.2 I2V | 5B | ~20GB download (see setup below) |

---

## Setup

### 1. Clone and activate venv

```bash
git clone https://github.com/KTS-o7/faceless-gen.git
cd faceless-gen
uv venv .venv --python /opt/homebrew/bin/python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in:
# - BIFROST_API_KEY (LLM gateway)
# - ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID
```

### 3. Verify Apple Silicon MPS

```bash
python scripts/verify_mps.py
# Expected: MPS available: True
```

### 4. Install frontend dependencies

```bash
cd frontend
bun install
```

### 5. Set up ComfyUI (Image Generation)

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git external/comfyui
pip install -r external/comfyui/requirements.txt

# Download Flux checkpoint (pick one):
# FLUX.1-schnell (Apache 2.0, faster, recommended)
huggingface-cli download black-forest-labs/FLUX.1-schnell \
  --include "flux1-schnell.safetensors" \
  --local-dir external/comfyui/models/checkpoints/

# Start ComfyUI, build img2img workflow, export API JSON to:
# backend/assets/comfyui_img2img_workflow.json
python external/comfyui/main.py --port 8188 --listen 127.0.0.1
```

See `docs/comfyui-workflow.md` for the full workflow setup guide.

### 6. Download Wan 2.2 I2V model

```bash
# WARNING: ~20GB download. Skip until ready to test video generation.
bash scripts/download_model.sh
# Then set WAN_MODEL_PATH in .env
```

### 7. Create your stickman seed image

Create `backend/assets/personas/default/seed.png` — a simple stickman drawing on a white background. Size: 512×512 or 1024×1024 PNG. Draw in Keynote, Figma, MS Paint, or any tool.

### 8. Add music tracks (optional)

Source royalty-free MP3 files from [Pixabay Music](https://pixabay.com/music/) or [Free Music Archive](https://freemusicarchive.org/) and place them in `backend/assets/music/`. Update `backend/assets/music/tracks.json` with filenames, titles, moods, and durations.

---

## Running

### Backend

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
bun run dev
# Opens at http://localhost:5173
```

---

## Using the Wizard

1. **Create a project** — paste a research document (Markdown, 200+ words), set target duration
2. **Choose an angle** — the LLM proposes 3 story angles; pick one or regenerate
3. **Edit story** — drag blocks to reorder, edit text inline, delete unwanted blocks; confirm when ready
4. **Edit scenes** — expand each scene card to edit dialog, image prompt, video prompt; use ↺ Regen buttons to regenerate image/video prompts; set aspect ratio; confirm when ready
5. **Select music** — preview tracks, pick one (or no music); continue
6. **Generate** — click Generate Video; watch SSE progress stream per scene; download the final MP4

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/generate` | Prompt-based generation (legacy quick mode) |
| `GET` | `/api/generate/{id}/stream` | SSE progress stream |
| `GET` | `/api/history` | All generation jobs |
| `POST` | `/api/projects` | Create project |
| `GET` | `/api/projects` | List projects |
| `GET` | `/api/projects/{id}` | Project detail |
| `POST` | `/api/projects/{id}/angles/generate` | Generate 3 story angles |
| `POST` | `/api/projects/{id}/angles/{angle_id}/choose` | Choose an angle |
| `POST` | `/api/projects/{id}/story/generate` | Generate story blocks |
| `POST` | `/api/projects/{id}/story/confirm` | Confirm story, advance to scene editing |
| `POST` | `/api/projects/{id}/scenes/generate` | Generate scenes from story |
| `POST` | `/api/projects/{id}/scenes/{scene_id}/regenerate` | Regenerate image/video prompt |
| `POST` | `/api/projects/{id}/scenes/confirm` | Confirm scenes, advance to music |
| `GET` | `/api/music/tracks` | List available music tracks |
| `POST` | `/api/projects/{id}/music/select` | Select music track |
| `POST` | `/api/projects/{id}/generate` | Start project-based generation |

---

## Pipeline Detail

### LangGraph nodes (sequential)

```
START
  │
  ├── [scenes empty]  → scripting_node   (LLM: script + video prompts)
  └── [scenes set]    → load_persona_node (load personality.md + character.md)
                              │
                          audio_node       (ElevenLabs TTS per scene)
                              │
                          image_gen_node   (ComfyUI img2img with seed.png anchor)
                              │
                          video_node       (Wan 2.2 I2V via diffusers + MPS)
                              │
                          assembly_node    (MovieLite + FFmpeg duration sync + music mix)
                              │
                            END → final.mp4
```

### Duration sync

After TTS synthesis, each clip's duration is measured with `ffprobe`. The assembly node then:
- **Video shorter than audio** → FFmpeg `tpad` freeze last frame to fill the gap
- **Video longer than audio** → FFmpeg trim to match audio length

### Music mixing

Background music is overlaid at **-18dB** under the voiceover using FFmpeg's `amix` filter with `stream_loop -1` for looping.

---

## Configuration

All configuration is via `.env`. Key variables:

```bash
# LLM (Bifrost gateway — model swappable)
BIFROST_BASE_URL=https://opencode.ai/zen/go/v1
BIFROST_API_KEY=your_key
BIFROST_MODEL=gpt-4o-mini         # swap to gpt-4o, claude-3-5-sonnet, etc.

# TTS
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel voice

# Video backend
VIDEO_BACKEND=local               # or: cloud
WAN_MODEL_PATH=./models/wan2.2-i2v-5b

# Image generation
COMFYUI_BASE_URL=http://127.0.0.1:8188

# Persona
ACTIVE_PERSONA=default            # matches folder under backend/assets/personas/
```

### Swapping the LLM model

```bash
# In .env:
BIFROST_MODEL=claude-3-5-sonnet-20241022
# Restart uvicorn — no code changes needed
```

### Switching to cloud video generation

```bash
# In .env:
VIDEO_BACKEND=cloud
CLOUD_VIDEO_API_KEY=your_key
CLOUD_VIDEO_BASE_URL=https://api.yourprovider.com
# Implement CloudVideoBackend.generate_clip() in backend/providers/video_backend.py
```

---

## Development

### Run tests

```bash
source .venv/bin/activate
pytest backend/tests/ -v        # 218 tests
```

### Build frontend

```bash
cd frontend
bun run build                   # exits 0, zero TypeScript errors
```

### Lint

```bash
source .venv/bin/activate
ruff check backend/
```

---

## Known Limitations

- **Video generation is slow on CPU** — Wan 2.2 I2V on MPS takes ~10–15 minutes per clip. Developing the pipeline without the model is fully supported (all nodes mock-testable).
- **ComfyUI requires manual workflow setup** — the img2img workflow JSON must be exported manually from the ComfyUI UI. See `docs/comfyui-workflow.md`.
- **Music tracks are not included** — source CC0 tracks manually from Pixabay or Free Music Archive. Only `tracks.json` is committed.
- **`seed.png` must be drawn manually** — no default stickman is provided. Any simple black-on-white stickman drawing works.

---

## Roadmap

- [ ] Multiple persona support (swap character per project)
- [ ] Cloud video backend integration (Replicate / fal.ai)
- [ ] Subtitle overlay via FFmpeg
- [ ] Thumbnail generation for YouTube upload
- [ ] Batch project generation queue
- [ ] Export `chapters.json` for YouTube chapter markers
