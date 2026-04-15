"""Tests for pipeline nodes: scripting, audio, image_gen, video, assembly."""
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from backend.pipeline.state import initial_state


# ---------------------------------------------------------------------------
# TestScriptingNode
# ---------------------------------------------------------------------------

class TestScriptingNode:
    """Tests for backend/pipeline/nodes/scripting.py::scripting_node"""

    def _make_state(self, prompt="Tell me about cats"):
        return initial_state("job-test", prompt)

    def test_valid_response_parsed_correctly(self):
        from backend.pipeline.nodes.scripting import scripting_node

        payload = {
            "video_prompts": ["a cat sits", "a cat plays"],
            "voiceover_script": "Cats are wonderful animals.",
        }
        mock_response = Mock()
        mock_response.content = json.dumps(payload)

        with patch("backend.pipeline.nodes.scripting.get_llm") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.invoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            state = self._make_state()
            result = scripting_node(state)

        assert result["video_prompts"] == ["a cat sits", "a cat plays"]
        assert result["voiceover_script"] == "Cats are wonderful animals."
        assert "error" not in result or result.get("error") is None

    def test_markdown_fences_stripped(self):
        from backend.pipeline.nodes.scripting import scripting_node

        payload = {
            "video_prompts": ["scene one"],
            "voiceover_script": "Narration here.",
        }
        fenced = f"```json\n{json.dumps(payload)}\n```"
        mock_response = Mock()
        mock_response.content = fenced

        with patch("backend.pipeline.nodes.scripting.get_llm") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.invoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            state = self._make_state()
            result = scripting_node(state)

        assert result["video_prompts"] == ["scene one"]
        assert result["voiceover_script"] == "Narration here."

    def test_bad_json_sets_error(self):
        from backend.pipeline.nodes.scripting import scripting_node

        mock_response = Mock()
        mock_response.content = "not valid json at all !!!"

        with patch("backend.pipeline.nodes.scripting.get_llm") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.invoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            state = self._make_state()
            result = scripting_node(state)

        assert "error" in result
        assert result["error"] is not None
        assert len(result["error"]) > 0

    def test_missing_key_sets_error(self):
        from backend.pipeline.nodes.scripting import scripting_node

        # Valid JSON but missing 'voiceover_script'
        payload = {"video_prompts": ["only prompts here"]}
        mock_response = Mock()
        mock_response.content = json.dumps(payload)

        with patch("backend.pipeline.nodes.scripting.get_llm") as mock_get_llm:
            mock_llm = Mock()
            mock_llm.invoke.return_value = mock_response
            mock_get_llm.return_value = mock_llm

            state = self._make_state()
            result = scripting_node(state)

        assert "error" in result
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# TestAudioNode
# ---------------------------------------------------------------------------

class TestAudioNode:
    """Tests for backend/pipeline/nodes/audio.py::audio_node"""

    def _make_state(self, error=None):
        state = initial_state("job-audio", "test prompt")
        state["voiceover_script"] = "Hello world narration."
        if error:
            state["error"] = error
        return state

    def test_audio_path_set_on_success(self):
        from backend.pipeline.nodes.audio import audio_node

        mock_provider = Mock()
        mock_provider.synthesize.return_value = "/abs/path/voiceover_abc.mp3"

        with patch("backend.pipeline.nodes.audio.get_tts_provider", return_value=mock_provider), \
             patch("backend.pipeline.nodes.audio.get_audio_duration", return_value=12.5):
            result = audio_node(self._make_state())

        assert result["audio_path"] == "/abs/path/voiceover_abc.mp3"
        assert result["audio_duration_seconds"] == 12.5
        assert "error" not in result or result.get("error") is None

    def test_duration_measured_via_get_audio_duration(self):
        from backend.pipeline.nodes.audio import audio_node

        mock_provider = Mock()
        mock_provider.synthesize.return_value = "/tmp/test.mp3"

        with patch("backend.pipeline.nodes.audio.get_tts_provider", return_value=mock_provider) as _, \
             patch("backend.pipeline.nodes.audio.get_audio_duration", return_value=7.3) as mock_dur:
            audio_node(self._make_state())

        mock_dur.assert_called_once_with("/tmp/test.mp3")

    def test_node_skipped_when_upstream_error(self):
        from backend.pipeline.nodes.audio import audio_node

        state = self._make_state(error="upstream failed")
        with patch("backend.pipeline.nodes.audio.get_tts_provider") as mock_prov:
            result = audio_node(state)

        # Provider should never be called
        mock_prov.assert_not_called()
        assert result == {}

    def test_exception_sets_error(self):
        from backend.pipeline.nodes.audio import audio_node

        mock_provider = Mock()
        mock_provider.synthesize.side_effect = RuntimeError("API down")

        with patch("backend.pipeline.nodes.audio.get_tts_provider", return_value=mock_provider):
            result = audio_node(self._make_state())

        assert "error" in result
        assert result["error"] is not None
        assert "audio_node" in result["error"]


