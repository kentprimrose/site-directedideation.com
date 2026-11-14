#!/usr/bin/env bash
# Operator-triggered isolated production certificate hook test (reloads nginx).
set -euo pipefail
exec ssh -t kent@138.197.24.16 'sudo env RENEWED_LINEAGE=/etc/letsencrypt/live/mcp.directedideation.com /etc/letsencrypt/renewal-hooks/deploy/di-mcp-reload.sh && echo "PASS: production renewal hook completed"'
