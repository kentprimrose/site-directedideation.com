#!/usr/bin/env python3
"""Run sequential Pi RPC prompts from a JSON array, emitting JSON events.

Requires an already-isolated PI_CODING_AGENT_DIR and working directory. The
caller is responsible for ensuring prompts and MCP arguments contain no private
context. A reader thread drains stdout continuously; each turn has one monotonic
absolute deadline, not a deadline reset by incoming events.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time


def main():  # noqa: C901
    """Run the configured sequence of model turns."""
    prompts = json.load(sys.stdin)
    events = queue.Queue()
    command = [
        "pi",
        "--mode",
        "rpc",
        "--no-session",
        "--no-extensions",
        "-e",
        "builtin:mcp",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--tools",
        "mcp__directed_ideation__*",
        "--model",
        "openai/gpt-6.1-terra",
        "--thinking",
        "low",
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    assert process.stdin is not None
    assert process.stdout is not None
    stdout = process.stdout

    def drain():
        for line in stdout:
            events.put(line)
        events.put(None)

    threading.Thread(target=drain, daemon=True).start()
    try:
        for index, prompt in enumerate(prompts):
            process.stdin.write(
                json.dumps({"type": "prompt", "message": prompt}) + "\n"
            )
            process.stdin.flush()
            deadline = time.monotonic() + float(os.environ.get("PROBE_TIMEOUT", "120"))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"turn {index + 1} exceeded deadline")
                try:
                    line = events.get(timeout=remaining)
                except queue.Empty as exc:
                    raise TimeoutError(f"turn {index + 1} exceeded deadline") from exc
                if line is None:
                    raise RuntimeError(f"Pi exited before turn {index + 1} settled")
                event = json.loads(line)
                print(json.dumps({"turn": index + 1, "event": event}), flush=True)
                if event.get("type") == "response" and not event.get("success", True):
                    raise RuntimeError(f"Pi rejected command on turn {index + 1}")
                if event.get("type") == "agent_settled":
                    break
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
