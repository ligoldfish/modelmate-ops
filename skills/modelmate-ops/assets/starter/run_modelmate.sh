#!/usr/bin/env bash
set -Eeuo pipefail
MM_SOURCE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
MM_PYTHON=${PYTHON_BIN:-python3}
exec "$MM_PYTHON" -u "$MM_SOURCE_ROOT/main.py" "$@"
