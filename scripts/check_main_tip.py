#!/usr/bin/env python3
"""Fail closed unless this workflow revision is still the main branch tip."""

import json
import os
import re
import urllib.request


def main():
    """Query GitHub immediately before starting a deployment."""
    repository = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid revision")
    request = urllib.request.Request(
        f"{os.environ['GITHUB_API_URL']}/repos/{repository}/git/ref/heads/main",
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        tip = json.load(response)["object"]["sha"]
    if tip != sha:
        raise SystemExit(
            "Refusing to deploy: workflow revision is not the current main tip"
        )


if __name__ == "__main__":
    main()
