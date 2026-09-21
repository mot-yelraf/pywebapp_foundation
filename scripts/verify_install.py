"""Verify real install, reinstall, and a launched runtime using temporary paths.

Downloads runtime dependencies into isolated virtual environments. No existing
installation or user data is read or modified.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    """Install twice, seed real persisted state, and prove it survives activation."""
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="pwaf-install-") as directory:
        root = Path(directory) / "Installed App With Spaces"
        command = [
            sys.executable,
            str(source / "scripts/install_runtime.py"),
            "--browser-only",
            "--destination",
            str(root),
        ]
        subprocess.run(command, check=True)
        first = json.loads((root / "active.json").read_text())["release"]
        python = (
            root
            / "releases"
            / first
            / ".venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        seed = """
import json
from pathlib import Path
from app.migrations import PERFORMANCE_MIGRATIONS
from app.example import ToolSettings
from pwaf_foundation.settings import SettingsStore
from pwaf_foundation.database import Database
root = Path(__import__('sys').argv[1]); root.mkdir()
(root/'settings.json').write_text('{"app_name":"Preserved","future":{"keep":true}}')
store=SettingsStore(root/'settings.json',ToolSettings)
store.load(); store.update({'default_iterations':7})
database=Database(root/'app.sqlite3'); database.migrate({'performance':PERFORMANCE_MIGRATIONS})
with database.transaction() as connection:
    connection.execute("INSERT INTO performance_results "
        "(job_id, recorded_at, iterations, elapsed_ms, checksum) VALUES "
        "('seed','2026-09-21T00:00:00.000000Z',7,0,'seed')")
"""
        subprocess.run([str(python), "-c", seed, str(root / "data")], cwd=root, check=True)
        before = {
            name: (root / "data" / name).read_bytes() for name in ("settings.json", "app.sqlite3")
        }
        subprocess.run(command, check=True)
        second = json.loads((root / "active.json").read_text())["release"]
        assert second != first
        assert before == {name: (root / "data" / name).read_bytes() for name in before}
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if not key.startswith("PWAF_")}
        env["PWAF_HTTP_PORT"] = str(port)
        launch = (
            [str(root / "run.sh")]
            if os.name != "nt"
            else [str(root / "releases" / second / ".venv/Scripts/python.exe"), "-m", "app"]
        )
        if os.name == "nt":
            env["PWAF_DATA_DIR"] = str(root / "data")
        with tempfile.TemporaryFile(mode="w+") as log:
            process = subprocess.Popen(
                launch, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/api/results", timeout=1
                        ) as response:
                            assert json.load(response)["total"] == 1
                            break
                    except urllib.error.URLError:
                        if process.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(log.read()) from None
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Installed server did not start")
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/settings") as response:
                    assert json.load(response)["app_name"] == "Preserved"
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        assert json.loads((root / "data/settings.json").read_text())["future"] == {"keep": True}
        no_desktop = 'import importlib.util; assert importlib.util.find_spec("webview") is None'
        subprocess.run([str(python), "-c", no_desktop], cwd=root, check=True)
    print(
        "Real install/reinstall passed: paths with spaces, saved settings/results, "
        "browser-only dependencies, startup."
    )


if __name__ == "__main__":
    main()
