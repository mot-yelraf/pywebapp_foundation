"""Run the example performance tool without starting a web server.

The JSON output is also the trusted subprocess protocol used by the web adapter.
"""

import argparse

from pydantic import ValidationError

from app.services.performance import PerformanceInput, benchmark


def main(argv: list[str] | None = None) -> None:
    """Validate workload limits and print the shared result model as JSON."""
    parser = argparse.ArgumentParser(description="Run a bounded SHA-256 benchmark")
    parser.add_argument("--iterations", type=int, default=100000)
    args = parser.parse_args(argv)
    try:
        parameters = PerformanceInput(iterations=args.iterations)
    except ValidationError:
        parser.error("--iterations must be between 1 and 5000000")
    print(benchmark(parameters).model_dump_json())


if __name__ == "__main__":
    main()
