"""Start the local browser server.

Only this command configures root logging and launches Uvicorn. Imports are inert.
"""

import logging

import uvicorn

from app.app import create_example_app
from pwaf_foundation.config import RuntimeConfig


def main() -> None:
    """Validate startup configuration and run one local server process."""
    try:
        config = RuntimeConfig.from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    logging.basicConfig(level=config.log_level, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        create_example_app(config),
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        proxy_headers=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
