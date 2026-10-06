"""Verify native artifacts with isolated folders and controlled platform adapters.

Real Finder/GTK/Windows behavior must also be checked on the corresponding host.
"""

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pwaf_foundation import launchers
from pwaf_foundation.identity import DesktopIdentity


@pytest.fixture
def identity():
    return DesktopIdentity("test-app", "Test App")


@pytest.mark.parametrize("document", [
    {"id": "test-app"}, {"id": "test-app", "name": "Test App"},
    {"id": "test-app", "name": "Test App", "icon_dir": "static/icons", "icon_stem": "test"},
])
def test_identity_metadata(tmp_path, document):
    path = tmp_path / 'identity.json'
    path.write_text(json.dumps(document))
    identity = DesktopIdentity.load(path)
    assert identity.id == 'test-app'
    assert identity.name == document.get('name', 'Python Web App')
    if 'icon_dir' in document:
        assert identity.icon('png') == tmp_path / 'static/icons/test.png'


@pytest.mark.parametrize('document', [
    [], {}, {'id': 42}, {'id': '../app'}, {'id': 'app', 'name': '\nBad'},
    {'id': 'app', 'name': '../Bad'}, {'id': 'app', 'name': ''},
    {'id': 'app', 'name': 42}, {'id': 'app', 'name': 'CON'}, {'id': 'app', 'icon_dir': '/absolute'},
    {'id': 'app', 'icon_dir': 'C:/absolute'},
    {'id': 'app', 'icon_dir': 'C:relative'},
    {'id': 'app', 'icon_dir': r'\rooted'},
    {'id': 'app', 'icon_dir': r'..\escape'},
    {'id': 'app', 'icon_dir': '../escape'}, {'id': 'app', 'icon_stem': '../bad'},
])
def test_invalid_identity(tmp_path, document):
    path = tmp_path / 'identity.json'
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='identity.json'):
        DesktopIdentity.load(path)


def test_native_ids_do_not_collapse_distinct_app_ids():
    assert DesktopIdentity('a-b').native_id != DesktopIdentity('a_b').native_id
    assert len(DesktopIdentity('a' * 128).native_id) < 128


def test_linux_launcher_quoting_upgrade_and_ownership(tmp_path, identity):
    root = tmp_path / 'Installed "App" $x `y` % \\ space'
    data_home = tmp_path / 'xdg'
    desktop = launchers.write_linux_launcher(root, identity, data_home)
    content = desktop.read_text()
    assert 'Name=Test App\n' in content
    assert ' --desktop\n' in content
    assert '%%' in content and '\\\\$' in content and '\\\\`' in content
    assert '\\\\"' in content and '\\\\\\\\' in content
    assert f'StartupWMClass={identity.native_id}\n' in content
    assert (data_home / 'icons/hicolor/512x512/apps' /
            f'{identity.native_id}.png').read_bytes() == identity.icon('png').read_bytes()
    assert launchers.write_linux_launcher(root, identity, data_home).read_text() == content
    with pytest.raises(ValueError, match='another installation'):
        launchers.write_linux_launcher(tmp_path / 'other', identity, data_home)
    assert desktop.read_text() == content


def test_macos_finder_bundle(tmp_path, identity, monkeypatch):
    calls = []
    monkeypatch.setattr(launchers.subprocess, 'run', lambda command, **kw: calls.append(command))
    root = tmp_path / "App with ' quotes"
    bundle = launchers.write_macos_launcher(root, identity, tmp_path / 'Applications')
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    assert info['CFBundleName'] == info['CFBundleDisplayName'] == 'Test App'
    assert info['CFBundleIdentifier'] == identity.native_id + '.launcher'
    assert info['PWAFOrigin'] == str(root)
    assert info['LSUIElement']
    executable = bundle / 'Contents/MacOS/Test App'
    if os.name != "nt":
        assert executable.stat().st_mode & 0o111
    assert executable.read_bytes()[:4] == b'\xca\xfe\xba\xbe'  # Universal Mach-O.
    script = bundle / 'Contents/Resources/launch.sh'
    subprocess.run(['/bin/sh', '-n', str(script)], check=True)
    assert ' --desktop ' in script.read_text()
    assert calls[0][0] == '/usr/bin/codesign' and calls[1][0] == launchers.LSREGISTER
    launchers.write_macos_launcher(root, identity, tmp_path / 'Applications')
    before = (bundle / 'Contents/Info.plist').read_bytes()
    with pytest.raises(ValueError, match='another installation'):
        launchers.write_macos_launcher(tmp_path / 'other', identity, tmp_path / 'Applications')
    assert (bundle / 'Contents/Info.plist').read_bytes() == before


