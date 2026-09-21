# pywebapp_foundation

A browser-first Python foundation for adding a web interface to existing tools.
Reusable infrastructure lives in `pwaf_foundation/`; replaceable application composition
lives in `app/`. Python 3.10 or newer is required.

The foundation includes a responsive UI, JSON settings, SQLite migrations,
cancellable jobs, and a CLI-to-web performance example. Standalone installers (with a native folder picker),
a native desktop window, password-free LAN access, and optional HTTPS
password authentication are implemented.

## Personalize your cloned app

Start by filling in [APP_BRIEF.md](APP_BRIEF.md) in your clone. Give that brief to
your agent alongside [AGENTS.md](AGENTS.md), then follow the
[personalization checklist](docs/personalizing.md). The brief describes your app;
it is not automatically loaded as runtime configuration.

| Decision | What to personalize |
| --- | --- |
| Identity | Display/window/API titles, repository and distribution names, version, author/support information |
| Appearance | Product icons, colors, typography, light/dark defaults, sidebar and header/footer text |
| Features | Landing page and navigation, removal of the performance demo, optional Graphum, app-owned metrics |
| Settings and data | Validated app settings, migrations, retention/export/backup policy, preserved user preferences |
| Operation | Separate installation/data directories, available port, desktop/browser/LAN choices, explicit shortcut requirements |
| Delivery | Metadata/notices, app-specific tests, clean install and upgrade verification, release and upstream-update process |

Ask the agent to map these decisions to actual files, implement through application
extension points, and record verification and remaining limitations in the brief.
Unfilled fields are open decisions, not permission to invent product requirements.
Use the PingTest walkthrough below as an example of that process.

## Create your own app: PingTest walkthrough

Clone this foundation into a separate project, then use your AI coding agent to
replace the example under `app/` with your application's behavior. Keep the shared
services in `pwaf_foundation/` reusable. **PingTest below is a development example,
not an application already included in this repository.**

### 1. Clone and name the project

The foundation repository is private; your GitHub account must have access.
Authenticate Git with GitHub, then run these commands from your projects directory:

```sh
git clone https://github.com/mot-yelraf/pywebapp_foundation.git PingTest
cd PingTest
git remote rename origin upstream
git switch -c build-pingtest
```

The folder is now `PingTest`; this does not change the UI name, Python distribution
name, or native window title. Those are separate branding steps for the agent.
To start from a local repository instead, use its path as the clone source. Git
copies committed files only: commit the intended foundation snapshot first. A
clone does not include uncommitted implementation files, `.venv`, or runtime data.

Keep `upstream` pointing to the foundation. When you create your own Git repository,
add its URL as `origin`; publish only when you choose to. See the
[detailed PingTest guide](docs/pingtest.md) for environment setup and naming details.

### 2. Give the agent the app brief

Open **the PingTest folder** in your coding tool. Ask the agent to read `AGENTS.md`
and your completed `APP_BRIEF.md`, inspect the existing code, and propose a short implementation
plan before building. A useful starting prompt is:

> Build a new application named PingTest in this cloned repository. Read AGENTS.md,
> my completed APP_BRIEF.md, and docs/pingtest.md first. Replace the performance demo with a host field,
> a packet-count field, and Run/Cancel controls. Use the operating system's ping
> command through a bounded, cancellable Python service shared by CLI and web jobs.
> Persist completed results and individual samples in SQLite. Enable optional
> Graphum and supply PingTest's own latency metric in milliseconds, showing lost
> packets as gaps. Keep application behavior in app/ and reuse the foundation's
> settings, jobs, persistence, errors, and desktop/browser startup. Use PingTest
> branding and the distribution name pingtest while preserving the app module
> entrypoints. Plan the work, then implement and verify it when I approve the plan.
> Start with loopback tests; report which operating systems were actually tested.

Tell the agent your target OS, additional requirements, and whether the first
version needs live updates or completed-run graphs. This example starts with
completed-run graphs and a finite packet count.

### 3. Build and verify in small steps

1. Establish a clean baseline; create the clone's virtual environment and run tests.
2. Set project identity, then implement and test the ping service and CLI independently.
3. Register a cancellable job, add SQLite migrations/history, and replace the demo UI.
4. Enable `UIConfig(graph_enabled=True)` and pass PingTest-defined metrics and samples
   to `PWAF.graph.setSeries(...)`. The foundation does not define ping metrics.
5. Check input validation, packet loss, timeouts, cancellation, persistence, and
   desktop/mobile layouts. Run the CLI and web UI against the same loopback target.
6. Update the derived project's README and AGENTS.md, build its package, and verify
   a real installation into a separate folder with pywebview and browser access.

The [PingTest build guide](docs/pingtest.md) gives the proposed file layout, command
handling rules, graph mapping, and acceptance checklist. The agent should deliver
working changes plus actual verification results, not only a plan or code snippets.

