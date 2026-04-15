"""Project API routes — CRUD, angles, story blocks, and scenes.

All DB operations use the synchronous ProjectRepository wrapped in asyncio.to_thread
to avoid blocking the async event loop. LLM calls also use run_in_executor.
"""
import asyncio
import queue as queue_module
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.models.schemas import (
    AngleResponse,
    ChooseAngleRequest,
    CreateProjectRequest,
    ProjectDetail,
    ProjectSummary,
    RegenerateFieldRequest,
    ReorderRequest,
    SceneResponse,
    StoryBlockResponse,
    UpdateProjectRequest,
    UpdateSceneRequest,
    UpdateStoryBlockRequest,
    angle_to_response,
    project_to_detail,
    project_to_summary,
    scene_to_response,
    story_block_to_response,
)
from backend.models.job import Job, JobStatus
from backend.pipeline.editorial import (
    generate_angles,
    generate_scenes,
    generate_story,
    regenerate_field,
)
from backend.pipeline.graph import compiled_graph
from backend.pipeline.state import initial_state
from backend.storage.database import get_sync_session
from backend.storage.job_store import job_store
from backend.storage.project_repo import repo

router = APIRouter(prefix="/projects", tags=["projects"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OUTPUTS_DIR = Path("outputs")


def _validate_project_id(project_id: str) -> None:
    """Guard against path traversal — project IDs are hex strings."""
    if not project_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid project ID format.")


def _get_project_detail_sync(project_id: str) -> ProjectDetail:
    """Fetch a project plus all its children synchronously; raises ValueError if not found."""
    with get_sync_session() as session:
        project = repo.get_project(session, project_id)
        if project is None:
            raise ValueError(f"Project {project_id!r} not found")

        from sqlmodel import select
        from backend.models.project import Angle, StoryBlock, Scene

        angles = list(session.exec(
            select(Angle).where(Angle.project_id == project_id).order_by(Angle.order)  # type: ignore[attr-defined]
        ).all())
        story_blocks = list(session.exec(
            select(StoryBlock).where(StoryBlock.project_id == project_id).order_by(StoryBlock.order)  # type: ignore[attr-defined]
        ).all())
        scenes = list(session.exec(
            select(Scene).where(Scene.project_id == project_id).order_by(Scene.order)  # type: ignore[attr-defined]
        ).all())

        return project_to_detail(project, angles, story_blocks, scenes)


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=ProjectDetail)
async def create_project(body: CreateProjectRequest) -> ProjectDetail:
    def _create() -> ProjectDetail:
        with get_sync_session() as session:
            project = repo.create_project(
                session,
                name=body.name,
                source_doc=body.source_doc,
                target_duration_minutes=body.target_duration_minutes,
            )
            return project_to_detail(project, [], [], [])

    return await asyncio.to_thread(_create)


@router.get("", response_model=list[ProjectSummary])
async def list_projects() -> list[ProjectSummary]:
    def _list() -> list[ProjectSummary]:
        with get_sync_session() as session:
            projects = repo.list_projects(session)
            return [project_to_summary(p) for p in projects]

    return await asyncio.to_thread(_list)


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str) -> ProjectDetail:
    _validate_project_id(project_id)

    def _get() -> ProjectDetail:
        try:
            return _get_project_detail_sync(project_id)
        except ValueError:
            return None  # type: ignore[return-value]

    result = await asyncio.to_thread(_get)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return result


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(project_id: str, body: UpdateProjectRequest) -> ProjectDetail:
    _validate_project_id(project_id)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    def _update() -> ProjectDetail:
        with get_sync_session() as session:
            project = repo.get_project(session, project_id)
            if project is None:
                return None  # type: ignore[return-value]
            if updates:
                project = repo.update_project(session, project_id, **updates)
        try:
            return _get_project_detail_sync(project_id)
        except ValueError:
            return None  # type: ignore[return-value]

    result = await asyncio.to_thread(_update)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return result


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str) -> Response:
    _validate_project_id(project_id)

    def _delete() -> None:
        with get_sync_session() as session:
            repo.delete_project(session, project_id)
        # Remove outputs directory if it exists
        output_dir = _OUTPUTS_DIR / project_id
        if output_dir.exists():
            shutil.rmtree(output_dir)

    await asyncio.to_thread(_delete)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Angle Routes
# ---------------------------------------------------------------------------


