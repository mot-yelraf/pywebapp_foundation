"""Exercise atomic installer activation without network downloads.

Real installation and launch checks are run separately using the shell installer.
"""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.install_runtime import install

SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_launchers(monkeypatch):
    """Installer doubles must never create real per-user shortcuts."""
    monkeypatch.setattr("scripts.install_runtime.install_launchers", lambda *args: [])



def test_upgrade_preserves_data_and_failed_activation(tmp_path, monkeypatch):
    root = tmp_path / "installed app"
    monkeypatch.setattr(
        "scripts.install_runtime.venv.EnvBuilder.create", lambda self, path: path.mkdir()
    )
    monkeypatch.setattr("scripts.install_runtime.subprocess.run", lambda *a, **k: None)
    first = install(SOURCE, root)
    data = root / "data"
    data.mkdir()
    settings = data / "settings.json"
    settings.write_text('{"app_name":"Mine","unknown":{"keep":true}}')
    database = data / "app.sqlite3"
    database.write_bytes(b"existing data")
    second = install(SOURCE, root, desktop=True)
    assert first != second and first.exists()
    assert json.loads((root / "active.json").read_text())["release"] == second.name
    snapshot = settings.read_bytes(), database.read_bytes(), (root / "active.json").read_bytes()

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr("scripts.install_runtime.subprocess.run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        install(SOURCE, root)
    assert snapshot == (
        settings.read_bytes(),
        database.read_bytes(),
        (root / "active.json").read_bytes(),
    )
    assert not (root / ".install-lock").exists()
    assert "launch.py" in (root / "run.sh").read_text()


def test_installer_rejects_unsafe_destinations(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        install(SOURCE, SOURCE / "installed")
    with pytest.raises(ValueError, match="pyproject"):
        install(tmp_path, tmp_path.parent / "other")
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "user-file").write_text("preserve")
    with pytest.raises(ValueError, match="empty"):
        install(SOURCE, root)
    (root / ".pwaf-install").touch()
    (root / ".install-lock").touch()
    with pytest.raises(ValueError, match="active"):
        install(SOURCE, root)


@pytest.mark.parametrize('platform, executable', [
    ('darwin', 'osascript'), ('win32', 'powershell.exe'), ('linux', 'zenity'),
])
def test_native_picker_preserves_selected_path(monkeypatch, platform, executable):
    from scripts import install_runtime as installer

    selected = '/chosen folder/with Unicode é and $literal'
    monkeypatch.setattr(installer.sys, 'platform', platform)
    monkeypatch.setenv('DISPLAY', ':0')
    monkeypatch.setattr(installer.shutil, 'which', lambda name: name)

    def choose(command, **kwargs):
        assert command[0] == executable
        assert kwargs['encoding'] == 'utf-8'
        return subprocess.CompletedProcess(command, 0, selected + '\n', '')

    monkeypatch.setattr(installer.subprocess, 'run', choose)
    assert installer.select_destination() == Path(selected)


@pytest.mark.parametrize('code, output', [(0, ''), (1, '')])
def test_linux_picker_cancel(monkeypatch, code, output):
    from scripts import install_runtime as installer

    monkeypatch.setattr(installer.sys, 'platform', 'linux')
    monkeypatch.setenv('DISPLAY', ':0')
    monkeypatch.setattr(installer.shutil, 'which', lambda name: name)
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], code, output, ''))
    assert installer.select_destination() is None


def test_picker_unavailable_or_failed(monkeypatch):
    from scripts import install_runtime as installer

    monkeypatch.setattr(installer.sys, 'platform', 'linux')
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    with pytest.raises(ValueError, match='--destination'):
        installer.select_destination()
    monkeypatch.setenv('DISPLAY', ':0')
    monkeypatch.setattr(installer.shutil, 'which', lambda name: None)
    with pytest.raises(ValueError, match='zenity or kdialog'):
        installer.select_destination()
    monkeypatch.setattr(installer.shutil, 'which', lambda name: name)
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 2, '', 'display failed'))
    with pytest.raises(ValueError, match='display failed'):
        installer.select_destination()


@pytest.mark.parametrize('explicit', [True, False])
def test_installer_destination_selection(tmp_path, monkeypatch, explicit):
    from scripts import install_runtime as installer

    destination = tmp_path / 'chosen folder'
    monkeypatch.setattr(installer.sys, 'argv', ['install'] + (
        ['--destination', str(destination)] if explicit else []))

    def choose():
        assert not explicit, 'Explicit destination must bypass the picker'
        return destination

    calls = []
    monkeypatch.setattr(installer, 'select_destination', choose)
    monkeypatch.setattr(installer, 'install', lambda source, path, **kw:
                        calls.append(path) or path / 'release')
    installer.main()
    assert calls == [destination]


def test_cancel_does_not_install(monkeypatch, capsys):
    from scripts import install_runtime as installer

    monkeypatch.setattr(installer.sys, 'argv', ['install'])
    monkeypatch.setattr(installer, 'select_destination', lambda: None)
    monkeypatch.setattr(installer, 'install', lambda *a, **k: pytest.fail('Install on cancel'))
    installer.main()
    assert 'cancelled' in capsys.readouterr().out


