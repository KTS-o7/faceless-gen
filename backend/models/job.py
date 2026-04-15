from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class Job(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    job_id: str
    status: JobStatus = JobStatus.pending
    user_prompt: str
    progress_log: list[str] = Field(default_factory=list)
    final_output: Optional[str] = None
    scene_thumbnails: list[str] = Field(default_factory=list)
    video_paths: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
