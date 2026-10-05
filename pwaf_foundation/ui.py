"""Define explicit UI extension points.

Applications register navigation and settings panes and may override any default
Jinja template. Static assets use separate named mounts to avoid collisions.
"""

import asyncio
import math
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
    general_settings_fields: tuple[str, ...] = ("app_name", "theme")
    graph_ranges: tuple[tuple[float, str], ...] = (
        (1, "1hr"), (6, "6hr"), (12, "12hr"), (24, "24hr"),
        (72, "3 days"), (168, "7 days"), (336, "14 days"), (696, "29 days"),
    )
    graph_default_hours: float = 24

    def __post_init__(self) -> None:
        if not self.graph_ranges or any(
            not math.isfinite(hours) or hours <= 0 or not label
            for hours, label in self.graph_ranges
        ):
            raise ValueError("Graph ranges must have positive finite hours and labels")
        hours = [value for value, _ in self.graph_ranges]
        if len(set(hours)) != len(hours) or self.graph_default_hours not in hours:
            raise ValueError("Graph ranges must be unique and include the default")


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
