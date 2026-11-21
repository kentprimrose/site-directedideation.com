# Rotation

Three models, three roles, three rounds. Each model plays each role once. The judge is never the answerer or interrogator in the same round.

| Round | Answerer | Interrogator | Judge |
|---|---|---|---|
| 1 | Claude | Codex | Gemini |
| 2 | Codex | Gemini | Claude |
| 3 | Gemini | Claude | Codex |

Each round runs every problem in both arms (`method`, `control`). Full run: 6 transcripts per problem.

Pilot: one problem, 3 rounds, 2 arms = 6 runs.
