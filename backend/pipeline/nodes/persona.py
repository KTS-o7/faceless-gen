"""Persona loading node for the project-based pipeline."""
from backend.pipeline.state import PipelineState
from backend.pipeline.editorial import _load_persona


def load_persona_node(state: PipelineState) -> dict:
    """Load the active persona and inject it into state."""
    if state.get("error"):
        return {}
    try:
        persona = _load_persona()
        return {
            "persona": persona,
            "progress_log": ["load_persona_node: persona loaded"],
        }
    except FileNotFoundError as e:
        return {"error": f"load_persona_node: Persona files missing: {e}"}
