# Directed ideation evaluation pilot

This is a **pilot**, not evidence of effectiveness on its own. The requested
`docs/test_plan` materials were absent in this checkout; no study-specific
rubric, scenario, sample size, stopping rule, or prompts are inferred here.
Supply and freeze those materials before running. This harness implements one
paired case per rotation, not a statistically powered study.

## Setup and preflight

Create a private JSON configuration (do not commit sensitive scenarios or
transcripts). Supply three distinct model entries in `models`, each with
`id`, exact `model` identifier, `command` (argument array), and
`version_command` (argument array). Commands must explicitly select the
recorded model and emit **only** the final assistant text on stdout; read the
prompt from stdin. `version_command` must only print a local CLI version, never
call a model. Record provider/model snapshots, CLI configuration, sampling
settings and relevant environment separately when the CLI cannot report them.
The harness records the declared model, not a verified provider response model.

Other fields: `scenario`, `method`, `control`, `judge_rubric` are nonempty
strings; `rounds` is a positive integer. Put the complete directed-ideation
method in `method` (including all three stages), and a matched ordinary-help
instruction in `control`. Retrieve the method from the project's canonical MCP
method tool and freeze its exact text; do not silently replace it with a
summary. Design a rubric specifying outcomes, scale, evidence and tie handling.
The harness does not enforce stage completion or validate rubric adherence.

Example entry (adapt all models and flags to your installed CLIs):

```json
{"id":"claude", "model":"YOUR_PINNED_MODEL", "command":["claude","--print","--output-format","text","--tools","","--model","YOUR_PINNED_MODEL"], "version_command":["claude","--version"]}
```

CLI interfaces change. Verify the installed `--help`, authentication, model
availability, tool/MCP permissions and data policy before running. In
particular, a CLI's default system instructions, tools, memory, and external
access can confound results; disable or document them. The harness does not
sandbox commands or guarantee that integrations are disabled. Use wrappers if
needed to extract only final text or enforce isolation; never use shell command
strings. On this machine `claude --help`, `codex exec --help`, and `herdr
--help` were inspected without inference calls. Herdr is not required; no job
schema is assumed. Codex's `exec` supports `--output-last-message` for a wrapper
that keeps diagnostic output separate from the final text.

```
python scripts/ideation_eval/harness.py config.json --preflight
python scripts/ideation_eval/harness.py config.json --output private/pilot-001 --seed 42
```

Preflight checks executable availability and executes each configured version
command; review those commands first. It does not validate credentials, model
availability, output format, isolation, or affordability. The second command
makes paid model calls: obtain authorization, set budgets, and inspect prompts
first. Each fresh output directory is created without overwrite; failures stop
the entire run, retain stdout/stderr/prompts, and write `status.json`. There is
no resume or automatic retry; start a new directory and retain the failed one.

## Design and interpretation

Each of three models rotates through facilitator, simulated participant, and
judge exactly once. In each rotation the facilitator and participant independently
run method and control from empty histories, for the same fixed number of
exchanges. The judge sees only the scenario, rubric, and transcripts labeled A
and B; condition order and A/B assignment are independently shuffled using the
recorded seed. `blind-key.json` maps labels and records role and execution
order; keep it hidden from judges until judgments are frozen. Prompts and raw
responses, stderr, transcripts, judgment, configuration, versions and status are
retained. The manifest's `running` value describes its initial state; consult
`status.json` for the outcome.

Blinding is partial: writing style, method language, and even model self-disclosure
can reveal identity or condition. The judge may share a provider with another
role. Simulated participants can react differently between conditions; fixed
turn counts can truncate stages, and no human outcomes are measured. Review
transcripts for leakage, protocol violations and completion before unblinding.
Report all failures and exclusions, per-rotation judgments, disagreements,
model/version/configuration, prompts, seed and limitations; do not claim
significance from three correlated judgments. Artifacts contain potentially
sensitive data and CLI stderr may contain secrets; store securely and redact
before sharing. The output directory is owner-only on POSIX systems.
