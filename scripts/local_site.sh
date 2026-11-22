#!/usr/bin/env bash
# Control the local live-reloading website server.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
exec uv run local-site "$@"
