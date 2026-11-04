#!/usr/bin/env python3
"""Disabled: a proxy alone cannot enforce local-only staging traffic."""

import sys


def main():
    """Fail closed without starting clients, listeners, or credential handling."""
    print(
        "Local HTTPS WorkOS harness disabled: proxy settings cannot prevent "
        "a client from connecting to the public staging endpoint. "
        "See scripts/WORKOS_LOCAL_HTTPS.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