## Give your cloned app its own icons

In your **cloned project**, replace PWAF's artwork with your application's identity
(for example, a PingTest icon). Changing `app_name` or the repository name does not
change the icons. The simplest supported workflow keeps the existing filenames
and replaces their contents, so browser links and the desktop launcher still work.

1. Replace `pwaf_foundation/static/icons/pwaf.svg` with your master artwork. Keep a
   `512 × 512` viewBox, a direct child background `<rect>`, and a direct child `<g>`
   containing the foreground mark: the generator uses that structure to create
   opaque mobile icons and the padded Android maskable variant. Update the SVG's
   accessible label. If your artwork uses a different structure, adapt the generator
   rather than assuming an arbitrary SVG or PNG can be dropped into it.
2. With the clone's virtual environment active, regenerate **all** platform assets:

   ```sh
   python -m pip install -r requirements-dev.txt
   python -m playwright install chromium
   python scripts/generate_icons.py
   ```

3. Update `pwaf_foundation/static/manifest.webmanifest`: app `name`, `short_name`,
   description, and theme/background colors. Match the `theme-color` in
   `pwaf_foundation/templates/base.html`. Review manifest `id`, `start_url`, and
   `scope` for the app's actual deployment. Update the generator's app-catalog
   author metadata if appropriate; keep it reproducible rather than editing only
   generated files.
4. Check the sidebar logo, browser favicon, iOS touch icon, Android standard/maskable
   icons, and macOS Dock icon. The generator also produces macOS ICNS/iconset, an
   iOS app-icon catalog, and Windows ICO assets for downstream packaging. Keep
   mobile backgrounds opaque and foreground artwork within the maskable safe area.
5. Run `python -m pytest tests/test_icons.py`, build with `python -m build`, and
   confirm the wheel includes the regenerated assets. Reinstall the derived app,
   close/reopen its desktop window, and check a fresh browser session. A cached
   favicon or existing home-screen shortcut may retain the old artwork; refresh
   or recreate it when verifying. Commit the master SVG, generator changes, and
   generated assets together when you commit your app.

