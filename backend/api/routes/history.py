from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.storage.job_store import job_store

router = APIRouter(prefix="/history")


@router.get("")
async def get_history():
    """Return all jobs sorted newest-first."""
    jobs = job_store.all()
    return [job.model_dump() for job in jobs]


@router.get("/{job_id}")
async def get_history_job(job_id: str):
    """Return a single job by ID, 404 if not found."""
    job = job_store.get(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Job {job_id} not found"},
        )
    return job
