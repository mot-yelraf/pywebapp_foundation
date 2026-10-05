"""Verify desktop coordination with controlled GUI and server doubles.

Native GUI smoke testing is recorded separately from these deterministic tests.
"""

import sys
import time
from types import SimpleNamespace

import pytest

from app.app import create_app
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.desktop import launch_desktop


class Listener:
    def setsockopt(self, *args):
        pass

    """No network access is required for deterministic lifecycle tests."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def bind(self, address):
        pass

    def listen(self, backlog):
        pass

    def setblocking(self, value):
        pass


class Server:
    """A server that remains alive until asked to exit."""

    def __init__(self, config):
        self.started = False
        self.should_exit = False

    def run(self, sockets):
        self.started = True
        while not self.should_exit:
            time.sleep(0.001)


def test_desktop_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setattr("pwaf_foundation.desktop.socket.socket", lambda *args: Listener())
    monkeypatch.setattr("pwaf_foundation.desktop._ready", lambda origin: True)
    monkeypatch.setattr("pwaf_foundation.desktop.set_macos_app_icon", lambda: None)
    calls = []
    gui = SimpleNamespace(create_window=lambda *a, **k: calls.append(a), start=lambda: None)
    config = RuntimeConfig(data_dir=tmp_path)
    launch_desktop(create_app(config), config, webview_module=gui, server_factory=Server)
    assert calls[0][1] == "http://127.0.0.1:8191"
    monkeypatch.setitem(sys.modules, "webview", gui)
    launch_desktop(create_app(config), config, server_factory=Server)
    assert len(calls) == 2


def test_desktop_failures(monkeypatch, tmp_path):
    config = RuntimeConfig(data_dir=tmp_path)
    monkeypatch.setattr("pwaf_foundation.desktop.socket.socket", lambda *args: Listener())
    monkeypatch.setitem(sys.modules, "webview", None)
    with pytest.raises(RuntimeError, match="optional"):
        launch_desktop(create_app(config), config)
    lan = RuntimeConfig(mode="lan", public_origin="http://tool.example:8191", data_dir=tmp_path)
    with pytest.raises(ValueError, match="local"):
        launch_desktop(create_app(lan), lan)
    gui = SimpleNamespace(create_window=lambda *a, **k: None, start=lambda: None)

    class Broken(Server):
        def run(self, sockets):
            raise RuntimeError("startup failure")

    with pytest.raises(RuntimeError, match="failed to start"):
        launch_desktop(create_app(config), config, webview_module=gui, server_factory=Broken)

    class Slow(Server):
        def run(self, sockets):
            while not self.should_exit:
                time.sleep(0.001)

    with pytest.raises(RuntimeError, match="timed out"):
        launch_desktop(
            create_app(config),
            config,
            webview_module=gui,
            server_factory=Slow,
            startup_timeout=0.01,
        )


def test_desktop_main(monkeypatch, tmp_path):
    from app.desktop import main

    monkeypatch.setattr("pwaf_foundation.desktop._ready", lambda origin: True)
    calls = []
    monkeypatch.setenv("PWAF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.desktop.launch_desktop", lambda *args: calls.append(args))
    main()
    assert calls
    monkeypatch.setenv("PWAF_MODE", "wrong")
    with pytest.raises(SystemExit):
        main()


def test_package_name_cannot_collide_with_macos_foundation():
    """macOS commonly stores case variants in the same installation directory."""
    import pwaf_foundation

    assert pwaf_foundation.__name__.casefold() != 'Foundation'.casefold()
    assert hasattr(pwaf_foundation, '__version__')


@pytest.mark.parametrize('status', [200, 503])
def test_readiness_checks_health_and_closes_response(monkeypatch, status):
    from contextlib import contextmanager

    from pwaf_foundation.desktop import _ready

    closed = []

    @contextmanager
    def response(url, timeout):
        assert url == 'http://[::1]:8191/healthz'
        assert timeout == 0.5
        try:
            yield SimpleNamespace(status=status)
        finally:
            closed.append(True)

    monkeypatch.setattr('pwaf_foundation.desktop.urllib.request.urlopen', response)
    assert _ready('http://[::1]:8191') is (status == 200)
    assert closed == [True]


@pytest.mark.parametrize('failure', [OSError('connection refused'), TimeoutError('slow response')])
def test_readiness_connection_failure_is_recoverable(monkeypatch, failure):
    from pwaf_foundation.desktop import _ready

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr('pwaf_foundation.desktop.urllib.request.urlopen', fail)
    assert _ready('http://127.0.0.1:8191') is False


@pytest.mark.parametrize('crash', [False, True])
def test_server_exit_closes_window_and_reports_failure(monkeypatch, tmp_path, crash):
    import threading

    from pwaf_foundation import desktop

    release = threading.Event()
    destroyed = threading.Event()
    servers = []
    monkeypatch.setattr(desktop.socket, 'socket', lambda *args: Listener())
    monkeypatch.setattr(desktop, '_ready', lambda origin: True)
    monkeypatch.setattr(desktop, 'set_macos_app_icon', lambda: None)

    class ExitingServer(Server):
        def __init__(self, config):
            super().__init__(config)
            servers.append(self)

        def run(self, sockets):
            self.started = True
            assert release.wait(2), 'GUI never started'
            if crash:
                raise OSError('server lost its listener')

    def start():
        release.set()
        assert destroyed.wait(2), 'Server exit did not close the window'

    window = SimpleNamespace(destroy=destroyed.set)
    gui = SimpleNamespace(create_window=lambda *a, **k: window, start=start)
    config = RuntimeConfig(data_dir=tmp_path)
    try:
        with pytest.raises(RuntimeError, match='stopped unexpectedly') as caught:
            launch_desktop(create_app(config), config, webview_module=gui,
                           server_factory=ExitingServer)
        assert servers[0].should_exit
        assert destroyed.is_set()
        if crash:
            assert isinstance(caught.value.__cause__, OSError)
        else:
            assert 'window was open' in str(caught.value.__cause__)
    finally:
        release.set()


@pytest.mark.parametrize('failure_stage', ['create_window', 'start'])
def test_gui_failure_stops_owned_server(monkeypatch, tmp_path, failure_stage):
    import threading

    from pwaf_foundation import desktop

    stopped = threading.Event()
    servers = []
    monkeypatch.setattr(desktop.socket, 'socket', lambda *args: Listener())
    monkeypatch.setattr(desktop, '_ready', lambda origin: True)
    monkeypatch.setattr(desktop, 'set_macos_app_icon', lambda: None)

    class TrackedServer(Server):
        def __init__(self, config):
            super().__init__(config)
            servers.append(self)

        def run(self, sockets):
            try:
                super().run(sockets)
            finally:
                stopped.set()

    def fail(*args, **kwargs):
        raise RuntimeError('GUI unavailable')

    gui = SimpleNamespace(create_window=lambda *a, **k: None, start=lambda: None)
    setattr(gui, failure_stage, fail)
    config = RuntimeConfig(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match='GUI unavailable'):
        launch_desktop(create_app(config), config, webview_module=gui,
                       server_factory=TrackedServer)
    assert servers[0].should_exit
    assert stopped.is_set()


def test_uncooperative_server_reports_bounded_shutdown(monkeypatch, tmp_path):
    import threading

    from pwaf_foundation import desktop

    release = threading.Event()
    threads, join_timeouts = [], []
    real_thread = threading.Thread
    monkeypatch.setattr(desktop.socket, 'socket', lambda *args: Listener())
    monkeypatch.setattr(desktop, '_ready', lambda origin: True)
    monkeypatch.setattr(desktop, 'set_macos_app_icon', lambda: None)

    class ShortJoinThread(real_thread):
        def join(self, timeout=None):
            if self.name == 'pwaf-desktop-server' and timeout is not None:
                join_timeouts.append(timeout)
                # Exercise the production deadline without waiting 35 seconds.
                timeout = 0.01
            return super().join(timeout)

    def make_thread(**kwargs):
        thread = ShortJoinThread(**kwargs)
        threads.append(thread)
        return thread

    class UncooperativeServer(Server):
        def run(self, sockets):
            self.started = True
            release.wait()

    monkeypatch.setattr(desktop.threading, 'Thread', make_thread)
    gui = SimpleNamespace(create_window=lambda *a, **k: None, start=lambda: None)
    config = RuntimeConfig(data_dir=tmp_path)
    try:
        with pytest.raises(RuntimeError, match='did not shut down'):
            launch_desktop(create_app(config), config, webview_module=gui,
                           server_factory=UncooperativeServer)
        assert join_timeouts == [35]
    finally:
        release.set()
        for thread in threads:
            real_thread.join(thread, timeout=2)
        assert all(not thread.is_alive() for thread in threads)


@pytest.mark.parametrize('loaded', [True, False])
def test_macos_icon_is_scheduled_and_applied_or_warned(monkeypatch, caplog, loaded):
    from pathlib import Path

    from pwaf_foundation import desktop

    callbacks, paths, applied = [], [], []
    image = object() if loaded else None

    def load(path):
        paths.append(Path(path))
        return image

    monkeypatch.setattr(desktop.sys, 'platform', 'darwin')
    monkeypatch.setitem(sys.modules, 'AppKit', SimpleNamespace(
        NSImage=SimpleNamespace(alloc=lambda: SimpleNamespace(initWithContentsOfFile_=load)),
        NSApplication=SimpleNamespace(sharedApplication=lambda:
                                     SimpleNamespace(setApplicationIconImage_=applied.append)),
    ))
    monkeypatch.setitem(sys.modules, 'PyObjCTools', SimpleNamespace(
        AppHelper=SimpleNamespace(callAfter=callbacks.append),
    ))
    desktop.set_macos_app_icon()
    assert len(callbacks) == 1
    assert paths == [] and applied == []  # Cocoa work must run through the GUI scheduler.
    callbacks[0]()
    assert paths == [Path(desktop.__file__).parent / 'static/icons/pwaf-desktop-icon.png']
    assert paths[0].is_file()
    assert applied == ([image] if loaded else [])
    assert ('Could not load PWAF desktop icon' in caplog.text) is (not loaded)


def test_missing_macos_icon_support_warns(monkeypatch, caplog):
    from pwaf_foundation import desktop

    monkeypatch.setattr(desktop.sys, 'platform', 'darwin')
    monkeypatch.setitem(sys.modules, 'AppKit', None)
    desktop.set_macos_app_icon()
    assert 'macOS icon support is unavailable' in caplog.text


@pytest.mark.parametrize('platform', ['win32', 'linux'])
def test_other_platforms_do_not_import_cocoa(monkeypatch, platform):
    import builtins

    from pwaf_foundation import desktop

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name not in ('AppKit', 'PyObjCTools'), 'Cocoa imported outside macOS'
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(desktop.sys, 'platform', platform)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    desktop.set_macos_app_icon()


@pytest.mark.parametrize('active,accept', [(True, True), (True, False), (False, True)])
def test_quit_confirmation_waits_for_cleanup(active, accept):
    import threading

    from pwaf_foundation.desktop import install_quit_handler

    callbacks, prompts = [], []
    finished = threading.Event()
    destroyed = threading.Event()
    server = SimpleNamespace(should_exit=False)

    class Event:
        def __iadd__(self, callback):
            callbacks.append(callback)
            return self

    def serve():
        while not server.should_exit:
            time.sleep(0.001)
        finished.set()

    worker = threading.Thread(target=serve)
    worker.start()

    def confirm(*args):
        prompts.append(args)
        return accept

    def destroy():
        assert finished.is_set()
        assert callbacks[0]() is True
        destroyed.set()

    window = SimpleNamespace(
        events=SimpleNamespace(closing=Event()), create_confirmation_dialog=confirm,
        destroy=destroy,
    )
    install_quit_handler(window, server, worker, lambda: active, 'NetProf', 'Stop and quit?')
    try:
        assert callbacks[0]() is False
        if not active or accept:
            assert destroyed.wait(2)
            assert server.should_exit
        else:
            time.sleep(0.05)
            assert not destroyed.is_set()
            assert not server.should_exit
        assert len(prompts) == int(active)
    finally:
        server.should_exit = True
        worker.join(2)


@pytest.mark.parametrize('platform', ['darwin', 'win32'])
def test_desktop_identity_and_socket_ownership(monkeypatch, tmp_path, platform):
    from pwaf_foundation import desktop

    options, titles, hooks = [], [], []
    listener = Listener()
    listener.setsockopt = lambda *args: options.append(args)
    monkeypatch.setattr(desktop.sys, 'platform', platform)
    monkeypatch.setattr(desktop.socket, 'SO_EXCLUSIVEADDRUSE', 999, raising=False)
    monkeypatch.setattr(desktop.socket, 'socket', lambda *a: listener)
    monkeypatch.setattr(desktop, '_ready', lambda origin: True)
    monkeypatch.setattr(desktop, 'set_macos_app_icon', lambda: None)
    monkeypatch.setattr(desktop, 'install_quit_handler', lambda *args: hooks.append(args))
    gui = SimpleNamespace(create_window=lambda title, *a, **k: titles.append(title),
                          start=lambda: None)
    config = RuntimeConfig(data_dir=tmp_path)
    launch_desktop(create_app(config), config, title='Custom Tool', confirm_exit=lambda: True,
                   webview_module=gui, server_factory=Server)
    assert titles == ['Custom Tool'] and len(hooks) == 1
    assert options[0][1] == (999 if platform == 'win32' else desktop.socket.SO_REUSEADDR)
