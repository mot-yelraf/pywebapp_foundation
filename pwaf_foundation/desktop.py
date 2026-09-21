"""Host the optional desktop window around an owned loopback server.

pywebview is imported only on desktop launch. A pre-bound socket prevents opening
an unrelated existing server, and the server is joined after the window closes.
"""

import importlib
import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from pwaf_foundation.config import RuntimeConfig


def launch_desktop(
    application: FastAPI,
    config: RuntimeConfig,
    *,
    webview_module=None,
    server_factory=uvicorn.Server,
    startup_timeout: float = 15,
) -> None:
    """Wait for server startup, run the native GUI on the main thread, then stop it."""
    if config.mode != "local":
        raise ValueError("Desktop mode requires PWAF_MODE=local")
    if webview_module is None:
        try:
            webview_module = importlib.import_module("webview")
        except ImportError as exc:
            raise RuntimeError(
                "Desktop support is optional; install requirements-desktop.txt first"
            ) from exc
    family = socket.AF_INET6 if ":" in config.host else socket.AF_INET
    with socket.socket(family) as listener:
        listener.bind((config.host, config.port))
        listener.listen(128)
        listener.setblocking(False)
        server = server_factory(
            uvicorn.Config(
                application,
                host=config.host,
                port=config.port,
                log_level=config.log_level.lower(),
                proxy_headers=False,
            )
        )
        failures = []

        def run() -> None:
            try:
                server.run(sockets=[listener])
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=run, name="pwaf-desktop-server", daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + startup_timeout
            host = f"[{config.host}]" if ":" in config.host else config.host
            origin = f"http://{host}:{config.port}"
            while not server.started or not _ready(origin):
                if not worker.is_alive():
                    raise RuntimeError("Desktop server failed to start; check the application log")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Desktop server startup timed out")
                time.sleep(0.01)
            window = webview_module.create_window(
                "Python Web App",
                origin,
                width=1200,
                height=850,
                min_size=(360, 500),
            )

            def watch_server() -> None:
                worker.join()
                if not server.should_exit:
                    failures.append(RuntimeError("Server exited while the window was open"))
                    window.destroy()

            watcher = threading.Thread(target=watch_server, name="pwaf-desktop-watch", daemon=True)
            watcher.start()
            set_macos_app_icon()
            webview_module.start()
        finally:
            server.should_exit = True
            worker.join(timeout=35)
            if worker.is_alive():
                raise RuntimeError(
                    "Desktop server did not shut down; a service may not support cancellation"
                )
        if failures:
            raise RuntimeError("Desktop server stopped unexpectedly") from failures[0]


def _ready(origin: str) -> bool:
    try:
        with urllib.request.urlopen(origin + "/healthz", timeout=0.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def set_macos_app_icon() -> None:
    """Apply the bundled PWAF artwork to the running macOS Dock/app switcher."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        from PyObjCTools import AppHelper

        def apply_icon() -> None:
            path = Path(__file__).parent / "static/icons/pwaf-desktop-icon.png"
            icon = NSImage.alloc().initWithContentsOfFile_(str(path))
            if icon is None:
                logging.getLogger(__name__).warning("Could not load PWAF desktop icon")
                return
            NSApplication.sharedApplication().setApplicationIconImage_(icon)

        AppHelper.callAfter(apply_icon)
    except ImportError:
        logging.getLogger(__name__).warning("macOS icon support is unavailable")
