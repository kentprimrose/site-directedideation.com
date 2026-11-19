"""Offline end-to-end tests for the evaluation driver."""

import csv
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ideation_eval/harness.py"


def test_pilot_and_role_isolation(tmp_path):
    """Six independent judgments follow the specified rotation and protocol."""
    cli = tmp_path / "cli.py"
    cli.write_text("""import sys, json
if '--version' in sys.argv:
 print('mock 1'); sys.exit()
p = sys.stdin.read()
if p.startswith('Score this single transcript'):
 assert 'SECRET_BRIEF' not in p and 'METHOD_TEXT' not in p
 assert 'KNOWN_GOOD_TEXT' in p
 scores = dict(distinct_approaches=6, stages_completed=3, actionability=4,
               falsifiability=3, correctness=5, usefulness=4, justification='Useful.')
 print(json.dumps(scores))
elif p.startswith('Role-play'):
 assert 'SECRET_BRIEF' in p and 'KNOWN_GOOD_TEXT' not in p
 print('Answer')
else:
 assert 'SECRET_BRIEF' not in p and 'KNOWN_GOOD_TEXT' not in p
 print('FINAL: Recommendation' if 'User: Answer' in p else 'QUESTION: Why?')
""")
    config = {
        "models": [
            dict(
                id=x,
                model=x + "-pinned",
                command=[sys.executable, str(cli)],
                version_command=[sys.executable, str(cli), "--version"],
            )
            for x in ("claude", "codex", "gemini")
        ]
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    problems = tmp_path / "problems"
    problems.mkdir()
    (problems / "one.json").write_text(
        json.dumps(
            dict(
                id="one",
                statement="Problem",
                hidden_brief="SECRET_BRIEF",
                known_good="KNOWN_GOOD_TEXT",
            )
        )
    )
    (tmp_path / "method.md").write_text("METHOD_TEXT")
    output = tmp_path / "out"
    cmd = [
        sys.executable,
        str(SCRIPT),
        str(tmp_path / "config.json"),
        "--problems",
        str(problems),
        "--method",
        str(tmp_path / "method.md"),
        "--output",
        str(output),
        "--pilot",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader((output / "summary.csv").open()))
    assert len(rows) == 6
    assert [(r["answerer"], r["interrogator"], r["judge"]) for r in rows[::2]] == [
        ("claude", "codex", "gemini"),
        ("codex", "gemini", "claude"),
        ("gemini", "claude", "codex"),
    ]
    assert all(r["status"] == "final" and r["turns"] == "2" for r in rows)
    assert len(list((output / "judgements").glob("*.json"))) == 6
    assert len(list((output / "transcripts").glob("*.jsonl"))) == 6
    assert "4.00" in (output / "report.md").read_text()
    assert subprocess.run(cmd, capture_output=True).returncode != 0


def test_validation_and_turn_limit(tmp_path):
    """Validate scoring and cap dialogues without fabricating a FINAL."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("eval_harness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import pytest

    with pytest.raises(ValueError):
        module.parse_scores('{"usefulness": 9}')
    module.invoke = lambda model, prompt: (
        "QUESTION: More?" if model == "a" else "Unknown"
    )
    transcript, status = module.run_dialogue(
        {"statement": "p", "hidden_brief": "b"},
        "control",
        "a",
        "i",
        "method",
        tmp_path / "t.jsonl",
    )
    assert status == "no_final"
    assert len(transcript) == 24
    assert len((tmp_path / "t.jsonl").read_text().splitlines()) == 24
