#!/usr/bin/env bash
# Operator-triggered private recovery record; does not restart the backend.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
wrapper=$(base64 < "$root/scripts/record_production_cutover.py" | tr -d '\n')
helper=$(base64 < "$root/staging_mcp/prod-cutover/backend-transition.sh" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$wrapper\"),\"backend-record\",\"exec\"))' '$helper'"
