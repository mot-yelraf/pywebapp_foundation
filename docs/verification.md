# Verification record

Current version: `v0.26.264.10` (2026-09-21).
The results below record local verification. Remote CI results are available in
[GitHub Actions](https://github.com/mot-yelraf/pywebapp_foundation/actions).

## Initial publication preflight

For `v0.26.264.10`, browser desktop/mobile, live HTTP, clean-copy adaptation,
direct LAN, and real browser-only install/reinstall checks passed on macOS before
initial publication. Installation checks preserved saved settings and SQLite results.
Ruff, syntax checks, and shell parsing passed. The latest strict-warning unit run
passed 107 tests with 98.62% combined coverage and 100% desktop-module coverage.
A scan of commit candidates found no credential-pattern matches; ignored runtime
data, environments, caches, and build outputs were excluded. Remote platform runs
must be assessed from GitHub Actions, independently of these local results.

## Desktop failure-path coverage

Version `v0.26.264.10`: all 107 tests passed on macOS/Python 3.13.9 with warnings
as errors. Combined statement/branch coverage is 98.62% against the 95% gate;
`pwaf_foundation/desktop.py` covers all 82 statements and 20 branches (100%).
Ruff passed. The existing CI command automatically includes the added tests.

New checks cover readiness status/connection failures and response closure,
unexpected server exit/crash closing the window, GUI creation/start failure cleanup,
bounded shutdown of an uncooperative worker, scheduled macOS icon application,
missing icon/support warnings, and avoiding Cocoa imports on other platforms.
Lifecycle tests use real threads with controlled server/GUI doubles; the shutdown
timeout test shortens only the wait and explicitly releases/joins its test workers.
Platform icon tests use mocked modules, not real Windows/Linux/macOS UI execution.
No desktop runtime behavior changed, and native smoke checks were not rerun for
this test-only change (apart from the required version metadata update).

## Optional Graphum development component

Version `v0.26.264.9`: 93 tests and Ruff passed. Route tests verify Graphum
markup/script are absent by default and present only with `UIConfig(graph_enabled=True)`.
The browser harness explicitly enables Graphum in its test application; production
defaults stay disabled. Metric definitions and data remain application-owned.

## Settings gear and reusable Graphum

Version `v0.26.264.8`: all 91 pytest tests and Ruff passed. Playwright verified
Settings access through the SVG gear, Graphum empty and populated states, metric
selection limits, escaped labels, range selection state, Escape/close focus
restoration, and populated mobile layouts at 390px and 320px. Desktop and mobile
screenshots were visually reviewed. Graphum accepts app-supplied data through
`PWAF.graph`; no domain data endpoint or background polling is introduced.

## PWAF platform icon set

Version `v0.26.264.7`: 91 tests and Ruff passed. The SVG and generated PNG
were visually checked; macOS `sips` decoded the generated ICNS. All 22 icon assets
are present in the built wheel. Playwright desktop/mobile checks and the real
pywebview startup/page-load/browser-access/shutdown check passed. iOS/Android
home-screen rendering and Xcode catalog import remain unverified.

## macOS installed-package collision fix

Version `v0.26.264.6` renames the import package to `pwaf_foundation` to avoid
colliding with PyObjC’s `Foundation` directory on case-insensitive filesystems.
A real desktop installation into `~/PWAF` passed staging and activation. Running
`scripts/verify_desktop.py --installed` with that release’s isolated Python passed
native page load, simultaneous browser HTTP access, and window/server shutdown.
The installed activation selects desktop mode. All 89 tests, Ruff, and compileall
passed. The namespace regression test prevents reuse of the conflicting name.

## Default desktop installation update

Version `v0.26.264.5`: all 88 tests passed with warnings treated as errors.
Ruff, compileall, and shell syntax checks passed. Installer/launcher tests verify
that default installs include desktop dependencies and select `app.desktop`, while
explicit browser-only installs omit them and start `app`. Existing activation files
without a mode keep their previous browser behavior until reinstallation. The real
macOS pywebview smoke check passed page loading, simultaneous browser HTTP access,
window closure, and server shutdown. Windows native execution remains unverified.

## Native installer folder selection update

Version `v0.26.264.4`: `python -m pytest -q -W error` passed all 81 tests;
Ruff, compileall, and `sh -n install.sh` passed. Installer tests cover native
backend selection, paths with spaces/Unicode, cancellation without installation,
explicit destination bypass, and missing/failed picker errors. The macOS chooser
script compiled with the host AppleScript compiler. Interactive folder selection
was not exercised; Windows/Linux native dialog execution remains unverified.

## Previous verification on macOS ARM64 / Python 3.13

The following checks were recorded for `v0.26.264.3`:

| Surface | Result |
| --- | --- |
| `python -m pytest -q -W error --cov --cov-report=term-missing` | 72 tests passed; 97.54% combined statement/branch coverage against a 95% gate. |
| Ruff and compileall | Passed for runtime, application, tests, and scripts. |
| Source/wheel builds | Packaging includes application/foundation templates, static assets, desktop entrypoint, migrations, and installer/deployment resources in the source archive. |
| `scripts/smoke_verify.py` | Real HTTP landing page, readiness, settings persistence, and rejected unsafe mutation. |
| `scripts/playwright_verify.py` | Bundled headless Chromium: desktop and 390/320-pixel mobile widths, focus/dialogs, settings success/failure, theme restore, jobs/cancellation, pagination, safe text, restart-expired status. |
| `scripts/verify_desktop.py` | Real pywebview/WebKit window: page loaded, window closed, owned server stopped. |
| `scripts/verify_install.py` | Two real installs at a path containing spaces, runtime startup, unchanged saved settings/unknown fields/SQLite results, no pywebview in browser-only environments. |
| Installer unit failures | Simulated dependency failure preserves activation and data; invalid destinations and concurrent-install locks rejected. |
| `scripts/verify_clone.py` | Clean source export, replaced branding/service/CLI, new route/settings pane/table/job, identical CLI/web output; foundation source/assets unchanged by hash comparison. |
| `scripts/verify_lan.py` | Password-free HTTP with a non-loopback hostname mapped to a temporary listener; Chromium's secure-context-only APIs unavailable, benchmark still succeeds. |
| `scripts/verify_lan.py --caddy /path/to/caddy` | Real Caddy 2.11.4 HTTPS with temporary internal CA, bad-password and direct-backend rejection, forged identity rejection, authorized operator job success. |

Temporary verification used isolated data, credentials, ports, and installations.
Caddy's release was checked against its published SHA-512 checksum. CA trust was
scoped to the test client; no machine trust store, system service, or real deployment
was changed. Native-window testing was an automated open/load/close smoke test, not
a comprehensive native accessibility audit.

The clean-copy check exports working source rather than cloning git HEAD because
this workspace contains uncommitted source. It exercises the same independent
application-directory boundaries a clone will use. This distinction avoids claiming
that a committed release or remote repository was verified.

## Reproduce

Use a development virtual environment with `requirements-dev.txt` installed:

```sh
python -m pytest -q -W error --cov --cov-report=term-missing
ruff check .
python -m compileall -q pwaf_foundation app tests scripts
python scripts/smoke_verify.py
python -m playwright install chromium
python scripts/playwright_verify.py
python scripts/verify_clone.py
python scripts/verify_lan.py
python scripts/verify_install.py
python -m build
```

Optional checks require the corresponding external capability:

```sh
python -m pip install -r requirements-desktop.txt
python scripts/verify_desktop.py
python scripts/verify_lan.py --caddy /absolute/path/to/caddy
```

The install verification downloads dependencies. The native check needs an active
graphical session. The proxy check needs an installed Caddy binary; it does not
install Caddy or modify certificate trust. These scripts stop their temporary
servers and remove temporary runtime data afterward.

## Not verified on actual target machines

The GitHub Actions matrix covers Python 3.10 and 3.14 on Linux, macOS, and Windows,
including tests, browser checks, clean-copy adaptation, direct LAN simulation,
installation, and builds. It is configured but has not run in this session.

Actual Windows PowerShell launcher behavior, Windows WebView2, Linux desktop
backends, and physical Raspberry Pi operation remain unverified on those systems.
The real installer smoke check used the Python implementation and the generated
POSIX launcher; the shell entry wrapper was syntax-checked. CI's Windows smoke
launches the selected installed Python directly; it does not claim to exercise
PowerShell GUI lifecycle. Other-device LAN routing, local firewalls, and client CA
trust must be checked on the intended network. No internet-facing deployment is
claimed. These are explicit environment limits, not optional components silently
being treated as verified.