@pytest.mark.parametrize('browser_only', [False, True])
def test_install_dependency_mode(tmp_path, monkeypatch, browser_only):
    from scripts import install_runtime as installer

    root = tmp_path / 'installed'
    monkeypatch.setattr(installer.venv.EnvBuilder, 'create', lambda self, path: path.mkdir())
    commands = []
    monkeypatch.setattr(installer.subprocess, 'run', lambda command, **kw: commands.append(command))
    kwargs = {'desktop': False} if browser_only else {}
    installer.install(SOURCE, root, **kwargs)
    assert commands[0][-1] == str(SOURCE) + ('' if browser_only else '[desktop]')
    assert json.loads((root / 'active.json').read_text())['desktop'] is not browser_only


@pytest.mark.parametrize('stored, args, module', [
    (True, [], 'app.desktop'), (False, [], 'app'),
    (True, ['--browser-only'], 'app'), (False, ['--desktop'], 'app.desktop'),
    (None, [], 'app'),
])
def test_installed_launcher_mode(tmp_path, monkeypatch, stored, args, module):
    from scripts import runtime_launcher as launcher

    root = tmp_path / 'Installed App'
    environment = root / 'releases/test/.venv'
    for relative in ('bin/python', 'Scripts/python.exe'):
        executable = environment / relative
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.touch()
    activation = {'release': 'test'}
    if stored is not None:
        activation['desktop'] = stored
    (root / 'active.json').write_text(json.dumps(activation))
    monkeypatch.setattr(launcher, '__file__', str(root / 'launch.py'))
    monkeypatch.setattr(launcher.sys, 'argv', ['launch.py', *args])
    monkeypatch.delenv('PWAF_DATA_DIR', raising=False)

    class Launched(Exception):
        pass

    def check(command, env):
        assert command[-1] == module
        assert env['PWAF_DATA_DIR'] == str(root / 'data')
        raise Launched

    monkeypatch.setattr(launcher.os, 'execve', lambda python, command, env: check(command, env))
    monkeypatch.setattr(launcher.subprocess, 'call', lambda command, env, cwd: check(command, env))
    with pytest.raises(Launched):
        launcher.main()


def test_application_identity_guards_and_legacy_adoption(tmp_path, monkeypatch):
    from scripts.install_runtime import application_identity

    monkeypatch.setattr("scripts.install_runtime.venv.EnvBuilder.create",
                        lambda self, path: path.mkdir())
    monkeypatch.setattr("scripts.install_runtime.subprocess.run", lambda *a, **k: None)
    root = tmp_path / "installed"
    install(SOURCE, root)
    marker = root / ".pwaf-install"
    assert json.loads(marker.read_text())["application_id"] == application_identity(SOURCE)
    original = (root / "active.json").read_bytes()
    for content in ('{"format":1,"application_id":"different-app"}', '{broken', '{}', '[]'):
        marker.write_text(content)
        with pytest.raises(ValueError):
            install(SOURCE, root, adopt_legacy=True)
        assert marker.read_text() == content
        assert (root / "active.json").read_bytes() == original
    marker.write_text('')
    with pytest.raises(ValueError, match='adopt-legacy'):
        install(SOURCE, root)
    assert marker.read_text() == ''
    install(SOURCE, root, adopt_legacy=True)
    assert json.loads(marker.read_text())['application_id'] == application_identity(SOURCE)


@pytest.mark.parametrize('content', ['{}', '[]', '{', '{"id":42}', '{"id":"../app"}'])
def test_source_identity_validation(tmp_path, content):
    from scripts.install_runtime import application_identity

    with pytest.raises(ValueError, match='identity.json'):
        application_identity(tmp_path)
    (tmp_path / 'app').mkdir()
    (tmp_path / 'app/identity.json').write_text(content)
    with pytest.raises(ValueError, match='identity.json'):
        application_identity(tmp_path)


def test_legacy_cli_requires_destination(monkeypatch):
    from scripts import install_runtime

    monkeypatch.setattr(install_runtime.sys, 'argv', ['install', '--adopt-legacy-install'])
    with pytest.raises(SystemExit, match='explicit --destination'):
        install_runtime.main()


@pytest.mark.parametrize('desktop,shortcuts,expected', [
    (True, True, 1), (True, False, 0), (False, True, 0),
])
def test_native_launcher_install_modes(tmp_path, monkeypatch, desktop, shortcuts, expected):
    from scripts import install_runtime as installer

    monkeypatch.setattr(installer.venv.EnvBuilder, 'create', lambda self, path: path.mkdir())
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(installer, 'install_launchers', lambda *a: calls.append(a))
    root = tmp_path / 'installed'
    installer.install(SOURCE, root, desktop=desktop, shortcuts=shortcuts)
    assert len(calls) == expected
    if expected:
        assert calls[0][0] == root
        assert calls[0][1].name == 'Python Web App'


def test_native_launcher_failure_preserves_activation_and_data(tmp_path, monkeypatch):
    from scripts import install_runtime as installer

    monkeypatch.setattr(installer.venv.EnvBuilder, 'create', lambda self, path: path.mkdir())
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k: None)
    root = tmp_path / 'installed'
    installer.install(SOURCE, root, desktop=False)
    active = (root / 'active.json').read_bytes()
    (root / 'data').mkdir()
    settings = root / 'data/settings.json'
    settings.write_text('{"app_name":"Keep me"}')

    def fail(*args):
        raise OSError('Shortcut creation failed')

    monkeypatch.setattr(installer, 'install_launchers', fail)
    with pytest.raises(OSError, match='Shortcut'):
        installer.install(SOURCE, root)
    assert (root / 'active.json').read_bytes() == active
    assert settings.read_text() == '{"app_name":"Keep me"}'