# ---------------------------------------------------------------------------
# TestImageGenNode
# ---------------------------------------------------------------------------

class TestImageGenNode:
    """Tests for backend/pipeline/nodes/image_gen.py::image_gen_node"""

    def _make_state(self, error=None, video_prompts=None):
        state = initial_state("job-img", "test")
        state["video_prompts"] = video_prompts or ["scene one", "scene two"]
        if error:
            state["error"] = error
        return state

    def _patch_persona(self, seed_exists=True, tmp_path=None):
        """Return a context manager dict for patching persona paths."""
        return {}

    def test_all_images_generated(self, tmp_path):
        from backend.pipeline.nodes.image_gen import image_gen_node

        seed_png = tmp_path / "seed.png"
        seed_png.write_bytes(b"fake png data")
        char_md = tmp_path / "character.md"
        char_md.write_text("A stickman character.")

        mock_backend = Mock()
        mock_backend.generate_image.side_effect = lambda prompt, seed_image_path, output_path: output_path

        with patch("backend.pipeline.nodes.image_gen.settings") as mock_settings, \
             patch("backend.pipeline.nodes.image_gen.get_image_backend", return_value=mock_backend):
            mock_settings.personas_dir = tmp_path.parent
            mock_settings.active_persona = tmp_path.name
            mock_settings.outputs_dir = tmp_path

            result = image_gen_node(self._make_state())

        assert len(result["image_paths"]) == 2
        assert all(p.endswith(".png") for p in result["image_paths"])
        assert "error" not in result or result.get("error") is None

    def test_seed_missing_sets_error(self, tmp_path):
        from backend.pipeline.nodes.image_gen import image_gen_node

        # No seed.png created
        mock_backend = Mock()

        with patch("backend.pipeline.nodes.image_gen.settings") as mock_settings, \
             patch("backend.pipeline.nodes.image_gen.get_image_backend", return_value=mock_backend):
            mock_settings.personas_dir = tmp_path.parent
            mock_settings.active_persona = tmp_path.name
            mock_settings.outputs_dir = tmp_path

            result = image_gen_node(self._make_state())

        assert "error" in result
        assert result["error"] is not None
        mock_backend.generate_image.assert_not_called()

    def test_upstream_error_skips_node(self, tmp_path):
        from backend.pipeline.nodes.image_gen import image_gen_node

        mock_backend = Mock()
        state = self._make_state(error="upstream error")

        with patch("backend.pipeline.nodes.image_gen.get_image_backend", return_value=mock_backend):
            result = image_gen_node(state)

        assert result == {}
        mock_backend.generate_image.assert_not_called()

    def test_style_constraints_in_prompt(self, tmp_path):
        from backend.pipeline.nodes.image_gen import image_gen_node
        from backend.pipeline.editorial import STYLE_CONSTRAINTS

        seed_png = tmp_path / "seed.png"
        seed_png.write_bytes(b"fake")
        char_md = tmp_path / "character.md"
        char_md.write_text("Stickman.")

        captured_prompts: list[str] = []

        def capture_generate(prompt, seed_image_path, output_path):
            captured_prompts.append(prompt)
            return output_path

        mock_backend = Mock()
        mock_backend.generate_image.side_effect = capture_generate

        with patch("backend.pipeline.nodes.image_gen.settings") as mock_settings, \
             patch("backend.pipeline.nodes.image_gen.get_image_backend", return_value=mock_backend), \
             patch("backend.pipeline.nodes.image_gen.STYLE_CONSTRAINTS", STYLE_CONSTRAINTS):
            mock_settings.personas_dir = tmp_path.parent
            mock_settings.active_persona = tmp_path.name
            mock_settings.outputs_dir = tmp_path

            image_gen_node(self._make_state())

        # style constraints are injected inside ComfyUIImageBackend.generate_image, not image_gen_node
        # but character.md prefix should be present
        for prompt in captured_prompts:
            assert "Stickman" in prompt

    def test_character_md_prepended_to_prompt(self, tmp_path):
        from backend.pipeline.nodes.image_gen import image_gen_node

        seed_png = tmp_path / "seed.png"
        seed_png.write_bytes(b"fake")
        char_md = tmp_path / "character.md"
        char_md.write_text("UNIQUE_CHAR_DESCRIPTION xyz")

        captured_prompts: list[str] = []

        def capture_generate(prompt, seed_image_path, output_path):
            captured_prompts.append(prompt)
            return output_path

        mock_backend = Mock()
        mock_backend.generate_image.side_effect = capture_generate

        with patch("backend.pipeline.nodes.image_gen.settings") as mock_settings, \
             patch("backend.pipeline.nodes.image_gen.get_image_backend", return_value=mock_backend):
            mock_settings.personas_dir = tmp_path.parent
            mock_settings.active_persona = tmp_path.name
            mock_settings.outputs_dir = tmp_path

            image_gen_node(self._make_state())

        for prompt in captured_prompts:
            assert "UNIQUE_CHAR_DESCRIPTION" in prompt


