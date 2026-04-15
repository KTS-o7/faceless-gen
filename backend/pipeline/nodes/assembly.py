import logging
import subprocess
from pathlib import Path

from movielite import AudioClip, VideoClip, VideoWriter

from backend.models.config import settings
from backend.pipeline.state import PipelineState
from backend.providers.audio_utils import get_audio_duration

logger = logging.getLogger(__name__)

_MUSIC_DIR = Path(__file__).parent.parent.parent / "assets" / "music"


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


def _mix_music(assembled_path: str, music_path: str, output_path: str) -> str:
    """Mix music track at -18dB under the assembled video's audio. Returns output_path."""
    cmd = [
        "ffmpeg", "-y",
        "-i", assembled_path,
        "-stream_loop", "-1",
        "-i", music_path,
        "-filter_complex",
        "[1:a]volume=-18dB[music];[0:a][music]amix=inputs=2:duration=first[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def assembly_node(state: PipelineState) -> dict:
    """LangGraph node: sync clip durations and assemble final video via MovieLite."""
    if state.get("error"):
        return {}

    # --- Project-based mode ---
    if state.get("project_id") and state.get("scenes"):
        return _assembly_node_project(state)

    # --- Legacy prompt mode ---
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


def _assembly_node_project(state: PipelineState) -> dict:
    """Handle project-based assembly with per-scene duration sync and optional music."""
    from backend.storage.database import get_sync_session
    from backend.storage.project_repo import repo

    project_id = state["project_id"]
    scenes = state["scenes"]

    output_dir = Path(settings.outputs_dir) / project_id
    output_dir.mkdir(parents=True, exist_ok=True)

    sorted_scenes = sorted(scenes, key=lambda s: s["order"])
    video_paths = [s.get("video_clip_path", "") for s in sorted_scenes]

    progress_entries: list[str] = []

    # Per-scene duration sync using per-scene audio_duration_seconds
    synced_paths: list[str] = []
    for i, (scene, clip_path) in enumerate(zip(sorted_scenes, video_paths)):
        target_duration = scene.get("audio_duration_seconds")
        if target_duration and target_duration > 0:
            try:
                synced = _sync_clip_duration(clip_path, target_duration)
                synced_paths.append(synced)
                progress_entries.append(
                    f"assembly_node: synced clip {i:02d} to {target_duration:.1f}s"
                )
            except Exception as exc:
                return {
                    "error": f"assembly_node: duration sync failed for clip {i:02d}: {exc}",
                    "progress_log": progress_entries,
                }
        else:
            synced_paths.append(clip_path)

    # Assemble via MovieLite
    assembled_path = str(output_dir / "assembled.mp4")
    final_path = str(output_dir / "final.mp4")

    clips: list = []
    try:
        current_start = 0.0
        for path in synced_paths:
            clip = VideoClip(path, start=current_start)
            clips.append(clip)
            current_start += clip.duration

        # Use per-scene audio — combine all scene audio clips
        writer = VideoWriter(assembled_path, fps=30)
        writer.add_clips(clips)

        # Add per-scene audio clips
        audio_start = 0.0
        for scene in sorted_scenes:
            ap = scene.get("audio_path")
            dur = scene.get("audio_duration_seconds", 0.0) or 0.0
            if ap:
                audio_clip = AudioClip(ap, start=audio_start)
                writer.add_clip(audio_clip)
            audio_start += dur

        writer.write()
        progress_entries.append(f"assembly_node: assembled clips → {assembled_path}")

    except Exception as exc:
        return {"error": f"assembly_node error: {exc}", "progress_log": progress_entries}
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    # Music mixing
    music_track = state.get("music_track")
    if music_track:
        music_file = _MUSIC_DIR / music_track
        if music_file.exists():
            try:
                _mix_music(assembled_path, str(music_file), final_path)
                progress_entries.append(
                    f"assembly_node: mixed music track '{music_track}' at -18dB → {final_path}"
                )
            except Exception as exc:
                # Log warning but don't fail — use assembled without music
                logger.warning("assembly_node: music mixing failed: %s", exc)
                progress_entries.append(
                    f"assembly_node: music mixing failed ({exc}), using assembled without music"
                )
                import shutil
                shutil.copy2(assembled_path, final_path)
        else:
            logger.warning("assembly_node: music file not found: %s", music_file)
            progress_entries.append(
                f"assembly_node: music file '{music_track}' not found, skipping music"
            )
            import shutil
            shutil.copy2(assembled_path, final_path)
    else:
        import shutil
        shutil.copy2(assembled_path, final_path)

    # Persist final output path to DB
    try:
        with get_sync_session() as session:
            repo.update_project(session, project_id, final_output_path=str(Path(final_path).resolve()))
    except Exception as db_exc:
        progress_entries.append(f"assembly_node: DB update warning: {db_exc}")

    assembly_msg = f"assembly_node: final video → {final_path}"
    progress_entries.append(assembly_msg)
    if state.get("progress_queue") is not None:
        state["progress_queue"].put(assembly_msg)

    return {
        "final_output": str(Path(final_path).resolve()),
        "progress_log": progress_entries,
    }
