#!/usr/bin/env bash
# Operator-triggered certificate issuance; does not change nginx configuration.
set -euo pipefail
exec ssh -t kent@138.197.24.16 'sudo certbot certonly --webroot -w /var/lib/di-staging-acme -d mcp.directedideation.com --keep-until-expiring'
