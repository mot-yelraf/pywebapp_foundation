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
    parser.add_argument("--identity", action="store_true",
                        help="Verify the application-owned native name and icons")
    parser.add_argument("--identity-home", type=Path,
                        help="Put native identity bundles in an isolated test directory")
    parser.add_argument("--expected-prefix", type=Path,
                        help="Assert that native relaunch retains this virtual environment")
    args = parser.parse_args()
    if not args.installed:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    if args.identity:
        from app import desktop as app_desktop
        from pwaf_foundation.identity import DesktopIdentity
        from pwaf_foundation.launchers import prepare_desktop_identity

        identity = DesktopIdentity.load(Path(app_desktop.__file__).with_name("identity.json"))
        prepare_desktop_identity(identity, module="scripts.verify_desktop",
                                 bundle_root=args.identity_home,
                                 entrypoint=Path(__file__).resolve())

    if args.expected_prefix:
        assert Path(sys.prefix).resolve() == args.expected_prefix.resolve(), sys.prefix

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

        def start(self, **kwargs):
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
                    if args.identity and sys.platform == "darwin":
                        from AppKit import NSApplication
                        from Foundation import NSBundle

                        assert NSBundle.mainBundle().objectForInfoDictionaryKey_(
                            "CFBundleName") == identity.name
                        menu = NSApplication.sharedApplication().mainMenu()
                        app_menu = menu.itemAtIndex_(0).submenu()
                        assert identity.name in app_menu.itemAtIndex_(0).title()
                    outcomes.append(True)
                finally:
                    self.window.destroy()

            webview.start(check, **kwargs)

    with tempfile.TemporaryDirectory(prefix="pwaf-native-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = RuntimeConfig(port=port, data_dir=Path(directory), log_level="WARNING")
        launch_desktop(create_example_app(config), config, webview_module=CheckedWebview(),
                       **({"identity": identity, "title": identity.name} if args.identity else {}))
        assert outcomes == [True]
    print(
        "Native desktop verified: real page load, browser HTTP access, "
        "window close, server shutdown."
    )


if __name__ == "__main__":
    main()
