"""Compose the replaceable performance demonstration.

Example routes, settings, job definitions, and persistence stay out of foundation
modules. Remove this composition to start a different application.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field

from app.migrations import PERFORMANCE_MIGRATIONS
from app.services.performance import PerformanceInput, PerformanceResult
from app.services.results import HistoryPage, ResultRepository
from pwaf_foundation.adapters import SubprocessAdapter
from pwaf_foundation.database import Database
from pwaf_foundation.errors import ERROR_RESPONSES
from pwaf_foundation.jobs import JobContext, JobDefinition
from pwaf_foundation.settings import FoundationSettings
from pwaf_foundation.ui import NavigationItem, SettingsPane, UIConfig, render_page

APP_DIR = Path(__file__).parent


class ToolSettings(FoundationSettings):
    """Application-specific defaults used when preparing a new run."""

    default_iterations: int = Field(default=100000, ge=1, le=5000000, title="Default iterations")


def performance_jobs(database: Database) -> dict[str, JobDefinition]:
    """Register a fixed executable and a separate durable-success callback."""
    repository = ResultRepository(database)
    adapter = SubprocessAdapter(
        lambda parameters: [
            sys.executable,
            "-m",
            "app.cli",
            "--iterations",
            str(parameters["iterations"]),
        ],
        cwd=str(APP_DIR.parent),
    )

    async def run(parameters: dict, context: JobContext) -> dict:
        output = await adapter(parameters, context)
        return PerformanceResult.model_validate(json.loads(output["stdout"])).model_dump()

    async def save(job_id: str, result: dict) -> None:
        await asyncio.to_thread(repository.save, job_id, result)

    return {"performance": JobDefinition(PerformanceInput, run, timeout=30, save=save)}


def example_router() -> APIRouter:
    """Register the performance page and paginated successful results."""
    router = APIRouter()

    @router.get("/performance", include_in_schema=False)
    async def page(request: Request):
        return await render_page(request, "performance.html")

    @router.get("/api/results", response_model=HistoryPage, responses=ERROR_RESPONSES)
    def history(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> HistoryPage:
        """List successful saved results, newest first; active jobs are not included."""
        return ResultRepository(request.app.state.database).history(offset, limit)

    return router


def example_options() -> dict:
    """Return explicit extensions used by the default command-line web launcher."""
    return {
        "settings_schema": ToolSettings,
        "migrations": {"performance": PERFORMANCE_MIGRATIONS},
        "routers": [example_router()],
        "job_factory": performance_jobs,
        "ui": UIConfig(
            template_dir=APP_DIR / "templates",
            static_dir=APP_DIR / "static",
            navigation=(NavigationItem("Performance", "/performance"),),
            settings_panes=(SettingsPane("performance", "Performance", ("default_iterations",)),),
        ),
    }
