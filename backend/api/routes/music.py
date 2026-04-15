"""Music routes — track listing and per-project music selection."""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.storage.database import get_sync_session
from backend.storage.project_repo import repo
from backend.models.schemas import project_to_summary

router = APIRouter(tags=["music"])

TRACKS_PATH = Path(__file__).parent.parent.parent / "assets" / "music" / "tracks.json"


def _read_tracks() -> list:
    if not TRACKS_PATH.exists():
        return []
    with open(TRACKS_PATH) as f:
        return json.load(f)


@router.get("/music/tracks")
async def get_tracks():
    return _read_tracks()


class MusicSelectRequest(BaseModel):
    track_filename: Optional[str] = None


@router.post("/projects/{project_id}/music/select")
async def select_music(project_id: str, body: MusicSelectRequest):
    """Select (or clear) a music track for a project."""
    # Validate track exists if filename provided
    if body.track_filename is not None:
        tracks = _read_tracks()
        filenames = [t["filename"] for t in tracks]
        if body.track_filename not in filenames:
            raise HTTPException(
                status_code=422,
                detail=f"Track '{body.track_filename}' not found in tracks.json",
            )

    with get_sync_session() as session:
        project = repo.get_project(session, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        updated = repo.update_project(session, project_id, music_track=body.track_filename)
        return project_to_summary(updated)
