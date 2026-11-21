#!/usr/bin/env python3
"""Directed-ideation test driver. Run by Herder as a single job."""
import argparse, csv, datetime, json, pathlib, re, subprocess, sys

CLI = {
    "claude": ["claude", "-p"],
    "codex": ["codex", "exec"],
    "gemini": ["gemini", "-p"],
}
VERSION_CMD = {"claude": ["claude", "--version"],
               "codex": ["codex", "--version"],
               "gemini": ["gemini", "--version"]}

ROUNDS = [
    {"round": 1, "answerer": "claude", "interrogator": "codex",  "judge": "gemini"},
    {"round": 2, "answerer": "codex",  "interrogator": "gemini", "judge": "claude"},
    {"round": 3, "answerer": "gemini", "interrogator": "claude", "judge": "codex"},
]
ARMS = ["method", "control"]
MAX_TURNS = 12
TIMEOUT_S = 600
MARKER = re.compile(r"^(QUESTION|FINAL):\s*(.*)$", re.MULTILINE)


def call(model, prompt):
    r = subprocess.run(CLI[model] + [prompt], capture_output=True,
                       text=True, timeout=TIMEOUT_S)
    if r.returncode != 0:
        raise RuntimeError(f"{model} exited {r.returncode}: {r.stderr[:500]}")
    return r.stdout.strip()


def render(transcript):
    if not transcript:
        return "CONVERSATION SO FAR: (none)"
    lines = ["CONVERSATION SO FAR:"]
    for t in transcript:
        label = "Answerer" if t["speaker"] == "answerer" else "User"
        lines.append(f"{label}: {t['text']}")
    return "\n".join(lines)


def answerer_prompt(problem, arm, method_text, transcript):
    if arm == "method":
        instr = ("Work this problem using the directed-ideation method below. "
                 "Ask the user one question at a time. End each message with a line "
                 "starting QUESTION: when you need input, or FINAL: when you are "
                 "ready to recommend.\n\nMETHOD:\n" + method_text)
    else:
        instr = ("Work this problem directly. You may ask the user clarifying "
                 "questions, one at a time. End each message with a line starting "
                 "QUESTION: when you need input, or FINAL: when you are ready to "
                 "recommend.")
    return "\n\n".join([instr, "PROBLEM:\n" + problem["statement"], render(transcript)])


def interrogator_prompt(problem, transcript, question):
    return ("You are role-playing the user described in the BRIEF. Answer the "
            "question using only facts in the BRIEF. Do not volunteer facts that "
            "were not asked for. If the BRIEF does not cover it, say you don't know. "
            "If asked to confirm a stage output, confirm or revise it as the BRIEF "
            "supports. Reply with the answer only.\n\nBRIEF:\n"
            + problem["hidden_brief"] + "\n\n" + render(transcript)
            + "\n\nQUESTION:\n" + question)


def judge_prompt(problem, transcript):
    rubric = (
        "Score this transcript of a user working a strategic problem with an AI "
        "assistant. Judge substance, not formatting: a structured-looking answer "
        "is not better unless its content is.\n\n"
        "Return only JSON with these keys:\n"
        "  distinct_approaches: integer count of genuinely different approaches\n"
        "  stages_completed: integer 0-3 (opportunity, goal, ideation), or null if not applicable\n"
        "  actionability: 1-5, does each promising idea have a concrete first action\n"
        "  falsifiability: 1-5, does each promising idea have evidence that would challenge it\n"
        "  correctness: 1-5, does the recommendation match KNOWN_GOOD\n"
        "  usefulness: 1-5, overall usefulness to the user\n"
        "  justification: one sentence\n"
    )
    return (rubric + "\nPROBLEM:\n" + problem["statement"]
            + "\n\nKNOWN_GOOD:\n" + problem["known_good"] + "\n\n" + render(transcript))


def parse_marker(text):
    m = None
    for m in MARKER.finditer(text):
        pass  # keep the last marker
    if m is None:
        return None, text
    return m.group(1), m.group(2).strip()


def parse_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in judge output")
    return json.loads(text[start:end + 1])


