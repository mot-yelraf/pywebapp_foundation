# Extend the foundation with your application

The default `python -m app` launcher builds the performance demonstration through
`create_example_app`. `create_app` remains a domain-independent composition function
in the replaceable `app/app.py`. Reusable modules never import the example.

## Add a page and navigation

Create `app/templates/report.html`:

```jinja
{% extends 'base.html' %}
{% from 'components.html' import metric, button, dialog %}
{% block title %}Report · {{ settings.app_name }}{% endblock %}
{% block content %}
<h1>Report</h1>
{{ metric('Completed items', completed, 'completed-count') }}
<button type="button" class="secondary" data-open-dialog="about-report">About this report</button>
{% call dialog('about-report', 'About this report') %}
<p>This view uses your existing Python service.</p>
{% endcall %}
{% endblock %}
```

Register a router and UI configuration in your application composition:

```python
from pathlib import Path
from fastapi import APIRouter, Request
from app.app import create_app
from pwaf_foundation.ui import NavigationItem, UIConfig, render_page

router = APIRouter()


@router.get("/report", include_in_schema=False)
async def report(request: Request):
    return await render_page(request, "report.html", completed=0)


application_dir = Path(__file__).parent
application = create_app(
    routers=[router],
    ui=UIConfig(
        template_dir=application_dir / "templates",
        static_dir=application_dir / "static",
        navigation=(NavigationItem("Report", "/report"),),
    ),
)
```

Create the directories before registering them. Navigation paths must be local.
`render_page` supplies current settings, navigation, pane definitions, and field
schemas. Template overrides are searched before foundation defaults. Replace
`base.html` to replace the entire layout, or extend its `title`, `head`, `content`,
and `scripts` blocks. A replacement base owns its browser scripts and accessibility.

Assets have named routes `foundation_static` and, when registered, `app_static`.
Use `url_for('app_static', path='report.js')`; do not edit foundation assets to add
a page. The provided macros are `button(label, type='button', class='secondary',
id=none)`, `setting_field(name, spec)`, `metric(label, value, id)`, and call-block
`dialog(id, title)`. Dialog buttons use `data-open-dialog` and `data-close-dialog`
with a local element ID; Escape closes native dialogs and focus returns to the
opener. The settings dialog additionally protects in-flight saves from dismissal.

The sibling UI reference was absent during implementation. The default design is
self-contained: a restrained sidebar, responsive cards, light/dark themes, clear
focus indicators, and a split settings dialog. No external fonts, images, or build
pipeline are required.

## Add an independently saved settings pane

Subclass `FoundationSettings` with validated, defaulted fields, then register their
ownership:

```python
from pydantic import Field
from pwaf_foundation.settings import FoundationSettings
from pwaf_foundation.ui import SettingsPane, UIConfig


class ToolSettings(FoundationSettings):
    repetitions: int = Field(default=3, ge=1, le=100, title="Repetitions")


ui = UIConfig(settings_panes=(SettingsPane("tool", "Tool", ("repetitions",)),))
# Pass settings_schema=ToolSettings and ui=ui to create_app.
```

The foundation owns `general` (`app_name`, `theme`). Keys and field ownership must
be unique; fields must exist in the schema. The default renderer supports strings,
integers, numbers, and string literal enums. Override `settings.html` or
`components.html` for other structures. Persisted settings never contain secrets.

The browser saves only the active pane through `PATCH /api/settings/panes/{key}`.
The server rejects fields belonging to another pane and validates the resulting
settings snapshot before saving. `PATCH /api/settings` remains available for
explicit whole-schema clients. Theme preview is temporary until General is saved;
closing or pressing Escape restores the last saved theme. A save in another pane
does not implicitly save pending General edits.

## Wrap an importable tool

First separate computation from CLI parsing. Keep a function that accepts validated
parameters and returns a small JSON-compatible result. Both interfaces call it.
For cooperative blocking I/O, register `FunctionAdapter`:

```python
from pydantic import BaseModel, ConfigDict, Field
from pwaf_foundation.adapters import FunctionAdapter
from pwaf_foundation.jobs import JobDefinition


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    count: int = Field(default=3, ge=1, le=100)


def run_tool(parameters, context):
    values = []
    for index in range(parameters["count"]):
        context.checkpoint()
        # Replace with one bounded unit of I/O, using its own timeout.
        values.append(index * index)
        context.progress((index + 1) / parameters["count"])
    return {"values": values}


def jobs(database):
    return {"tool": JobDefinition(ToolInput, FunctionAdapter(run_tool), timeout=10)}


# Pass job_factory=jobs to create_app. No jobs are enabled when this is omitted.
```

The thread must check cancellation and use bounded I/O. Cancellation/timeout waits
for cooperative cleanup; Python cannot forcibly stop an uncooperative thread.
Use a child process for CPU-heavy work or tools requiring enforced termination.
The example follows that pattern: `app.services.performance.benchmark` is the
shared computation, `app.cli` is the CLI wrapper, and `app.example.performance_jobs`
registers the web adapter.

