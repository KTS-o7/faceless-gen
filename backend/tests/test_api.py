"""Tests for the FastAPI backend — generate, history, health endpoints."""
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import app after load_dotenv() has been called (main.py calls it at the top)
from backend.main import app

client = TestClient(app)

# Patch target for Thread in the generate route module
_THREAD_PATCH = "backend.api.routes.generate.threading.Thread"


class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body(self):
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "faceless-gen"


class TestGeneratePost:
    def test_post_returns_200_with_job_id(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            resp = client.post("/api/generate", json={"user_prompt": "test topic"})
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_post_returns_unique_job_ids(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            resp1 = client.post("/api/generate", json={"user_prompt": "topic 1"})
            resp2 = client.post("/api/generate", json={"user_prompt": "topic 2"})
        assert resp1.json()["job_id"] != resp2.json()["job_id"]

    def test_post_missing_prompt_returns_422(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            resp = client.post("/api/generate", json={})
        assert resp.status_code == 422


class TestGenerateGet:
    def test_get_existing_job_returns_200(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            post_resp = client.post("/api/generate", json={"user_prompt": "some topic"})
        job_id = post_resp.json()["job_id"]

        resp = client.get(f"/api/generate/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id

    def test_get_unknown_job_returns_404(self):
        resp = client.get("/api/generate/nonexistent-job-id-xyz")
        assert resp.status_code == 404

    def test_get_job_has_expected_fields(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            post_resp = client.post("/api/generate", json={"user_prompt": "fields test"})
        job_id = post_resp.json()["job_id"]

        resp = client.get(f"/api/generate/{job_id}")
        data = resp.json()
        assert "job_id" in data
        assert "status" in data
        assert "user_prompt" in data
        assert "progress_log" in data


class TestGenerateStream:
    def test_stream_returns_event_stream_content_type(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            post_resp = client.post("/api/generate", json={"user_prompt": "stream test"})
        job_id = post_resp.json()["job_id"]

        # Remove the queue from _queues so the stream returns immediately
        # (simulates a completed job with no active queue)
        from backend.api.routes.generate import _queues
        _queues.pop(job_id, None)

        with client.stream("GET", f"/api/generate/{job_id}/stream") as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_unknown_job_returns_event_stream(self):
        # Even for unknown jobs, SSE returns text/event-stream with an error event
        with client.stream("GET", "/api/generate/unknown-stream-id/stream") as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")


class TestHistory:
    def test_history_returns_200(self):
        resp = client.get("/api/history")
        assert resp.status_code == 200

    def test_history_returns_list(self):
        resp = client.get("/api/history")
        assert isinstance(resp.json(), list)

    def test_history_contains_created_jobs(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            post_resp = client.post("/api/generate", json={"user_prompt": "history job"})
        job_id = post_resp.json()["job_id"]

        resp = client.get("/api/history")
        job_ids = [j["job_id"] for j in resp.json()]
        assert job_id in job_ids

    def test_history_single_job_returns_200(self):
        with patch(_THREAD_PATCH) as MockThread:
            MockThread.return_value.start.return_value = None
            post_resp = client.post("/api/generate", json={"user_prompt": "single history"})
        job_id = post_resp.json()["job_id"]

        resp = client.get(f"/api/history/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id

    def test_history_unknown_job_returns_404(self):
        resp = client.get("/api/history/unknown-history-id-xyz")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
