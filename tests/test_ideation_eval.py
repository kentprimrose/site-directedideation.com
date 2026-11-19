"""Offline tests for the evaluation harness."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ideation_eval/harness.py"


@pytest.fixture
def setup(tmp_path):
    """Create a mock executable and configuration."""
    cli = tmp_path / "mock.py"
    cli.write_text(
        'import sys\nif "--version" in sys.argv: print("mock 1.0")\n'
        'else:\n s=sys.stdin.read(); print("response")\n'
    )
    config = {
        "models": [
            {
                "id": x,
                "model": x + "-version",
                "command": [sys.executable, str(cli)],
                "version_command": [sys.executable, str(cli), "--version"],
            }
            for x in ("one", "two", "three")
        ],
        "scenario": "A scenario",
        "method": "Use method",
        "control": "Normal help",
        "judge_rubric": "Compare usefulness",
        "rounds": 1,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return tmp_path, path, config, cli


def call(*args):
    """Run the harness as a CLI."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True
    )


def test_preflight_does_not_run_model(setup):
    """Exercise the offline CLI behavior."""
    tmp, path, _, cli = setup
    cli.write_text('import sys\nassert "--version" in sys.argv\nprint("v1")\n')
    result = call(path, "--preflight")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {x: "v1" for x in ("one", "two", "three")}
    assert not (tmp / "output").exists()


def test_pilot_rotation_blinding_and_no_overwrite(setup):
    """Exercise the offline CLI behavior."""
    tmp, path, _, _ = setup
    output = tmp / "output"
    result = call(path, "--output", output, "--seed", "42")
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "status.json").read_text())["status"] == "complete"
    for index, expected in enumerate(("one", "two", "three"), 1):
        folder = output / f"rotation-{index}"
        key = json.loads((folder / "blind-key.json").read_text())
        assert key["facilitator"] == expected
        assert len({key["facilitator"], key["participant"], key["judge"]}) == 3
        assert {key["A"], key["B"]} == {"control", "method"}
        prompt = (folder / "judgment.prompt.txt").read_text()
        assert "Use method" not in prompt and "Normal help" not in prompt
        assert (folder / "method/transcript.json").exists()
    assert call(path, "--output", output).returncode != 0


def test_failure_is_preserved_and_aborts(setup):
    """Exercise the offline CLI behavior."""
    tmp, path, _, cli = setup
    cli.write_text(
        'import sys\nif "--version" in sys.argv: print("v1")\n'
        'else: print("bad", file=sys.stderr); sys.exit(3)\n'
    )
    output = tmp / "output"
    assert call(path, "--output", output).returncode == 1
    assert json.loads((output / "status.json").read_text())["status"] == "failed"
    assert list(output.rglob("*.stderr.txt"))[0].read_text().strip() == "bad"
    assert not (output / "rotation-2").exists()


def test_invalid_configuration_fails_before_model_calls(setup):
    """Exercise the offline CLI behavior."""
    tmp, path, config, _ = setup
    config["models"] = config["models"][:2]
    path.write_text(json.dumps(config))
    result = call(path, "--output", tmp / "output")
    assert result.returncode == 1
    assert not (tmp / "output").exists()
