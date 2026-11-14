#!/usr/bin/env bash
# Operator-triggered creation of private settings; no service restart.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
program=$(base64 < "$root/scripts/create_production_backend_env.py" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$program\"),\"production-env\",\"exec\"))'"
