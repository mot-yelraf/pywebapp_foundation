"""Launch the example in an optional native desktop window.

Browser operation never imports this module or the pywebview dependency.
"""

import logging
from pathlib import Path

from app.app import create_example_app
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.desktop import launch_desktop
from pwaf_foundation.identity import DesktopIdentity
from pwaf_foundation.launchers import prepare_desktop_identity


def main() -> None:
    """Read configuration and coordinate the desktop window and web server."""
    try:
        config = RuntimeConfig.from_env()
        logging.basicConfig(level=config.log_level)
        identity = DesktopIdentity.load(Path(__file__).with_name("identity.json"))
        if config.mode != "local":
            raise ValueError("Desktop mode requires PWAF_MODE=local")
        prepare_desktop_identity(identity, module="app.desktop")
        launch_desktop(create_example_app(config), config, title=identity.name,
                       identity=identity)
    except (ValueError, RuntimeError, OSError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
