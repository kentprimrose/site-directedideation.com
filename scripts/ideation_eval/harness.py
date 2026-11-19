#!/usr/bin/env python3
"""Run the directed-ideation experiment with configurable CLI wrappers."""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROLES = ((0, 1, 2), (1, 2, 0), (2, 0, 1))
ARMS = ("method", "control")
SCORES = (
    "distinct_approaches",
    "stages_completed",
    "actionability",
    "falsifiability",
    "correctness",
    "usefulness",
)
MARKER = re.compile(r"^(QUESTION|FINAL):\s*(.*)$", re.MULTILINE)


def load_config(path):
    """Load config."""
    config = json.loads(Path(path).read_text())
    models = config["models"]
    if len(models) != 3 or len({m["id"] for m in models}) != 3:
        raise ValueError("exactly three uniquely named models required")
    for m in models:
        if not m.get("model") or any(
            not isinstance(m.get(k), list)
            or not m[k]
            or not all(isinstance(x, str) and x for x in m[k])
            for k in ("command", "version_command")
        ):
            raise ValueError("each model needs model, command and version_command")
    return models


def preflight(models):
    """Preflight."""
    versions = {}
    for m in models:
        for key in ("command", "version_command"):
            if not shutil.which(m[key][0]):
                raise ValueError(f"executable not found: {m[key][0]}")
        r = subprocess.run(
            m["version_command"], capture_output=True, text=True, timeout=30, check=True
        )
        if not r.stdout.strip():
            raise ValueError("empty version output")
        versions[m["id"]] = {"model": m["model"], "cli_version": r.stdout.strip()}
    return versions


