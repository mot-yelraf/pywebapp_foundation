"""Create per-user application launchers and native desktop identities.

Launchers select the stable installation root rather than a particular release.
No GUI libraries are imported while creating installer artifacts.
"""

import ctypes
import json
import logging
import os
import plistlib
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from pwaf_foundation.identity import DesktopIdentity

LOG = logging.getLogger(__name__)
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _text(path: Path, content: str) -> None:
    _write(path, content.encode("utf-8"))


def _desktop_string(value: str) -> str:
    return (value.replace("\\", "\\\\").replace("\n", "\\n")
            .replace("\r", "\\r").replace("\t", "\\t"))


def _exec_arg(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in ('"', '`', '$'):
        escaped = escaped.replace(character, "\\" + character)
    return _desktop_string('"' + escaped.replace("%", "%%") + '"')


def write_linux_launcher(root: Path, identity: DesktopIdentity, data_home: Path) -> Path:
    """Create a Linux/Raspberry Pi application-menu entry and themed icon."""
    path = data_home / "applications" / f"{identity.native_id}.desktop"
    owner = f"X-PWAF-InstallRoot={_desktop_string(str(root))}\n"
    if path.exists() and owner not in path.read_text(encoding="utf-8"):
        raise ValueError("Application menu entry belongs to another installation")
    _write(data_home / "icons/hicolor/512x512/apps" / f"{identity.native_id}.png",
           identity.icon("png").read_bytes())
    _text(path, "\n".join([
        "[Desktop Entry]", "Type=Application", f"Name={_desktop_string(identity.name)}",
        f"Exec={_exec_arg(str(root / 'run.sh'))} --desktop", f"Path={_desktop_string(str(root))}",
        f"Icon={identity.native_id}", "Terminal=false", "StartupNotify=true",
        f"StartupWMClass={identity.native_id}", f"X-PWAF-InstallRoot={_desktop_string(str(root))}",
        "Categories=Utility;", "",
    ]))
    return path


def _bundle(bundle: Path, identity: DesktopIdentity, owner: str, *, launcher: bool) -> Path:
    info = bundle / "Contents/Info.plist"
    identifier = identity.native_id + (".launcher" if launcher else "")
    if bundle.exists():
        try:
            existing = plistlib.loads(info.read_bytes())
            if (not isinstance(existing, dict)
                    or existing.get("CFBundleIdentifier") != identifier
                    or existing.get("PWAFOrigin") != owner):
                raise ValueError("Application bundle belongs to another installation")
        except (OSError, plistlib.InvalidFileException) as exc:
            raise ValueError("Refusing to overwrite an unrecognized application bundle") from exc
    executable = bundle / "Contents/MacOS" / identity.name
    executable.parent.mkdir(parents=True, exist_ok=True)
    _write(bundle / "Contents/Resources/app.icns", identity.icon("icns").read_bytes())
    _write(info, plistlib.dumps({
        "CFBundleDisplayName": identity.name, "CFBundleName": identity.name,
        "CFBundleExecutable": identity.name, "CFBundleIdentifier": identifier,
        "CFBundleIconFile": "app.icns", "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0", "NSHighResolutionCapable": True,
        "LSUIElement": launcher, "PWAFOrigin": owner,
    }))
    return executable


def write_macos_launcher(root: Path, identity: DesktopIdentity, applications: Path) -> Path:
    """Create a Finder app with a bundled native launcher and installed icon."""
    bundle = applications / f"{identity.name}.app"
    executable = _bundle(bundle, identity, str(root), launcher=True)
    native = Path(__file__).parent / "static/launchers/pwaf-macos-launcher"
    _write(executable, native.read_bytes())
    executable.chmod(0o755)
    _text(bundle / "Contents/Resources/launch.sh",
          "#!/bin/sh\n" + f"cd {shlex.quote(str(root))}\n"
          + "mkdir -p data\n" + f"exec {shlex.quote(str(root / 'run.sh'))} --desktop "
          + '>>data/desktop-launch.log 2>&1\n')
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--identifier",
                    identity.native_id + ".launcher", str(bundle)], check=True, capture_output=True)
    subprocess.run([LSREGISTER, "-f", str(bundle)], check=True, capture_output=True)
    return bundle