@router.post("/{project_id}/angles/generate", response_model=list[AngleResponse])
async def generate_project_angles(project_id: str) -> list[AngleResponse]:
    _validate_project_id(project_id)

    def _get_project():
        with get_sync_session() as session:
            project = repo.get_project(session, project_id)
            if project is None:
                return None
            return {
                "source_doc": project.source_doc,
                "target_duration_minutes": project.target_duration_minutes,
            }

    project_data = await asyncio.to_thread(_get_project)
    if project_data is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    # Run blocking LLM call in executor
    try:
        loop = asyncio.get_event_loop()
        angles_data = await loop.run_in_executor(
            None,
            generate_angles,
            project_data["source_doc"],
            project_data["target_duration_minutes"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Attach order to each angle dict
    for i, angle in enumerate(angles_data):
        angle["order"] = i

    def _save_angles() -> list[AngleResponse]:
        with get_sync_session() as session:
            saved = repo.set_angles(session, project_id, angles_data)
            repo.update_project(session, project_id, stage="angle_selection")
            return [angle_to_response(a) for a in saved]

    return await asyncio.to_thread(_save_angles)


@router.post(
    "/{project_id}/angles/{angle_id}/choose", response_model=AngleResponse
)
async def choose_angle(project_id: str, angle_id: str) -> AngleResponse:
    _validate_project_id(project_id)

    def _choose() -> AngleResponse:
        with get_sync_session() as session:
            project = repo.get_project(session, project_id)
            if project is None:
                return None  # type: ignore[return-value]
            try:
                chosen = repo.choose_angle(session, project_id, angle_id)
            except ValueError as exc:
                raise exc
            repo.update_project(session, project_id, stage="story_editing")
            return angle_to_response(chosen)

    try:
        result = await asyncio.to_thread(_choose)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return result


# ---------------------------------------------------------------------------
# Story Routes
# ---------------------------------------------------------------------------


@router.post("/{project_id}/story/generate", response_model=list[StoryBlockResponse])
async def generate_project_story(project_id: str) -> list[StoryBlockResponse]:
    _validate_project_id(project_id)

    def _get_project_and_angle():
        with get_sync_session() as session:
            from sqlmodel import select
            from backend.models.project import Angle

            project = repo.get_project(session, project_id)
            if project is None:
                return None, None
            # Find the chosen angle
            stmt = select(Angle).where(
                Angle.project_id == project_id, Angle.chosen == True  # noqa: E712
            )
            chosen_angle = session.exec(stmt).first()
            if chosen_angle is None:
                return project, None
            return (
                {
                    "source_doc": project.source_doc,
                    "target_duration_minutes": project.target_duration_minutes,
                },
                {"title": chosen_angle.title, "pitch": chosen_angle.pitch},
            )

    project_data, angle_data = await asyncio.to_thread(_get_project_and_angle)
    if project_data is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if angle_data is None:
        raise HTTPException(
            status_code=409,
            detail="No angle has been chosen yet. Choose an angle before generating a story.",
        )

    # Run blocking LLM call in executor
    loop = asyncio.get_event_loop()
    try:
        blocks_data = await loop.run_in_executor(
            None,
            generate_story,
            project_data["source_doc"],
            angle_data,
            project_data["target_duration_minutes"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def _save_blocks() -> list[StoryBlockResponse]:
        with get_sync_session() as session:
            saved = repo.set_story_blocks(session, project_id, blocks_data)
            repo.update_project(session, project_id, stage="story_editing")
            return [story_block_to_response(b) for b in saved]

    return await asyncio.to_thread(_save_blocks)


@router.get("/{project_id}/story", response_model=list[StoryBlockResponse])
async def get_story(project_id: str) -> list[StoryBlockResponse]:
    _validate_project_id(project_id)

    def _get() -> list[StoryBlockResponse]:
        from sqlmodel import select
        from backend.models.project import StoryBlock

        with get_sync_session() as session:
            stmt = (
                select(StoryBlock)
                .where(StoryBlock.project_id == project_id)
                .order_by(StoryBlock.order)  # type: ignore[attr-defined]
            )
            blocks = list(session.exec(stmt).all())
            return [story_block_to_response(b) for b in blocks]

    return await asyncio.to_thread(_get)


@router.patch("/{project_id}/story/reorder", response_model=list[StoryBlockResponse])
async def reorder_story(project_id: str, body: ReorderRequest) -> list[StoryBlockResponse]:
    _validate_project_id(project_id)

    def _reorder() -> list[StoryBlockResponse]:
        with get_sync_session() as session:
            blocks = repo.reorder_story_blocks(session, project_id, body.ordered_ids)
            return [story_block_to_response(b) for b in blocks]

    return await asyncio.to_thread(_reorder)


@router.patch("/{project_id}/story/{block_id}", response_model=StoryBlockResponse)
async def update_story_block(
    project_id: str, block_id: str, body: UpdateStoryBlockRequest
) -> StoryBlockResponse:
    _validate_project_id(project_id)

    def _update() -> StoryBlockResponse:
        with get_sync_session() as session:
            try:
                block = repo.update_story_block(session, project_id, block_id, body.content)
                return story_block_to_response(block)
            except ValueError as exc:
                raise exc

    try:
        return await asyncio.to_thread(_update)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{project_id}/story/{block_id}", status_code=204)
async def delete_story_block(project_id: str, block_id: str) -> Response:
    _validate_project_id(project_id)

    def _delete() -> None:
        with get_sync_session() as session:
            try:
                repo.delete_story_block(session, project_id, block_id)
            except ValueError as exc:
                raise exc

    try:
        await asyncio.to_thread(_delete)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=204)


@router.post("/{project_id}/story/confirm", response_model=ProjectSummary)
async def confirm_story(project_id: str) -> ProjectSummary:
    _validate_project_id(project_id)

    def _confirm() -> ProjectSummary:
        with get_sync_session() as session:
            project = repo.get_project(session, project_id)
            if project is None:
                return None  # type: ignore[return-value]
            project = repo.update_project(session, project_id, stage="scene_editing")
            return project_to_summary(project)

    result = await asyncio.to_thread(_confirm)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return result


# ---------------------------------------------------------------------------
# Scene Routes
# ---------------------------------------------------------------------------


@router.post("/{project_id}/scenes/generate", response_model=list[SceneResponse])
async def generate_project_scenes(project_id: str) -> list[SceneResponse]:
    _validate_project_id(project_id)

    def _get_project_and_blocks():
        from sqlmodel import select
        from backend.models.project import StoryBlock

        with get_sync_session() as session:
            project = repo.get_project(session, project_id)
            if project is None:
                return None, None
            stmt = (
                select(StoryBlock)
                .where(StoryBlock.project_id == project_id)
                .order_by(StoryBlock.order)  # type: ignore[attr-defined]
            )
            blocks = list(session.exec(stmt).all())
            return (
                {"target_duration_minutes": project.target_duration_minutes},
                [{"order": b.order, "content": b.content} for b in blocks],
            )

    project_data, blocks_data = await asyncio.to_thread(_get_project_and_blocks)
    if project_data is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    if len(blocks_data) < 2:
        raise HTTPException(
            status_code=409,
            detail="Story must have at least 2 blocks before generating scenes.",
        )

    # Run blocking LLM call in executor
    loop = asyncio.get_event_loop()
    try:
        scenes_data = await loop.run_in_executor(
            None,
            generate_scenes,
            blocks_data,
            project_data["target_duration_minutes"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def _save_scenes() -> list[SceneResponse]:
        with get_sync_session() as session:
            saved = repo.set_scenes(session, project_id, scenes_data)
            repo.update_project(session, project_id, stage="scene_editing")
            return [scene_to_response(s) for s in saved]

    return await asyncio.to_thread(_save_scenes)


@router.get("/{project_id}/scenes", response_model=list[SceneResponse])
async def get_scenes(project_id: str) -> list[SceneResponse]:
    _validate_project_id(project_id)

    def _get() -> list[SceneResponse]:
        with get_sync_session() as session:
            scenes = repo.get_scenes(session, project_id)
            return [scene_to_response(s) for s in scenes]

    return await asyncio.to_thread(_get)


@router.patch("/{project_id}/scenes/reorder", response_model=list[SceneResponse])
async def reorder_scenes(project_id: str, body: ReorderRequest) -> list[SceneResponse]:
    _validate_project_id(project_id)

    def _reorder() -> list[SceneResponse]:
        with get_sync_session() as session:
            scenes = repo.reorder_scenes(session, project_id, body.ordered_ids)
            return [scene_to_response(s) for s in scenes]

    return await asyncio.to_thread(_reorder)


@router.patch("/{project_id}/scenes/{scene_id}", response_model=SceneResponse)
async def update_scene(
    project_id: str, scene_id: str, body: UpdateSceneRequest
) -> SceneResponse:
    _validate_project_id(project_id)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    def _update() -> SceneResponse:
        with get_sync_session() as session:
            try:
                scene = repo.update_scene(session, project_id, scene_id, **updates)
                return scene_to_response(scene)
            except ValueError as exc:
                raise exc

    try:
        return await asyncio.to_thread(_update)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{project_id}/scenes/{scene_id}/regenerate", response_model=SceneResponse)
async def regenerate_scene_field(
    project_id: str, scene_id: str, body: RegenerateFieldRequest
) -> SceneResponse:
    _validate_project_id(project_id)

    def _get_scene():
        from backend.models.project import Scene

        with get_sync_session() as session:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return None
            return {
                "id": scene.id,
                "order": scene.order,
                "title": scene.title,
                "dialog": scene.dialog,
                "image_prompt": scene.image_prompt,
                "video_prompt": scene.video_prompt,
            }

    scene_data = await asyncio.to_thread(_get_scene)
    if scene_data is None:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found.")

    # Run blocking LLM call in executor
    loop = asyncio.get_event_loop()
    try:
        new_value = await loop.run_in_executor(
            None,
            regenerate_field,
            scene_data,
            body.field_name,
            body.story_context,
            body.source_doc_excerpt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def _save_field() -> SceneResponse:
        with get_sync_session() as session:
            scene = repo.update_scene(
                session, project_id, scene_id, **{body.field_name: new_value}
            )
            return scene_to_response(scene)

    return await asyncio.to_thread(_save_field)


@router.post("/{project_id}/scenes/confirm", response_model=ProjectSummary)
async def confirm_scenes(project_id: str) -> ProjectSummary:
    _validate_project_id(project_id)

    def _confirm() -> ProjectSummary:
        with get_sync_session() as session:
            project = repo.get_project(session, project_id)
            if project is None:
                return None  # type: ignore[return-value]
            project = repo.update_project(session, project_id, stage="music_selection")
            return project_to_summary(project)

    result = await asyncio.to_thread(_confirm)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return result


# ---------------------------------------------------------------------------
# Project-Based Generation
# ---------------------------------------------------------------------------


@router.post("/{project_id}/generate")
async def generate_project_video(project_id: str):
    """Kick off background pipeline for an approved project."""
    _validate_project_id(project_id)

    def _get_project():
        with get_sync_session() as session:
            return repo.get_project(session, project_id)

    project = await asyncio.to_thread(_get_project)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Validate stage
    if project.stage not in ("music_selection", "failed"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot generate from stage '{project.stage}'. "
                "Must be 'music_selection' or 'failed'."
            ),
        )

    def _get_scenes():
        with get_sync_session() as session:
            scenes = repo.get_scenes(session, project_id)
            if len(scenes) < 2:
                raise ValueError("Project needs at least 2 scenes")
            return [
                {
                    "id": s.id,
                    "order": s.order,
                    "title": s.title,
                    "dialog": s.dialog,
                    "image_prompt": s.image_prompt,
                    "video_prompt": s.video_prompt,
                    "audio_path": s.audio_path,
                    "audio_duration_seconds": s.audio_duration_seconds,
                    "image_path": s.image_path,
                    "video_clip_path": s.video_clip_path,
                    "thumbnail_path": s.thumbnail_path,
                }
                for s in scenes
            ]

    try:
        scenes = await asyncio.to_thread(_get_scenes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Create job
    job_id = uuid.uuid4().hex
    job = Job(job_id=job_id, user_prompt=f"Project: {project.name}", status=JobStatus.pending)
    job_store.create(job)

    # Reset error if retrying from failed; set stage to generating
    def _reset_and_start():
        with get_sync_session() as session:
            repo.update_project(
                session,
                project_id,
                stage="generating",
                error=None,
                active_job_id=job_id,
            )

    await asyncio.to_thread(_reset_and_start)

    music_track = project.music_track
    project_name = project.name

    q: queue_module.Queue = queue_module.Queue()

    def _run_pipeline():
        # Mark job as running
        existing = job_store.get(job_id)
        if existing:
            job_store.update(Job(**{**existing.model_dump(), "status": JobStatus.running}))

        try:
            state = initial_state(
                job_id,
                f"Project: {project_name}",
                progress_queue=q,
                project_id=project_id,
                scenes=scenes,
                music_track=music_track,
            )

            result = compiled_graph.invoke(state)

            if result.get("error"):
                with get_sync_session() as session:
                    repo.update_project(
                        session,
                        project_id,
                        stage="failed",
                        error=result["error"],
                        active_job_id=None,
                    )
                j = job_store.get(job_id)
                if j:
                    job_store.update(
                        Job(**{**j.model_dump(), "status": JobStatus.failed, "error": result["error"]})
                    )
            else:
                with get_sync_session() as session:
                    repo.update_project(
                        session,
                        project_id,
                        stage="done",
                        final_output_path=result.get("final_output"),
                        active_job_id=None,
                    )
                j = job_store.get(job_id)
                if j:
                    job_store.update(
                        Job(
                            **{
                                **j.model_dump(),
                                "status": JobStatus.done,
                                "final_output": result.get("final_output"),
                                "progress_log": result.get("progress_log", []),
                            }
                        )
                    )

        except Exception as e:
            with get_sync_session() as session:
                repo.update_project(
                    session,
                    project_id,
                    stage="failed",
                    error=str(e),
                    active_job_id=None,
                )
            j = job_store.get(job_id)
            if j:
                job_store.update(Job(**{**j.model_dump(), "status": JobStatus.failed, "error": str(e)}))
        finally:
            q.put(None)  # sentinel

    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()

    return {"job_id": job_id, "project_id": project_id, "status": "pending"}