def invoke(model, prompt):
    """Invoke."""
    r = subprocess.run(
        model["command"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=600,
        check=True,
    )
    if not r.stdout.strip():
        raise ValueError("empty model response")
    return r.stdout.strip()


def render(transcript):
    """Render."""
    return (
        "\n".join(
            ("Answerer" if t["speaker"] == "answerer" else "User") + ": " + t["text"]
            for t in transcript
        )
        or "(none)"
    )


def answerer_prompt(problem, arm, method, transcript):
    """Answerer prompt."""
    instruction = (
        "Work this problem using the directed-ideation method below.\nMETHOD:\n"
        + method
        if arm == "method"
        else "Work this problem directly."
    )
    return (
        instruction
        + (
            "\nAsk one question at a time. End with a line starting "
            "QUESTION: when you need input or FINAL: when ready to "
            "recommend.\nPROBLEM:\n"
        )
        + problem["statement"]
        + "\nCONVERSATION SO FAR:\n"
        + render(transcript)
    )


def interrogator_prompt(problem, transcript, question):
    """Interrogator prompt."""
    return (
        (
            "Role-play the user using only the BRIEF. Do not volunteer "
            "facts not asked for. If the brief does not cover a question,"
            " say you don't know. Confirm or revise stage outputs as the "
            "brief supports. Reply with the answer only.\nBRIEF:\n"
        )
        + problem["hidden_brief"]
        + "\nCONVERSATION SO FAR:\n"
        + render(transcript)
        + "\nQUESTION:\n"
        + question
    )


def judge_prompt(problem, transcript):
    """Judge prompt."""
    return (
        (
            "Score this single transcript on substance, not formatting. "
            "Return only JSON: distinct_approaches (integer count), "
            "stages_completed (integer 0-3 for opportunity, goal, "
            "ideation, or null if not applicable), actionability, "
            "falsifiability, correctness, usefulness (each integer 1-5), "
            "and justification (one sentence). Actionability: concrete "
            "first actions for promising ideas; falsifiability: evidence "
            "challenging them; correctness: match KNOWN_GOOD.\nPROBLEM:\n"
        )
        + problem["statement"]
        + "\nKNOWN_GOOD:\n"
        + problem["known_good"]
        + "\nTRANSCRIPT:\n"
        + render(transcript)
    )


def parse_scores(text):
    """Parse scores."""
    scores = json.loads(text)
    if not isinstance(scores, dict):
        raise ValueError("judgment must be an object")
    for key in SCORES:
        value = scores.get(key)
        if key == "stages_completed" and value is None and key in scores:
            continue
        lo, hi = (
            (0, None)
            if key == "distinct_approaches"
            else ((0, 3) if key == "stages_completed" else (1, 5))
        )
        if type(value) is not int or value < lo or (hi is not None and value > hi):
            raise ValueError(f"invalid score: {key}")
    if (
        not isinstance(scores.get("justification"), str)
        or not scores["justification"].strip()
    ):
        raise ValueError("missing justification")
    return scores


def run_dialogue(problem, arm, answerer, interrogator, method, transcript_path):
    """Run dialogue."""
    transcript = []
    with transcript_path.open("w") as f:

        def add(speaker, text):
            entry = {"speaker": speaker, "text": text}
            transcript.append(entry)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()

        for _ in range(12):
            text = invoke(answerer, answerer_prompt(problem, arm, method, transcript))
            add("answerer", text)
            matches = list(MARKER.finditer(text))
            marker = matches[-1] if matches else None
            if marker and marker.group(1) == "FINAL":
                return transcript, "final"
            question = marker.group(2).strip() if marker else text
            add(
                "user",
                invoke(
                    interrogator, interrogator_prompt(problem, transcript, question)
                ),
            )
    return transcript, "no_final"


def load_problems(directory, pilot):
    """Load problems."""
    files = sorted(Path(directory).glob("*.json"))
    if pilot:
        files = files[:1]
    if not files:
        raise ValueError("no problem JSON files found")
    problems = []
    for path in files:
        p = json.loads(path.read_text())
        if any(
            not isinstance(p.get(k), str) or not p[k].strip()
            for k in ("id", "statement", "hidden_brief", "known_good")
        ):
            raise ValueError(f"invalid problem: {path}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", p["id"]) or any(
            x["id"] == p["id"] for x in problems
        ):
            raise ValueError("problem IDs must be unique and filename-safe")
        problems.append(p)
    return problems


def run(models, versions, problems, method, output):
    """Run."""
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for d in ("transcripts", "judgements"):
        (output / d).mkdir()
    (output / "versions.json").write_text(json.dumps(versions, indent=2) + "\n")
    (output / "method.md").write_text(method)
    rows = []
    for problem in problems:
        for number, indices in enumerate(ROLES, 1):
            answerer, interrogator, judge = (models[i] for i in indices)
            for arm in ARMS:
                run_id = f"{problem['id']}_r{number}_{arm}"
                row = dict(
                    run_id=run_id,
                    problem=problem["id"],
                    round=number,
                    arm=arm,
                    answerer=answerer["id"],
                    interrogator=interrogator["id"],
                    judge=judge["id"],
                )
                try:
                    transcript, status = run_dialogue(
                        problem,
                        arm,
                        answerer,
                        interrogator,
                        method,
                        output / "transcripts" / (run_id + ".jsonl"),
                    )
                    row.update(
                        status=status,
                        turns=sum(t["speaker"] == "answerer" for t in transcript),
                    )
                    raw = invoke(judge, judge_prompt(problem, transcript))
                    scores = parse_scores(raw)
                    (output / "judgements" / (run_id + ".json")).write_text(
                        json.dumps(scores, indent=2) + "\n"
                    )
                    row.update({k: scores[k] for k in SCORES})
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    row["status"] = "error: " + str(exc)[:250]
                rows.append(row)
    fields = [
        "run_id",
        "problem",
        "round",
        "arm",
        "answerer",
        "interrogator",
        "judge",
        "status",
        "turns",
        *SCORES,
    ]
    with (output / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Directed-ideation test report",
        "",
        f"Problems: {len(problems)}; runs: {len(rows)}",
        "",
        "| Arm | Runs scored | " + " | ".join(SCORES) + " |",
        "|---|---|" + "---|" * len(SCORES),
    ]
    for arm in ARMS:
        scored = [r for r in rows if r["arm"] == arm and "usefulness" in r]
        means = []
        for key in SCORES:
            vals = [r[key] for r in scored if isinstance(r[key], int)]
            means.append(f"{sum(vals) / len(vals):.2f}" if vals else "n/a")
        lines.append(f"| {arm} | {len(scored)} | " + " | ".join(means) + " |")
    lines += [
        "",
        (
            "See summary.csv for errors and non-final runs. Results are "
            "directional, not statistically conclusive."
        ),
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return all(r["status"] == "final" for r in rows)


def main():
    """Main."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--problems", type=Path)
    parser.add_argument("--method", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    try:
        models = load_config(args.config)
        if not args.preflight and not all((args.problems, args.method, args.output)):
            parser.error("--problems, --method and --output are required")
        problems = (
            load_problems(args.problems, args.pilot) if not args.preflight else None
        )
        method = args.method.read_text() if not args.preflight else None
        if method is not None and not method.strip():
            raise ValueError("method must not be empty")
        versions = preflight(models)
        if args.preflight:
            print(json.dumps(versions, indent=2))
            return 0
        return 0 if run(models, versions, problems, method, args.output) else 1
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
