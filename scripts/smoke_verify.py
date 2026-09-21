"""Verify a live local server using curl and isolated temporary storage.

An available loopback port is selected; the child server is stopped on all exit
paths. Run from a development environment with curl installed.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    """Check startup, HTML, settings persistence, and mutation protection."""
    with tempfile.TemporaryDirectory(prefix="pwaf-smoke-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "PWAF_DATA_DIR": directory,
            "PWAF_HTTP_PORT": str(port),
            "PWAF_HTTP_HOST": "127.0.0.1",
            "PWAF_LOG_LEVEL": "INFO",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "app"],
            env=env,
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            for _ in range(100):
                probe = subprocess.run(
                    ["curl", "--max-time", "2", "-fsS", origin + "/healthz"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if probe.returncode == 0:
                    break
                if process.poll() is not None:
                    raise RuntimeError(process.stdout.read())
                time.sleep(0.1)
            else:
                raise RuntimeError("Server readiness timed out")
            assert json.loads(probe.stdout)["status"] == "ready"
            page = subprocess.check_output(["curl", "-fsS", origin + "/"], text=True)
            assert "Your Python web foundation is running." in page
            token = json.loads(
                subprocess.check_output(
                    [
                        "curl",
                        "-fsS",
                        origin + "/api/csrf",
                    ]
                )
            )["csrf_token"]
            result = subprocess.check_output(
                [
                    "curl",
                    "-fsS",
                    "-X",
                    "PATCH",
                    origin + "/api/settings",
                    "-H",
                    "Content-Type: application/json",
                    "-H",
                    "Origin: " + origin,
                    "-H",
                    "X-CSRF-Token: " + token,
                    "--data",
                    '{"app_name":"Smoke verified"}',
                ]
            )
            assert json.loads(result)["app_name"] == "Smoke verified"
            assert json.loads((Path(directory) / "settings.json").read_text())["app_name"] == (
                "Smoke verified"
            )
            denied = subprocess.check_output(
                [
                    "curl",
                    "-sS",
                    "-o",
                    os.devnull,
                    "-w",
                    "%{http_code}",
                    "-X",
                    "PATCH",
                    origin + "/api/settings",
                    "-H",
                    "Content-Type: application/json",
                    "--data",
                    "{}",
                ],
                text=True,
            )
            assert denied == "403"
            print(
                "Live curl checks passed: HTML, readiness, CSRF, saved settings, denied mutation."
            )
        finally:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
            if process.returncode not in (0, -15):
                print(output)


if __name__ == "__main__":
    main()
