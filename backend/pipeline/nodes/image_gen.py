import logging
from pathlib import Path

from backend.models.config import settings
from backend.pipeline.editorial import STYLE_CONSTRAINTS
from backend.pipeline.state import PipelineState
from backend.providers.image_backend import get_image_backend

logger = logging.getLogger(__name__)


def image_gen_node(state: PipelineState) -> dict:
    """LangGraph node: generate one image per video prompt via ComfyUI."""
    if state.get("error"):
        return {}

    personas_dir = settings.personas_dir
    persona = settings.active_persona
    persona_dir = Path(personas_dir) / persona

    seed_image_path = persona_dir / "seed.png"
    if not seed_image_path.exists():
        return {
            "error": (
                f"image_gen_node: seed.png not found at {seed_image_path}. "
                "Please add a seed image for the active persona."
            )
        }

    # Load character visual description
    char_md_path = persona_dir / "character.md"
    char_description = ""
    if char_md_path.exists():
        char_description = char_md_path.read_text().strip()[:500]

    backend = get_image_backend()
    job_id = state["job_id"]
    output_base = Path(settings.outputs_dir) / job_id
    output_base.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    progress_entries: list[str] = []

    for n, prompt in enumerate(state.get("video_prompts", [])):
        if char_description:
            full_prompt = f"{char_description}. {prompt}"
        else:
            full_prompt = prompt

        output_path = str(output_base / f"scene_{n:02d}.png")

        try:
            saved_path = backend.generate_image(
                prompt=full_prompt,
                seed_image_path=str(seed_image_path),
                output_path=output_path,
            )
            image_paths.append(saved_path)
            progress_entries.append(f"image_gen_node: scene {n:02d} → {saved_path}")
        except Exception as exc:
            return {
                "error": f"image_gen_node: failed on scene {n:02d}: {exc}",
                "image_paths": image_paths,
                "progress_log": progress_entries,
            }

    return {
        "image_paths": image_paths,
        "progress_log": progress_entries,
    }
