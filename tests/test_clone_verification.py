"""Keep clone-origin verification strict across filesystem path aliases.

The import guard must normalize both its module path and the clone directory,
while continuing to reject packages loaded from the original checkout.
"""

import os
import subprocess

import pytest

from scripts.verify_clone import assert_clone_import


def test_clone_import_rejects_external_package(tmp_path):
    clone = tmp_path / 'clone'
    clone.mkdir()
    local = clone / 'pwaf_foundation/__init__.py'
    local.parent.mkdir()
    local.touch()
    assert_clone_import(str(local), clone)
    external = tmp_path / 'other/pwaf_foundation/__init__.py'
    external.parent.mkdir(parents=True)
    external.touch()
    with pytest.raises(AssertionError, match='outside clone'):
        assert_clone_import(str(external), clone)


def test_clone_import_accepts_directory_alias(tmp_path):
    root = tmp_path / 'long clone directory'
    module = root / 'pwaf_foundation/__init__.py'
    module.parent.mkdir(parents=True)
    module.touch()
    alias = tmp_path / 'alias'
    if os.name == 'nt':
        # Junction creation needs no administrator or symlink privilege on NTFS.
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(root)],
                       check=True, capture_output=True)
    else:
        alias.symlink_to(root, target_is_directory=True)
    try:
        assert module.resolve().is_relative_to(root.resolve())
        assert not module.resolve().is_relative_to(alias)
        assert_clone_import(str(module), alias)
        assert_clone_import(str(alias / 'pwaf_foundation/__init__.py'), root)
    finally:
        if os.name == 'nt':
            alias.rmdir()  # Remove only the junction, never the target directory.
        else:
            alias.unlink()
    assert module.is_file()
