"""
Editorial LLM functions for faceless-gen video pipeline.

Provides four synchronous LangChain functions called from FastAPI route handlers:
- generate_angles: produce 3 story angle options from a source document
- generate_story: write narration story blocks for a chosen angle
- generate_scenes: break story into scene descriptions with image/video prompts
- regenerate_field: regenerate a single field (image_prompt or video_prompt) for a scene

STYLE_CONSTRAINTS is the single source of truth for the visual style that must
be applied to every generated image and video clip.
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from backend.models.config import settings
from backend.providers.llm import get_llm

STYLE_CONSTRAINTS = (
    "flat 2D vector art, unshaded, solid #FFFFFF white background, "
    "black lines, zero shadows, minimal character motion, zero camera movement"
)

# Module-level persona cache — populated on first call to _load_persona()
_persona_cache: dict = {}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """Strip whitespace and optional markdown fences, then parse JSON.

    Raises ValueError with up to 300 chars of the raw content on failure.
    """
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse JSON response: {exc}. "
            f"Raw content (first 300 chars): {raw[:300]!r}"
        ) from exc


def _build_system_prompt(instructions: str) -> str:
    """Wrap instructions with a consistent JSON-only preamble."""
    preamble = (
        "You are a helpful assistant. "
        "Output ONLY valid JSON. "
        "No prose, no markdown fences, no explanation outside the JSON object."
    )
    return f"{preamble}\n\n{instructions}"


def _load_persona() -> dict:
    """Load the active persona files, caching after first read.

    Returns a dict with keys: personality, character, voice_id.
    Raises FileNotFoundError if personality.md or character.md is missing.
    """
    global _persona_cache
    if _persona_cache:
        return _persona_cache

    persona_dir = settings.personas_dir / settings.active_persona

    personality_path = persona_dir / "personality.md"
    if not personality_path.exists():
        raise FileNotFoundError(
            f"Persona personality.md not found at: {personality_path}"
        )

    character_path = persona_dir / "character.md"
    if not character_path.exists():
        raise FileNotFoundError(
            f"Persona character.md not found at: {character_path}"
        )

    personality_raw = personality_path.read_text(encoding="utf-8")
    character_content = character_path.read_text(encoding="utf-8")

    # Parse Voice-ID from first line: "Voice-ID: <id>"
    lines = personality_raw.splitlines()
    voice_id = None
    personality_lines = lines
    if lines and lines[0].startswith("Voice-ID:"):
        voice_id = lines[0].split(":", 1)[1].strip()
        personality_lines = lines[1:]

    personality_content = "\n".join(personality_lines).strip()

    _persona_cache = {
        "personality": personality_content,
        "character": character_content,
        "voice_id": voice_id,
    }
    return _persona_cache


def _truncate_doc(doc: str, max_chars: int = 12000) -> str:
    """Truncate doc to max_chars and append a truncation notice if needed."""
    if len(doc) > max_chars:
        return doc[:max_chars] + "\n\n[Document truncated for context window]"
    return doc


# ---------------------------------------------------------------------------
# Public LLM functions
# ---------------------------------------------------------------------------

def generate_angles(source_doc: str, target_duration_minutes: int) -> list[dict]:
    """Generate exactly 3 story angle options from a source document.

    Returns a list of 3 dicts, each with 'title' and 'pitch' keys.
    Raises ValueError if the LLM response does not contain exactly 3 valid angles.
    """
    persona = _load_persona()
    truncated_doc = _truncate_doc(source_doc)

    instructions = (
        f"You are a video scriptwriter for a channel with this narration persona:\n"
        f"{persona['personality']}\n\n"
        "Read the provided source document and return exactly 3 story angle options.\n"
        "Each angle must have:\n"
        "  - title: 3–6 words\n"
        "  - pitch: exactly 2 sentences — what the angle covers and why it's compelling.\n\n"
        'Return JSON in this exact shape: {"angles": [{"title": "...", "pitch": "..."}, ...]}'
    )
    system_prompt = _build_system_prompt(instructions)

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Source document:\n{truncated_doc}\n\n"
                f"Target duration: {target_duration_minutes} minutes"
            )
        ),
    ])

    data = _parse_json_response(response.content)
    angles = data.get("angles", [])

    if len(angles) != 3:
        raise ValueError(
            f"Expected exactly 3 angles, got {len(angles)}. "
            f"Raw response (first 300 chars): {response.content[:300]!r}"
        )

    for i, angle in enumerate(angles):
        if "title" not in angle or "pitch" not in angle:
            raise ValueError(
                f"Angle at index {i} missing required fields (title, pitch). "
                f"Got keys: {list(angle.keys())}"
            )

    return angles


def generate_story(
    source_doc: str,
    chosen_angle: dict,
    target_duration_minutes: int,
) -> list[dict]:
    """Generate narration story blocks for a chosen angle.

    Returns a list of dicts with 'order' and 'content' keys.
    Raises ValueError if fewer than 2 blocks or any block is missing required fields.
    """
    persona = _load_persona()
    truncated_doc = _truncate_doc(source_doc)
    target_blocks = target_duration_minutes * 2

    instructions = (
        f"You are a video narrator with this persona:\n"
        f"{persona['personality']}\n\n"
        "Write a video narration story in the persona's voice, based on the chosen angle "
        "and source document.\n"
        f"Target approximately {target_blocks} story blocks (one ~30-second narration paragraph each).\n"
        "Each story block is a self-contained paragraph of 2 to 4 sentences.\n\n"
        "Return JSON in this exact shape:\n"
        '{"story_blocks": [{"order": 0, "content": "..."}, ...]}'
    )
    system_prompt = _build_system_prompt(instructions)

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Source document:\n{truncated_doc}\n\n"
                f"Chosen angle title: {chosen_angle.get('title', '')}\n"
                f"Chosen angle pitch: {chosen_angle.get('pitch', '')}\n\n"
                f"Target duration: {target_duration_minutes} minutes"
            )
        ),
    ])

    data = _parse_json_response(response.content)
    blocks = data.get("story_blocks", [])

    if len(blocks) < 2:
        raise ValueError(
            f"Expected at least 2 story blocks, got {len(blocks)}. "
            f"Raw response (first 300 chars): {response.content[:300]!r}"
        )

    for i, block in enumerate(blocks):
        if "order" not in block:
            raise ValueError(f"Story block at index {i} missing 'order' field.")
        if not isinstance(block["order"], int):
            raise ValueError(
                f"Story block at index {i} 'order' must be int, got {type(block['order']).__name__}."
            )
        if "content" not in block or not str(block["content"]).strip():
            raise ValueError(
                f"Story block at index {i} missing or empty 'content' field."
            )

    return blocks


def generate_scenes(
    story_blocks: list[dict],
    target_duration_minutes: int,
) -> list[dict]:
    """Break story blocks into scene descriptions with image and video prompts.

    Returns a list of scene dicts with: order, title, dialog, image_prompt, video_prompt.
    Always appends STYLE_CONSTRAINTS to image_prompt and video_prompt after LLM response.
    Raises ValueError if fewer than 2 scenes or any required field is missing.
    """
    persona = _load_persona()
    target_scenes = round(target_duration_minutes * 1.5)

    story_text = "\n\n".join(
        f"[Block {b.get('order', i)}] {b.get('content', '')}"
        for i, b in enumerate(story_blocks)
    )

    instructions = (
        f"You are a storyboard artist and video director with this persona:\n"
        f"{persona['personality']}\n\n"
        f"Character description (use this consistently for all visual prompts):\n"
        f"{persona['character']}\n\n"
        f"Break the provided story into approximately {target_scenes} scenes.\n"
        "Each scene corresponds to one video clip.\n\n"
        "STRICT RULES:\n"
        "1. dialog: 1 to 2 SHORT, punchy sentences ONLY — never more. Fast pacing.\n"
        "2. image_prompt: describe the scene layout with the stickman character performing "
        "a specific action. Must be consistent with the character description above. "
        f"MUST end with: {STYLE_CONSTRAINTS}\n"
        "3. video_prompt: describe subtle motion only — consistent with stickman animation. "
        f"MUST end with: {STYLE_CONSTRAINTS}\n"
        "4. FORBIDDEN in all prompts: shadows, 3D rendering, gradients, camera movement.\n\n"
        "Required JSON shape:\n"
        '{"scenes": [{"order": 0, "title": "...", "dialog": "...", '
        '"image_prompt": "...", "video_prompt": "..."}, ...]}'
    )
    system_prompt = _build_system_prompt(instructions)

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Story blocks:\n{story_text}\n\n"
                f"Target duration: {target_duration_minutes} minutes"
            )
        ),
    ])

    data = _parse_json_response(response.content)
    scenes = data.get("scenes", [])

    if len(scenes) < 2:
        raise ValueError(
            f"Expected at least 2 scenes, got {len(scenes)}. "
            f"Raw response (first 300 chars): {response.content[:300]!r}"
        )

    required_fields = {"order", "title", "dialog", "image_prompt", "video_prompt"}
    for i, scene in enumerate(scenes):
        missing = required_fields - set(scene.keys())
        if missing:
            raise ValueError(
                f"Scene at index {i} missing required fields: {missing}"
            )
        if not str(scene.get("dialog", "")).strip():
            raise ValueError(f"Scene at index {i} has empty 'dialog' field.")

    # Post-processing: always append STYLE_CONSTRAINTS if not already present
    for scene in scenes:
        if not scene["image_prompt"].endswith(STYLE_CONSTRAINTS):
            scene["image_prompt"] = scene["image_prompt"].rstrip() + ", " + STYLE_CONSTRAINTS
        if not scene["video_prompt"].endswith(STYLE_CONSTRAINTS):
            scene["video_prompt"] = scene["video_prompt"].rstrip() + ", " + STYLE_CONSTRAINTS

    return scenes


def regenerate_field(
    scene: dict,
    field_name: str,
    story_context: str,
    source_doc_excerpt: str,
) -> str:
    """Regenerate a single image_prompt or video_prompt field for a scene.

    Only 'image_prompt' and 'video_prompt' are allowed — raises ValueError for
    any other field_name including 'dialog'.

    Returns the regenerated string value, always ending with STYLE_CONSTRAINTS.
    """
    allowed_fields = {"image_prompt", "video_prompt"}
    if field_name not in allowed_fields:
        raise ValueError(
            f"Field '{field_name}' cannot be regenerated via LLM. "
            f"Allowed fields: {sorted(allowed_fields)}. "
            "'dialog' is editorial-only and must be edited manually."
        )

    persona = _load_persona()

    instructions = (
        f"You are a storyboard artist with this persona:\n"
        f"{persona['personality']}\n\n"
        f"Character description (maintain consistency in all visual prompts):\n"
        f"{persona['character']}\n\n"
        f"Regenerate ONLY the '{field_name}' field for the given scene.\n"
        "Maintain visual and narrative consistency with the story context.\n"
        f"The regenerated value MUST end with: {STYLE_CONSTRAINTS}\n"
        "FORBIDDEN: camera movement, shadows, 3D rendering, gradients.\n\n"
        f"Return JSON in this exact shape: {{\"{ field_name}\": \"new value\"}}"
    )
    system_prompt = _build_system_prompt(instructions)

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Scene to update:\n{json.dumps(scene, indent=2)}\n\n"
                f"Story context:\n{story_context}\n\n"
                f"Source document excerpt:\n{source_doc_excerpt}"
            )
        ),
    ])

    data = _parse_json_response(response.content)

    if field_name not in data:
        raise ValueError(
            f"LLM response missing expected key '{field_name}'. "
            f"Got keys: {list(data.keys())}"
        )

    value = str(data[field_name])

    # Post-processing: always append STYLE_CONSTRAINTS if not already present
    if not value.endswith(STYLE_CONSTRAINTS):
        value = value.rstrip() + ", " + STYLE_CONSTRAINTS

    return value
