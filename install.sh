#!/bin/sh
# Install into a user-owned directory; Python handles quoting and atomic activation.
set -eu
PWAF_SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Bootstrap only; install_runtime.py selects and validates the runtime interpreter.
# Honor an explicit interpreter even when python3 is absent or points to an old Python.
PWAF_BOOTSTRAP=python3
PWAF_EXPECT_PYTHON=false
for PWAF_ARGUMENT do
    if [ "$PWAF_EXPECT_PYTHON" = true ]; then
        PWAF_BOOTSTRAP=$PWAF_ARGUMENT
        break
    fi
    case "$PWAF_ARGUMENT" in
        --python) PWAF_EXPECT_PYTHON=true ;;
        --python=*) PWAF_BOOTSTRAP=${PWAF_ARGUMENT#--python=}; break ;;
    esac
done
exec "$PWAF_BOOTSTRAP" "$PWAF_SOURCE_DIR/scripts/install_runtime.py" "$@"
