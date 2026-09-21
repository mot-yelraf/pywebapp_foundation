"""Wire reusable routes and HTTP policies.

Derived applications supply state and optional routers through their application
factory. This module never imports application-specific code.
"""

import asyncio
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, create_model

from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.errors import ERROR_RESPONSES, DomainError, install_error_handlers
from pwaf_foundation.health import HealthResponse, evaluate_checks
from pwaf_foundation.security import BrowserSecurity
from pwaf_foundation.settings import FoundationSettings
from pwaf_foundation.ui import SettingsPane, UIConfig, render_page


class CsrfResponse(BaseModel):
    """CSRF token to echo in the X-CSRF-Token header of browser mutations."""

    csrf_token: str


def register_web(
    app: FastAPI, config: RuntimeConfig, settings_schema: type[FoundationSettings], ui: UIConfig
) -> None:
    """Install standard endpoints, templates, errors, and local security policy."""
    install_error_handlers(app)
    app.add_middleware(BrowserSecurity, config=config)
    foundation_dir = Path(__file__).parent
    directories = [str(foundation_dir / "templates")]
    if ui.template_dir is not None:
        directories.insert(0, str(ui.template_dir))
    templates = Jinja2Templates(directory=directories)
    app.mount(
        "/static/foundation",
        StaticFiles(directory=foundation_dir / "static"),
        name="foundation_static",
    )
    if ui.static_dir is not None:
        app.mount("/static/app", StaticFiles(directory=ui.static_dir), name="app_static")
    panes = (SettingsPane("general", "General", ("app_name", "theme")), *ui.settings_panes)
    keys, owned = set(), set()
    for pane in panes:
        if pane.key in keys or owned.intersection(pane.fields):
            raise ValueError("Settings panes must have unique keys and disjoint fields")
        if not set(pane.fields).issubset(settings_schema.model_fields):
            raise ValueError("Settings pane refers to an unknown field")
        keys.add(pane.key)
        owned.update(pane.fields)
    app.state.ui, app.state.settings_panes = ui, panes
    app.state.settings_schema = settings_schema
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home(request: Request) -> HTMLResponse:
        return await render_page(request, "index.html")

    @app.get("/healthz", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
    async def health(request: Request, response: Response) -> HealthResponse:
        """Check initialized runtime and all explicitly required services."""
        if not request.app.state.started:
            response.status_code = 503
            return HealthResponse(status="not_ready", checks={"runtime": False})
        result = await evaluate_checks(request.app.state.readiness_checks)
        if result.status != "ready":
            response.status_code = 503
        return result

    @app.get("/api/csrf", response_model=CsrfResponse, responses=ERROR_RESPONSES)
    async def csrf(request: Request) -> CsrfResponse:
        """Read the current token; no cookie or persistent state is created."""
        return CsrfResponse(csrf_token=request.app.state.csrf_token)

    @app.get("/api/settings", response_model=settings_schema, responses=ERROR_RESPONSES)
    async def read_settings(request: Request) -> FoundationSettings:
        """Read recognized editable settings; startup configuration is separate."""
        return await asyncio.to_thread(request.app.state.settings.snapshot)

    fields = {}
    for name, field in settings_schema.model_fields.items():
        optional_field = deepcopy(field)
        optional_field.default = None
        optional_field.default_factory = None
        fields[name] = (field.annotation, optional_field)
    patch_schema = create_model(
        f"{settings_schema.__name__}Patch",
        __config__=ConfigDict(extra="forbid", strict=True),
        **fields,
    )

    @app.patch("/api/settings", response_model=settings_schema, responses=ERROR_RESPONSES)
    async def update_settings(
        request: Request,
        changes: patch_schema,
    ) -> FoundationSettings:
        """Atomically update supplied fields; requires Origin and X-CSRF-Token headers.

        Keys must be fields of the settings response model. Omitted values remain
        unchanged. Unknown fields and invalid values return 422.
        """
        return await asyncio.to_thread(
            request.app.state.settings.update, changes.model_dump(exclude_unset=True)
        )

    @app.patch(
        "/api/settings/panes/{pane_key}", response_model=settings_schema, responses=ERROR_RESPONSES
    )
    async def update_pane(
        request: Request, pane_key: str, changes: patch_schema
    ) -> FoundationSettings:
        """Save only fields owned by the named pane; omitted fields remain unchanged."""
        pane = next((item for item in panes if item.key == pane_key), None)
        if pane is None:
            raise DomainError("pane_not_found", "Settings pane does not exist.", 404)
        values = changes.model_dump(exclude_unset=True)
        if not set(values).issubset(pane.fields):
            raise DomainError("invalid_pane_fields", "This pane cannot change those fields.", 422)
        return await asyncio.to_thread(request.app.state.settings.update, values)
