"""Tests for backend/models/config.py"""
import pytest

from backend.models.config import Settings, settings


class TestSettings:
    def test_settings_singleton_exists(self):
        """settings module-level singleton is importable and is a Settings instance."""
        assert isinstance(settings, Settings)

    def test_bifrost_base_url_is_string_starting_with_http(self):
        assert isinstance(settings.bifrost_base_url, str)
        assert settings.bifrost_base_url.startswith("http")

    def test_bifrost_model_default(self):
        assert settings.bifrost_model == "gpt-4o-mini"

    def test_api_port_default(self):
        assert settings.api_port == 8000
        assert isinstance(settings.api_port, int)

    def test_comfyui_base_url_default(self):
        assert settings.comfyui_base_url == "http://127.0.0.1:8188"

    def test_active_persona_default(self):
        assert settings.active_persona == "default"

    def test_video_backend_is_local_or_cloud(self):
        assert settings.video_backend in ("local", "cloud")

    def test_outputs_dir_is_path(self):
        from pathlib import Path
        assert isinstance(settings.outputs_dir, Path)

    def test_models_dir_is_path(self):
        from pathlib import Path
        assert isinstance(settings.models_dir, Path)

    def test_personas_dir_is_path(self):
        from pathlib import Path
        assert isinstance(settings.personas_dir, Path)
