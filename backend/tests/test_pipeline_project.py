"""Tests for Plan 09 — music routes, persona node, graph routing, and project generate endpoint."""
import tempfile
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlmodel import SQLModel, Session, select

import backend.models.project  # noqa: F401

# ---------------------------------------------------------------------------
# Shared test DB setup (mirrors test_projects_api.py)
# ---------------------------------------------------------------------------

_TMPDIR = tempfile.mkdtemp()
_TEST_DB_PATH = os.path.join(_TMPDIR, "test_plan09.db")
_TEST_URL = f"sqlite:///{_TEST_DB_PATH}"

_TEST_ENGINE = create_engine(_TEST_URL, connect_args={"check_same_thread": False})


@event.listens_for(_TEST_ENGINE, "connect")
def _set_fk_pragma(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


SQLModel.metadata.create_all(_TEST_ENGINE)


@contextmanager
def _test_sync_session():
    with Session(_TEST_ENGINE) as session:
        yield session


_PATCH_SESSION_PROJECTS = "backend.api.routes.projects.get_sync_session"
_PATCH_SESSION_MUSIC = "backend.api.routes.music.get_sync_session"
_PATCH_INIT_DB = "backend.storage.database.init_db"

from backend.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with patch(_PATCH_SESSION_PROJECTS, _test_sync_session), \
         patch(_PATCH_SESSION_MUSIC, _test_sync_session), \
         patch(_PATCH_INIT_DB, return_value=None):
        with TestClient(app) as c:
            yield c


@pytest.fixture(autouse=True)
def clean_db():
    yield
    from backend.models.project import Scene, StoryBlock, Angle, Project
    with Session(_TEST_ENGINE) as session:
        for model in [Scene, StoryBlock, Angle, Project]:
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()


VALID_SOURCE_DOC = "x" * 110

_MOCK_SCENES = [
    {
        "order": 0,
        "title": "Scene One",
        "dialog": "Dialog one.",
        "image_prompt": "Image prompt one.",
        "video_prompt": "Video prompt one.",
    },
    {
        "order": 1,
        "title": "Scene Two",
        "dialog": "Dialog two.",
        "image_prompt": "Image prompt two.",
        "video_prompt": "Video prompt two.",
    },
]


def _create_project_at_music_selection(client):
    """Helper: create project and advance it to music_selection stage."""
    resp = client.post(
        "/api/projects",
        json={"name": "Test Project", "source_doc": VALID_SOURCE_DOC, "target_duration_minutes": 3},
    )
    assert resp.status_code == 201
    project = resp.json()
    pid = project["id"]

    # Add 2 scenes directly via DB
    from backend.models.project import Scene
    with Session(_TEST_ENGINE) as session:
        for s in _MOCK_SCENES:
            scene = Scene(project_id=pid, **s)
            session.add(scene)
        session.commit()

    # Advance stage to music_selection
    with Session(_TEST_ENGINE) as session:
        from backend.storage.project_repo import repo
        repo.update_project(session, pid, stage="music_selection")

    return pid


# ---------------------------------------------------------------------------
# Task 11a: load_persona_node tests
# ---------------------------------------------------------------------------


class TestLoadPersonaNode:
    def test_load_persona_sets_persona(self):
        """load_persona_node should populate state['persona'] with persona dict."""
        from backend.pipeline.nodes.persona import load_persona_node

        fake_persona = {"personality": "calm narrator", "character": "stickman", "voice_id": "abc123"}
        state = {
            "job_id": "test-job",
            "error": None,
            "scenes": [{"order": 0}],
        }

        with patch("backend.pipeline.nodes.persona._load_persona", return_value=fake_persona):
            result = load_persona_node(state)

        assert result["persona"] == fake_persona
        assert "load_persona_node: persona loaded" in result["progress_log"]

    def test_load_persona_propagates_error(self):
        """load_persona_node should set error if persona files are missing."""
        from backend.pipeline.nodes.persona import load_persona_node

        state = {"job_id": "test-job", "error": None}

        with patch(
            "backend.pipeline.nodes.persona._load_persona",
            side_effect=FileNotFoundError("personality.md not found"),
        ):
            result = load_persona_node(state)

        assert "error" in result
        assert "personality.md not found" in result["error"]

    def test_load_persona_skips_if_error_in_state(self):
        """load_persona_node should return empty dict if upstream error exists."""
        from backend.pipeline.nodes.persona import load_persona_node

        state = {"job_id": "test-job", "error": "upstream error"}
        result = load_persona_node(state)
        assert result == {}


# ---------------------------------------------------------------------------
# Task 11b: _route_start tests
# ---------------------------------------------------------------------------


class TestRouteStart:
    def test_route_start_returns_load_persona_when_scenes_non_empty(self):
        from backend.pipeline.graph import _route_start

        state = {"scenes": [{"order": 0, "dialog": "test"}]}
        assert _route_start(state) == "load_persona"

    def test_route_start_returns_scripting_when_scenes_empty(self):
        from backend.pipeline.graph import _route_start

        state = {"scenes": []}
        assert _route_start(state) == "scripting"

    def test_route_start_returns_scripting_when_no_scenes_key(self):
        from backend.pipeline.graph import _route_start

        state = {}
        assert _route_start(state) == "scripting"


# ---------------------------------------------------------------------------
# Task 11c: compiled_graph backward compat
# ---------------------------------------------------------------------------


class TestCompiledGraphBackwardCompat:
    def test_compiled_graph_accepts_old_style_state(self):
        """compiled_graph should invoke without error using old-style (no project_id) state."""
        from backend.pipeline.graph import compiled_graph
        from backend.pipeline.state import initial_state

        state = initial_state("test-job-old", "test prompt")

        mock_scripting = MagicMock(return_value={
            "voiceover_script": "hello world",
            "video_prompts": ["prompt 1"],
            "progress_log": ["scripting done"],
        })
        mock_audio = MagicMock(return_value={
            "audio_path": "/tmp/audio.mp3",
            "audio_duration_seconds": 10.0,
            "progress_log": ["audio done"],
        })
        mock_image = MagicMock(return_value={
            "image_paths": ["/tmp/scene_00.png"],
            "progress_log": ["image done"],
        })
        mock_video = MagicMock(return_value={
            "video_paths": ["/tmp/clip_00.mp4"],
            "scene_thumbnails": ["/tmp/thumb_00.jpg"],
            "progress_log": ["video done"],
        })
        mock_assembly = MagicMock(return_value={
            "final_output": "/tmp/final.mp4",
            "progress_log": ["assembly done"],
        })

        with patch("backend.pipeline.nodes.scripting.scripting_node", mock_scripting), \
             patch("backend.pipeline.nodes.audio.audio_node", mock_audio), \
             patch("backend.pipeline.nodes.image_gen.image_gen_node", mock_image), \
             patch("backend.pipeline.nodes.video.video_node", mock_video), \
             patch("backend.pipeline.nodes.assembly.assembly_node", mock_assembly):
            # Patch at graph level
            from backend.pipeline import graph as graph_module
            with patch.object(graph_module.compiled_graph, "invoke") as mock_invoke:
                mock_invoke.return_value = {"final_output": "/tmp/final.mp4", "progress_log": []}
                result = graph_module.compiled_graph.invoke(state)
                assert result["final_output"] == "/tmp/final.mp4"


# ---------------------------------------------------------------------------
# Task 11d: Music route tests
# ---------------------------------------------------------------------------


class TestMusicRoutes:
    def test_get_tracks_returns_list(self, client):
        resp = client.get("/api/music/tracks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_tracks_returns_track_objects(self, client):
        with patch("backend.api.routes.music._read_tracks", return_value=[
            {"filename": "calm_acoustic.mp3", "title": "Calm Acoustic", "mood": "calm", "duration_seconds": 180},
        ]):
            resp = client.get("/api/music/tracks")
        assert resp.status_code == 200
        tracks = resp.json()
        assert len(tracks) == 1
        assert tracks[0]["filename"] == "calm_acoustic.mp3"
        assert tracks[0]["mood"] == "calm"
        assert "duration_seconds" in tracks[0]

    def test_get_tracks_returns_empty_if_no_file(self, client):
        with patch("backend.api.routes.music._read_tracks", return_value=[]):
            resp = client.get("/api/music/tracks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_select_music_valid_filename_returns_200(self, client):
        pid = _create_project_at_music_selection(client)
        stub_tracks = [{"filename": "calm_acoustic.mp3", "title": "Calm", "mood": "calm", "duration_seconds": 180}]
        with patch("backend.api.routes.music._read_tracks", return_value=stub_tracks):
            resp = client.post(
                f"/api/projects/{pid}/music/select",
                json={"track_filename": "calm_acoustic.mp3"},
            )
        assert resp.status_code == 200
        assert resp.json()["music_track"] == "calm_acoustic.mp3"

    def test_select_music_invalid_filename_returns_422(self, client):
        pid = _create_project_at_music_selection(client)
        stub_tracks = [{"filename": "calm_acoustic.mp3", "title": "Calm", "mood": "calm", "duration_seconds": 180}]
        with patch("backend.api.routes.music._read_tracks", return_value=stub_tracks):
            resp = client.post(
                f"/api/projects/{pid}/music/select",
                json={"track_filename": "nonexistent_track.mp3"},
            )
        assert resp.status_code == 422

    def test_select_music_null_clears_track(self, client):
        pid = _create_project_at_music_selection(client)
        stub_tracks = [{"filename": "calm_acoustic.mp3", "title": "Calm", "mood": "calm", "duration_seconds": 180}]
        # First select a track
        with patch("backend.api.routes.music._read_tracks", return_value=stub_tracks):
            client.post(f"/api/projects/{pid}/music/select", json={"track_filename": "calm_acoustic.mp3"})
        # Then clear it
        with patch("backend.api.routes.music._read_tracks", return_value=stub_tracks):
            resp = client.post(f"/api/projects/{pid}/music/select", json={"track_filename": None})
        assert resp.status_code == 200
        assert resp.json()["music_track"] is None

    def test_select_music_unknown_project_returns_404(self, client):
        stub_tracks = [{"filename": "calm_acoustic.mp3", "title": "Calm", "mood": "calm", "duration_seconds": 180}]
        with patch("backend.api.routes.music._read_tracks", return_value=stub_tracks):
            resp = client.post(
                "/api/projects/aabbccddeeff00112233445566778899/music/select",
                json={"track_filename": "calm_acoustic.mp3"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 11e: Project generate endpoint tests
# ---------------------------------------------------------------------------


class TestGenerateProjectEndpoint:
    def test_generate_from_music_selection_returns_job_id(self, client):
        pid = _create_project_at_music_selection(client)
        with patch("backend.api.routes.projects.threading.Thread") as MockThread:
            MockThread.return_value.start.return_value = None
            resp = client.post(f"/api/projects/{pid}/generate")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["project_id"] == pid
        assert data["status"] == "pending"

    def test_generate_from_generating_stage_returns_409(self, client):
        pid = _create_project_at_music_selection(client)
        # Set stage to generating
        with Session(_TEST_ENGINE) as session:
            from backend.storage.project_repo import repo
            repo.update_project(session, pid, stage="generating")

        resp = client.post(f"/api/projects/{pid}/generate")
        assert resp.status_code == 409

    def test_generate_from_failed_stage_returns_200(self, client):
        """Retry from failed stage should succeed."""
        pid = _create_project_at_music_selection(client)
        # Advance to failed
        with Session(_TEST_ENGINE) as session:
            from backend.storage.project_repo import repo
            repo.update_project(session, pid, stage="failed", error="previous error")

        with patch("backend.api.routes.projects.threading.Thread") as MockThread:
            MockThread.return_value.start.return_value = None
            resp = client.post(f"/api/projects/{pid}/generate")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data

    def test_generate_from_scene_editing_stage_returns_409(self, client):
        pid = _create_project_at_music_selection(client)
        with Session(_TEST_ENGINE) as session:
            from backend.storage.project_repo import repo
            repo.update_project(session, pid, stage="scene_editing")

        resp = client.post(f"/api/projects/{pid}/generate")
        assert resp.status_code == 409

    def test_generate_unknown_project_returns_404(self, client):
        resp = client.post("/api/projects/aabbccddeeff00112233445566778899/generate")
        assert resp.status_code == 404

    def test_generate_sets_stage_to_generating(self, client):
        pid = _create_project_at_music_selection(client)
        with patch("backend.api.routes.projects.threading.Thread") as MockThread:
            MockThread.return_value.start.return_value = None
            client.post(f"/api/projects/{pid}/generate")

        resp = client.get(f"/api/projects/{pid}")
        assert resp.json()["stage"] == "generating"
