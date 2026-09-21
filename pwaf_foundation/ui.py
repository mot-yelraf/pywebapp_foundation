"""Define explicit UI extension points.

Applications register navigation and settings panes and may override any default
Jinja template. Static assets use separate named mounts to avoid collisions.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse


@dataclass(frozen=True)
class NavigationItem:
    """A human-facing local navigation destination."""

    label: str
    path: str

    def __post_init__(self) -> None:
        if not self.path.startswith("/") or self.path.startswith("//"):
            raise ValueError("Navigation paths must be local absolute paths")


@dataclass(frozen=True)
class SettingsPane:
    """Fields owned and saved independently by one settings pane."""

    key: str
    label: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.key.isidentifier():
            raise ValueError("Settings pane keys must be identifiers")


@dataclass(frozen=True)
class UIConfig:
    """Application template overrides, optional assets, navigation, and extra panes."""

    template_dir: Path | None = None
    static_dir: Path | None = None
    navigation: tuple[NavigationItem, ...] = ()
    settings_panes: tuple[SettingsPane, ...] = ()
    graph_enabled: bool = False


async def render_page(request: Request, name: str, **context) -> HTMLResponse:
    """Render an application page with the shared UI and current settings context."""
    settings = await asyncio.to_thread(request.app.state.settings.snapshot)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "settings": settings,
            "ui": request.app.state.ui,
            "panes": request.app.state.settings_panes,
            "setting_fields": request.app.state.settings_schema.model_json_schema()["properties"],
            **context,
        },
    )
