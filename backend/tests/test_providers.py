"""Tests for backend/providers/llm.py"""
import pytest

from backend.providers.llm import get_llm


class TestGetLLM:
    def test_returns_chat_openai_instance(self):
        from langchain_openai import ChatOpenAI
        llm = get_llm()
        assert isinstance(llm, ChatOpenAI)

    def test_base_url_does_not_contain_openai_com(self):
        llm = get_llm()
        # openai_api_base or base_url depending on langchain_openai version
        base_url = getattr(llm, "openai_api_base", None) or str(llm.base_url or "")
        assert "openai.com" not in base_url

    def test_default_temperature(self):
        llm = get_llm()
        assert llm.temperature == 0.7

    def test_custom_temperature(self):
        llm = get_llm(temperature=0.0)
        assert llm.temperature == 0.0

    def test_model_comes_from_settings(self):
        from backend.models.config import settings
        llm = get_llm()
        assert llm.model_name == settings.bifrost_model