def write_windows_launchers(root: Path, identity: DesktopIdentity, bootstrap: Path) -> list[Path]:
    """Create Desktop and Start Menu shortcuts through the user's Windows shell."""
    # JSON transports paths/names safely; no application text is interpolated into PowerShell.
    metadata = root / "native-shortcut.json"
    _text(metadata, json.dumps({"root": str(root), "name": identity.name,
                               "python": str(bootstrap.with_name("pythonw.exe")
                                             if bootstrap.with_name("pythonw.exe").is_file()
                                             else bootstrap), "id": identity.native_id,
                               "icon": str(identity.icon("ico"))}))
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$m = Get-Content -LiteralPath __METADATA__ -Raw | ConvertFrom-Json
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PWAFShortcutIdentity {
    [StructLayout(LayoutKind.Sequential)] public struct Key {
        public Guid format; public uint id;
    }
    [StructLayout(LayoutKind.Explicit, Size=24)] public struct Variant {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr text;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface Store {
        void GetCount(out uint count);
        void GetAt(uint index, out Key key);
        void GetValue(ref Key key, out Variant value);
        void SetValue(ref Key key, ref Variant value);
        void Commit();
    }
    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
    static extern void SHGetPropertyStoreFromParsingName(
        string path, IntPtr context, uint flags, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out Store store);
    public static void Set(string path, string id) {
        Guid iid = typeof(Store).GUID;
        Store store;
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out store);
        Variant value = new Variant();
        value.type = 31;
        value.text = Marshal.StringToCoTaskMemUni(id);
        try {
            Key key = new Key();
            key.format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
            key.id = 5;
            store.SetValue(ref key, ref value);
            store.Commit();
        } finally {
            Marshal.FreeCoTaskMem(value.text);
            Marshal.ReleaseComObject(store);
        }
    }
}
'@
$shell = New-Object -ComObject WScript.Shell
$folders = @([Environment]::GetFolderPath('DesktopDirectory'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) $m.id))
foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $path = Join-Path $folder ($m.name + '.lnk')
    $link = $shell.CreateShortcut($path)
    if ((Test-Path -LiteralPath $path) -and $link.WorkingDirectory -ne $m.root) {
        throw 'Shortcut belongs to another installation'
    }
    $link.TargetPath = $m.python
    $link.Arguments = '"' + (Join-Path $m.root 'launch.py') + '" --desktop'
    $link.WorkingDirectory = $m.root
    $link.IconLocation = $m.icon + ',0'
    $link.Description = $m.name
    $link.Save()
    [PWAFShortcutIdentity]::Set($path, $m.id)
    Write-Output $path
}
'''
    script = script.replace("__METADATA__", "'" + str(metadata).replace("'", "''") + "'")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                            check=True, capture_output=True, text=True, encoding="utf-8")
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def install_launchers(root: Path, identity: DesktopIdentity, bootstrap: Path) -> list[Path]:
    """Install the current platform's per-user launchers, preserving other apps."""
    # Keep icons stable across release selection and independent of the checkout.
    icons = root / "native-icons"
    for extension in ("png", "ico", "icns"):
        _write(icons / f"app.{extension}", identity.icon(extension).read_bytes())
    identity = DesktopIdentity(identity.id, identity.name, icons, "app")
    if sys.platform == "darwin":
        paths = [write_macos_launcher(root, identity, Path.home() / "Applications")]
    elif sys.platform == "win32":
        paths = write_windows_launchers(root, identity, bootstrap)
    elif sys.platform.startswith("linux"):
        data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        if not data_home.is_absolute():
            raise ValueError("XDG_DATA_HOME must be absolute")
        paths = [write_linux_launcher(root, identity, data_home)]
    else:
        raise ValueError("Native launchers are unsupported on this platform")
    _text(root / "native-launchers.json", json.dumps([str(path) for path in paths]) + "\n")
    return paths


def prepare_desktop_identity(
    identity: DesktopIdentity, *, module: str, bundle_root: Path | None = None,
    entrypoint: Path | None = None,
) -> None:
    """Establish app identity before importing pywebview or starting any resources.

    macOS re-executes the same interpreter through an app bundle. Linux sets GLib
    naming before GTK initialization; Windows sets its process AppUserModelID.
    """
    if (sys.platform == "darwin" and not getattr(sys, "frozen", False)
            and not hasattr(sys, "_MEIPASS")):
        if os.environ.get("PWAF_DESKTOP_IDENTITY") == identity.native_id:
            return
        # Scope by interpreter so source and installed environments cannot collide.
        import hashlib

        scope = hashlib.sha256(str(sys.executable).encode()).hexdigest()[:16]
        directory = bundle_root or Path.home() / "Library/Application Support/PWAF"
        bundle = directory / identity.id / scope / f"{identity.name}.app"
        executable = _bundle(bundle, identity, str(sys.executable), launcher=False)
        temporary = executable.with_name(".python-link")
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(sys.executable)
        temporary.replace(executable)
        environment = dict(os.environ, PWAF_DESKTOP_IDENTITY=identity.native_id)
        # CPython otherwise searches beside the bundle link and loses a copied
        # venv's pyvenv.cfg. This macOS launcher hint preserves its original prefix.
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        # Source launch keeps its current cwd; installed launch preserves isolated imports.
        flags = ["-I"] if sys.flags.isolated else []
        target = [str(entrypoint)] if entrypoint else ["-m", module]
        os.execve(executable, [str(executable), *flags, *target, *sys.argv[1:]], environment)
    elif sys.platform.startswith("linux"):
        configured = False
        try:
            from gi.repository import GLib

            GLib.set_prgname(identity.native_id)
            GLib.set_application_name(identity.name)
            configured = True
        except ImportError:
            pass
        try:
            from qtpy.QtCore import QCoreApplication
            from qtpy.QtGui import QGuiApplication

            QCoreApplication.setApplicationName(identity.name)
            QGuiApplication.setApplicationDisplayName(identity.name)
            QGuiApplication.setDesktopFileName(identity.native_id)
            configured = True
        except ImportError:
            pass
        if not configured:
            LOG.warning("Linux native identity requires GTK/GLib or Qt desktop support")
    elif sys.platform == "win32":
        set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_id.argtypes = [ctypes.c_wchar_p]
        set_id.restype = ctypes.c_long
        result = set_id(identity.native_id)
        if result:
            raise OSError("Could not set Windows application identity")
