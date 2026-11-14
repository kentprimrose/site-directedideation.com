#!/usr/bin/env bash
# Operator-triggered production HTTP-01 route installation; requires approval.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
installer="$root/staging_mcp/install-production-http01.py"
expected=2322781f2c33f5410093746e52043add26259ed030aff157ef0421c25aa7e2a7
actual=$(shasum -a 256 "$installer" | cut -d ' ' -f 1)
[[ "$actual" == "$expected" ]] || { echo 'Installer hash mismatch.' >&2; exit 1; }
encoded=$(base64 < "$installer" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64,hashlib; d=base64.b64decode(\"$encoded\"); assert hashlib.sha256(d).hexdigest()==\"$expected\"; exec(compile(d,\"http01-installer\",\"exec\"))'"
