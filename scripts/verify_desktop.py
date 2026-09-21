"""Open and automatically close a real pywebview window for native smoke verification.

This optional check requires desktop dependencies and an active graphical session.
It uses an isolated data directory and does not alter installed user data.
"""

import argparse
import socket
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path


def main() -> None:
    """Check actual page loading and coordinated GUI/server shutdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true",
                        help="Test this interpreter’s installed packages, excluding source imports")
    args = parser.parse_args()
    if not args.installed:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    import webview

    from app.app import create_example_app
    from pwaf_foundation.config import RuntimeConfig
    from pwaf_foundation.desktop import launch_desktop

    loaded = threading.Event()
    outcomes = []

    class CheckedWebview:
        def create_window(self, *args, **kwargs):
            self.window = webview.create_window(*args, **kwargs)
            self.window.events.loaded += loaded.set
            return self.window

        def start(self):
            def check():
                try:
                    if not loaded.wait(20):
                        raise RuntimeError("Native page did not load")
                    text = self.window.evaluate_js("document.querySelector('h1').textContent")
                    assert "Python tools" in text, text
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/", timeout=5
                    ) as response:
                        assert response.status == 200
                        assert b"Python tools" in response.read()
                    outcomes.append(True)
                finally:
                    self.window.destroy()

            webview.start(check)

    with tempfile.TemporaryDirectory(prefix="pwaf-native-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = RuntimeConfig(port=port, data_dir=Path(directory), log_level="WARNING")
        launch_desktop(create_example_app(config), config, webview_module=CheckedWebview())
        assert outcomes == [True]
    print(
        "Native desktop verified: real page load, browser HTTP access, "
        "window close, server shutdown."
    )


if __name__ == "__main__":
    main()
