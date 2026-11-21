#!/usr/bin/env bash
# Helper script to configure BuildBuddy RBE credentials into .bazelrc.user
# Reads BB_TOKEN and optional BB_ENDPOINT from command line arguments or environment variables.
set -euo pipefail

WORKSPACE_DIR="${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
TARGET_RC="${WORKSPACE_DIR}/.bazelrc.user"

TOKEN="${1:-${BB_TOKEN:-}}"
ENDPOINT="${2:-${BB_ENDPOINT:-grpcs://remote.buildbuddy.io}}"

if [ -z "${TOKEN}" ]; then
  echo "Usage: $0 [BB_TOKEN] [BB_ENDPOINT]" >&2
  echo "Or export BB_TOKEN (and optional BB_ENDPOINT) in your environment before running." >&2
  exit 1
fi

if [[ ! "${ENDPOINT}" =~ ^grpcs?:// ]]; then
  ENDPOINT="grpcs://${ENDPOINT}"
fi

HOST="${ENDPOINT#*://}"
RESULTS_URL="https://${HOST}/invocation/"

cat <<EOF >> "${TARGET_RC}"

# BuildBuddy RBE credentials (configured via tools/setup_rbe.sh)
common:rbe --remote_executor=${ENDPOINT}
common:rbe --remote_cache=${ENDPOINT}
common:rbe --bes_backend=${ENDPOINT}
common:rbe --bes_results_url=${RESULTS_URL}
common:rbe --remote_header=x-buildbuddy-api-key=${TOKEN}
common:rbe --bes_header=x-buildbuddy-api-key=${TOKEN}
EOF

echo "BuildBuddy RBE credentials configured in ${TARGET_RC}"
