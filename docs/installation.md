# Installation, upgrades, and desktop operation

## Standalone installation

Python 3.10 or newer with `venv`/pip is required. Run from a source checkout or
source archive. No administrator access is required by the installer.

macOS, Linux, or Raspberry Pi:

```sh
./install.sh
# Or choose an empty destination (spaces are supported):
./install.sh --destination "$HOME/My Python App"
```

Windows PowerShell:

```powershell
.\install.ps1
# Or:
.\install.ps1 -Destination "$env:LOCALAPPDATA\My Python App"
```

If local PowerShell policy disallows scripts, invoke the shared installer directly
rather than changing machine-wide policy:

```powershell
py -3 scripts/install_runtime.py --destination "$env:LOCALAPPDATA\My Python App"
```

Without a destination argument, the installer opens the native folder selector:
macOS Finder dialog, Windows folder browser, or Zenity/KDialog on Linux and
Raspberry Pi desktops. Create/select an empty folder, or select an existing PWAF
installation to upgrade. The selected folder is the installation root; no extra
subfolder is appended. Cancel exits without installation changes.

For SSH, headless systems, or automated installation, supply `--destination`
(`-Destination` in PowerShell). Linux desktop selection requires `zenity` or
`kdialog`; if the picker is unavailable, the installer explains how to supply a
path rather than installing somewhere automatically. On Debian-derived systems,
install the platform's Python `venv` package if ensurepip is unavailable.

Each installation contains:

```text
active.json             Selected release identifier
launch.py               Standard-library release selector
run.sh / run.ps1        Stable launchers
releases/<id>/.venv/    Independent runtime and installed application package
data/                   Settings and SQLite state, created by the runtime
.pwaf-install           Identifies an installer-owned destination
```

Run the printed `run.sh` or `run.ps1` path. Runtime configuration comes from the
same `PWAF_*` variables as source operation. `PWAF_DATA_DIR` defaults to the
installation's absolute data path unless you explicitly override it. Launchers
use the base Python interpreter used during installation; keep that interpreter
installed. Do not move release virtual environments; reinstall at a new destination
and restore data when relocating.

The installer refuses a nonempty unrecognized destination and refuses to install
inside its own source checkout. It uses a lock to prevent concurrent installs.
A fresh release is populated, checked against disposable storage, and then activated
with an atomic `active.json` replacement. Runtime dependencies are downloaded;
pywebview is included by default. For headless installations, pass `--browser-only`
(or `-BrowserOnly` on Windows) to omit desktop dependencies and make the launcher
start only the web server.

## Upgrade and recovery

Stop the application before upgrading so old and new processes never use the same
data directory concurrently. Run the installer from the updated source against the
same destination. It creates a new virtual environment and leaves all data and
previous releases untouched. Migration preparation uses temporary storage; actual
user-data migrations occur at the next application startup.

A failed dependency install or preparation check leaves the previous activation
unchanged. Failed releases remain inactive for inspection; the installer never
prunes releases or deletes data. A crashed installer can leave `.install-lock`;
remove that file only after confirming no installer is still running.

To recover an activation problem, stop the app and inspect `active.json`. You can
select a retained release by replacing its `release` value with that directory's
identifier. **Restore a matching data backup before a downgrade** when the old
release does not support the newer schema. A retained runtime is not a data backup.
Installer-owned launchers should not contain customizations; put application changes
in your source and runtime configuration in your launch environment.

## Backup, restore, and uninstall

With the application stopped, copy the entire `data/` directory to a backup location.
This preserves JSON, SQLite, and any SQLite sidecar files consistently. Also preserve
private proxy configuration/token material separately if you use authenticated LAN
access. Do not store credentials in the application repository.

To restore, stop the app, retain the current data as a safety copy, and replace the
installation's data directory with the backed-up directory. Start a compatible
release; verify settings and history before resuming work. If you override
`PWAF_DATA_DIR`, back up and restore that location instead.

To uninstall, stop all application/proxy processes, retain any desired data backup,
then remove the chosen installation directory through your file manager. The
installer creates no system services or autostart entries, so there are none to
unregister. Caddy, Python, and any manually installed certificates are separately
managed by the operator.

## Desktop window and browser access

Source checkout:

```sh
python -m pip install -r requirements.txt -r requirements-desktop.txt
python -m app.desktop
```

Standalone install:

```sh
./install.sh
# Then use the printed launcher with:
"/path/to/installation/run.sh"
```

On Windows use `install.ps1` and `run.ps1` (or `python launch.py`).
The default installation opens pywebview when launched. While it is open, a browser
on the same machine can use http://127.0.0.1:8191 (or the configured port). Closing
the app stops its server, including browser access. Use `run.sh --browser-only` or
`run.ps1 --browser-only` to run the server without a window, including for LAN mode.
`--desktop` remains accepted for compatibility. Reinstall into an existing
installation to add pywebview and update its default launch mode. Desktop mode requires local mode and a graphical
session. Browser-only operation never imports pywebview. Missing optional support,
bind conflicts, and startup failures are reported clearly.

The launcher reserves its own socket, waits for `/healthz`, opens the native window
on the main thread, and stops/joins the server when the window closes. Unexpected
server termination closes the window. As with browser shutdown, application job
adapters must support bounded cancellation to avoid delaying exit.

macOS uses WebKit through PyObjC. Windows requires an available WebView2 runtime;
Linux desktop use needs a supported GTK/WebKit or Qt backend and its system packages.
See the [pywebview installation guide](https://pywebview.flowrl.com/guide/installation.html)
for platform prerequisites. A headless Raspberry Pi uses browser mode; no desktop
packages are needed there.

## Verification scope

macOS ARM64 was exercised with a real native window, real browser-only installs and
reinstalls, installed launch, and data preservation. Windows PowerShell and
Linux/Raspberry Pi native behavior require testing on those actual platforms; unit
doubles and a configured CI matrix are not evidence of a native run.
