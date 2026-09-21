"""Compose the example application.

The factory owns state wiring while lifespan initializes persistent resources.
Creating or importing the application does not touch its data directory.
"""

import asyncio
import logging
import secrets
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from pwaf_foundation import __version__
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.database import Database, Migration
from pwaf_foundation.health import ReadinessCheck
from pwaf_foundation.job_routes import job_router
from pwaf_foundation.jobs import JobDefinition, JobManager
from pwaf_foundation.settings import FoundationSettings, SettingsStore
from pwaf_foundation.ui import UIConfig
from pwaf_foundation.web import register_web

logger = logging.getLogger(__name__)


def create_app(
    config: RuntimeConfig | None = None,
    *,
    settings_schema: type[FoundationSettings] = FoundationSettings,
    migrations: dict[str, Sequence[Migration]] | None = None,
    readiness_checks: Sequence[ReadinessCheck] = (),
    routers: Sequence[APIRouter] = (),
    ui: UIConfig | None = None,
    job_factory: Callable[[Database], dict[str, JobDefinition]] | None = None,
) -> FastAPI:
    """Build an isolated app with explicit settings, migration, route, and health extensions."""
    runtime = config if config is not None else RuntimeConfig.from_env()
    settings = SettingsStore(runtime.data_dir / "settings.json", settings_schema)
    database = Database(runtime.data_dir / "app.sqlite3")
    migration_sets = {"foundation": ()} | dict(migrations or {})
    if "foundation" in (migrations or {}):
        raise ValueError("The foundation migration namespace is reserved")
    if len({check.name for check in readiness_checks}) != len(readiness_checks):
        raise ValueError("Readiness check names must be unique")
    if any(check.name == "database" for check in readiness_checks):
        raise ValueError("The database readiness name is reserved")

    async def database_ready() -> bool:
        return await asyncio.to_thread(database.ready)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.started = False
        application.state.csrf_token = secrets.token_urlsafe(32)
        try:
            await asyncio.to_thread(settings.load)
            await asyncio.to_thread(database.migrate, migration_sets)
            logger.info("Runtime data directory: %s", runtime.data_dir)
            if job_factory is not None:
                application.state.jobs = JobManager(job_factory(database))
            application.state.started = True
            yield
        finally:
            application.state.started = False
            application.state.csrf_token = ""
            if application.state.jobs is not None:
                await application.state.jobs.close()
            # Settings and database operations own their file/connection lifetimes.

    application = FastAPI(title="Python Web App Foundation", version=__version__, lifespan=lifespan)
    application.state.jobs = None
    application.state.config = runtime
    application.state.settings = settings
    application.state.database = database
    application.state.started = False
    application.state.csrf_token = ""
    application.state.readiness_checks = (
        ReadinessCheck("database", database_ready, timeout=3),
        *readiness_checks,
    )
    register_web(application, runtime, settings_schema, ui or UIConfig())
    if job_factory is not None:
        application.include_router(job_router())
    for router in routers:
        application.include_router(router)
    return application


def create_example_app(config: RuntimeConfig | None = None) -> FastAPI:
    """Build the replaceable performance demonstration for the default launcher."""
    from app.example import example_options

    return create_app(config, **example_options())
