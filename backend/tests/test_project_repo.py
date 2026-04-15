"""Tests for ProjectRepository using an in-memory SQLite database.

All tests are synchronous (no asyncio) since the repo uses sync sessions.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel, Session

# Import all models so their metadata is registered before create_all
import backend.models.project  # noqa: F401
from backend.models.project import Angle, Project, ProjectStage, Scene, StoryBlock
from backend.storage.project_repo import ProjectRepository

repo = ProjectRepository()


@pytest.fixture()
def db_session():
    """Create in-memory SQLite engine, all tables, yield a Session, then drop all."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    # Enable FK enforcement so CASCADE deletes work
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def _make_project(session: Session, name: str = "Test Project") -> Project:
    return repo.create_project(
        session, name=name, source_doc="# Doc\nSome content.", target_duration_minutes=3
    )


# ---------------------------------------------------------------------------
# Project tests
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_create_and_read_back(self, db_session):
        project = _make_project(db_session)
        assert project.id is not None
        fetched = repo.get_project(db_session, project.id)
        assert fetched is not None
        assert fetched.name == "Test Project"
        assert fetched.target_duration_minutes == 3

    def test_default_stage_is_angle_selection(self, db_session):
        project = _make_project(db_session)
        assert project.stage == ProjectStage.angle_selection

    def test_created_at_is_set(self, db_session):
        from datetime import datetime
        project = _make_project(db_session)
        assert isinstance(project.created_at, datetime)


class TestGetProject:
    def test_returns_none_for_missing(self, db_session):
        result = repo.get_project(db_session, "nonexistent-id")
        assert result is None


class TestListProjects:
    def test_returns_newest_first(self, db_session):
        import time
        p1 = _make_project(db_session, name="First")
        time.sleep(0.01)  # ensure different timestamps
        p2 = _make_project(db_session, name="Second")
        projects = repo.list_projects(db_session)
        assert len(projects) == 2
        # Newest first
        assert projects[0].name == "Second"
        assert projects[1].name == "First"

    def test_empty_returns_empty_list(self, db_session):
        assert repo.list_projects(db_session) == []


