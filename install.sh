#!/bin/sh
# Install into a user-owned directory; Python handles quoting and atomic activation.
set -eu
PWAF_SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$PWAF_SOURCE_DIR/scripts/install_runtime.py" "$@"
