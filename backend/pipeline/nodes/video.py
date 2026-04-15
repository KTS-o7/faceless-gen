import logging
import subprocess
from pathlib import Path

from backend.models.config import settings
from backend.pipeline.state import PipelineState
from backend.providers.video_backend import get_video_backend

logger = logging.getLogger(__name__)


def _extract_thumbnail(video_path: str, thumbnail_path: str) -> None:
    """Extract the first frame of a video as a JPEG thumbnail via ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        thumbnail_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def video_node(state: PipelineState) -> dict:
    """LangGraph node: generate one video clip per scene using the video backend."""
    if state.get("error"):
        return {}

    image_paths = state.get("image_paths", [])
    if not image_paths:
        return {"error": "video_node: image_paths is empty — image_gen_node must run first"}

    backend = get_video_backend()
    job_id = state["job_id"]
    output_base = Path(settings.outputs_dir) / job_id
    output_base.mkdir(parents=True, exist_ok=True)

    video_paths: list[str] = []
    scene_thumbnails: list[str] = []
    progress_entries: list[str] = []

    video_prompts = state.get("video_prompts", [])

    for n, (prompt, image_path) in enumerate(zip(video_prompts, image_paths)):
        clip_path = str(output_base / f"clip_{n:02d}.mp4")
        thumb_path = str(output_base / f"thumb_{n:02d}.jpg")

        try:
            saved_path = backend.generate_clip(
                prompt=prompt,
                first_frame_image_path=image_path,
                output_path=clip_path,
            )
            video_paths.append(saved_path)
            clip_msg = f"video_node: clip {n:02d} → {saved_path}"
            progress_entries.append(clip_msg)
            if state.get("progress_queue") is not None:
                state["progress_queue"].put(clip_msg)

            # Extract thumbnail
            _extract_thumbnail(saved_path, thumb_path)
            scene_thumbnails.append(thumb_path)
            thumb_msg = f"video_node: thumbnail {n:02d} → {thumb_path}"
            progress_entries.append(thumb_msg)
            if state.get("progress_queue") is not None:
                state["progress_queue"].put(thumb_msg)

        except Exception as exc:
            return {
                "error": f"video_node: failed on clip {n:02d}: {exc}",
                "video_paths": video_paths,
                "scene_thumbnails": scene_thumbnails,
                "progress_log": progress_entries,
            }

    return {
        "video_paths": video_paths,
        "scene_thumbnails": scene_thumbnails,
        "progress_log": progress_entries,
    }
