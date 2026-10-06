"""Launch an installed release through its stable activation file.

This standalone script uses only the standard library so it can select the
release's private Python environment without importing repository code.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Resolve the selected release and use a stable installation data directory."""
    root = Path(__file__).resolve().parent
    try:
        activation = json.loads((root / "active.json").read_text())
        release_name = activation["release"]
        if not isinstance(release_name, str) or Path(release_name).name != release_name:
            raise ValueError("Invalid release name")
        release = (root / "releases" / release_name).resolve()
        if release.parent != (root / "releases").resolve():
            raise ValueError("Invalid release path")
        python = release / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise ValueError("Selected release Python is missing")
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit("Installation is incomplete; rerun the installer") from exc
    args = sys.argv[1:]
    if args not in ([], ["--desktop"], ["--browser-only"]):
        raise SystemExit(
            "Usage: run [--desktop | --browser-only]; configure using PWAF_* variables"
        )
    desktop = activation.get("desktop", False) if not args else args == ["--desktop"]
    if os.name == "nt" and desktop:
        pythonw = python.with_name("pythonw.exe")
        if pythonw.is_file():
            python = pythonw
    env = dict(os.environ)
    env.setdefault("PWAF_DATA_DIR", str(root / "data"))
    command = [str(python), "-I", "-m", "app.desktop" if desktop else "app"]
    # exec replaces the launcher on POSIX so signals reach the server directly.
    if os.name != "nt":
        os.execve(python, command, env)
    return subprocess.call(command, env=env, cwd=release)


if __name__ == "__main__":
    raise SystemExit(main())
