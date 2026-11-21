#!/usr/bin/env bash
set -euo pipefail

# Locate port_3rdparty.py relative to script or workspace
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/port_3rdparty.py" ]]; then
  PY_SCRIPT="${SCRIPT_DIR}/port_3rdparty.py"
elif [[ -n "${BUILD_WORKSPACE_DIRECTORY:-}" && -f "${BUILD_WORKSPACE_DIRECTORY}/tools/port_3rdparty.py" ]]; then
  PY_SCRIPT="${BUILD_WORKSPACE_DIRECTORY}/tools/port_3rdparty.py"
else
  PY_SCRIPT="$(find -L "${SCRIPT_DIR}" -name "port_3rdparty.py" 2>/dev/null | head -n 1)"
fi

exec python3 "${PY_SCRIPT}" "$@"
