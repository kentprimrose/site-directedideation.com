"""Bounded, transactional aggregate metrics shared by MCP and the admin site."""

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

TOOLS = (
    "get_directed_ideation_method",
    "get_interview_guidance",
    "get_diagnostic_checks",
    "get_alternative_techniques",
)
STAGES = ("identify-opportunities", "select-goals", "ideate-with-purpose", "unfiltered")


def configuration():
    """Require an explicit environment and database location."""
    load_dotenv()
    environment = os.getenv("METRICS_ENV", "")
    path = os.getenv("METRICS_DB", "")
    if (
        environment not in {"development", "production"}
        or not path
        or path == ":memory:"
        or path.startswith("file:")
    ):
        raise RuntimeError(
            "Set METRICS_ENV to development or production and "
            "METRICS_DB to a SQLite file path"
        )
    return environment, Path(path).expanduser().resolve()


def connect():
    """Open and initialize the aggregate-only database."""
    _, path = configuration()
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS counters (dimension TEXT NOT NULL, "
            "name TEXT NOT NULL, count INTEGER NOT NULL CHECK(count >= 0), "
            "PRIMARY KEY(dimension, name))"
        )
        connection.commit()
    except BaseException:
        connection.close()
        raise
    return connection


def increment(tool, stage=None):
    """Atomically update only predefined independent counters."""
    if tool not in TOOLS or (stage is not None and stage not in STAGES):
        raise ValueError("Invalid aggregate key")
    connection = connect()
    try:
        with connection:
            for dimension, name in (
                ("tools", tool),
                *([("stage_filters", stage)] if stage is not None else []),
            ):
                connection.execute(
                    "INSERT INTO counters VALUES (?, ?, 1) "
                    "ON CONFLICT(dimension, name) DO UPDATE SET count = count + 1",
                    (dimension, name),
                )
    finally:
        connection.close()


def snapshot():
    """Return all bounded counters, including zeroes."""
    result = {
        "tools": dict.fromkeys(TOOLS, 0),
        "stage_filters": dict.fromkeys(STAGES, 0),
    }
    connection = connect()
    try:
        for dimension, name, count in connection.execute(
            "SELECT dimension, name, count FROM counters"
        ):
            if dimension in result and name in result[dimension]:
                result[dimension][name] = count
    finally:
        connection.close()
    return result
