from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any settings imports so pydantic-settings sees the env vars
load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from backend.api.routes import generate, history  # noqa: E402
from backend.api.routes.music import router as music_router  # noqa: E402
from backend.api.routes.projects import router as projects_router  # noqa: E402
from backend.storage.database import init_db  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Faceless-Gen", version="0.1.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Routers
app.include_router(generate.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(music_router, prefix="/api")

# Static files for outputs directory
outputs_dir = Path("outputs")
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

# Mount music assets
music_dir = Path(__file__).parent / "assets" / "music"
music_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets/music", StaticFiles(directory=str(music_dir)), name="music_assets")

# Mount personas assets
personas_dir = Path(__file__).parent / "assets" / "personas"
personas_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets/personas", StaticFiles(directory=str(personas_dir)), name="personas_assets")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "faceless-gen"}
