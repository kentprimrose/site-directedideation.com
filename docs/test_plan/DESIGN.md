# Directed Ideation Test Harness: Design

## Purpose

A repeatable test of whether the directed-ideation method improves answers to strategic problems. For each problem, the answerer works it in two arms: `method` (following the three directed-ideation stages) and `control` (solving it directly). Three model families fill three roles, so no model grades its own work and every model plays every role.

## Roles

- **Answerer.** Works the problem under one arm.
- **Interrogator.** Plays the simulated user. Holds a hidden brief and answers only from it. Never volunteers facts that were not asked for. Confirms stage outputs as the method requires.
- **Judge.** Reads the finished transcript without knowing the arm or which models held the other roles. Scores it against a fixed rubric.

## Harnesses

Claude (`claude -p`), Codex (`codex exec`), and Gemini CLI (`gemini -p`). Model versions are pinned at the start of a run and recorded in `versions.json`.

## Rotation

A Latin square over three rounds. Each model plays each role once. The judge is never the answerer or interrogator in the same round. See `rotation.md`.

## Problem input

One JSON file per problem in `problems/`, with `id`, `statement`, `hidden_brief`, and `known_good`.

## Rubric

1. Distinct approaches (count; the method requires at least six in ideation).
2. Stages completed (0 to 3).
3. Actionability (1 to 5): each promising idea has a concrete first action.
4. Falsifiability (1 to 5): each promising idea has evidence that would challenge it.
5. Correctness (1 to 5): the recommendation matches `known_good`.
6. Usefulness (1 to 5), with a one-sentence justification.

The judge scores substance, not formatting.

## Execution

Herder runs one job (`herder-job.yaml`) that calls `driver.py`. The driver is a script, not an agent, so each run is fixed and repeatable:

1. Read problems and build the rounds and arms.
2. Dispatch each role to its CLI with only that role's inputs.
3. Save every transcript as JSON Lines.
4. Send each finished transcript to the judge.
5. Write the summary CSV and markdown report.

## Output

Per run, in `runs/<timestamp>/`:

- `transcripts/` (one JSONL per problem, arm, and round)
- `judgements/` (one JSON per transcript)
- `summary.csv` (one row per run)
- `report.md` (per-arm means)
- `versions.json` (CLI versions)

## Pilot

One problem, all three rounds, both arms: 6 runs. Check dispatch, transcripts, FINAL markers, judge output, and score variation before scaling.

## Limitations

- The interrogator is a proxy for a real user.
- The judge may favour structured output. The prompt counters this, but check it in the pilot.
- Invented problems show less than real practitioner problems.
- Three rounds gives a small sample. Treat results as directional.
- Method text is delivered as plain text to all three answerers, so the connector is not a confound. Save it once to `method.md`.
