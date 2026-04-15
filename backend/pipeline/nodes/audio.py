from backend.models.config import settings
from backend.pipeline.state import PipelineState
from backend.providers.audio_utils import get_audio_duration
from backend.providers.tts import get_tts_provider


def audio_node(state: PipelineState) -> dict:
    """LangGraph node: synthesize voiceover and measure duration."""
    if state.get("error"):
        return {}

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
