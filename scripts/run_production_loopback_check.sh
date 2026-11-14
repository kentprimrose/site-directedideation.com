#!/usr/bin/env bash
# Read-only loopback checks; the issuer remains on the server.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
program=$(base64 < "$root/scripts/verify_production_backend.py" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$program\"),\"verify-backend\",\"exec\"))'"
