"""SQLModel table definitions for video projects."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, SQLModel


class ProjectStage(str, Enum):
    angle_selection = "angle_selection"
    story_editing = "story_editing"
    scene_editing = "scene_editing"
    music_selection = "music_selection"
    generating = "generating"
    done = "done"
    failed = "failed"


class AspectRatio(str, Enum):
    widescreen = "16:9"
    portrait = "9:16"
    square = "1:1"


class Project(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    name: str
    source_doc: str
    target_duration_minutes: int = 5
    stage: str = ProjectStage.angle_selection
    aspect_ratio: Optional[str] = None
    music_track: Optional[str] = None
    final_output_path: Optional[str] = None
    error: Optional[str] = None
    active_job_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class Angle(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    project_id: str = Field(
        sa_column=Column(String, ForeignKey("project.id", ondelete="CASCADE"))
    )
    order: int
    title: str
    pitch: str
    chosen: bool = False


class StoryBlock(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    project_id: str = Field(
        sa_column=Column(String, ForeignKey("project.id", ondelete="CASCADE"))
    )
    order: int
    content: str


class Scene(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    project_id: str = Field(
        sa_column=Column(String, ForeignKey("project.id", ondelete="CASCADE"))
    )
    order: int
    title: str
    dialog: str
    image_prompt: str
    video_prompt: str
    image_path: Optional[str] = None
    audio_path: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    video_clip_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
