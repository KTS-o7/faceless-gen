import threading
from typing import Optional

from backend.models.job import Job


class JobStore:
    """Thread-safe in-memory job store."""

    def __init__(self) -> None:
        self._store: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job: Job) -> Job:
        """Store a job and return it."""
        with self._lock:
            self._store[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        """Return the job or None if not found."""
        with self._lock:
            return self._store.get(job_id)

    def update(self, job: Job) -> None:
        """Overwrite the existing entry for the job."""
        with self._lock:
            self._store[job.job_id] = job

    def append_log(self, job_id: str, message: str) -> None:
        """Thread-safe append a message to a job's progress_log."""
        with self._lock:
            job = self._store.get(job_id)
            if job is not None:
                job.progress_log.append(message)

    def all(self) -> list[Job]:
        """Return all jobs sorted newest-first by created_at."""
        with self._lock:
            jobs = list(self._store.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs


# Module-level singleton
job_store = JobStore()
