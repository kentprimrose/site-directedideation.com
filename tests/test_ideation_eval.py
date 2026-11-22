"""Offline end-to-end tests for the evaluation driver."""

import csv
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ideation_eval/harness.py"


def test_live_cases_load_and_have_interview_scoring_keys():
    """The live case bank also works with the method-text fixture loader."""
    load_problems = runpy.run_path(str(SCRIPT))["load_problems"]
    cases_dir = SCRIPT.parents[2] / "docs/test_plan/live_cases"
    cases = load_problems(cases_dir, pilot=False)
    assert len(cases) >= 3
    assert load_problems(cases_dir, pilot=True) == cases[:1]
    expected_keys = (
        "baseline",
        "bottleneck",
        "prior_attempt",
        "constraints",
        "success",
    )
    for case in cases:
        assert (cases_dir / f"{case['id']}.json").is_file()
        keys = re.findall(r"^\[(\w+)\] \S", case["hidden_brief"], re.M)
        assert tuple(keys) == expected_keys


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


def test_validation_and_turn_limit(tmp_path, monkeypatch):
    """Validate scoring and cap dialogues without fabricating a FINAL."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("eval_harness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import pytest

    with pytest.raises(ValueError):
        module.parse_scores('{"usefulness": 9}')
    monkeypatch.setattr(
        module,
        "invoke",
        lambda model, _prompt: "QUESTION: More?" if model == "a" else "Unknown",
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


def test_review_regressions(tmp_path, monkeypatch):
    """Exercise validation, protocol termination, and completed-only means offline."""
    import importlib.util

    import pytest

    spec = importlib.util.spec_from_file_location("eval_harness_regressions", SCRIPT)
    assert spec is not None and spec.loader is not None
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    models = [
        dict(id=str(i), model=str(i), command=["mock"], version_command=["mock"])
        for i in range(3)
    ]
    config = tmp_path / "config.json"
    models[1]["model"] = " 0 "
    config.write_text(json.dumps({"models": models}))
    with pytest.raises(ValueError, match="distinct declared"):
        h.load_config(config)
    scores = dict(
        distinct_approaches=2,
        stages_completed=None,
        actionability=4,
        falsifiability=3,
        correctness=5,
        usefulness=4,
        justification="Good",
    )
    assert h.parse_scores("```json\n" + json.dumps(scores) + "\n```") == scores
    scores["usefulness"] = True
    with pytest.raises(ValueError):
        h.parse_scores("```\n" + json.dumps(scores) + "\n```")
    with pytest.raises(ValueError):
        h.parse_scores("prefix\n```json\n{}\n```")

    problem = {"id": "p", "statement": "p", "hidden_brief": "b", "known_good": "k"}
    for i, response in enumerate(("FINAL:", "FINAL: premature\nQUESTION: Continue?")):
        monkeypatch.setattr(
            h, "invoke", lambda model, _prompt: response if model == "a" else "answer"
        )
        _, status = h.run_dialogue(
            problem, "control", "a", "i", "", tmp_path / f"{i}.jsonl"
        )
        assert status == "no_final"
    monkeypatch.setattr(
        h, "invoke", lambda _model, _prompt: "FINAL:\nA substantive\nrecommendation"
    )
    _, status = h.run_dialogue(
        problem, "control", "a", "i", "", tmp_path / "final.jsonl"
    )
    assert status == "final"

    def dialogue(_problem, _arm, answerer, _interrogator, _method, _path):
        return [], "final" if answerer["id"] == "0" else "no_final"

    def judge(model, _prompt):
        return json.dumps(
            dict(
                distinct_approaches=2,
                stages_completed=3,
                actionability=4,
                falsifiability=3,
                correctness=5,
                usefulness=4 if model["id"] == "2" else 1,
                justification="Good",
            )
        )

    monkeypatch.setattr(h, "run_dialogue", dialogue)
    monkeypatch.setattr(h, "invoke", judge)
    h.run(models, {}, [problem], "method", tmp_path / "out")
    report = (tmp_path / "out/report.md").read_text()
    assert "| method | 1 | 2 | 0 | 1 |" in report
    assert "4.00" in report
    assert next(
        line for line in report.splitlines() if line.startswith("| method | ")
    ).endswith("| 4.00 |")