def run_dialogue(problem, arm, answerer, interrogator, method_text):
    transcript, final, status = [], None, "no_final"
    for _ in range(MAX_TURNS):
        a_out = call(answerer, answerer_prompt(problem, arm, method_text, transcript))
        transcript.append({"speaker": "answerer", "text": a_out})
        kind, body = parse_marker(a_out)
        if kind == "FINAL":
            final, status = body, "final"
            break
        if kind is None:
            body = a_out  # no marker: treat whole message as the question
        u_out = call(interrogator, interrogator_prompt(problem, transcript, body))
        transcript.append({"speaker": "user", "text": u_out})
    return transcript, final, status


def versions():
    out = {}
    for m, cmd in VERSION_CMD.items():
        try:
            out[m] = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=30).stdout.strip()
        except Exception as e:
            out[m] = f"unavailable: {e}"
    return out


def check():
    ok = True
    for m, cmd in VERSION_CMD.items():
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            print(f"{m}: {'ok' if r.returncode == 0 else 'FAILED'} {r.stdout.strip()}")
            ok &= r.returncode == 0
        except FileNotFoundError:
            print(f"{m}: NOT FOUND"); ok = False
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--problems")
    ap.add_argument("--method")
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = pathlib.Path("runs") / stamp
    for sub in ("transcripts", "judgements"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    (out / "versions.json").write_text(json.dumps(versions(), indent=2))

    method_text = pathlib.Path(args.method).read_text()
    problems = sorted(pathlib.Path(args.problems).glob("*.json"))
    if args.pilot:
        problems = problems[:1]

    rows = []
    for pfile in problems:
        prob = json.loads(pfile.read_text())
        for rnd in ROUNDS:
            for arm in ARMS:
                run_id = f"{prob['id']}_r{rnd['round']}_{arm}"
                row = {"run_id": run_id, "problem": prob["id"], "round": rnd["round"],
                       "arm": arm, "answerer": rnd["answerer"],
                       "interrogator": rnd["interrogator"], "judge": rnd["judge"]}
                try:
                    transcript, final, status = run_dialogue(
                        prob, arm, rnd["answerer"], rnd["interrogator"], method_text)
                    with open(out / "transcripts" / f"{run_id}.jsonl", "w") as f:
                        for t in transcript:
                            f.write(json.dumps(t) + "\n")
                    row["status"] = status
                    row["turns"] = len(transcript) // 2
                    judge_transcript = transcript + (
                        [{"speaker": "answerer", "text": "FINAL: " + final}] if final else [])
                    judge_out = call(rnd["judge"], judge_prompt(prob, judge_transcript))
                    scores = parse_json(judge_out)
                    (out / "judgements" / f"{run_id}.json").write_text(
                        json.dumps(scores, indent=2))
                    row.update({k: scores.get(k) for k in (
                        "distinct_approaches", "stages_completed", "actionability",
                        "falsifiability", "correctness", "usefulness")})
                except Exception as e:
                    row["status"] = f"error: {e}"[:300]
                rows.append(row)
                print(run_id, row["status"], flush=True)

    fields = ["run_id", "problem", "round", "arm", "answerer", "interrogator",
              "judge", "status", "turns", "distinct_approaches", "stages_completed",
              "actionability", "falsifiability", "correctness", "usefulness"]
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    lines = ["# Directed-ideation test report", "", f"Run: {stamp}",
             f"Problems: {len(problems)}, runs: {len(rows)}", "",
             "| Arm | Runs scored | Mean usefulness | Mean correctness | Mean distinct approaches |",
             "|---|---|---|---|---|"]
    for arm in ARMS:
        ar = [r for r in rows if r["arm"] == arm and isinstance(r.get("usefulness"), (int, float))]
        def mean(k):
            vals = [r[k] for r in ar if isinstance(r.get(k), (int, float))]
            return round(sum(vals) / len(vals), 2) if vals else "n/a"
        lines.append(f"| {arm} | {len(ar)} | {mean('usefulness')} | "
                     f"{mean('correctness')} | {mean('distinct_approaches')} |")
    lines += ["", "Errors and non-final runs are listed in summary.csv under status."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