Keeping the `pwaf-*` asset filenames does not keep PWAF artwork or branding on screen.
If you prefer names such as `pingtest-*`, update the generator, template/sidebar
links, manifest paths, desktop icon path, icon-catalog metadata, packaging rules,
and tests together. See [icon locations and customization options](docs/icons.md#derived-application-customization)
for the complete reference, including application-owned assets.

The Settings gear and Graphum glyph are reusable control icons; they do not need
to change when replacing your product logo.

## Run locally

On macOS, Linux, or Raspberry Pi:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m app
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app
```

Open <http://127.0.0.1:8191>. API documentation is at `/docs`, the OpenAPI schema
is at `/openapi.json`, and readiness is at `/healthz`. Stop the server with Ctrl+C.
These source browser commands do not require desktop dependencies. The default launcher includes the performance
example at `/performance`; the generic `create_app` factory also works without jobs.

Local mode is the default. To use the app from another LAN device, select LAN mode;
**password authentication is off by default**. For example:

```sh
PWAF_MODE=lan PWAF_PUBLIC_ORIGIN=http://192.168.1.50:8191 .venv/bin/python -m app
```

Replace the address with this machine's LAN address. Optional password-protected
HTTPS access uses a same-machine Caddy proxy. See [deployment](docs/deployment.md)
for both choices and PowerShell examples. Run one process per data directory.

For a standalone installation, run `./install.sh` (macOS/Linux/Raspberry Pi) or
`install.ps1` (Windows). The installer includes pywebview; the installed `run.sh`
or `run.ps1` opens the native app and serves the same UI at http://127.0.0.1:8191
for browser access. Use `--browser-only` (`-BrowserOnly` on the Windows installer)
for a headless installation. See [installation and upgrades](docs/installation.md)
for destinations, launchers, backups, restoration, and uninstall behavior.

## Configuration

| Variable | Default | Behavior |
| --- | --- | --- |
| `PWAF_HTTP_HOST` | `127.0.0.1`; `0.0.0.0` for direct LAN | IP or localhost; local/proxy mode stays on loopback. |
| `PWAF_HTTP_PORT` | `8191` | Integer from 1 to 65535. |
| `PWAF_DATA_DIR` | `./data` | Resolved from the startup working directory; use an absolute path for a stable installation. |
| `PWAF_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |

LAN selection also uses `PWAF_MODE`, `PWAF_LAN_AUTH`, and `PWAF_PUBLIC_ORIGIN`.
The complete [environment reference](docs/deployment.md#environment-reference)
includes optional proxy credentials and user allowlists.

Invalid explicit values stop startup. These variables configure the process and
are not editable through the settings API or written into JSON. No variables
currently overlap editable settings, so there is no persisted override layer.
The data directory is logged at startup and contains `app.sqlite3` plus
`settings.json` after the first settings update. Neither belongs in source control.

Editable settings include `app_name` (1–100 characters), `theme` (`light`/`dark`),
and the example's `default_iterations` (1–5,000,000). The Settings dialog saves
General and Performance independently. A missing file uses
defaults. Invalid individual fields produce warnings and fall back to defaults;
unknown fields survive writes without being returned by the API. Invalid whole-file
JSON stops startup and remains untouched for repair or restoration.

## API

| Method and path | Purpose |
| --- | --- |
| `GET /healthz` | Required-service readiness; 200 or 503. |
| `GET /api/csrf` | Read the process-lifetime CSRF token. |
| `GET /api/settings` | Read recognized editable settings. |
| `PATCH /api/settings` | Validate and atomically save supplied fields. |
| `PATCH /api/settings/panes/{key}` | Save only fields owned by a registered pane. |
| `POST /api/jobs` | Submit a registered operation with an `Idempotency-Key`; returns 202. |
| `GET /api/jobs/{id}` | Read temporary job status and result/error. |
| `POST /api/jobs/{id}/cancel` | Request cancellation of unfinished work. |
| `GET /api/results` | Read saved successful measurements with `offset`/`limit` pagination. |

Every mutation requires an allowed `Origin` and an `X-CSRF-Token` header. The token
changes on restart. Host validation includes the configured origin/port. Proxy identity is accepted
only in opt-in proxy mode after verifying the local peer and shared token; arbitrary
forwarding headers are not trusted. Responses are not cached and unrestricted
CORS is not enabled.

For a same-origin page, the API interaction is:

```javascript
const { csrf_token } = await fetch('/api/csrf').then(r => r.json());
const response = await fetch('/api/settings', {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf_token },
  body: JSON.stringify({ app_name: 'My Performance Tool' })
});
const result = await response.json();
if (!response.ok) throw new Error(result.error.message);
```

The browser supplies `Origin`. Command-line clients must supply it explicitly,
including the configured port. API errors use `error.code`, `error.message`, and
`error.details`; submitted values and internal exception messages are not echoed.
Malformed JSON with a JSON content type returns 400; invalid field values return 422.

## Try the example

Open `/performance`, choose an iteration count, and run or cancel a benchmark.
Successful measurements remain in SQLite after restart. Run status and idempotency
keys are temporary; jobs do not resume after restart. The web server stays responsive
because CPU work runs in a child process.

The same service works without the web server:

```sh
.venv/bin/python -m app.cli --iterations 100000
```

The CLI prints JSON containing `iterations`, `elapsed_ms`, and `checksum`. The
checksum is deterministic for a given count; measured elapsed time naturally varies.
CLI invocation does not save results or create a settings/database file.

## Extend and verify

- [Architecture and extension guide](docs/architecture.md): working settings,
  router, migration, and readiness examples and resource ownership contracts.
- [Extension walkthrough](docs/extending.md): add a page, settings pane, or tool;
  replace the example without editing foundation modules.
- [Job lifecycle and limits](docs/jobs.md): capacity, idempotency, cancellation,
  process ownership, and persistence.
- [Implementation plan](docs/implementation-plan.md): completed phases and verification scope.
- [Verification record](docs/verification.md): local results, repeatable commands,
  and unverified platforms.
- [Troubleshooting](docs/troubleshooting.md): startup, LAN, jobs, and recovery.
- [Agent instructions](AGENTS.md): repository conventions and target interfaces.

With the virtual environment active:

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q -W error --cov --cov-report=term-missing
ruff check .
python3 -m compileall -q pwaf_foundation app tests scripts
python3 scripts/smoke_verify.py
python3 -m playwright install chromium
python3 scripts/playwright_verify.py
python3 scripts/verify_clone.py
python3 scripts/verify_lan.py
python3 -m build
```

The smoke script needs `curl`, uses temporary data and an available loopback port,
and stops its server afterward. Packaging derives the version from
`pwaf_foundation/__init__.py` (packaging normalizes the leading `v`). Development
requirements are split so the package's `dev` extra and source checkout share the
same test tools. The current coverage gate is 95% for statements and branches
combined; it complements explicit failure-path tests.

Verified locally on macOS ARM64 with Python 3.13: strict-warning tests, the 95%
coverage gate, Ruff, browser checks, real installation/reinstallation, native window
startup/shutdown, and a clean-copy application adaptation. See the verification
record for exact results and optional proxy checks. The configured cross-platform
CI matrix has not run here; Windows, Linux, and physical Raspberry Pi runtime
behavior remain unverified on those actual platforms.

PWAF includes original platform icons for macOS, iOS, Android, and browsers.
See [icon assets and regeneration](docs/icons.md).

The shared toolbar includes a Settings gear. App developers can opt into the
[Graphum graph window](docs/graphs.md) with `UIConfig(graph_enabled=True)` and
supply their application-specific metrics and data.
