# Directed ideation evaluation pilot

This benchmark compares method text against a direct answer. To evaluate
live MCP use instead, see the [paired live-MCP suite](test_plan/LIVE_MCP.md).

This is a directional pilot, not evidence of effectiveness by itself. The
answerer, simulated user (interrogator), and judge rotate as follows:

| Round | Answerer | Interrogator | Judge |
|---|---|---|---|
| 1 | Claude | Codex | Gemini |
| 2 | Codex | Gemini | Claude |
| 3 | Gemini | Claude | Codex |

Every problem is run in both method and control arms in each round. A pilot
selects the first sorted problem file: six independent transcripts and six
individual judgments. The interrogator receives the hidden brief; the answerer
never does. The judge receives the statement, known-good reference and one
transcript, without arm or model labels. Styles and method language can still
reveal the condition; blindness is not guaranteed.

## Prepare

Create a private directory of JSON files, one per problem, each with nonempty
string fields `id` (unique filename-safe alphanumerics, underscore or hyphen),
`statement`, `hidden_brief`, and `known_good`. Freeze complete canonical method
text from the project's MCP method tool in a UTF-8 `method.md`. Only the method
arm receives it; both arms may ask questions. The answerer has at most 12
messages, marked `QUESTION:` or `FINAL:` at the start of a line. Missing markers
are treated as questions. A FINAL must be the last protocol marker and have
substantive text after it, including on subsequent lines; otherwise it is not
accepted as final. Missing FINAL is reported, not fabricated.

Create a private config with three model entries **in Claude, Codex, Gemini
order**, each with `id`, pinned `model`, `command`, and `version_command`.
Commands are argument arrays, receive prompt on stdin and must print only the
assistant response on stdout. Use wrappers to adapt CLI interfaces, extract final
text and disable tools, memory, MCP and external access as appropriate. The
`model` field is recorded, not enforced: commands must select the pinned model.
Declared model identities must be distinct (ignoring case and surrounding
whitespace), but neither model family nor wrapper behavior is verified. Different
declarations may still invoke the same underlying model; inspect wrappers and
independently verify identity and family before interpreting role independence.
Version commands should be local and must not invoke a model. Example entry:

```json
{"id":"claude", "model":"PINNED_MODEL", "command":["/path/to/claude-wrapper", "PINNED_MODEL"], "version_command":["claude", "--version"]}
```

Review wrappers, CLI settings, authentication, data policy, costs and budgets
before use. Preflight runs version commands but does not check credentials,
model availability, isolation or affordability. Actual execution may incur
charges; obtain authorization first. No calls are made merely by running tests.

```sh
python scripts/ideation_eval/harness.py config.json --preflight
python scripts/ideation_eval/harness.py config.json --problems problems --method method.md --output private/pilot-001 --pilot
pytest -q tests/test_ideation_eval.py
```

Omit `--pilot` to run all problems. Output must not already exist. It contains
`versions.json`, a method snapshot, JSONL transcripts, JSON judgments,
`summary.csv` and `report.md`. Each transcript is scored for distinct
approaches, stages completed (0–3 or null), actionability, falsifiability,
correctness and usefulness (1–5), plus a justification. A single JSON object may be returned bare or inside one JSON code fence.
Invalid JSON or scores
are recorded as errors; runs continue and exit nonzero for errors or missing
FINAL. Partial transcripts survive failures. The report shows completed, non-final, error, and completed-scored counts by
arm. Primary means include only scored completed runs; non-final judgments remain
available in the individual artifacts and CSV. Check status and counts before
interpreting means. There is no
resume or retry. Store artifacts securely: transcripts, reference answers and
method text can be sensitive. The CLI wrappers are not sandboxed.

A simulated user is not a real user, and the judge may favor structured output
despite the prompt. Inspect transcripts, FINAL markers, judgments and score
variation before scaling; three rounds are a small correlated sample. Record
model versions, settings and limitations when reporting results.
