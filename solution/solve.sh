#!/bin/sh
set -eu
# Harbor executes this after provisioning the starter project at /app.
TARGET_DIR=${TARGET_DIR:-/app}
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

cp "$SOURCE_DIR/gravity_sim/__init__.py" "$TARGET_DIR/gravity_sim/__init__.py"
cp "$SOURCE_DIR/gravity_sim/core.py" "$TARGET_DIR/gravity_sim/core.py"
cp "$SOURCE_DIR/gravity_sim/__main__.py" "$TARGET_DIR/gravity_sim/__main__.py"
