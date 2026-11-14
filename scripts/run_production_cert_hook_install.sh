#!/usr/bin/env bash
# Operator-triggered installation of the pinned production renewal hook.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
hook=/tmp/di-prod-package.sRcAd3JH/render/certbot-deploy-hook.sh
installer=$(base64 < "$root/scripts/install_production_cert_hook.py" | tr -d '\n')
encoded_hook=$(base64 < "$hook" | tr -d '\n')
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import base64; exec(compile(base64.b64decode(\"$installer\"),\"install-hook\",\"exec\"))' '$encoded_hook'"