class TestUpdateProject:
    def test_update_name(self, db_session):
        project = _make_project(db_session)
        updated = repo.update_project(db_session, project.id, name="New Name")
        assert updated.name == "New Name"

    def test_update_stage(self, db_session):
        project = _make_project(db_session)
        updated = repo.update_project(db_session, project.id, stage=ProjectStage.done)
        assert updated.stage == ProjectStage.done

    def test_raises_for_missing_project(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            repo.update_project(db_session, "bad-id", name="x")

    def test_updated_at_changes(self, db_session):
        import time
        project = _make_project(db_session)
        original_updated_at = project.updated_at
        time.sleep(0.01)
        updated = repo.update_project(db_session, project.id, name="Changed")
        assert updated.updated_at >= original_updated_at


class TestDeleteProject:
    def test_delete_removes_project(self, db_session):
        project = _make_project(db_session)
        repo.delete_project(db_session, project.id)
        assert repo.get_project(db_session, project.id) is None

    def test_delete_cascades_to_angles(self, db_session):
        project = _make_project(db_session)
        repo.set_angles(
            db_session,
            project.id,
            [{"order": 0, "title": "A1", "pitch": "p1"}],
        )
        repo.delete_project(db_session, project.id)
        from sqlmodel import select
        angles = list(db_session.exec(select(Angle)).all())
        assert angles == []

    def test_delete_cascades_to_story_blocks(self, db_session):
        project = _make_project(db_session)
        repo.set_story_blocks(
            db_session, project.id, [{"order": 0, "content": "block"}]
        )
        repo.delete_project(db_session, project.id)
        from sqlmodel import select
        blocks = list(db_session.exec(select(StoryBlock)).all())
        assert blocks == []

    def test_delete_cascades_to_scenes(self, db_session):
        project = _make_project(db_session)
        repo.set_scenes(
            db_session,
            project.id,
            [
                {
                    "order": 0,
                    "title": "S1",
                    "dialog": "d",
                    "image_prompt": "ip",
                    "video_prompt": "vp",
                }
            ],
        )
        repo.delete_project(db_session, project.id)
        from sqlmodel import select
        scenes = list(db_session.exec(select(Scene)).all())
        assert scenes == []

    def test_delete_nonexistent_is_noop(self, db_session):
        # Should not raise
        repo.delete_project(db_session, "nonexistent")


# ---------------------------------------------------------------------------
# Angle tests
# ---------------------------------------------------------------------------


class TestSetAngles:
    def test_inserts_angles(self, db_session):
        project = _make_project(db_session)
        angles = repo.set_angles(
            db_session,
            project.id,
            [
                {"order": 0, "title": "A1", "pitch": "p1"},
                {"order": 1, "title": "A2", "pitch": "p2"},
            ],
        )
        assert len(angles) == 2
        assert angles[0].title == "A1"

    def test_replaces_existing_angles(self, db_session):
        project = _make_project(db_session)
        repo.set_angles(
            db_session, project.id, [{"order": 0, "title": "Old", "pitch": "op"}]
        )
        angles = repo.set_angles(
            db_session, project.id, [{"order": 0, "title": "New", "pitch": "np"}]
        )
        assert len(angles) == 1
        assert angles[0].title == "New"


class TestChooseAngle:
    def test_sets_chosen_true_and_others_false(self, db_session):
        project = _make_project(db_session)
        angles = repo.set_angles(
            db_session,
            project.id,
            [
                {"order": 0, "title": "A1", "pitch": "p1"},
                {"order": 1, "title": "A2", "pitch": "p2"},
            ],
        )
        chosen = repo.choose_angle(db_session, project.id, angles[0].id)
        assert chosen.chosen is True
        # The second angle should now be False
        from sqlmodel import select
        all_angles = list(db_session.exec(select(Angle).where(Angle.project_id == project.id)).all())
        not_chosen = [a for a in all_angles if a.id != angles[0].id]
        assert all(not a.chosen for a in not_chosen)

    def test_choose_angle_unsets_previous_chosen(self, db_session):
        project = _make_project(db_session)
        angles = repo.set_angles(
            db_session,
            project.id,
            [
                {"order": 0, "title": "A1", "pitch": "p1"},
                {"order": 1, "title": "A2", "pitch": "p2"},
            ],
        )
        # Choose first
        repo.choose_angle(db_session, project.id, angles[0].id)
        # Switch to second
        chosen = repo.choose_angle(db_session, project.id, angles[1].id)
        assert chosen.chosen is True
        # First is no longer chosen
        first = db_session.get(Angle, angles[0].id)
        assert first.chosen is False

    def test_raises_for_unknown_angle(self, db_session):
        project = _make_project(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.choose_angle(db_session, project.id, "bad-angle-id")


# ---------------------------------------------------------------------------
# StoryBlock tests
# ---------------------------------------------------------------------------


class TestSetStoryBlocks:
    def test_inserts_blocks(self, db_session):
        project = _make_project(db_session)
        blocks = repo.set_story_blocks(
            db_session,
            project.id,
            [{"order": 0, "content": "Intro"}, {"order": 1, "content": "Body"}],
        )
        assert len(blocks) == 2

    def test_replaces_existing_blocks(self, db_session):
        project = _make_project(db_session)
        repo.set_story_blocks(db_session, project.id, [{"order": 0, "content": "Old"}])
        blocks = repo.set_story_blocks(
            db_session, project.id, [{"order": 0, "content": "New"}]
        )
        assert len(blocks) == 1
        assert blocks[0].content == "New"


class TestReorderStoryBlocks:
    def test_reorder_correctly_flips_order(self, db_session):
        project = _make_project(db_session)
        blocks = repo.set_story_blocks(
            db_session,
            project.id,
            [{"order": 0, "content": "First"}, {"order": 1, "content": "Second"}],
        )
        # Reverse order
        reversed_ids = [blocks[1].id, blocks[0].id]
        reordered = repo.reorder_story_blocks(db_session, project.id, reversed_ids)
        assert reordered[0].content == "Second"
        assert reordered[0].order == 0
        assert reordered[1].content == "First"
        assert reordered[1].order == 1


class TestUpdateStoryBlock:
    def test_updates_content(self, db_session):
        project = _make_project(db_session)
        blocks = repo.set_story_blocks(
            db_session, project.id, [{"order": 0, "content": "Original"}]
        )
        updated = repo.update_story_block(
            db_session, project.id, blocks[0].id, "Updated"
        )
        assert updated.content == "Updated"

    def test_raises_for_missing_block(self, db_session):
        project = _make_project(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.update_story_block(db_session, project.id, "bad-id", "x")


class TestDeleteStoryBlock:
    def test_deletes_and_renumbers(self, db_session):
        project = _make_project(db_session)
        blocks = repo.set_story_blocks(
            db_session,
            project.id,
            [
                {"order": 0, "content": "A"},
                {"order": 1, "content": "B"},
                {"order": 2, "content": "C"},
            ],
        )
        # Delete middle block
        repo.delete_story_block(db_session, project.id, blocks[1].id)
        from sqlmodel import select
        remaining = list(
            db_session.exec(
                select(StoryBlock)
                .where(StoryBlock.project_id == project.id)
                .order_by(StoryBlock.order)
            ).all()
        )
        assert len(remaining) == 2
        assert remaining[0].content == "A"
        assert remaining[0].order == 0
        assert remaining[1].content == "C"
        assert remaining[1].order == 1

    def test_raises_for_missing_block(self, db_session):
        project = _make_project(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.delete_story_block(db_session, project.id, "bad-id")


# ---------------------------------------------------------------------------
# Scene tests
# ---------------------------------------------------------------------------


def _scene_data(order: int, title: str = "Scene") -> dict:
    return {
        "order": order,
        "title": title,
        "dialog": "Some dialog.",
        "image_prompt": "An image.",
        "video_prompt": "A video.",
    }


class TestSetScenes:
    def test_inserts_scenes(self, db_session):
        project = _make_project(db_session)
        scenes = repo.set_scenes(
            db_session,
            project.id,
            [_scene_data(0, "S1"), _scene_data(1, "S2")],
        )
        assert len(scenes) == 2

    def test_replaces_existing_scenes(self, db_session):
        project = _make_project(db_session)
        repo.set_scenes(db_session, project.id, [_scene_data(0, "Old")])
        scenes = repo.set_scenes(db_session, project.id, [_scene_data(0, "New")])
        assert len(scenes) == 1
        assert scenes[0].title == "New"


class TestUpdateScene:
    def test_update_image_path(self, db_session):
        project = _make_project(db_session)
        scenes = repo.set_scenes(db_session, project.id, [_scene_data(0)])
        updated = repo.update_scene(
            db_session, project.id, scenes[0].id, image_path="/tmp/img.png"
        )
        assert updated.image_path == "/tmp/img.png"

    def test_update_audio_duration_seconds(self, db_session):
        project = _make_project(db_session)
        scenes = repo.set_scenes(db_session, project.id, [_scene_data(0)])
        updated = repo.update_scene(
            db_session, project.id, scenes[0].id, audio_duration_seconds=3.14
        )
        assert abs(updated.audio_duration_seconds - 3.14) < 1e-6

    def test_raises_for_missing_scene(self, db_session):
        project = _make_project(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.update_scene(db_session, project.id, "bad-id", title="x")


class TestReorderScenes:
    def test_reorder_scenes(self, db_session):
        project = _make_project(db_session)
        scenes = repo.set_scenes(
            db_session,
            project.id,
            [_scene_data(0, "First"), _scene_data(1, "Second")],
        )
        reversed_ids = [scenes[1].id, scenes[0].id]
        reordered = repo.reorder_scenes(db_session, project.id, reversed_ids)
        assert reordered[0].title == "Second"
        assert reordered[0].order == 0
        assert reordered[1].title == "First"
        assert reordered[1].order == 1


class TestGetScenes:
    def test_returns_ordered_by_order_asc(self, db_session):
        project = _make_project(db_session)
        repo.set_scenes(
            db_session,
            project.id,
            [_scene_data(1, "B"), _scene_data(0, "A")],  # inserted out of order
        )
        scenes = repo.get_scenes(db_session, project.id)
        assert scenes[0].title == "A"
        assert scenes[1].title == "B"

    def test_returns_empty_for_no_scenes(self, db_session):
        project = _make_project(db_session)
        assert repo.get_scenes(db_session, project.id) == []
