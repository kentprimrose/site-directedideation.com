#!/usr/bin/env bash
# Operator-triggered public production routing; reloads nginx.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
package=/tmp/di-prod-package.sRcAd3JH/render
wrapper=$(base64 < "$root/scripts/apply_production_nginx.py" | tr -d '\n')
installer=$(base64 < "$root/staging_mcp/prod-cutover/install-nginx-cutover.sh" | tr -d '\n')
conf=$(base64 < "$package/di-staging-public-test.conf" | tr -d '\n')
helper=$(base64 < "$package/di-shared-test" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$wrapper\"),\"nginx-cutover\",\"exec\"))' '$installer' '$conf' '$helper'"
