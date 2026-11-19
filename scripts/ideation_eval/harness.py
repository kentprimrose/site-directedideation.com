#!/usr/bin/env python3
"""Run a locally configured, paired directed-ideation pilot."""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def load_config(path):
    """Load and validate the pilot configuration."""
    try:
        config = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read configuration: {exc}") from exc
    roles = config["models"]
    if len(roles) != 3 or len({r["id"] for r in roles}) != 3:
        raise ValueError("exactly three uniquely named models are required")
    for role in roles:
        if (
            not role.get("model")
            or not isinstance(role.get("command"), list)
            or not role["command"]
        ):
            raise ValueError("each model needs an explicit model and command array")
        if (
            not isinstance(role.get("version_command"), list)
            or not role["version_command"]
        ):
            raise ValueError("each model needs a version_command array")
    if (
        not isinstance(config.get("rounds"), int)
        or isinstance(config["rounds"], bool)
        or config["rounds"] < 1
    ):
        raise ValueError("rounds must be a positive integer")
    for key in ("scenario", "method", "control", "judge_rubric"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"{key} must be nonempty text")
    return config


def preflight(config):
    """Check local executable and version commands."""
    versions = {}
    for model in config["models"]:
        for command in (model["command"], model["version_command"]):
            if not shutil.which(command[0]):
                raise ValueError(f"executable not found: {command[0]}")
        result = subprocess.run(
            model["version_command"], capture_output=True, text=True, timeout=30
        )
        if result.returncode or not result.stdout.strip():
            raise ValueError(
                f"version check failed for {model['id']}: {result.stderr.strip()}"
            )
        versions[model["id"]] = result.stdout.strip()
    return versions


def save(path, value):
    """Write a JSON artifact."""
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def invoke(model, prompt, directory, name):
    """Invoke one configured model and retain its artifacts."""
    # Persist input before starting; retain failures and stderr.
    (directory / f"{name}.prompt.txt").write_text(prompt)
    try:
        result = subprocess.run(
            model["command"], input=prompt, text=True, capture_output=True, timeout=900
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        (directory / f"{name}.error.txt").write_text(str(exc))
        raise RuntimeError(f"{name} could not complete: {exc}") from exc
    (directory / f"{name}.stdout.txt").write_text(result.stdout)
    (directory / f"{name}.stderr.txt").write_text(result.stderr)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(f"{name} failed (exit {result.returncode}); see artifacts")
    return result.stdout.strip()


def session(config, facilitator, user, condition, folder):
    """Run a fresh simulated conversation."""
    instruction = config[condition]
    transcript = []
    for turn in range(config["rounds"]):
        history = json.dumps(transcript, ensure_ascii=False)
        message = invoke(
            facilitator,
            f"You are the facilitator. Follow these instructions:\n{instruction}\n"
            f"Scenario:\n{config['scenario']}\nConversation so far: {history}\n"
            "Provide only your next message.",
            folder,
            f"{turn:02d}-facilitator",
        )
        transcript.append({"speaker": "facilitator", "text": message})
        history = json.dumps(transcript, ensure_ascii=False)
        message = invoke(
            user,
            "You are simulating the participant in this scenario:\n"
            f"{config['scenario']}\n"
            f"Conversation so far: {history}\n"
            "Respond naturally as the participant; provide only your next message.",
            folder,
            f"{turn:02d}-participant",
        )
        transcript.append({"speaker": "participant", "text": message})
        save(folder / "transcript.json", transcript)
    return transcript


def run(config, versions, output, seed):
    """Run three paired role rotations."""
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    save(
        output / "manifest.json",
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "config": config,
            "versions": versions,
            "seed": seed,
            "status": "running",
        },
    )
    rng = random.Random(seed)
    try:
        for rotation in range(3):
            facilitator, participant, judge = (
                config["models"][(rotation + i) % 3] for i in range(3)
            )
            folder = output / f"rotation-{rotation + 1}"
            folder.mkdir()
            order = ["method", "control"]
            rng.shuffle(order)
            transcripts = {}
            for condition in order:
                case = folder / condition
                case.mkdir()
                transcripts[condition] = session(
                    config, facilitator, participant, condition, case
                )
            blind_order = ["method", "control"]
            rng.shuffle(blind_order)
            candidates = {
                label: transcripts[condition]
                for label, condition in zip(("A", "B"), blind_order)
            }
            save(
                folder / "blind-key.json",
                {
                    "A": blind_order[0],
                    "B": blind_order[1],
                    "execution_order": order,
                    "facilitator": facilitator["id"],
                    "participant": participant["id"],
                    "judge": judge["id"],
                },
            )
            prompt = (
                "Evaluate these anonymized conversations independently "
                "and compare them. "
                "Do not infer conditions or model identities.\n"
                f"Rubric:\n{config['judge_rubric']}\n"
                f"Scenario:\n{config['scenario']}\nCandidates:\n"
                f"{json.dumps(candidates, ensure_ascii=False)}"
            )
            invoke(judge, prompt, folder, "judgment")
    except Exception as exc:
        save(output / "status.json", {"status": "failed", "error": str(exc)})
        raise
    save(output / "status.json", {"status": "complete"})


def main():
    """Parse arguments and run preflight or the pilot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--output", type=Path, help="new output directory (required to run)"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check executables and versions only; no model calls",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        versions = preflight(config)
        if args.preflight:
            print(json.dumps(versions, indent=2))
        elif args.output:
            run(config, versions, args.output, args.seed)
        else:
            parser.error("--output is required unless --preflight is supplied")
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.TimeoutExpired,
        RuntimeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
