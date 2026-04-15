"""ProjectRepository — synchronous CRUD for projects, angles, story blocks, and scenes.

All methods accept a SQLAlchemy ``Session`` (sync) and are designed to be called
from pipeline nodes or background threads. FastAPI route handlers should wrap calls
in ``run_in_executor`` or use a sync-to-async bridge.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from backend.models.project import Angle, Project, Scene, StoryBlock


class ProjectRepository:
    # ------------------------------------------------------------------
    # Project CRUD
    # ------------------------------------------------------------------

    def create_project(
        self,
        session: Session,
        name: str,
        source_doc: str,
        target_duration_minutes: int = 5,
    ) -> Project:
        """Create and persist a new Project, return it."""
        project = Project(
            name=name,
            source_doc=source_doc,
            target_duration_minutes=target_duration_minutes,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return project

    def get_project(self, session: Session, project_id: str) -> Optional[Project]:
        """Return project by id or None."""
        return session.get(Project, project_id)

    def list_projects(self, session: Session) -> list[Project]:
        """Return all projects ordered by created_at descending."""
        stmt = select(Project).order_by(Project.created_at.desc())  # type: ignore[attr-defined]
        return list(session.exec(stmt).all())

    def update_project(self, session: Session, project_id: str, **kwargs) -> Project:
        """Update any subset of fields on a project.

        Raises ``ValueError`` if project not found.
        """
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project {project_id!r} not found")
        for key, value in kwargs.items():
            setattr(project, key, value)
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        session.refresh(project)
        return project

    def delete_project(self, session: Session, project_id: str) -> None:
        """Delete project and all its child rows (CASCADE handles children when FK pragma is on)."""
        project = session.get(Project, project_id)
        if project is None:
            return
        session.delete(project)
        session.commit()

    # ------------------------------------------------------------------
    # Angles
    # ------------------------------------------------------------------

    def set_angles(
        self, session: Session, project_id: str, angles: list[dict]
    ) -> list[Angle]:
        """Delete existing angles for project, insert new ones, return inserted list."""
        stmt = select(Angle).where(Angle.project_id == project_id)
        existing = list(session.exec(stmt).all())
        for a in existing:
            session.delete(a)
        session.flush()

        new_angles: list[Angle] = []
        for item in angles:
            angle = Angle(project_id=project_id, **item)
            session.add(angle)
            new_angles.append(angle)
        session.commit()
        for a in new_angles:
            session.refresh(a)
        return new_angles

    def choose_angle(
        self, session: Session, project_id: str, angle_id: str
    ) -> Angle:
        """Set chosen=True for angle_id, chosen=False for all others on that project."""
        stmt = select(Angle).where(Angle.project_id == project_id)
        all_angles = list(session.exec(stmt).all())
        chosen_angle: Optional[Angle] = None
        for angle in all_angles:
            if angle.id == angle_id:
                angle.chosen = True
                chosen_angle = angle
            else:
                angle.chosen = False
            session.add(angle)
        if chosen_angle is None:
            raise ValueError(f"Angle {angle_id!r} not found in project {project_id!r}")
        session.commit()
        session.refresh(chosen_angle)
        return chosen_angle

    # ------------------------------------------------------------------
    # Story blocks
    # ------------------------------------------------------------------

    def set_story_blocks(
        self, session: Session, project_id: str, blocks: list[dict]
    ) -> list[StoryBlock]:
        """Delete existing story blocks for project, insert new ones."""
        stmt = select(StoryBlock).where(StoryBlock.project_id == project_id)
        existing = list(session.exec(stmt).all())
        for b in existing:
            session.delete(b)
        session.flush()

        new_blocks: list[StoryBlock] = []
        for item in blocks:
            block = StoryBlock(project_id=project_id, **item)
            session.add(block)
            new_blocks.append(block)
        session.commit()
        for b in new_blocks:
            session.refresh(b)
        return new_blocks

    def reorder_story_blocks(
        self, session: Session, project_id: str, ordered_ids: list[str]
    ) -> list[StoryBlock]:
        """Update order field of each StoryBlock to match position in ordered_ids."""
        stmt = select(StoryBlock).where(StoryBlock.project_id == project_id)
        blocks_by_id = {b.id: b for b in session.exec(stmt).all()}
        for new_order, block_id in enumerate(ordered_ids):
            if block_id in blocks_by_id:
                blocks_by_id[block_id].order = new_order
                session.add(blocks_by_id[block_id])
        session.commit()
        # Return in new order
        result = [blocks_by_id[bid] for bid in ordered_ids if bid in blocks_by_id]
        for b in result:
            session.refresh(b)
        return result

    def update_story_block(
        self, session: Session, project_id: str, block_id: str, content: str
    ) -> StoryBlock:
        """Update content of a single story block."""
        block = session.get(StoryBlock, block_id)
        if block is None or block.project_id != project_id:
            raise ValueError(
                f"StoryBlock {block_id!r} not found in project {project_id!r}"
            )
        block.content = content
        session.add(block)
        session.commit()
        session.refresh(block)
        return block

    def delete_story_block(
        self, session: Session, project_id: str, block_id: str
    ) -> None:
        """Delete a single story block and renumber remaining blocks to fill the gap."""
        block = session.get(StoryBlock, block_id)
        if block is None or block.project_id != project_id:
            raise ValueError(
                f"StoryBlock {block_id!r} not found in project {project_id!r}"
            )
        session.delete(block)
        session.flush()

        # Renumber remaining blocks
        stmt = (
            select(StoryBlock)
            .where(StoryBlock.project_id == project_id)
            .order_by(StoryBlock.order)  # type: ignore[attr-defined]
        )
        remaining = list(session.exec(stmt).all())
        for idx, b in enumerate(remaining):
            b.order = idx
            session.add(b)
        session.commit()

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------

    def set_scenes(
        self, session: Session, project_id: str, scenes: list[dict]
    ) -> list[Scene]:
        """Delete existing scenes for project, insert new ones."""
        stmt = select(Scene).where(Scene.project_id == project_id)
        existing = list(session.exec(stmt).all())
        for s in existing:
            session.delete(s)
        session.flush()

        new_scenes: list[Scene] = []
        for item in scenes:
            scene = Scene(project_id=project_id, **item)
            session.add(scene)
            new_scenes.append(scene)
        session.commit()
        for s in new_scenes:
            session.refresh(s)
        return new_scenes

    def update_scene(
        self, session: Session, project_id: str, scene_id: str, **kwargs
    ) -> Scene:
        """Update any subset of fields on a single scene."""
        scene = session.get(Scene, scene_id)
        if scene is None or scene.project_id != project_id:
            raise ValueError(
                f"Scene {scene_id!r} not found in project {project_id!r}"
            )
        for key, value in kwargs.items():
            setattr(scene, key, value)
        session.add(scene)
        session.commit()
        session.refresh(scene)
        return scene

    def reorder_scenes(
        self, session: Session, project_id: str, ordered_ids: list[str]
    ) -> list[Scene]:
        """Update order field of each Scene to match position in ordered_ids."""
        stmt = select(Scene).where(Scene.project_id == project_id)
        scenes_by_id = {s.id: s for s in session.exec(stmt).all()}
        for new_order, scene_id in enumerate(ordered_ids):
            if scene_id in scenes_by_id:
                scenes_by_id[scene_id].order = new_order
                session.add(scenes_by_id[scene_id])
        session.commit()
        result = [scenes_by_id[sid] for sid in ordered_ids if sid in scenes_by_id]
        for s in result:
            session.refresh(s)
        return result

    def get_scenes(self, session: Session, project_id: str) -> list[Scene]:
        """Return all scenes for project ordered by order ascending."""
        stmt = (
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.order)  # type: ignore[attr-defined]
        )
        return list(session.exec(stmt).all())


# Module-level singleton
repo = ProjectRepository()