def test_macos_identity_reexec_preserves_venv_isolation_and_env(tmp_path, identity, monkeypatch):
    monkeypatch.setattr(launchers.sys, 'platform', 'darwin')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(launchers.sys, 'executable', '/some/venv/bin/python')
    monkeypatch.setattr(launchers.sys, 'flags', SimpleNamespace(isolated=True))
    monkeypatch.setattr(launchers.sys, 'argv', ['desktop', 'argument'])
    monkeypatch.delenv('PWAF_DESKTOP_IDENTITY', raising=False)
    monkeypatch.setenv('PWAF_DATA_DIR', '/private/app-data')
    calls = []
    monkeypatch.setattr(launchers.os, 'execve', lambda *args: calls.append(args))
    launchers.prepare_desktop_identity(identity, module='app.desktop')
    executable, command, env = calls[0]
    assert executable.is_symlink()
    assert executable.readlink() == Path('/some/venv/bin/python')
    assert command == [str(executable), '-I', '-m', 'app.desktop', 'argument']
    assert env['PWAF_DATA_DIR'] == '/private/app-data'
    assert env['PWAF_DESKTOP_IDENTITY'] == identity.native_id
    assert env['__PYVENV_LAUNCHER__'] == '/some/venv/bin/python'
    info = plistlib.loads((executable.parent.parent / 'Info.plist').read_bytes())
    assert info['CFBundleName'] == identity.name and not info['LSUIElement']
    monkeypatch.setenv('PWAF_DESKTOP_IDENTITY', identity.native_id)
    launchers.prepare_desktop_identity(identity, module='app.desktop')
    assert len(calls) == 1


def test_linux_and_windows_process_identity(monkeypatch, identity):
    names = []
    monkeypatch.setattr(launchers.sys, 'platform', 'linux')
    monkeypatch.setitem(sys.modules, 'gi.repository', SimpleNamespace(GLib=SimpleNamespace(
        set_prgname=names.append, set_application_name=names.append)))
    launchers.prepare_desktop_identity(identity, module='app.desktop')
    assert names == [identity.native_id, identity.name]
    monkeypatch.setattr(launchers.sys, 'platform', 'win32')
    monkeypatch.setattr(launchers.ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=lambda value: names.append(value) or 0)),
        raising=False)
    launchers.prepare_desktop_identity(identity, module='app.desktop')
    assert names[-1] == identity.native_id


def test_windows_shortcut_identity(tmp_path, identity, monkeypatch):
    root = tmp_path / "Installed ' App"
    calls = []
    monkeypatch.setattr(launchers.subprocess, 'run', lambda command, **kw:
                        calls.append(command) or
                        SimpleNamespace(stdout='C:\\Desktop\\Test App.lnk\n'))
    paths = launchers.write_windows_launchers(root, identity, Path('C:/Python/python.exe'))
    metadata = json.loads((root / 'native-shortcut.json').read_text())
    assert metadata['root'] == str(root) and metadata['id'] == identity.native_id
    assert metadata['icon'] == str(identity.icon('ico'))
    script = calls[0][-1]
    assert '-Command' in calls[0] and '-ExecutionPolicy' not in calls[0]
    assert "Installed '' App" in script
    assert "GetFolderPath('DesktopDirectory')" in script
    assert "GetFolderPath('Programs')" in script
    assert '[PWAFShortcutIdentity]::Set($path, $m.id)' in script
    assert ' --desktop' in script and 'launch.py' in script
    assert paths == [Path('C:\\Desktop\\Test App.lnk')]


def test_installed_launcher_icons_survive_source_removal(tmp_path, identity, monkeypatch):
    monkeypatch.setattr(launchers.sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg'))
    root = tmp_path / 'runtime'
    paths = launchers.install_launchers(root, identity, Path('/python'))
    assert json.loads((root / 'native-launchers.json').read_text()) == [str(p) for p in paths]
    for extension in ('png', 'ico', 'icns'):
        assert ((root / f'native-icons/app.{extension}').read_bytes()
                == identity.icon(extension).read_bytes())


def test_qt_identity_without_glib(monkeypatch, identity):
    names = []
    monkeypatch.setattr(launchers.sys, 'platform', 'linux')
    monkeypatch.setitem(sys.modules, 'gi.repository', None)
    monkeypatch.setitem(sys.modules, 'qtpy.QtCore', SimpleNamespace(
        QCoreApplication=SimpleNamespace(setApplicationName=names.append)))
    monkeypatch.setitem(sys.modules, 'qtpy.QtGui', SimpleNamespace(
        QGuiApplication=SimpleNamespace(setApplicationDisplayName=names.append,
                                       setDesktopFileName=names.append)))
    launchers.prepare_desktop_identity(identity, module='app.desktop')
    assert names == [identity.name, identity.name, identity.native_id]
