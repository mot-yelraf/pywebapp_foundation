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
.pwaf-install           JSON format version and stable application identifier
```

Desktop installs also create a per-user click-to-launch app/menu icon; see
[native launchers](#native-launchers-and-application-name). Run the printed `run.sh`
or `run.ps1` path. Runtime configuration comes from the
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
installer records created launcher paths in `native-launchers.json`. Remove
those Finder/menu/shortcut entries too, after confirming they still target this
installation. macOS runtime identity bundles live under
`~/Library/Application Support/PWAF/<application-id>/`; remove only this app’s
identity directory if it is no longer used by another installation/source checkout.
The installer creates no system services or autostart entries. Caddy, Python, and any manually installed certificates are separately
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

## Installation identity

`app/identity.json` contains
`{"id": "pywebapp-foundation", "name": "Python Web App"}`. Derived applications
must choose their own stable identifier before their first installation, using
1–128 lowercase letters, digits, dots, underscores, or hyphens, beginning with a
letter or digit. This file is included in the application package. Display names,
versions, and directory names may change without changing the identifier.

The installer writes `{"format": 1, "application_id": "..."}` to `.pwaf-install`.
An identifier mismatch always rejects the destination before release preparation
or activation. A malformed marker is rejected as well. The identifier prevents
accidental cross-application upgrades; it is not an authentication mechanism.

Older releases used an empty marker. Stop the app, back up its data, and verify
that the destination belongs to the source application before adopting it:

```sh
./install.sh --destination /absolute/path/to/existing-app --adopt-legacy-install
```

PowerShell uses `-Destination ... -AdoptLegacyInstall`. Adoption requires an
explicit destination, applies only to empty legacy markers, and cannot override a
known mismatch. The marker is assigned under the install lock before preparation;
if dependency installation fails, the assigned identity remains, while activation
and user data remain unchanged. Retry normally with the same application identity.
Never use adoption to turn one application’s installation into another application.


## Native launchers and application name

Desktop installation creates launchers for the current user:

- macOS: `~/Applications/<name>.app`, with ICNS artwork and a universal ARM64/x86_64
  native launcher. It starts `run.sh --desktop` and records startup output at
  `<installation>/data/desktop-launch.log`. The installer applies an ad-hoc local
  signature and refreshes LaunchServices; this is not notarized distribution.
- Linux/Raspberry Pi: `<XDG_DATA_HOME>/applications/<native-id>.desktop`, defaulting
  to `~/.local/share/applications`, with a matching hicolor PNG icon.
- Windows: `<Desktop>/<name>.lnk` and `<Programs>/<native-id>/<name>.lnk`, targeting
  the stable `launch.py` selector with `--desktop`. Shortcut and process
  AppUserModelIDs match. `pythonw.exe` is used when available to avoid a console.

Launchers reference the installation root, so upgrades select the new release
without tying shortcuts to a discarded virtual environment or the source checkout.
Icons are copied to `<installation>/native-icons/`. Existing launchers from a
separate installation or unrelated bundle are rejected rather than overwritten.
One app identity/name has one per-user launcher set; use `--no-shortcuts` for an
additional installation. Renaming the display name creates new paths; manually
remove the previous entries after checking their targets. Browser-only upgrades
leave existing shortcuts in place; those explicitly request desktop mode, so
remove them if desktop support is no longer installed.

Use `--no-shortcuts` (`-NoShortcuts` in PowerShell) to install desktop dependencies
without writing per-user launcher entries. `--browser-only` automatically skips
native launchers. Neither option deletes existing launchers. Launchers do not
create system services, autostart, or native mobile applications.

App-owned native branding is explicit in `app/identity.json`:

```json
{
  "id": "your-app",
  "name": "Your App",
  "icon_dir": "static/icons",
  "icon_stem": "your-app-desktop-icon"
}
```

`name` defaults to `Python Web App` for older ID-only files. Use a nonempty name
of at most 100 characters without control characters, path separators, Windows
reserved filename characters/names (such as `CON`), or a trailing dot/space. `icon_dir` is relative to
the application package and must stay inside it. Supply matching `.png`, `.ico`,
and `.icns` files. Omit icon fields to use the foundation's generated artwork.
Nested application static assets are included by the default package-data rules.
The native ID is `org.pwaf.app_` plus the first 32 hex characters of the SHA-256
of the stable app ID; display-name changes do not alter it. The installer loads
metadata without running app services or reading saved settings.

In the application-owned desktop entrypoint, prepare native identity before
importing GUI libraries or creating resources:

```python
from pathlib import Path
from pwaf_foundation.identity import DesktopIdentity
from pwaf_foundation.launchers import prepare_desktop_identity
from pwaf_foundation.desktop import launch_desktop

identity = DesktopIdentity.load(Path(__file__).with_name("identity.json"))
prepare_desktop_identity(identity, module="app.desktop")
launch_desktop(create_my_app(config), config, title=identity.name, identity=identity)
```

On macOS this re-executes the current interpreter through a named app bundle,
retaining virtual-environment ownership, isolated-import mode, arguments, and
runtime environment. This gives the running menu/Dock app its product name rather
than `Python`. Linux sets GLib application name/program ID before GTK starts, or Qt application
name/display name/desktop file ID when Qt is installed;
Windows sets the process AppUserModelID and native window icon. Frozen macOS apps
supply their own bundle identity. Callers using `launch_desktop` directly should
perform this preparation in their own entrypoint. Editable `settings.app_name`,
web page titles, manifest names, and distribution metadata remain separate
branding choices; changing a default never rewrites saved preferences.

`PWAF_DESKTOP_IDENTITY` is an internal macOS re-exec marker set by the launcher,
not a user configuration option. It prevents recursive re-launch and must not be
set manually. Rebuild the bundled native launcher on macOS with Command Line
Tools using `bash scripts/build_macos_launcher.sh` after changing its C source.
The executable is included in wheel/source-distribution package data.


Platform contracts: [Apple bundle keys](https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/CoreFoundationKeys.html),
[freedesktop desktop entries](https://specifications.freedesktop.org/desktop-entry/latest-single/),
and [Windows AppUserModelIDs](https://learn.microsoft.com/en-us/windows/win32/shell/appids).
