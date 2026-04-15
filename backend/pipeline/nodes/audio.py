from pathlib import Path

from backend.models.config import settings
from backend.pipeline.state import PipelineState
from backend.providers.audio_utils import get_audio_duration
from backend.providers.tts import get_tts_provider


def audio_node(state: PipelineState) -> dict:
    """LangGraph node: synthesize voiceover and measure duration."""
    if state.get("error"):
        return {}

    # --- Project-based mode: per-scene TTS ---
    if state.get("project_id") and state.get("scenes"):
        return _audio_node_project(state)

    # --- Legacy prompt mode ---
    output_dir = str(settings.outputs_dir / state["job_id"])

    try:
        provider = get_tts_provider()
        audio_path = provider.synthesize(state["voiceover_script"], output_dir)
        duration = get_audio_duration(audio_path)

        updates: dict = {
            "audio_path": audio_path,
            "audio_duration_seconds": duration,
            "progress_log": [f"audio_node: synthesized audio → {audio_path} ({duration:.1f}s)"],
        }

        # Put progress update to queue if available
        q = state.get("progress_queue")
        if q is not None:
            try:
                q.put_nowait(f"audio_node: synthesized {duration:.1f}s of audio")
            except Exception:
                pass

        return updates

    except Exception as exc:
        return {"error": f"audio_node error: {exc}"}


def _audio_node_project(state: PipelineState) -> dict:
    """Handle per-scene TTS synthesis in project mode."""
    from backend.storage.database import get_sync_session
    from backend.storage.project_repo import repo

    project_id = state["project_id"]
    scenes = state["scenes"]
    output_dir = settings.outputs_dir / project_id
    output_dir.mkdir(parents=True, exist_ok=True)

    provider = get_tts_provider()

    # Use persona voice_id if available
    persona = state.get("persona") or {}
    voice_id = persona.get("voice_id") or getattr(settings, "elevenlabs_voice_id", None)

    progress_entries: list[str] = []
    total_duration = 0.0
    first_audio_path: str | None = None

    sorted_scenes = sorted(scenes, key=lambda s: s["order"])

    for i, scene in enumerate(sorted_scenes):
        try:
            audio_path = provider.synthesize(
                scene["dialog"],
                str(output_dir),
                filename=f"audio_{scene['order']:02d}.mp3",
            )
        except TypeError:
            # Fallback if provider.synthesize doesn't accept filename kwarg
            audio_path = provider.synthesize(scene["dialog"], str(output_dir))

        duration = get_audio_duration(audio_path)
        total_duration += duration

        # Update scene dict in state
        scene["audio_path"] = audio_path
        scene["audio_duration_seconds"] = duration

        # Persist to DB
        try:
            with get_sync_session() as session:
                repo.update_scene(
                    session,
                    project_id,
                    scene["id"],
                    audio_path=audio_path,
                    audio_duration_seconds=duration,
                )
        except Exception as db_exc:
            progress_entries.append(f"audio_node: DB update warning for scene {i}: {db_exc}")

        msg = f"audio_node: scene {i:02d} → {audio_path} ({duration:.1f}s)"
        progress_entries.append(msg)
        q = state.get("progress_queue")
        if q is not None:
            try:
                q.put_nowait(msg)
            except Exception:
                pass

        if first_audio_path is None:
            first_audio_path = audio_path

    return {
        "scenes": sorted_scenes,
        "audio_path": first_audio_path,
        "audio_duration_seconds": total_duration,
        "progress_log": progress_entries,
    }
