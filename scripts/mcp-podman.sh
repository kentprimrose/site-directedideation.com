#!/usr/bin/env bash
# Manage only the local MCP container; the metrics volume is never removed.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
container=directedideation-local-mcp
image=localhost/directedideation-local-mcp:latest
volume=directedideation-local-mcp-metrics
label=site-directedideation.local-mcp

usage() { echo "Usage: $0 {start|stop}" >&2; }
if [[ $# != 1 || ( $1 != start && $1 != stop ) ]]; then usage; exit 2; fi
command -v podman >/dev/null || { echo 'Podman is required.' >&2; exit 1; }

# On macOS/Windows, start the configured default machine if the engine is down.
# A running native Linux engine needs no machine.
if ! podman info >/dev/null 2>&1; then
    if [[ $1 == stop ]]; then
        echo 'Podman is unavailable; no container was stopped.' >&2
        exit 1
    fi
    echo 'Podman is unavailable; attempting to start the default Podman machine.' >&2
    podman machine start
    podman info >/dev/null || { echo 'Podman is still unavailable.' >&2; exit 1; }
fi

# Refuse to touch a same-named container not created by this script.
if podman container exists "$container"; then
    owner=$(podman inspect --format '{{index .Config.Labels "site-directedideation.owner"}}' "$container")
    if [[ $owner != "$label" ]]; then
        echo "Container $container already exists and is not managed by this script." >&2
        exit 1
    fi
    exists=1
else
    exists=0
fi

if [[ $1 == stop ]]; then
    if (( exists )); then
        podman stop --ignore "$container"
        echo 'MCP stopped; metrics volume preserved.'
    else
        echo 'MCP is not running; metrics volume preserved.'
    fi
    exit 0
fi

# Always invoke the build: Podman's layer cache avoids unnecessary work while
# ensuring changes to the build context are incorporated, including dirty files.
podman build --tag "$image" --file "$root/Dockerfile" "$root"
if (( exists )); then
    podman rm --force "$container" >/dev/null
fi
if ! podman run --detach --name "$container" \
    --label "site-directedideation.owner=$label" \
    --publish 127.0.0.1:8001:8001 \
    --volume "$volume:/metrics" \
    --security-opt no-new-privileges --cap-drop ALL --read-only --tmpfs /tmp \
    "$image"; then
    echo 'Failed to start MCP. Check Podman output above; localhost port 8001 may already be in use. No other service was stopped.' >&2
    exit 1
fi
echo 'MCP started on localhost port 8001: http://127.0.0.1:8001/mcp'
echo 'Metrics are retained in the Podman volume.'
