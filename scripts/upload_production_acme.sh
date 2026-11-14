#!/usr/bin/env bash
# Upload the reviewed HTTP-01 config only; does not activate it.
set -euo pipefail
source_file=/tmp/di-prod-package.sRcAd3JH/render/di-staging-acme-http01.conf
expected=178bb69096c437e5474e2f0af3e472d50435d4eae9c751d350089c60b7195d1f
actual=$(shasum -a 256 "$source_file" | cut -d ' ' -f 1)
[[ $actual == "$expected" ]] || { echo 'Local file hash mismatch.' >&2; exit 1; }
ssh kent@138.197.24.16 'umask 077; set -C; cat > /home/kent/di-production-acme-178bb690.conf' < "$source_file"
ssh kent@138.197.24.16 'sha256sum /home/kent/di-production-acme-178bb690.conf'
