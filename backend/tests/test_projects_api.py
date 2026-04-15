"""Integration tests for Project API routes (Tasks 2–5 of Plan 07).

Uses FastAPI TestClient with a temporary-file SQLite database.
All LLM functions are mocked — no real API calls are made.

Strategy for DB isolation:
  - We use a named temporary SQLite file so that multiple connections share the same data.
  - We patch `backend.api.routes.projects.get_sync_session` so routes use our test engine.
  - We call SQLModel.metadata.create_all on the test engine before tests run.
"""
import tempfile
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlmodel import SQLModel, Session, select

# Ensure models are registered before create_all
import backend.models.project  # noqa: F401

# ---------------------------------------------------------------------------
# Set up a shared temporary SQLite DB file for the test session
# ---------------------------------------------------------------------------

_TMPDIR = tempfile.mkdtemp()
_TEST_DB_PATH = os.path.join(_TMPDIR, "test_projects.db")
_TEST_URL = f"sqlite:///{_TEST_DB_PATH}"

_TEST_ENGINE = create_engine(_TEST_URL, connect_args={"check_same_thread": False})


@event.listens_for(_TEST_ENGINE, "connect")
def _set_fk_pragma(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


# Create all tables once
SQLModel.metadata.create_all(_TEST_ENGINE)


@contextmanager
def _test_sync_session():
    """Test version of get_sync_session using the test engine."""
    with Session(_TEST_ENGINE) as session:
        yield session


# ---------------------------------------------------------------------------
# Import the app AFTER defining the test session factory so we can patch it
# ---------------------------------------------------------------------------
from backend.main import app  # noqa: E402 — app uses lifespan that calls init_db

# Patch init_db so the lifespan doesn't create tables on the production engine
# (the test engine already has tables)
import backend.storage.database as _db_module  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SOURCE_DOC = "x" * 110  # min_length=100 for source_doc

_MOCK_ANGLES = [
    {"title": "Angle One", "pitch": "Pitch one."},
    {"title": "Angle Two", "pitch": "Pitch two."},
    {"title": "Angle Three", "pitch": "Pitch three."},
]

_MOCK_STORY_BLOCKS = [
    {"order": 0, "content": "Story block one content."},
    {"order": 1, "content": "Story block two content."},
    {"order": 2, "content": "Story block three content."},
]

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

# Patch target — routes module imports get_sync_session by name
_PATCH_SESSION = "backend.api.routes.projects.get_sync_session"
_PATCH_INIT_DB = "backend.storage.database.init_db"


@pytest.fixture(scope="module")
def client():
    """TestClient with test DB — shared for the module.
    
    Patches get_sync_session in the routes module to use the test engine,
    and stubs out init_db so the lifespan doesn't touch the production DB.
    """
    with patch(_PATCH_SESSION, _test_sync_session), \
         patch(_PATCH_INIT_DB, return_value=None):
        with TestClient(app) as c:
            yield c


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all rows between tests to keep tests independent."""
    yield
    from backend.models.project import Scene, StoryBlock, Angle, Project
    with Session(_TEST_ENGINE) as session:
        for model in [Scene, StoryBlock, Angle, Project]:
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()


def _create_project(client, name="Test Project", source_doc=None):
    """Helper: create a project and return the JSON dict."""
    resp = client.post(
        "/api/projects",
        json={
            "name": name,
            "source_doc": source_doc or VALID_SOURCE_DOC,
            "target_duration_minutes": 3,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Task 2: Project CRUD tests
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_create_project_returns_201(self, client):
        resp = client.post(
            "/api/projects",
            json={"name": "My Video", "source_doc": VALID_SOURCE_DOC},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["stage"] == "angle_selection"
        assert data["name"] == "My Video"

    def test_create_project_has_empty_children(self, client):
        data = _create_project(client)
        assert data["angles"] == []
        assert data["story_blocks"] == []
        assert data["scenes"] == []

    def test_create_project_rejects_short_name(self, client):
        resp = client.post(
            "/api/projects",
            json={"name": "", "source_doc": VALID_SOURCE_DOC},
        )
        assert resp.status_code == 422

    def test_create_project_rejects_short_source_doc(self, client):
        resp = client.post(
            "/api/projects",
            json={"name": "Test", "source_doc": "too short"},
        )
        assert resp.status_code == 422

    def test_create_project_rejects_duration_out_of_range(self, client):
        resp = client.post(
            "/api/projects",
            json={
                "name": "Test",
                "source_doc": VALID_SOURCE_DOC,
                "target_duration_minutes": 31,
            },
        )
        assert resp.status_code == 422


class TestListProjects:
    def test_list_returns_empty_initially(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_projects(self, client):
        _create_project(client, name="P1")
        _create_project(client, name="P2")
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "P1" in names
        assert "P2" in names


class TestGetProject:
    def test_get_returns_detail(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pid
        assert "source_doc" in data

    def test_get_unknown_returns_404(self, client):
        resp = client.get("/api/projects/aabbccddeeff00112233445566778899")
        assert resp.status_code == 404


class TestDeleteProject:
    def test_delete_returns_204(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

    def test_delete_then_get_returns_404(self, client):
        created = _create_project(client)
        pid = created["id"]
        client.delete(f"/api/projects/{pid}")
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    def test_delete_unknown_returns_204(self, client):
        # delete is idempotent (repo.delete_project is a no-op for missing)
        resp = client.delete("/api/projects/aabbccddeeff00112233445566778899")
        assert resp.status_code == 204


class TestUpdateProject:
    def test_patch_music_track(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.patch(f"/api/projects/{pid}", json={"music_track": "chill.mp3"})
        assert resp.status_code == 200
        assert resp.json()["music_track"] == "chill.mp3"

    def test_patch_unknown_returns_404(self, client):
        resp = client.patch(
            "/api/projects/aabbccddeeff00112233445566778899",
            json={"music_track": "chill.mp3"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 3: Angle tests
# ---------------------------------------------------------------------------


class TestGenerateAngles:
    def test_generate_angles_returns_3(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            resp = client.post(f"/api/projects/{pid}/angles/generate")
        assert resp.status_code == 200
        angles = resp.json()
        assert len(angles) == 3
        assert all("title" in a and "pitch" in a and "id" in a for a in angles)

    def test_generate_angles_chosen_is_false(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            resp = client.post(f"/api/projects/{pid}/angles/generate")
        assert all(a["chosen"] is False for a in resp.json())

    def test_generate_angles_404_for_unknown_project(self, client):
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            resp = client.post("/api/projects/aabbccddeeff00112233445566778899/angles/generate")
        assert resp.status_code == 404

    def test_generate_angles_value_error_returns_422(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.side_effect = ValueError("LLM returned garbage")
            resp = client.post(f"/api/projects/{pid}/angles/generate")
        assert resp.status_code == 422


class TestChooseAngle:
    def test_choose_angle_sets_chosen_true(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()

        angle_id = angles[0]["id"]
        resp = client.post(f"/api/projects/{pid}/angles/{angle_id}/choose")
        assert resp.status_code == 200
        assert resp.json()["chosen"] is True
        assert resp.json()["id"] == angle_id

    def test_choose_angle_advances_stage_to_story_editing(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()

        angle_id = angles[0]["id"]
        client.post(f"/api/projects/{pid}/angles/{angle_id}/choose")

        project = client.get(f"/api/projects/{pid}").json()
        assert project["stage"] == "story_editing"

    def test_choose_angle_unsets_others(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()

        # Choose first, then second
        client.post(f"/api/projects/{pid}/angles/{angles[0]['id']}/choose")
        client.post(f"/api/projects/{pid}/angles/{angles[1]['id']}/choose")

        project = client.get(f"/api/projects/{pid}").json()
        chosen = [a for a in project["angles"] if a["chosen"]]
        assert len(chosen) == 1
        assert chosen[0]["id"] == angles[1]["id"]


# ---------------------------------------------------------------------------
# Task 4: Story tests
# ---------------------------------------------------------------------------


class TestGenerateStory:
    def _setup_with_angle(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()
        client.post(f"/api/projects/{pid}/angles/{angles[0]['id']}/choose")
        return pid

    def test_generate_story_returns_blocks(self, client):
        pid = self._setup_with_angle(client)
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            resp = client.post(f"/api/projects/{pid}/story/generate")
        assert resp.status_code == 200
        blocks = resp.json()
        assert len(blocks) == 3
        assert all("content" in b and "id" in b for b in blocks)

    def test_generate_story_no_chosen_angle_returns_409(self, client):
        created = _create_project(client)
        pid = created["id"]
        # Generate angles but don't choose
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            client.post(f"/api/projects/{pid}/angles/generate")
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            resp = client.post(f"/api/projects/{pid}/story/generate")
        assert resp.status_code == 409

    def test_generate_story_no_angles_at_all_returns_409(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            resp = client.post(f"/api/projects/{pid}/story/generate")
        assert resp.status_code == 409

    def test_generate_story_advances_stage(self, client):
        pid = self._setup_with_angle(client)
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            client.post(f"/api/projects/{pid}/story/generate")
        project = client.get(f"/api/projects/{pid}").json()
        assert project["stage"] == "story_editing"


class TestGetStory:
    def test_get_story_returns_empty_list(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.get(f"/api/projects/{pid}/story")
        assert resp.status_code == 200
        assert resp.json() == []


class TestReorderStory:
    def test_reorder_reverses_order(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()
        client.post(f"/api/projects/{pid}/angles/{angles[0]['id']}/choose")

        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            blocks = client.post(f"/api/projects/{pid}/story/generate").json()

        original_ids = [b["id"] for b in sorted(blocks, key=lambda b: b["order"])]
        reversed_ids = list(reversed(original_ids))

        resp = client.patch(
            f"/api/projects/{pid}/story/reorder",
            json={"ordered_ids": reversed_ids},
        )
        assert resp.status_code == 200
        result = resp.json()
        result_ids = [b["id"] for b in result]
        assert result_ids == reversed_ids


class TestConfirmStory:
    def test_confirm_story_advances_to_scene_editing(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.post(f"/api/projects/{pid}/story/confirm")
        assert resp.status_code == 200
        assert resp.json()["stage"] == "scene_editing"


# ---------------------------------------------------------------------------
# Task 5: Scene tests
# ---------------------------------------------------------------------------


class TestGenerateScenes:
    def _setup_with_story(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()
        client.post(f"/api/projects/{pid}/angles/{angles[0]['id']}/choose")
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            client.post(f"/api/projects/{pid}/story/generate")
        return pid

    def test_generate_scenes_returns_scenes(self, client):
        pid = self._setup_with_story(client)
        with patch("backend.api.routes.projects.generate_scenes") as mock:
            mock.return_value = list(_MOCK_SCENES)
            resp = client.post(f"/api/projects/{pid}/scenes/generate")
        assert resp.status_code == 200
        scenes = resp.json()
        assert len(scenes) == 2
        assert all("title" in s and "dialog" in s and "id" in s for s in scenes)

    def test_generate_scenes_fewer_than_2_blocks_returns_409(self, client):
        created = _create_project(client)
        pid = created["id"]
        # Add only 1 story block directly via DB
        from backend.models.project import StoryBlock
        with Session(_TEST_ENGINE) as session:
            block = StoryBlock(project_id=pid, order=0, content="Only one block.")
            session.add(block)
            session.commit()

        with patch("backend.api.routes.projects.generate_scenes") as mock:
            mock.return_value = list(_MOCK_SCENES)
            resp = client.post(f"/api/projects/{pid}/scenes/generate")
        assert resp.status_code == 409

    def test_generate_scenes_no_blocks_returns_409(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_scenes") as mock:
            mock.return_value = list(_MOCK_SCENES)
            resp = client.post(f"/api/projects/{pid}/scenes/generate")
        assert resp.status_code == 409

    def test_generate_scenes_advances_stage(self, client):
        pid = self._setup_with_story(client)
        with patch("backend.api.routes.projects.generate_scenes") as mock:
            mock.return_value = list(_MOCK_SCENES)
            client.post(f"/api/projects/{pid}/scenes/generate")
        project = client.get(f"/api/projects/{pid}").json()
        assert project["stage"] == "scene_editing"


class TestGetScenes:
    def test_get_scenes_empty(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.get(f"/api/projects/{pid}/scenes")
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateScene:
    def _setup_with_scenes(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()
        client.post(f"/api/projects/{pid}/angles/{angles[0]['id']}/choose")
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            client.post(f"/api/projects/{pid}/story/generate")
        with patch("backend.api.routes.projects.generate_scenes") as mock:
            mock.return_value = list(_MOCK_SCENES)
            scenes = client.post(f"/api/projects/{pid}/scenes/generate").json()
        return pid, scenes

    def test_update_scene_dialog_only(self, client):
        pid, scenes = self._setup_with_scenes(client)
        sid = scenes[0]["id"]
        original_image_prompt = scenes[0]["image_prompt"]

        resp = client.patch(
            f"/api/projects/{pid}/scenes/{sid}",
            json={"dialog": "Updated dialog."},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["dialog"] == "Updated dialog."
        # Other fields unchanged
        assert updated["image_prompt"] == original_image_prompt

    def test_regenerate_field_updates_image_prompt(self, client):
        pid, scenes = self._setup_with_scenes(client)
        sid = scenes[0]["id"]

        with patch("backend.api.routes.projects.regenerate_field") as mock:
            mock.return_value = "New image prompt value."
            resp = client.post(
                f"/api/projects/{pid}/scenes/{sid}/regenerate",
                json={"field_name": "image_prompt"},
            )
        assert resp.status_code == 200
        assert resp.json()["image_prompt"] == "New image prompt value."

    def test_regenerate_field_updates_video_prompt(self, client):
        pid, scenes = self._setup_with_scenes(client)
        sid = scenes[0]["id"]

        with patch("backend.api.routes.projects.regenerate_field") as mock:
            mock.return_value = "New video prompt value."
            resp = client.post(
                f"/api/projects/{pid}/scenes/{sid}/regenerate",
                json={"field_name": "video_prompt"},
            )
        assert resp.status_code == 200
        assert resp.json()["video_prompt"] == "New video prompt value."

    def test_regenerate_field_invalid_field_name_returns_422(self, client):
        pid, scenes = self._setup_with_scenes(client)
        sid = scenes[0]["id"]

        resp = client.post(
            f"/api/projects/{pid}/scenes/{sid}/regenerate",
            json={"field_name": "dialog"},
        )
        assert resp.status_code == 422


class TestConfirmScenes:
    def test_confirm_scenes_advances_to_music_selection(self, client):
        created = _create_project(client)
        pid = created["id"]
        resp = client.post(f"/api/projects/{pid}/scenes/confirm")
        assert resp.status_code == 200
        assert resp.json()["stage"] == "music_selection"


class TestReorderScenes:
    def _setup_with_scenes(self, client):
        created = _create_project(client)
        pid = created["id"]
        with patch("backend.api.routes.projects.generate_angles") as mock:
            mock.return_value = list(_MOCK_ANGLES)
            angles = client.post(f"/api/projects/{pid}/angles/generate").json()
        client.post(f"/api/projects/{pid}/angles/{angles[0]['id']}/choose")
        with patch("backend.api.routes.projects.generate_story") as mock:
            mock.return_value = list(_MOCK_STORY_BLOCKS)
            client.post(f"/api/projects/{pid}/story/generate")
        with patch("backend.api.routes.projects.generate_scenes") as mock:
            mock.return_value = list(_MOCK_SCENES)
            scenes = client.post(f"/api/projects/{pid}/scenes/generate").json()
        return pid, scenes

    def test_reorder_scenes(self, client):
        pid, scenes = self._setup_with_scenes(client)
        original_ids = [s["id"] for s in sorted(scenes, key=lambda s: s["order"])]
        reversed_ids = list(reversed(original_ids))

        resp = client.patch(
            f"/api/projects/{pid}/scenes/reorder",
            json={"ordered_ids": reversed_ids},
        )
        assert resp.status_code == 200
        result_ids = [s["id"] for s in resp.json()]
        assert result_ids == reversed_ids
