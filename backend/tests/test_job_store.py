import threading
import time

import pytest

from backend.models.job import Job, JobStatus
from backend.storage.job_store import JobStore


def _make_job(job_id: str = "job-1", prompt: str = "test prompt") -> Job:
    return Job(job_id=job_id, user_prompt=prompt)


class TestJobStoreCreate:
    def test_create_returns_job(self):
        store = JobStore()
        job = _make_job()
        result = store.create(job)
        assert result is job

    def test_create_stores_job(self):
        store = JobStore()
        job = _make_job("abc")
        store.create(job)
        assert store.get("abc") is job

    def test_create_multiple_jobs(self):
        store = JobStore()
        j1 = _make_job("j1")
        j2 = _make_job("j2")
        store.create(j1)
        store.create(j2)
        assert store.get("j1") is j1
        assert store.get("j2") is j2


class TestJobStoreGet:
    def test_get_existing_job(self):
        store = JobStore()
        job = _make_job("x")
        store.create(job)
        assert store.get("x") is job

    def test_get_missing_returns_none(self):
        store = JobStore()
        assert store.get("nonexistent") is None

    def test_get_after_update_returns_new_job(self):
        store = JobStore()
        job = _make_job("y")
        store.create(job)
        updated_job = Job(job_id="y", user_prompt="updated", status=JobStatus.done)
        store.update(updated_job)
        retrieved = store.get("y")
        assert retrieved is updated_job
        assert retrieved.status == "done"


class TestJobStoreUpdate:
    def test_update_overwrites_entry(self):
        store = JobStore()
        job = _make_job("u1")
        store.create(job)
        new_job = Job(job_id="u1", user_prompt="updated prompt", status=JobStatus.running)
        store.update(new_job)
        assert store.get("u1").status == "running"

    def test_update_creates_if_not_exists(self):
        store = JobStore()
        job = Job(job_id="new", user_prompt="fresh")
        store.update(job)
        assert store.get("new") is job


class TestJobStoreAppendLog:
    def test_append_log_adds_message(self):
        store = JobStore()
        job = _make_job("log1")
        store.create(job)
        store.append_log("log1", "step one")
        assert "step one" in store.get("log1").progress_log

    def test_append_log_multiple_messages(self):
        store = JobStore()
        job = _make_job("log2")
        store.create(job)
        store.append_log("log2", "a")
        store.append_log("log2", "b")
        assert store.get("log2").progress_log == ["a", "b"]

    def test_append_log_missing_job_noop(self):
        store = JobStore()
        # Should not raise
        store.append_log("ghost", "message")

    def test_append_log_concurrent_no_data_loss(self):
        """Two threads calling append_log concurrently must produce two entries."""
        store = JobStore()
        job = _make_job("concurrent")
        store.create(job)

        results: list[str] = []

        def worker(msg: str) -> None:
            time.sleep(0.01)
            store.append_log("concurrent", msg)

        t1 = threading.Thread(target=worker, args=("msg-1",))
        t2 = threading.Thread(target=worker, args=("msg-2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        log = store.get("concurrent").progress_log
        assert len(log) == 2
        assert "msg-1" in log
        assert "msg-2" in log


class TestJobStoreAll:
    def test_all_empty(self):
        store = JobStore()
        assert store.all() == []

    def test_all_returns_all_jobs(self):
        store = JobStore()
        j1 = _make_job("a1")
        j2 = _make_job("a2")
        store.create(j1)
        store.create(j2)
        all_jobs = store.all()
        assert len(all_jobs) == 2

    def test_all_sorted_newest_first(self):
        store = JobStore()
        # Create jobs with slight delay to ensure distinct timestamps
        j1 = _make_job("old")
        time.sleep(0.01)
        j2 = _make_job("new")
        store.create(j1)
        store.create(j2)
        all_jobs = store.all()
        # Newest (j2) should come first
        assert all_jobs[0].job_id == "new"
        assert all_jobs[1].job_id == "old"
