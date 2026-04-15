"""Pydantic request and response schemas for the project API.

Kept separate from SQLModel table definitions in project.py.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.models.project import Angle, Project, ProjectStage, Scene, StoryBlock


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    source_doc: str = Field(..., min_length=100)
    target_duration_minutes: int = Field(default=5, ge=1, le=30)


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    stage: Optional[str] = None
    aspect_ratio: Optional[str] = None
    music_track: Optional[str] = None


class ReorderRequest(BaseModel):
    ordered_ids: list[str] = Field(..., min_length=1)


class UpdateStoryBlockRequest(BaseModel):
    content: str = Field(..., min_length=1)


class UpdateSceneRequest(BaseModel):
    title: Optional[str] = None
    dialog: Optional[str] = None
    image_prompt: Optional[str] = None
    video_prompt: Optional[str] = None


class ChooseAngleRequest(BaseModel):
    angle_id: str


class RegenerateFieldRequest(BaseModel):
    field_name: Literal["image_prompt", "video_prompt"]
    story_context: str = ""
    source_doc_excerpt: str = ""


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AngleResponse(BaseModel):
    id: str
    order: int
    title: str
    pitch: str
    chosen: bool

    model_config = {"from_attributes": True}


class StoryBlockResponse(BaseModel):
    id: str
    order: int
    content: str

    model_config = {"from_attributes": True}


class SceneResponse(BaseModel):
    id: str
    order: int
    title: str
    dialog: str
    image_prompt: str
    video_prompt: str
    audio_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    image_path: Optional[str] = None
    audio_duration_seconds: Optional[float] = None

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: str
    name: str
    stage: str
    target_duration_minutes: int
    aspect_ratio: Optional[str] = None
    music_track: Optional[str] = None
    active_job_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    source_doc: str
    final_output_path: Optional[str] = None
    error: Optional[str] = None
    angles: list[AngleResponse] = []
    story_blocks: list[StoryBlockResponse] = []
    scenes: list[SceneResponse] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helper conversion functions
# ---------------------------------------------------------------------------


def angle_to_response(angle: Angle) -> AngleResponse:
    return AngleResponse(
        id=angle.id,
        order=angle.order,
        title=angle.title,
        pitch=angle.pitch,
        chosen=angle.chosen,
    )


def story_block_to_response(block: StoryBlock) -> StoryBlockResponse:
    return StoryBlockResponse(
        id=block.id,
        order=block.order,
        content=block.content,
    )


def scene_to_response(scene: Scene) -> SceneResponse:
    return SceneResponse(
        id=scene.id,
        order=scene.order,
        title=scene.title,
        dialog=scene.dialog,
        image_prompt=scene.image_prompt,
        video_prompt=scene.video_prompt,
        audio_path=scene.audio_path,
        video_clip_path=scene.video_clip_path,
        thumbnail_path=scene.thumbnail_path,
        image_path=scene.image_path,
        audio_duration_seconds=scene.audio_duration_seconds,
    )


def project_to_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        stage=project.stage,
        target_duration_minutes=project.target_duration_minutes,
        aspect_ratio=project.aspect_ratio,
        music_track=project.music_track,
        active_job_id=project.active_job_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def project_to_detail(
    project: Project,
    angles: list[Angle],
    story_blocks: list[StoryBlock],
    scenes: list[Scene],
) -> ProjectDetail:
    return ProjectDetail(
        id=project.id,
        name=project.name,
        stage=project.stage,
        target_duration_minutes=project.target_duration_minutes,
        aspect_ratio=project.aspect_ratio,
        music_track=project.music_track,
        active_job_id=project.active_job_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        source_doc=project.source_doc,
        final_output_path=project.final_output_path,
        error=project.error,
        angles=[angle_to_response(a) for a in angles],
        story_blocks=[story_block_to_response(b) for b in story_blocks],
        scenes=[scene_to_response(s) for s in scenes],
    )
