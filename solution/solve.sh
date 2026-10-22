#!/bin/sh
set -eu
# Harbor executes this after provisioning the starter project at /app.
TARGET_DIR=${TARGET_DIR:-/app}
cp "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/gravity_sim/core.py" "$TARGET_DIR/gravity_sim/core.py"
