# Graphum: reusable graph window

Graphum is an optional development component, disabled by default. An application
opts in when composing its UI:

```python
from app.app import create_app
from pwaf_foundation.ui import UIConfig

application = create_app(ui=UIConfig(graph_enabled=True))
```

Add `graph_enabled=True` to an existing `UIConfig` alongside its navigation,
templates, and settings panes. This is a developer choice, not a user setting.
When disabled, the toolbar button, dialog, and graph script are omitted; the
reusable assets remain packaged. The default performance example leaves it off.

When enabled, a graph button appears beside the Settings gear. It opens a
large native HTML dialog adapted from Caelus Graphum: time ranges and metric
selection on the left, a dark plotting area on the right, and stacked controls on
mobile. Close with the upper-right button, Escape, or a click outside the dialog.
Keyboard focus returns to the toolbar opener.

The application owns which metrics are available, their labels and units, how data
is fetched, and any domain-specific selection rules. The bundled selector lists
only the metrics supplied by that app; applications can replace the selector via
a `graph.html` template override.

The enabled window starts with an empty state. It does not fetch weather data or
invent application observations. Supply data from your own service/API through
an application script loaded in the base template's `scripts` block:

```javascript
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const result = await PWAF.api('/api/my-tool/history');
    PWAF.graph.setSeries([{
      id: 'elapsed',
      label: 'Execution time',
      unit: 'ms',
      points: result.rows.map(row => ({
        x: Date.parse(row.recorded_at), // Unix milliseconds, not seconds
        y: row.elapsed_ms              // finite number, or null for a gap
      }))
    }]);
  } catch (error) {
    // Show failure in your application's existing visible status area.
    PWAF.status(document.querySelector('#history-status'), error.message, true);
  }
});
```

`PWAF.graph` is ready when `DOMContentLoaded` fires. Methods:

- `setSeries(series)` validates and copies the full input before replacing data.
  Each series requires a unique nonempty string `id`, a string `label`, optional
  string `unit`, and a `points` array. Points have numeric epoch-millisecond `x`
  and numeric or null `y`. Invalid input throws `TypeError` without replacing
  existing data. Limits are 100 available metrics and 5,000 points per metric;
  aggregate larger histories in application services before supplying them.
- `open()` / `close()` control the dialog programmatically.
- `refresh()` redraws supplied data against the current clock. No polling is
  started by the foundation; call `setSeries` when your application receives updates.

The first metric is selected initially; users can select up to four. Data is
sorted by timestamp and filtered to the selected trailing range (1 hour through
29 days). Future points are excluded. Each metric has its own labeled scale and
unit, so unrelated units are not mixed on a single axis. Nulls break lines; zero,
negative, constant, and single-point series are supported. Tick labels use local
time. Each graph has an accessible text description and a visible observation
count, minimum, maximum, and latest value. Labels are inserted as text, never HTML.

Derived applications can override `graph.html` through `UIConfig.template_dir`
or replace the graph assets through a custom base template. Keep element IDs if
using the bundled JavaScript. This is an in-page window; closing it leaves the
application and server running.

The reusable SVGs live at `static/icons/settings-gear.svg` and
`static/icons/dashboard-graph.svg`. CSS masks allow both to inherit the toolbar's
current text color across light and dark themes. The gear is original SVG artwork;
the graph glyph is adapted from Caelus, with generic labeling and theme-aware color.

## Application time ranges and live refreshes

Use hours as the unit, including fractions for minutes; default ranges are unchanged:

```python
ui = UIConfig(graph_enabled=True,
              graph_ranges=((1/60, "1min"), (5/60, "5min"), (1, "1hr")),
              graph_default_hours=1/60)
```

Ranges must be nonempty, finite, positive, and unique, with a nonempty label and
a default included in the range list. The initial selection comes from the
rendered template. No `graph.html` copy is needed to change these controls.
`setSeries()` retains existing metric controls when IDs, labels, and units match,
so live updates preserve checkbox focus. Plot replacement preserves ancestor
scroll positions at desktop and mobile sizes. Applications still own polling,
sampling, data bounds, and missing-value semantics.