## Wrap a command-line executable

Choose the executable in source/configuration trusted by the application. Build an
argument list from a strict input schema. Never accept executable paths, shell
fragments, or an unrestricted argument list from a browser.

```python
import sys
from pwaf_foundation.adapters import SubprocessAdapter
from pwaf_foundation.jobs import JobDefinition
from app.services.performance import PerformanceInput

adapter = SubprocessAdapter(
    lambda parameters: [
        sys.executable,
        "-m",
        "app.cli",
        "--iterations",
        str(parameters["iterations"]),
    ],
    output_limit=65536,
)
# Supply an explicit cwd if the executable requires one.
# Register JobDefinition(PerformanceInput, adapter, timeout=30).
```

`SubprocessAdapter` returns `stdout`, `stderr`, and `returncode`. Parse and validate
structured output in an application wrapper before returning or saving it. The
performance example returns a `PerformanceResult`, not raw command output. Other
tools' output should be treated as untrusted text, never safe HTML. Nonzero exit
codes and output overflow produce safe domain errors without returning raw stderr.

See [job lifecycle and limits](jobs.md) for cancellation and process ownership.

## Save results and remove the example

Use an application-owned migration namespace and repository, as demonstrated by
`app/migrations` and `app/services/results.py`. A job's optional asynchronous `save`
callback receives its identifier and result, offloads blocking storage, and returns
only after the transaction succeeds. A failed save makes the job fail. Result
history contains successful persisted measurements; in-memory job state is separate.

To replace the demonstration:

1. Change `app/__main__.py` to compose your options through `create_app` instead of
   calling `create_example_app`.
2. Replace example routers, settings, UI configuration, and `job_factory` with your
   own. Keep the runtime configuration and startup validation.
3. Remove the unused example CLI, services, templates, and assets from your source
   copy. Preserve migrations/data for installations you have already distributed;
   omitting a namespace does not delete existing tables.
4. Update branding, documentation, and application tests. Preserve the foundation's
   tests and version source; use a separate application version if needed.

`tests/test_example.py` includes a second tiny application demonstrating independent
routes, settings, migrations, assets, navigation registration, and a replaced base
layout. Tests and the browser harness use temporary storage, never your runtime data.

## Import package compatibility

Since `v0.26.264.6`, use `pwaf_foundation` instead of `foundation` in imports.
The old name collides with macOS PyObjC’s `Foundation` package on case-insensitive
filesystems, so no alias is installed. Existing settings, database tables, migration
namespaces, and static URLs are unchanged. Update derived-app imports when upgrading.

For time-series displays, optionally enable the shared [Graphum window](graphs.md)
with `UIConfig(graph_enabled=True)`. Your application defines its available metrics
and supplies their data through `PWAF.graph.setSeries(...)`.

## Settings and alternative layouts

`UIConfig.general_settings_fields` defaults to `("app_name", "theme")`. To put an
application field in General, include it explicitly; existing unknown-field and
cross-pane ownership validation still applies:

```python
from pydantic import Field
from app.app import create_app
from pwaf_foundation.settings import FoundationSettings
from pwaf_foundation.ui import UIConfig

class Settings(FoundationSettings):
    repetitions: int = Field(default=3, ge=1, le=100)

application = create_app(settings_schema=Settings, ui=UIConfig(
    general_settings_fields=("app_name", "theme", "repetitions"),
))
```

Shared browser code emits `settings-loaded` after a successful dialog load and
`settings-saved` after a successful save. Both events carry recognized settings
in `event.detail`. Listen to the load event to populate application-owned dynamic
selectors; failed loads and saves emit neither success event. Never put secrets in
settings or these events. For example:

```javascript
document.addEventListener('settings-loaded', event => {
  document.querySelector('#saved-repetitions').textContent = event.detail.repetitions;
});
```

Application layouts may omit the menu/navigation or the entire Settings feature.
When including Settings, keep the complete shared dialog and control IDs; partial
copies are not a supported component contract. Navigation initializes independently.

## Native title and close policy

Desktop apps can pass `title`, `confirm_exit`, and `quit_message` without editing
shared code. With no predicate, the previous immediate-close behavior remains.
The predicate runs in a background thread and returns whether a native prompt is
needed; it must be quick and thread-safe. False skips the prompt, but still waits
for cleanup before closing. A declined prompt leaves the app running.

```python
from app.app import create_example_app
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.desktop import launch_desktop

config = RuntimeConfig.from_env()
launch_desktop(create_example_app(config), config, title="My Tool",
               confirm_exit=lambda: True, quit_message="Stop work and quit?")
```

Accepted close requests stop the owned server and wait up to 35 seconds for
lifespan cleanup; repeated requests do not create duplicate prompts. A cleanup
failure is logged and the window stays open. This hook does not make in-memory
jobs durable or guarantee cleanup after a forced process kill. POSIX listeners
allow immediate address reuse; Windows listeners retain exclusive ownership.
