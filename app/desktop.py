"""Launch the example in an optional native desktop window.

Browser operation never imports this module or the pywebview dependency.
"""

import logging

from app.app import create_example_app
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.desktop import launch_desktop


def main() -> None:
    """Read configuration and coordinate the desktop window and web server."""
    try:
        config = RuntimeConfig.from_env()
        logging.basicConfig(level=config.log_level)
        launch_desktop(create_example_app(config), config)
    except (ValueError, RuntimeError, OSError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
