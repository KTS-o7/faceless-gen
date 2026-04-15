import operator
import queue
from typing import Annotated, Any, Optional, TypedDict


class PipelineState(TypedDict):
    job_id: str
    user_prompt: str
    video_prompts: Annotated[list[str], operator.add]
    voiceover_script: str
    audio_path: Optional[str]
    audio_duration_seconds: Optional[float]
    image_paths: Annotated[list[str], operator.add]
    video_paths: Annotated[list[str], operator.add]
    scene_thumbnails: Annotated[list[str], operator.add]
    final_output: Optional[str]
    progress_log: Annotated[list[str], operator.add]
    error: Optional[str]
    progress_queue: Optional[Any]  # queue.Queue at runtime, Any for typing


def initial_state(
    job_id: str,
    user_prompt: str,
    progress_queue: Optional[Any] = None,
) -> PipelineState:
    """Return a fully initialized PipelineState with empty collections and None for optional fields."""
    return PipelineState(
        job_id=job_id,
        user_prompt=user_prompt,
        video_prompts=[],
        voiceover_script="",
        audio_path=None,
        audio_duration_seconds=None,
        image_paths=[],
        video_paths=[],
        scene_thumbnails=[],
        final_output=None,
        progress_log=[],
        error=None,
        progress_queue=progress_queue,
    )
