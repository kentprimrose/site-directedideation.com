#!/usr/bin/env bash
# Explicit operator-triggered staging switch. Never run without live approval.
set -euo pipefail
exec ssh -t kent@138.197.24.16 "sudo python3 -c 'import hashlib; p=\"/home/kent/di-manual-switch.py\"; data=open(p,\"rb\").read(); assert hashlib.sha256(data).hexdigest()==\"205c9a5ae7f7b21dd2e67a64f669e4e9e7e7376aea3920b9146b914935513205\"; exec(compile(data,p,\"exec\"))' switch sha256:00e4d4579ef34ed01128851597be7e72cbded412a9bfb43dffa31a9344f31dde sha256:68ed3c8ec24a9a4cc0ff22244595e155fd9d4fb92469eb2c32db36d288c416bc 8530bd8b4071cfba9943d66105a776da613193cb8fbe10f317c200ab82cae5ff"
