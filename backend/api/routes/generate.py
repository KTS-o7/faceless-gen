import asyncio
import queue as q_module
import threading
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.models.job import Job, JobStatus
from backend.pipeline.graph import compiled_graph
from backend.pipeline.state import initial_state
from backend.storage.job_store import job_store

router = APIRouter(prefix="/generate")


class GenerateRequest(BaseModel):
    user_prompt: str


def _run_pipeline(job_id: str, user_prompt: str, progress_queue: q_module.Queue) -> None:
    """Background function that runs the LangGraph pipeline."""
    # Mark job as running
    job = job_store.get(job_id)
    if job is None:
        progress_queue.put(None)
        return

    job.status = JobStatus.running
    job_store.update(job)

    try:
        state = compiled_graph.invoke(
            initial_state(job_id, user_prompt, progress_queue=progress_queue)
        )

        # Update job with results
        job = job_store.get(job_id)
        if job is not None:
            job.status = JobStatus.done
            job.progress_log = state.get("progress_log", [])
            job.final_output = state.get("final_output")
            job.scene_thumbnails = state.get("scene_thumbnails", [])
            job.video_paths = state.get("video_paths", [])
            job.error = state.get("error")
            if job.error:
                job.status = JobStatus.failed
            job_store.update(job)

    except Exception as exc:
        job = job_store.get(job_id)
        if job is not None:
            job.status = JobStatus.failed
            job.error = str(exc)
            job_store.update(job)
    finally:
        # Always send sentinel to unblock SSE stream
        progress_queue.put(None)


@router.post("")
async def post_generate(body: GenerateRequest):
    """Create a new generation job and start the pipeline in a background thread."""
    job_id = str(uuid.uuid4())
    progress_queue: q_module.Queue = q_module.Queue()

    job = Job(job_id=job_id, user_prompt=body.user_prompt)
    job_store.create(job)

    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id, body.user_prompt, progress_queue),
        daemon=True,
    )
    thread.start()

    # Store queue for SSE access (keyed by job_id)
    _queues[job_id] = progress_queue

    return {"job_id": job_id, "status": "pending"}


# In-process queue registry (job_id -> Queue)
_queues: dict[str, q_module.Queue] = {}


@router.get("/{job_id}/stream")
async def stream_job(job_id: str):
    """SSE endpoint streaming pipeline progress for a job."""
    job = job_store.get(job_id)
    if job is None:
        async def error_gen():
            yield {"event": "error", "data": f"Job {job_id} not found"}
        return EventSourceResponse(error_gen())

    progress_queue = _queues.get(job_id)

    async def event_generator():
        if progress_queue is None:
            # Job exists but no active queue (already completed)
            finished_job = job_store.get(job_id)
            if finished_job:
                yield {"event": "done", "data": finished_job.model_dump_json()}
            return

        loop = asyncio.get_event_loop()
        while True:
            try:
                item = await loop.run_in_executor(
                    None, lambda: progress_queue.get(timeout=0.5)
                )
            except q_module.Empty:
                continue

            if item is None:
                # Sentinel received — pipeline finished
                finished_job = job_store.get(job_id)
                if finished_job:
                    yield {"event": "done", "data": finished_job.model_dump_json()}
                # Clean up queue reference
                _queues.pop(job_id, None)
                return

            yield {"event": "progress", "data": item}

    return EventSourceResponse(event_generator())


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Return current job state as JSON, 404 if not found."""
    job = job_store.get(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Job {job_id} not found"},
        )
    return job
