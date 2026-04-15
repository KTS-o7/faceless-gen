import logging
import subprocess
from pathlib import Path

from movielite import AudioClip, VideoClip, VideoWriter

from backend.models.config import settings
from backend.pipeline.state import PipelineState
from backend.providers.audio_utils import get_audio_duration

logger = logging.getLogger(__name__)


def _get_video_duration(video_path: str) -> float:
    """Return the duration of a video file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {video_path}: {result.stderr.strip()}"
        )
    return float(result.stdout.strip())


def _sync_clip_duration(clip_path: str, target_duration: float) -> str:
    """
    Pad or trim a video clip so its duration matches target_duration.

    Returns the path to the (possibly modified) clip.
    """
    video_duration = _get_video_duration(clip_path)
    gap = target_duration - video_duration

    if abs(gap) < 0.05:
        # Already close enough
        return clip_path

    base = Path(clip_path)
    if gap > 0:
        # Video is shorter than audio — freeze last frame
        synced_path = str(base.parent / f"{base.stem}_padded{base.suffix}")
        cmd = [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-vf", f"tpad=stop_mode=clone:stop_duration={gap:.4f}",
            synced_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return synced_path
    else:
        # Video is longer than audio — trim
        synced_path = str(base.parent / f"{base.stem}_trimmed{base.suffix}")
        cmd = [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-t", f"{target_duration:.4f}",
            synced_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return synced_path


def assembly_node(state: PipelineState) -> dict:
    """LangGraph node: sync clip durations and assemble final video via MovieLite."""
    if state.get("error"):
        return {}

    video_paths = list(state.get("video_paths", []))
    audio_path = state.get("audio_path")
    audio_duration = state.get("audio_duration_seconds")
    job_id = state["job_id"]

    output_dir = Path(settings.outputs_dir) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / "final.mp4")

    # Per-clip duration sync
    synced_paths: list[str] = []
    if audio_duration is not None:
        per_clip_duration = audio_duration / max(len(video_paths), 1)
        for clip_path in video_paths:
            try:
                synced = _sync_clip_duration(clip_path, per_clip_duration)
                synced_paths.append(synced)
            except Exception as exc:
                return {"error": f"assembly_node: duration sync failed for {clip_path}: {exc}"}
    else:
        synced_paths = video_paths

    clips: list = []
    try:
        # Build sequentially chained clips
        current_start = 0.0
        for path in synced_paths:
            clip = VideoClip(path, start=current_start)
            clips.append(clip)
            current_start += clip.duration

        writer = VideoWriter(output_path, fps=30)
        writer.add_clips(clips)

        if audio_path:
            audio_clip = AudioClip(audio_path, start=0)
            writer.add_clip(audio_clip)

        writer.write()

    except Exception as exc:
        return {"error": f"assembly_node error: {exc}"}
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    assembly_msg = f"assembly_node: assembled final video → {output_path}"
    if state.get("progress_queue") is not None:
        state["progress_queue"].put(assembly_msg)
    return {
        "final_output": str(Path(output_path).resolve()),
        "progress_log": [assembly_msg],
    }
