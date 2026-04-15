"""Database engine and session factories for faceless-gen.

- sync_engine / get_sync_session() — used by pipeline nodes running in background threads
- async_engine / get_async_session() — used by FastAPI route handlers via Depends()
- init_db() — creates all tables synchronously (called from FastAPI lifespan)
"""
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, Session

from backend.models.config import settings

# Resolve DB path: one level up from outputs_dir → project root level
db_path: Path = settings.outputs_dir.parent / "faceless_gen.db"

_SYNC_URL = f"sqlite:///{db_path}"
_ASYNC_URL = f"sqlite+aiosqlite:///{db_path}"

sync_engine = create_engine(_SYNC_URL, connect_args={"check_same_thread": False})
async_engine = create_async_engine(_ASYNC_URL)

# Enable WAL mode on the sync engine to reduce read/write contention
with sync_engine.connect() as _conn:
    _conn.execute(text("PRAGMA journal_mode=WAL"))
    _conn.commit()


def init_db() -> None:
    """Create all SQLModel tables using the synchronous engine.

    Safe to call multiple times — ``create_all`` is idempotent.
    """
    # Ensure all model modules are imported so their metadata is registered
    import backend.models.project  # noqa: F401

    SQLModel.metadata.create_all(sync_engine)


@contextmanager
def get_sync_session():
    """Synchronous context manager for pipeline nodes / background threads.

    Usage::

        with get_sync_session() as session:
            repo.create_project(session, ...)
    """
    with Session(sync_engine) as session:
        yield session


async def get_async_session():
    """Async generator for FastAPI ``Depends()``.

    Usage::

        @app.get("/projects")
        async def list_projects(session: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with AsyncSession(async_engine) as session:
        yield session
