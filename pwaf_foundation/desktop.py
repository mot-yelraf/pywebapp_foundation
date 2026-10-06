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
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.identity import DesktopIdentity


def launch_desktop(
    application: FastAPI,
    config: RuntimeConfig,
    *,
    webview_module=None,
    server_factory=uvicorn.Server,
    startup_timeout: float = 15,
    title: str = "Python Web App",
    identity: DesktopIdentity | None = None,
    confirm_exit: Callable[[], bool] | None = None,
    quit_message: str = "Stop running work and quit?",
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
        # Windows needs exclusive ownership; POSIX needs TIME_WAIT reuse.
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
                title,
                origin,
                width=1200,
                height=850,
                min_size=(360, 500),
            )

            if confirm_exit is not None:
                install_quit_handler(
                    window, server, worker, confirm_exit, title, quit_message
                )

            def watch_server() -> None:
                worker.join()
                if not server.should_exit:
                    failures.append(RuntimeError("Server exited while the window was open"))
                    window.destroy()

            watcher = threading.Thread(target=watch_server, name="pwaf-desktop-watch", daemon=True)
            watcher.start()
            if identity is None:
                set_macos_app_icon()
            else:
                set_macos_app_icon(identity.icon("png"))
            if identity is not None and sys.platform == "win32":
                window.events.shown += lambda: set_windows_app_icon(window, identity.icon("ico"))
            if identity is not None and sys.platform.startswith("linux"):
                webview_module.start(icon=str(identity.icon("png")))
            else:
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


def set_macos_app_icon(icon_path: Path | None = None) -> None:
    """Apply the bundled PWAF artwork to the running macOS Dock/app switcher."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        from PyObjCTools import AppHelper

        def apply_icon() -> None:
            path = icon_path or Path(__file__).parent / "static/icons/pwaf-desktop-icon.png"
            icon = NSImage.alloc().initWithContentsOfFile_(str(path))
            if icon is None:
                logging.getLogger(__name__).warning("Could not load PWAF desktop icon")
                return
            NSApplication.sharedApplication().setApplicationIconImage_(icon)

        AppHelper.callAfter(apply_icon)
    except ImportError:
        logging.getLogger(__name__).warning("macOS icon support is unavailable")


def set_windows_app_icon(window, icon_path: Path) -> None:
    """Apply app-owned ICO artwork to the native WinForms window and taskbar."""
    try:
        from System.Drawing import Icon

        # Retain the managed icon for the complete lifetime of the native window.
        window.native.Icon = Icon(str(icon_path))
    except (ImportError, AttributeError, OSError):
        logging.getLogger(__name__).warning("Windows native icon support is unavailable")


def install_quit_handler(window, server, worker, confirm_exit, title, message) -> None:
    """Veto native close until confirmation and owned-server cleanup finish.

    Dialog work runs off the closing callback so Cocoa's main loop can display
    the native prompt. Repeated close requests cannot spawn duplicate prompts.
    """
    lock = threading.Lock()
    approved = False

    def closing():
        if approved or not worker.is_alive():
            return True
        if not lock.acquire(blocking=False):
            return False

        def finish():
            nonlocal approved
            try:
                if confirm_exit() and not window.create_confirmation_dialog(title, message):
                    return
                server.should_exit = True
                worker.join(timeout=35)
                if worker.is_alive():
                    logging.getLogger(__name__).error("Shutdown is still waiting for cleanup")
                    return
                approved = True
                window.destroy()
            except Exception:
                logging.getLogger(__name__).exception("Could not complete desktop shutdown")
            finally:
                lock.release()

        threading.Thread(target=finish, name="pwaf-desktop-quit", daemon=True).start()
        return False

    window.events.closing += closing
