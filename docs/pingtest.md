# From PWAF to PingTest with an AI coding agent

This is a build brief and walkthrough for a new derived application. **PingTest is
not shipped or implemented by this document.** The foundation currently ships the
performance example. The commands in the final acceptance section apply after the
agent implements PingTest.

## Clone, prepare, and establish the baseline

Use the cloning commands and agent prompt in the [README](../README.md#create-your-own-app-pingtest-walkthrough).
Clone into a separate `PingTest` directory. A local source path is also a valid
Git clone source, provided it contains the committed implementation you want.
If the foundation has no commits yet, commit the intended source snapshot before
cloning; copying a working folder is a different operation and needs explicit
exclusions for environments, data, build output, and credentials.

Inside the new clone on macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt -r requirements-desktop.txt
python -m playwright install chromium
python -m pytest -q -W error
python -m app.desktop
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m app.desktop
```

This launches the existing example to establish a baseline. Close it before
starting another app on the same port. Desktop prerequisites are described in
[installation](installation.md). For a headless project, omit desktop requirements
and start `python -m app` instead.

Fill in [APP_BRIEF.md](../APP_BRIEF.md) using the PingTest choices below. Open the
clone in your agent tool, provide that brief and the README's prompt, and review
its plan. Use the [personalization checklist](personalizing.md) for the broader
branding, runtime isolation, and delivery requirements.
A useful first milestone is a CLI test against `127.0.0.1`, followed by the same
operation through a web job. Do not ask the agent to rebuild working foundation
services from scratch.

## Decide the app's identity and scope

| Item | PingTest choice |
| --- | --- |
| Directory / new repository | `PingTest` |
| Python distribution (`project.name`) | `pingtest` |
| Python application module | Keep `app`; retain `python -m app`, `app.desktop`, and `app.cli` |
| Reusable package | Keep `pwaf_foundation`; do not rename it to `foundation` |
| Display identity | `PingTest` in settings defaults, page titles, native window, and manifest |
| Feature | A validated host and packet count, Run/Cancel, result summary, saved history, graphs |
| First graph | Round-trip latency in milliseconds; dropped packets are null gaps |
| First targets | Loopback on the development OS; additional OSes tested separately |
| First update model | Display samples after a bounded run completes; streaming is a later feature |

A directory rename alone does not update product identity. Ask the agent to inspect
all user-facing names and installed launchers. Use an application settings subclass
for new defaults; do not rewrite saved settings. Prefer template/static overrides
for application branding. The native launcher currently has a default window title;
if customization needs a new argument, add a small reusable title option and pass
`PingTest` from the app, rather than hardcoding PingTest in the foundation. Replace
manifest/icon branding deliberately using the [icon guide](icons.md).

Keep the inherited version scheme unless you explicitly adopt a separate app
version and update packaging consistently. Do not mass-replace `PWAF` in internal
markers, configuration variables, or package imports. Changing those contracts is
a separate compatibility decision.

## Build in application-owned layers

These are proposed derived-app files, not existing PingTest implementations:

| Layer | Proposed location and responsibility |
| --- | --- |
| Service | `app/services/ping.py`: validation, platform command construction, bounded execution, output parsing, normalized samples |
| CLI | `app/cli.py`: arguments and JSON/text output, delegating to the same service used by web jobs |
| Persistence | `app/migrations/` and `app/services/ping_results.py`: run summaries and ordered samples with additive migrations |
| Composition | `app/app.py` plus an app-owned integration module: register the ping operation, settings, routes, and UI |
| UI | `app/templates/ping.html`, `app/static/ping.js`: form, job status, cancellation, saved runs, graph integration |
| Tests | Service fixtures, route/job tests, persistence tests, and updated browser/install verification scripts |

Use the existing [job contracts](jobs.md). Register an operation named `ping` with
validated parameters, an explicit timeout, and a save callback. Keep route handlers
thin. Job requests still require CSRF and idempotency keys; call `PWAF.api` from the
browser. Replace the performance navigation and its example-specific verification
expectations as part of completing the derived app.

For persistence, store a run ID, target, UTC start/completion times, sent/received
counts, loss percentage, and individual samples. A sample should include its
sequence, timestamp, response status, and nullable latency. Commit a run and its
samples atomically. Keep timestamps consistent with the foundation's UTC convention.
Do not drop inherited tables or saved data during an upgrade just because the UI
no longer displays the performance example.

## Wrap the ping command carefully

Examples of short manual loopback checks are:

```sh
# macOS / Linux
ping -c 5 127.0.0.1
```

```powershell
# Windows
ping -n 5 127.0.0.1
```

The app must build an argument list for the actual OS; these flags are not a shared
cross-platform command string. Locate the executable on the server with
`shutil.which`, keep executable selection server-controlled, validate a hostname
or IP address, reject option-like input, and bound the packet count (for example,
1–20). Do not accept arbitrary command lines, shell options, or `shell=True`.
Document whether the first version supports IPv4 only or both address families.

Give each run an overall deadline and bounded output capture. A cancelled or timed
out job must terminate and reap the ping child. If DNS resolution is needed, its
work must also be bounded. Keep process ownership explicit: a wrapper CLI that
spawns ping introduces a descendant process, and the existing Windows subprocess
adapter only owns its direct child. Prefer a shared app service that owns ping
directly from either the CLI or the job worker.

**Packet loss is a measurement outcome.** The generic `SubprocessAdapter` currently
raises `tool_failed` for every nonzero exit, so using it unchanged may discard
useful ping output. Implement app-owned handling for platform-specific return codes
and stdout/stderr: distinguish packet loss from an invalid invocation, unavailable
executable, permissions, or unparseable output. Reuse the lifecycle approach without
weakening the foundation's generic failure handling for unrelated tools.

Output formats, locales, timeout flags, and return codes vary by platform. Test
parsers against captured fixtures for each supported OS, including decimal latency,
`time<1ms`, partial/total loss, and unreachable targets. A reported upper bound is
not an exact zero; preserve the qualifier or present a documented bound in the UI.
Missing replies use `latency_ms=null`, not zero. If reply lines lack timestamps,
record how sample times are assigned and label estimated times honestly.

## Enable the reusable graph window

The app chooses the metrics; the foundation supplies the window and renderer. Add
`graph_enabled=True` to the application's `UIConfig`, alongside its template paths,
navigation, and settings panes. Graphum remains disabled in unrelated apps.

After retrieving a saved run with a `samples` array, the app can map its own result
schema to the graph API:

```javascript
PWAF.graph.setSeries([{
  id: 'latency',
  label: 'Round-trip latency',
  unit: 'ms',
  points: run.samples.map(sample => ({
    x: Date.parse(sample.recorded_at),
    y: sample.latency_ms
  }))
}]);
PWAF.graph.open();
```

Use this once `DOMContentLoaded` has fired and the asynchronous result is ready.
This example assumes the app's API supplies valid ISO UTC timestamps and nullable
numeric `latency_ms`; adapt it to the implemented schema. Keep loss counts and
percentage in a summary unless you deliberately define another useful series.

Graphum uses trailing ranges relative to the current time, from one hour through
29 days. Recent loopback samples work with the default range; an older saved run
can fall outside it. Arbitrary historical-run ranges or live sample streaming need
an explicit app requirement and, if needed, a generic extension. Do not imply that
the existing component already supports them. See [Graphum](graphs.md) for limits,
null handling, selection, and template overrides.

## Verify and deliver

After implementation, the agent should make these proposed commands work:

```sh
python -m app.cli --host 127.0.0.1 --count 5
python -m app.desktop
```

In the web/native UI, run the same target, review the packet summary, open Graphum,
and confirm that the latency points match the service result. Browser access uses
the same server. Also verify:

- Invalid hosts/counts are rejected before launching a process.
- A real loopback run completes; deterministic fixtures exercise loss and parser cases.
- Timeout and Cancel leave no owned ping process running and keep the UI responsive.
- Zero latency remains visible; loss creates gaps; all-loss runs produce an honest
  summary/empty plot rather than fabricated values.
- Settings and completed results survive restart; migrations preserve prior data.
- The gear, optional graph window, keyboard focus, and mobile layouts work.
- A built package and real install work outside the source checkout, including
  pywebview startup and simultaneous browser access.

Run the derived project's tests, Ruff, browser checks, and packaging/install checks.
Adapt foundation-example smoke scripts that still expect `/performance`, hashing
results, or its original branding. Keep reusable framework regression checks.
Report supported-platform fixtures separately from real OS verification.

Finally, update the derived README and AGENTS.md to describe PingTest's actual
entrypoints, parameters, schemas, metrics, and limitations. Do not claim planned
features work until implemented and checked. Leave the source foundation checkout
unchanged; publish to the new app's remote only when the user authorizes it.
