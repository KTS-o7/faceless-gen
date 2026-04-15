"""Tests for backend/pipeline/state.py"""
import pytest

from backend.pipeline.state import PipelineState, initial_state


class TestInitialState:
    def test_all_keys_present(self):
        state = initial_state("job-1", "test prompt")
        expected_keys = {
            "job_id",
            "user_prompt",
            "video_prompts",
            "voiceover_script",
            "audio_path",
            "audio_duration_seconds",
            "image_paths",
            "video_paths",
            "scene_thumbnails",
            "final_output",
            "progress_log",
            "error",
            "progress_queue",
            # Plan 09 project-based fields
            "project_id",
            "scenes",
            "music_track",
            "persona",
        }
        assert set(state.keys()) == expected_keys

    def test_job_id_and_prompt_set(self):
        state = initial_state("abc123", "my prompt")
        assert state["job_id"] == "abc123"
        assert state["user_prompt"] == "my prompt"

    def test_optional_fields_are_none(self):
        state = initial_state("j", "p")
        assert state["audio_path"] is None
        assert state["audio_duration_seconds"] is None
        assert state["final_output"] is None
        assert state["error"] is None
        assert state["progress_queue"] is None

    def test_list_fields_default_to_empty(self):
        state = initial_state("j", "p")
        assert state["video_prompts"] == []
        assert state["image_paths"] == []
        assert state["video_paths"] == []
        assert state["scene_thumbnails"] == []
        assert state["progress_log"] == []

    def test_voiceover_script_defaults_to_empty_string(self):
        state = initial_state("j", "p")
        assert state["voiceover_script"] == ""

    def test_progress_queue_can_be_passed(self):
        import queue
        q = queue.Queue()
        state = initial_state("j", "p", progress_queue=q)
        assert state["progress_queue"] is q
