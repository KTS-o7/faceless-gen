"""Tests for backend/pipeline/editorial.py — LLM editorial nodes."""

import json
from unittest.mock import MagicMock, patch

import pytest

import backend.pipeline.editorial as ed
from backend.pipeline.editorial import (
    STYLE_CONSTRAINTS,
    _build_system_prompt,
    _parse_json_response,
    _truncate_doc,
    generate_angles,
    generate_scenes,
    generate_story,
    regenerate_field,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_llm(content: str) -> MagicMock:
    """Return a mock LLM whose .invoke() returns an object with .content = content."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = content
    return mock_llm


def _make_angles_json(n: int = 3) -> str:
    angles = [{"title": f"Angle {i}", "pitch": f"Sentence one. Sentence two."} for i in range(n)]
    return json.dumps({"angles": angles})


def _make_story_json(n: int = 4) -> str:
    blocks = [{"order": i, "content": f"Block content number {i}."} for i in range(n)]
    return json.dumps({"story_blocks": blocks})


def _make_scenes_json(n: int = 3, include_style: bool = False) -> str:
    suffix = ", " + STYLE_CONSTRAINTS if include_style else ""
    scenes = [
        {
            "order": i,
            "title": f"Scene {i}",
            "dialog": f"Dialog for scene {i}.",
            "image_prompt": f"Image desc {i}{suffix}",
            "video_prompt": f"Video desc {i}{suffix}",
        }
        for i in range(n)
    ]
    return json.dumps({"scenes": scenes})


# ---------------------------------------------------------------------------
# TestSharedUtils
# ---------------------------------------------------------------------------

class TestSharedUtils:
    def setup_method(self):
        ed._persona_cache.clear()

    def test_parse_json_response_fenced_json(self):
        raw = '```json\n{"a": 1}\n```'
        assert _parse_json_response(raw) == {"a": 1}

    def test_parse_json_response_fenced_no_lang(self):
        raw = '```\n{"b": 2}\n```'
        assert _parse_json_response(raw) == {"b": 2}

    def test_parse_json_response_clean(self):
        raw = '{"c": 3}'
        assert _parse_json_response(raw) == {"c": 3}

    def test_parse_json_response_bad_json_raises(self):
        with pytest.raises(ValueError, match="not json"):
            _parse_json_response("not json")

    def test_parse_json_response_error_includes_content(self):
        bad = "this is not valid json at all"
        with pytest.raises(ValueError) as exc_info:
            _parse_json_response(bad)
        assert "this is not valid json" in str(exc_info.value)

    def test_build_system_prompt_contains_preamble(self):
        result = _build_system_prompt("do x")
        assert "Output ONLY valid JSON" in result
        assert "No prose" in result

    def test_build_system_prompt_contains_instructions(self):
        result = _build_system_prompt("do x and y")
        assert "do x and y" in result

    def test_truncate_doc_short_unchanged(self):
        doc = "short doc"
        assert _truncate_doc(doc) == doc

    def test_truncate_doc_long_truncated(self):
        doc = "x" * 20000
        result = _truncate_doc(doc)
        assert result.startswith("x" * 12000)
        assert "[Document truncated for context window]" in result

    def test_truncate_doc_exact_length_unchanged(self):
        doc = "y" * 12000
        assert _truncate_doc(doc) == doc

    def test_truncate_doc_custom_max(self):
        doc = "a" * 100
        result = _truncate_doc(doc, max_chars=50)
        assert result.startswith("a" * 50)
        assert "[Document truncated for context window]" in result

    def test_load_persona_returns_dict(self):
        persona = ed._load_persona()
        assert "personality" in persona
        assert "character" in persona
        assert "voice_id" in persona

    def test_load_persona_voice_id_stripped_from_personality(self):
        persona = ed._load_persona()
        # personality content should NOT contain the Voice-ID line
        assert "Voice-ID:" not in persona["personality"]

    def test_load_persona_voice_id_parsed(self):
        persona = ed._load_persona()
        assert persona["voice_id"] == "21m00Tcm4TlvDq8ikWAM"

    def test_load_persona_cached(self):
        p1 = ed._load_persona()
        p2 = ed._load_persona()
        assert p1 is p2  # same object from cache

    def test_load_persona_missing_directory(self):
        ed._persona_cache.clear()
        original = ed.settings.active_persona
        ed.settings.active_persona = "nonexistent_persona_xyz"
        try:
            with pytest.raises(FileNotFoundError):
                ed._load_persona()
        finally:
            ed.settings.active_persona = original
            ed._persona_cache.clear()


# ---------------------------------------------------------------------------
# TestGenerateAngles
# ---------------------------------------------------------------------------

class TestGenerateAngles:
    def setup_method(self):
        ed._persona_cache.clear()

    def test_valid_three_angles(self):
        mock_llm = _make_mock_llm(_make_angles_json(3))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_angles("some doc content", 5)
        assert len(result) == 3
        for angle in result:
            assert "title" in angle
            assert "pitch" in angle

    def test_fewer_than_three_angles_raises(self):
        mock_llm = _make_mock_llm(_make_angles_json(2))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="exactly 3"):
                generate_angles("some doc", 5)

    def test_more_than_three_angles_raises(self):
        mock_llm = _make_mock_llm(_make_angles_json(4))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="exactly 3"):
                generate_angles("some doc", 5)

    def test_missing_pitch_raises(self):
        angles = [{"title": f"Angle {i}"} for i in range(3)]  # no pitch
        mock_llm = _make_mock_llm(json.dumps({"angles": angles}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="pitch"):
                generate_angles("some doc", 5)

    def test_persona_personality_in_system_prompt(self):
        mock_llm = _make_mock_llm(_make_angles_json(3))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            generate_angles("some doc", 5)
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0].content
        persona = ed._load_persona()
        assert persona["personality"] in system_msg

    def test_source_doc_truncated_if_long(self):
        long_doc = "z" * 20000
        mock_llm = _make_mock_llm(_make_angles_json(3))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            generate_angles(long_doc, 5)
        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "[Document truncated for context window]" in human_msg

    def test_fenced_json_response_handled(self):
        fenced = f'```json\n{_make_angles_json(3)}\n```'
        mock_llm = _make_mock_llm(fenced)
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_angles("doc", 5)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# TestGenerateStory
# ---------------------------------------------------------------------------

class TestGenerateStory:
    def setup_method(self):
        ed._persona_cache.clear()

    def test_valid_blocks_returned(self):
        mock_llm = _make_mock_llm(_make_story_json(4))
        angle = {"title": "Test Angle", "pitch": "Sentence one. Sentence two."}
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_story("doc content", angle, 5)
        assert len(result) == 4
        for block in result:
            assert "order" in block
            assert "content" in block

    def test_fewer_than_two_blocks_raises(self):
        mock_llm = _make_mock_llm(_make_story_json(1))
        angle = {"title": "Angle", "pitch": "Pitch."}
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="at least 2"):
                generate_story("doc", angle, 5)

    def test_missing_content_raises(self):
        blocks = [{"order": 0, "content": "Valid."}, {"order": 1}]  # second missing content
        mock_llm = _make_mock_llm(json.dumps({"story_blocks": blocks}))
        angle = {"title": "Angle", "pitch": "Pitch."}
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="content"):
                generate_story("doc", angle, 5)

    def test_persona_personality_in_system_prompt(self):
        mock_llm = _make_mock_llm(_make_story_json(4))
        angle = {"title": "Angle", "pitch": "Pitch."}
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            generate_story("doc content", angle, 5)
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0].content
        persona = ed._load_persona()
        assert persona["personality"] in system_msg

    def test_source_doc_truncated_if_long(self):
        long_doc = "w" * 20000
        mock_llm = _make_mock_llm(_make_story_json(4))
        angle = {"title": "Angle", "pitch": "Pitch."}
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            generate_story(long_doc, angle, 5)
        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "[Document truncated for context window]" in human_msg


# ---------------------------------------------------------------------------
# TestGenerateScenes
# ---------------------------------------------------------------------------

class TestGenerateScenes:
    def setup_method(self):
        ed._persona_cache.clear()

    def _make_blocks(self, n: int = 3):
        return [{"order": i, "content": f"Content {i}."} for i in range(n)]

    def test_valid_scenes_returned(self):
        mock_llm = _make_mock_llm(_make_scenes_json(3))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_scenes(self._make_blocks(), 5)
        assert len(result) == 3
        for scene in result:
            for field in ("order", "title", "dialog", "image_prompt", "video_prompt"):
                assert field in scene

    def test_style_constraints_appended_to_image_prompt(self):
        # LLM response does NOT include STYLE_CONSTRAINTS
        mock_llm = _make_mock_llm(_make_scenes_json(3, include_style=False))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_scenes(self._make_blocks(), 5)
        for scene in result:
            assert scene["image_prompt"].endswith(STYLE_CONSTRAINTS)

    def test_style_constraints_appended_to_video_prompt(self):
        mock_llm = _make_mock_llm(_make_scenes_json(3, include_style=False))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_scenes(self._make_blocks(), 5)
        for scene in result:
            assert scene["video_prompt"].endswith(STYLE_CONSTRAINTS)

    def test_style_constraints_not_duplicated_when_already_present(self):
        # LLM already includes STYLE_CONSTRAINTS — should not duplicate
        mock_llm = _make_mock_llm(_make_scenes_json(3, include_style=True))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = generate_scenes(self._make_blocks(), 5)
        for scene in result:
            # Should end with STYLE_CONSTRAINTS exactly once
            assert scene["image_prompt"].endswith(STYLE_CONSTRAINTS)
            double = STYLE_CONSTRAINTS + ", " + STYLE_CONSTRAINTS
            assert double not in scene["image_prompt"]

    def test_fewer_than_two_scenes_raises(self):
        mock_llm = _make_mock_llm(_make_scenes_json(1))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="at least 2"):
                generate_scenes(self._make_blocks(), 5)

    def test_missing_video_prompt_raises(self):
        scenes = [
            {"order": 0, "title": "T", "dialog": "D", "image_prompt": "I"},
            {"order": 1, "title": "T", "dialog": "D", "image_prompt": "I"},
        ]  # no video_prompt
        mock_llm = _make_mock_llm(json.dumps({"scenes": scenes}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="video_prompt"):
                generate_scenes(self._make_blocks(), 5)

    def test_persona_character_in_system_prompt(self):
        mock_llm = _make_mock_llm(_make_scenes_json(3))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            generate_scenes(self._make_blocks(), 5)
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0].content
        persona = ed._load_persona()
        assert persona["character"] in system_msg

    def test_persona_personality_in_system_prompt(self):
        mock_llm = _make_mock_llm(_make_scenes_json(3))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            generate_scenes(self._make_blocks(), 5)
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0].content
        persona = ed._load_persona()
        assert persona["personality"] in system_msg

    def test_empty_dialog_raises(self):
        scenes = [
            {"order": 0, "title": "T", "dialog": "   ", "image_prompt": "I", "video_prompt": "V"},
            {"order": 1, "title": "T", "dialog": "D.", "image_prompt": "I", "video_prompt": "V"},
        ]
        mock_llm = _make_mock_llm(json.dumps({"scenes": scenes}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="dialog"):
                generate_scenes(self._make_blocks(), 5)


# ---------------------------------------------------------------------------
# TestRegenerateField
# ---------------------------------------------------------------------------

class TestRegenerateField:
    def setup_method(self):
        ed._persona_cache.clear()

    _scene = {
        "order": 0,
        "title": "Scene Title",
        "dialog": "Some dialog.",
        "image_prompt": "Original image.",
        "video_prompt": "Original video.",
    }

    def test_image_prompt_returns_string_with_style_constraints(self):
        new_val = "A fresh image prompt"
        mock_llm = _make_mock_llm(json.dumps({"image_prompt": new_val}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = regenerate_field(self._scene, "image_prompt", "story ctx", "doc excerpt")
        assert isinstance(result, str)
        assert result.endswith(STYLE_CONSTRAINTS)

    def test_video_prompt_returns_string_with_style_constraints(self):
        new_val = "A fresh video prompt"
        mock_llm = _make_mock_llm(json.dumps({"video_prompt": new_val}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = regenerate_field(self._scene, "video_prompt", "story ctx", "doc excerpt")
        assert isinstance(result, str)
        assert result.endswith(STYLE_CONSTRAINTS)

    def test_style_constraints_not_duplicated_if_already_present(self):
        new_val = "Prompt, " + STYLE_CONSTRAINTS
        mock_llm = _make_mock_llm(json.dumps({"image_prompt": new_val}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            result = regenerate_field(self._scene, "image_prompt", "ctx", "doc")
        assert result.endswith(STYLE_CONSTRAINTS)
        double = STYLE_CONSTRAINTS + ", " + STYLE_CONSTRAINTS
        assert double not in result

    def test_dialog_raises_immediately_no_llm_call(self):
        mock_llm = _make_mock_llm("{}")
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="dialog"):
                regenerate_field(self._scene, "dialog", "ctx", "doc")
        # LLM should NOT have been called
        mock_llm.invoke.assert_not_called()

    def test_invalid_field_raises_immediately(self):
        mock_llm = _make_mock_llm("{}")
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError):
                regenerate_field(self._scene, "aspect_ratio", "ctx", "doc")
        mock_llm.invoke.assert_not_called()

    def test_persona_character_in_system_prompt(self):
        new_val = "Prompt"
        mock_llm = _make_mock_llm(json.dumps({"image_prompt": new_val}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            regenerate_field(self._scene, "image_prompt", "ctx", "doc")
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0].content
        persona = ed._load_persona()
        assert persona["character"] in system_msg

    def test_missing_key_in_llm_response_raises(self):
        # LLM returns wrong key
        mock_llm = _make_mock_llm(json.dumps({"wrong_key": "value"}))
        with patch("backend.pipeline.editorial.get_llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="image_prompt"):
                regenerate_field(self._scene, "image_prompt", "ctx", "doc")
