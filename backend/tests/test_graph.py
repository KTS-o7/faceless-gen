"""Tests for backend/pipeline/graph.py"""
import pytest
from unittest.mock import patch, MagicMock

from backend.pipeline.state import initial_state


class TestGraph:
    def test_compiled_graph_is_not_none(self):
        from backend.pipeline.graph import compiled_graph
        assert compiled_graph is not None

    def test_all_five_nodes_present(self):
        from backend.pipeline.graph import build_graph
        graph = build_graph()
        node_names = set(graph.nodes.keys())
        for expected in ("scripting", "audio", "image_gen", "video", "assembly"):
            assert expected in node_names, f"Node '{expected}' missing from graph"

    def test_graph_compiles_without_error(self):
        from backend.pipeline.graph import build_graph
        compiled = build_graph()
        assert compiled is not None

    def test_graph_invoke_with_mocked_nodes(self):
        """Graph can be invoked end-to-end when all nodes are patched."""
        from backend.pipeline.graph import build_graph
        from backend.pipeline.state import PipelineState

        def mock_scripting(state):
            return {
                "video_prompts": ["scene one", "scene two"],
                "voiceover_script": "Narration text.",
                "progress_log": ["scripting done"],
            }

        def mock_audio(state):
            return {
                "audio_path": "/tmp/voice.mp3",
                "audio_duration_seconds": 10.0,
                "progress_log": ["audio done"],
            }

        def mock_image_gen(state):
            return {
                "image_paths": ["/tmp/s00.png", "/tmp/s01.png"],
                "progress_log": ["img done"],
            }

        def mock_video(state):
            return {
                "video_paths": ["/tmp/c00.mp4", "/tmp/c01.mp4"],
                "scene_thumbnails": ["/tmp/t00.jpg", "/tmp/t01.jpg"],
                "progress_log": ["video done"],
            }

        def mock_assembly(state):
            return {
                "final_output": "/tmp/final.mp4",
                "progress_log": ["assembly done"],
            }

        with patch("backend.pipeline.nodes.scripting.scripting_node", mock_scripting), \
             patch("backend.pipeline.nodes.audio.audio_node", mock_audio), \
             patch("backend.pipeline.nodes.image_gen.image_gen_node", mock_image_gen), \
             patch("backend.pipeline.nodes.video.video_node", mock_video), \
             patch("backend.pipeline.nodes.assembly.assembly_node", mock_assembly), \
             patch("backend.pipeline.graph.scripting_node", mock_scripting), \
             patch("backend.pipeline.graph.audio_node", mock_audio), \
             patch("backend.pipeline.graph.image_gen_node", mock_image_gen), \
             patch("backend.pipeline.graph.video_node", mock_video), \
             patch("backend.pipeline.graph.assembly_node", mock_assembly):
            compiled = build_graph()
            state = initial_state("job-graph", "test prompt")
            result = compiled.invoke(state)

        assert result is not None
        # Result should have final_output from assembly
        assert result.get("final_output") == "/tmp/final.mp4"
