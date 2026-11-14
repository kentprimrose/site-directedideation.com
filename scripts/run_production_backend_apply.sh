#!/usr/bin/env bash
# Operator-triggered backend switch; staging access will be interrupted.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
wrapper=$(base64 < "$root/scripts/apply_production_cutover.py" | tr -d '\n')
helper=$(base64 < "$root/staging_mcp/prod-cutover/backend-transition.sh" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$wrapper\"),\"backend-apply\",\"exec\"))' '$helper'"
