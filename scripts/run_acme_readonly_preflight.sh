#!/usr/bin/env bash
# Read-only nginx preflight; no remote file or configuration changes.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
encoded=$(base64 < "$root/scripts/acme_readonly_preflight.py" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$encoded\"),\"acme-preflight\",\"exec\"))'"
