"""Stage and activate an isolated user-owned installation.

A fresh release receives its own virtual environment. Activation is atomic and
occurs only after installation and startup verification with disposable data.
Persistent data and previous releases are never deleted by this installer.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
import venv
from pathlib import Path

PROBE = """
import json, os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pwaf_foundation import __version__
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
env = {key: value for key, value in os.environ.items() if not key.startswith('PWAF_')}
env.update(PWAF_DATA_DIR=sys.argv[1], PWAF_HTTP_PORT=str(port), PWAF_HTTP_HOST='127.0.0.1')
with tempfile.TemporaryFile(mode='w+') as log:
    child = subprocess.Popen([sys.executable, '-I', '-m', 'app'], env=env,
                             stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(150):
            try:
                url = f'http://127.0.0.1:{port}/healthz'
                with urllib.request.urlopen(url, timeout=1) as response:
                    assert json.load(response)['status'] == 'ready'
                    break
            except urllib.error.URLError:
                if child.poll() is not None:
                    log.seek(0); raise RuntimeError(log.read()) from None
                time.sleep(.1)
        else:
            raise RuntimeError('Installed application readiness timed out')
    finally:
        child.terminate()
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired: child.kill(); child.wait()
print(__version__)
"""


def select_destination() -> Path | None:
    """Open the platform folder chooser; return None when the user cancels."""
    title = "Choose an empty folder or an existing PWAF installation"
    if sys.platform == "darwin":
        script = '''
try
    set promptText to "Choose an empty folder or an existing PWAF installation"
    return POSIX path of (choose folder with prompt promptText)
on error number -128
    return ""
end try
'''
        command = ["osascript", "-e", script]
        cancel_codes = ()
    elif sys.platform == "win32":
        script = '''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose an empty folder or an existing PWAF installation'
$dialog.ShowNewFolderButton = $true
try {
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        [Console]::WriteLine($dialog.SelectedPath)
    }
} finally { $dialog.Dispose() }
'''
        command = ["powershell.exe", "-NoProfile", "-STA", "-Command", script]
        cancel_codes = ()
    else:
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise ValueError("No graphical session. Supply --destination /path/to/app.")
        if shutil.which("zenity"):
            command = ["zenity", "--file-selection", "--directory", f"--title={title}"]
        elif shutil.which("kdialog"):
            command = ["kdialog", "--getexistingdirectory", str(Path.home()), "--title", title]
        else:
            raise ValueError(
                "Install zenity or kdialog for a native folder picker, "
                "or supply --destination /path/to/app."
            )
        cancel_codes = (1,)
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "Could not open the native folder picker. Supply --destination /path/to/app."
        ) from exc
    if result.returncode in cancel_codes:
        return None
    if result.returncode != 0:
        raise ValueError(
            "Native folder picker failed. Supply --destination /path/to/app. "
            + result.stderr.strip()
        )
    selected = result.stdout.rstrip("\r\n")
    return Path(selected) if selected else None


def atomic_write(path: Path, content: str) -> None:
    """Replace one installer-owned file without exposing a partial write."""
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def application_identity(source: Path) -> str:
    """Read the stable app-owned installation identifier without importing code."""
    try:
        value = json.loads((source / "app/identity.json").read_text(encoding="utf-8"))["id"]
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", value):
            raise ValueError
        return value
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("Source requires app/identity.json with a valid stable id") from exc


def validate_identity(marker: Path, identity: str, adopt_legacy: bool) -> None:
    """Reject other apps and malformed markers; require explicit legacy adoption."""
    if not marker.exists():
        return
    content = marker.read_text(encoding="utf-8")
    if not content.strip():
        if not adopt_legacy:
            raise ValueError(
                "Legacy installation has no application identity. Verify its origin, then use "
                "--adopt-legacy-install with --destination to claim it for this application."
            )
        return
    try:
        document = json.loads(content)
        if document["format"] != 1 or not isinstance(document["application_id"], str):
            raise ValueError
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "Invalid installation identity marker; preserve it for inspection"
        ) from exc
    if document["application_id"] != identity:
        raise ValueError("Destination belongs to a different application; choose another folder")


def install(
    source: Path, destination: Path, *, desktop: bool = True, adopt_legacy: bool = False
) -> Path:
    """Build a verified release and switch activation while preserving installed data."""
    source, destination = source.resolve(), destination.expanduser().resolve()
    if source == destination or source in destination.parents:
        raise ValueError("Installation destination must be outside the source checkout")
    if not (source / "pyproject.toml").is_file():
        raise ValueError("Source must contain pyproject.toml")
    identity = application_identity(source)
    marker = destination / ".pwaf-install"
    if destination.exists() and any(destination.iterdir()) and not marker.is_file():
        raise ValueError("Choose an empty destination or an existing PWAF installation")
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / ".install-lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "Another install is active; remove a stale .install-lock only after checking"
        ) from exc
    os.close(descriptor)
    try:
        validate_identity(marker, identity, adopt_legacy)
        atomic_write(marker, json.dumps({"format": 1, "application_id": identity}) + "\n")
        release = destination / "releases" / uuid.uuid4().hex
        release.mkdir(parents=True)
        environment = release / ".venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        package = str(source) + ("[desktop]" if desktop else "")
        subprocess.run([str(python), "-m", "pip", "install", package], check=True)
        # No migrations touch installed user data during preparation.
        with tempfile.TemporaryDirectory(prefix="pwaf-install-probe-") as scratch:
            subprocess.run([str(python), "-I", "-c", PROBE, scratch], check=True, cwd=release)
        launcher = (source / "scripts/runtime_launcher.py").read_text(encoding="utf-8")
        atomic_write(destination / "launch.py", launcher)
        bootstrap = str(Path(sys._base_executable).resolve())
        shell = (
            "#!/bin/sh\nset -eu\n"
            'PWAF_INSTALL_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
            f'exec {shlex.quote(bootstrap)} "$PWAF_INSTALL_ROOT/launch.py" "$@"\n'
        )
        atomic_write(destination / "run.sh", shell)
        (destination / "run.sh").chmod(0o755)
        powershell_python = bootstrap.replace("'", "''")
        atomic_write(
            destination / "run.ps1",
            f"& '{powershell_python}' (Join-Path $PSScriptRoot 'launch.py') @args\n"
            "exit $LASTEXITCODE\n",
        )
        atomic_write(
            destination / "active.json",
            json.dumps({"release": release.name, "desktop": desktop}) + "\n",
        )
        return release
    finally:
        lock.unlink(missing_ok=True)


def main() -> None:
    """Install the checkout with desktop support unless explicitly disabled."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination", type=Path, help="Installation folder; opens a native picker if omitted"
    )
    parser.add_argument("--adopt-legacy-install", action="store_true",
                        help="Claim an unidentified legacy installation after verifying its origin")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--desktop", dest="desktop", action="store_true", help="Default")
    mode.add_argument("--browser-only", dest="desktop", action="store_false",
                      help="Omit desktop dependencies and launch only the web server")
    parser.set_defaults(desktop=True)
    args = parser.parse_args()
    try:
        if args.adopt_legacy_install and args.destination is None:
            raise ValueError("Legacy adoption requires an explicit --destination")
        destination = args.destination if args.destination is not None else select_destination()
        if destination is None:
            print("Installation cancelled; no installation changes made.")
            return
        destination = destination.expanduser().resolve()
        release = install(
            Path(__file__).resolve().parents[1], destination, desktop=args.desktop,
            adopt_legacy=args.adopt_legacy_install
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"Installation failed; prior activation and user data are preserved. {exc}"
        ) from exc
    launcher = destination / ("run.ps1" if os.name == "nt" else "run.sh")
    print(f"Installed release: {release}\nLaunch with {launcher}")


if __name__ == "__main__":
    main()