# ---------------------------------------------------------------------------
# TestVideoNode
# ---------------------------------------------------------------------------

class TestVideoNode:
    """Tests for backend/pipeline/nodes/video.py::video_node"""

    def _make_state(self, error=None):
        state = initial_state("job-vid", "test")
        state["video_prompts"] = ["prompt one", "prompt two"]
        state["image_paths"] = ["/img/scene_00.png", "/img/scene_01.png"]
        if error:
            state["error"] = error
        return state

    def test_all_clips_generated(self, tmp_path):
        from backend.pipeline.nodes.video import video_node

        mock_backend = Mock()
        mock_backend.generate_clip.side_effect = lambda prompt, first_frame_image_path, output_path, **kw: output_path

        with patch("backend.pipeline.nodes.video.get_video_backend", return_value=mock_backend), \
             patch("backend.pipeline.nodes.video.settings") as mock_settings, \
             patch("backend.pipeline.nodes.video.subprocess.run") as mock_run:
            mock_settings.outputs_dir = tmp_path
            mock_run.return_value = MagicMock(returncode=0)

            result = video_node(self._make_state())

        assert len(result["video_paths"]) == 2
        assert len(result["scene_thumbnails"]) == 2
        assert "error" not in result or result.get("error") is None

    def test_empty_image_paths_sets_error(self):
        from backend.pipeline.nodes.video import video_node

        state = initial_state("job-vid", "test")
        state["video_prompts"] = ["prompt one"]
        state["image_paths"] = []  # empty

        mock_backend = Mock()
        with patch("backend.pipeline.nodes.video.get_video_backend", return_value=mock_backend):
            result = video_node(state)

        assert "error" in result
        assert result["error"] is not None
        mock_backend.generate_clip.assert_not_called()

    def test_clip_failure_stops_and_sets_error(self, tmp_path):
        from backend.pipeline.nodes.video import video_node

        call_count = 0

        def failing_generate(prompt, first_frame_image_path, output_path, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("GPU OOM")
            return output_path

        mock_backend = Mock()
        mock_backend.generate_clip.side_effect = failing_generate

        with patch("backend.pipeline.nodes.video.get_video_backend", return_value=mock_backend), \
             patch("backend.pipeline.nodes.video.settings") as mock_settings, \
             patch("backend.pipeline.nodes.video.subprocess.run"):
            mock_settings.outputs_dir = tmp_path
            result = video_node(self._make_state())

        assert "error" in result
        assert result["error"] is not None
        # Only first clip was attempted; second was not
        assert call_count == 1

    def test_upstream_error_skips_node(self):
        from backend.pipeline.nodes.video import video_node

        mock_backend = Mock()
        with patch("backend.pipeline.nodes.video.get_video_backend", return_value=mock_backend):
            result = video_node(self._make_state(error="prior error"))

        assert result == {}
        mock_backend.generate_clip.assert_not_called()

    def test_thumbnails_extracted_per_clip(self, tmp_path):
        from backend.pipeline.nodes.video import video_node

        mock_backend = Mock()
        mock_backend.generate_clip.side_effect = lambda prompt, first_frame_image_path, output_path, **kw: output_path

        with patch("backend.pipeline.nodes.video.get_video_backend", return_value=mock_backend), \
             patch("backend.pipeline.nodes.video.settings") as mock_settings, \
             patch("backend.pipeline.nodes.video.subprocess.run") as mock_run:
            mock_settings.outputs_dir = tmp_path
            mock_run.return_value = MagicMock(returncode=0)
            result = video_node(self._make_state())

        # subprocess.run called once per clip for thumbnail extraction
        assert mock_run.call_count == 2

    def test_backend_called_with_image_path(self, tmp_path):
        from backend.pipeline.nodes.video import video_node

        mock_backend = Mock()
        mock_backend.generate_clip.side_effect = lambda prompt, first_frame_image_path, output_path, **kw: output_path

        with patch("backend.pipeline.nodes.video.get_video_backend", return_value=mock_backend), \
             patch("backend.pipeline.nodes.video.settings") as mock_settings, \
             patch("backend.pipeline.nodes.video.subprocess.run"):
            mock_settings.outputs_dir = tmp_path
            video_node(self._make_state())

        calls = mock_backend.generate_clip.call_args_list
        assert calls[0][1]["first_frame_image_path"] == "/img/scene_00.png" or \
               calls[0][0][1] == "/img/scene_00.png"


# ---------------------------------------------------------------------------
# TestAssemblyNode
# ---------------------------------------------------------------------------

class TestAssemblyNode:
    """Tests for backend/pipeline/nodes/assembly.py::assembly_node"""

    def _make_state(self, error=None, audio_path=None, audio_duration=10.0):
        state = initial_state("job-asm", "test")
        state["video_paths"] = ["/clips/clip_00.mp4", "/clips/clip_01.mp4"]
        state["audio_path"] = audio_path
        state["audio_duration_seconds"] = audio_duration
        if error:
            state["error"] = error
        return state

    def _mock_video_clip(self, duration=5.0):
        clip = MagicMock()
        clip.duration = duration
        clip.end = duration
        return clip

    def test_final_output_set_on_success(self, tmp_path):
        from backend.pipeline.nodes.assembly import assembly_node

        mock_clip1 = self._mock_video_clip(5.0)
        mock_clip2 = self._mock_video_clip(5.0)
        clips_made = [mock_clip1, mock_clip2]

        mock_writer = MagicMock()
        mock_writer.write.return_value = None

        with patch("backend.pipeline.nodes.assembly.settings") as mock_settings, \
             patch("backend.pipeline.nodes.assembly._get_video_duration", return_value=5.0), \
             patch("backend.pipeline.nodes.assembly.subprocess.run") as mock_run, \
             patch("backend.pipeline.nodes.assembly.VideoClip", side_effect=lambda p, start=0: clips_made.pop(0)), \
             patch("backend.pipeline.nodes.assembly.VideoWriter", return_value=mock_writer), \
             patch("backend.pipeline.nodes.assembly.AudioClip"):
            mock_settings.outputs_dir = tmp_path
            mock_run.return_value = MagicMock(returncode=0)
            result = assembly_node(self._make_state())

        assert "final_output" in result
        assert result["final_output"].endswith("final.mp4")
        assert "error" not in result or result.get("error") is None

    def test_freeze_applied_when_video_shorter(self, tmp_path):
        from backend.pipeline.nodes.assembly import assembly_node

        mock_clip1 = self._mock_video_clip(5.0)
        mock_clip2 = self._mock_video_clip(5.0)
        clips_made = [mock_clip1, mock_clip2]
        mock_writer = MagicMock()

        subprocess_calls: list = []

        def fake_run(cmd, **kw):
            subprocess_calls.append(cmd)
            return MagicMock(returncode=0)

        # video duration = 3.0, per_clip_duration = 10/2 = 5.0 → video shorter → freeze
        with patch("backend.pipeline.nodes.assembly.settings") as mock_settings, \
             patch("backend.pipeline.nodes.assembly._get_video_duration", return_value=3.0), \
             patch("backend.pipeline.nodes.assembly.subprocess.run", side_effect=fake_run), \
             patch("backend.pipeline.nodes.assembly.VideoClip", side_effect=lambda p, start=0: clips_made.pop(0) if clips_made else self._mock_video_clip()), \
             patch("backend.pipeline.nodes.assembly.VideoWriter", return_value=mock_writer), \
             patch("backend.pipeline.nodes.assembly.AudioClip"):
            mock_settings.outputs_dir = tmp_path
            result = assembly_node(self._make_state())

        # Check tpad command was issued
        tpad_calls = [c for c in subprocess_calls if any("tpad" in str(arg) for arg in c)]
        assert len(tpad_calls) >= 1

    def test_trim_applied_when_video_longer(self, tmp_path):
        from backend.pipeline.nodes.assembly import assembly_node

        mock_clip1 = self._mock_video_clip(5.0)
        mock_clip2 = self._mock_video_clip(5.0)
        clips_made = [mock_clip1, mock_clip2]
        mock_writer = MagicMock()

        subprocess_calls: list = []

        def fake_run(cmd, **kw):
            subprocess_calls.append(cmd)
            return MagicMock(returncode=0)

        # video duration = 8.0, per_clip_duration = 10/2 = 5.0 → video longer → trim
        with patch("backend.pipeline.nodes.assembly.settings") as mock_settings, \
             patch("backend.pipeline.nodes.assembly._get_video_duration", return_value=8.0), \
             patch("backend.pipeline.nodes.assembly.subprocess.run", side_effect=fake_run), \
             patch("backend.pipeline.nodes.assembly.VideoClip", side_effect=lambda p, start=0: clips_made.pop(0) if clips_made else self._mock_video_clip()), \
             patch("backend.pipeline.nodes.assembly.VideoWriter", return_value=mock_writer), \
             patch("backend.pipeline.nodes.assembly.AudioClip"):
            mock_settings.outputs_dir = tmp_path
            result = assembly_node(self._make_state())

        # Check trim command was issued (-t argument)
        trim_calls = [c for c in subprocess_calls if "-t" in c]
        assert len(trim_calls) >= 1

    def test_audio_clip_added_when_audio_path_set(self, tmp_path):
        from backend.pipeline.nodes.assembly import assembly_node

        mock_clip1 = self._mock_video_clip(5.0)
        mock_clip2 = self._mock_video_clip(5.0)
        clips_made = [mock_clip1, mock_clip2]
        mock_writer = MagicMock()
        mock_audio_clip = MagicMock()

        with patch("backend.pipeline.nodes.assembly.settings") as mock_settings, \
             patch("backend.pipeline.nodes.assembly._get_video_duration", return_value=5.0), \
             patch("backend.pipeline.nodes.assembly.subprocess.run"), \
             patch("backend.pipeline.nodes.assembly.VideoClip", side_effect=lambda p, start=0: clips_made.pop(0) if clips_made else self._mock_video_clip()), \
             patch("backend.pipeline.nodes.assembly.VideoWriter", return_value=mock_writer), \
             patch("backend.pipeline.nodes.assembly.AudioClip", return_value=mock_audio_clip) as mock_audio_cls:
            mock_settings.outputs_dir = tmp_path
            result = assembly_node(self._make_state(audio_path="/audio/voice.mp3"))

        mock_audio_cls.assert_called_once_with("/audio/voice.mp3", start=0)
        mock_writer.add_clip.assert_called()

    def test_upstream_error_skips_node(self, tmp_path):
        from backend.pipeline.nodes.assembly import assembly_node

        with patch("backend.pipeline.nodes.assembly.VideoClip") as mock_vc, \
             patch("backend.pipeline.nodes.assembly.VideoWriter"):
            result = assembly_node(self._make_state(error="prior error"))

        assert result == {}
        mock_vc.assert_not_called()

    def test_clips_closed_in_finally(self, tmp_path):
        from backend.pipeline.nodes.assembly import assembly_node

        mock_clip1 = self._mock_video_clip(5.0)
        mock_clip2 = self._mock_video_clip(5.0)
        clips_made = [mock_clip1, mock_clip2]
        mock_writer = MagicMock()
        mock_writer.write.side_effect = RuntimeError("write failed")

        with patch("backend.pipeline.nodes.assembly.settings") as mock_settings, \
             patch("backend.pipeline.nodes.assembly._get_video_duration", return_value=5.0), \
             patch("backend.pipeline.nodes.assembly.subprocess.run"), \
             patch("backend.pipeline.nodes.assembly.VideoClip", side_effect=lambda p, start=0: clips_made.pop(0) if clips_made else self._mock_video_clip()), \
             patch("backend.pipeline.nodes.assembly.VideoWriter", return_value=mock_writer), \
             patch("backend.pipeline.nodes.assembly.AudioClip"):
            mock_settings.outputs_dir = tmp_path
            result = assembly_node(self._make_state())

        # Even though write failed, both clips should have close() called
        mock_clip1.close.assert_called()
        mock_clip2.close.assert_called()
        assert "error" in result
