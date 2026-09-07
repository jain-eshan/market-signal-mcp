"""Eval layer 3, LLM-as-judge half (issue #10): is the SUBSTANCE of a
generated SIGNAL REPORT actually correct -- right verdict, no hallucinated
numbers, real caveats -- not just the right shape (that's
test_report_structure.py, which needs no LLM and is unchanged).

Two `claude -p` calls per gold query: one to generate the report (through
the real /market-signal skill against the real MCP server), one to judge it
against tests/eval/rubric.md and the gold answer. Both run through Claude
Code's own headless CLI, authenticated via whatever login is already active
-- no separate LLM provider API key. Replaces an earlier version of this eval
that used `mcp-eval` with a dedicated Anthropic/OpenAI/Google key in
mcpeval.secrets.yaml, which was the wrong design for a tool meant to live
entirely inside Claude Code (see run_tool_selection.py's docstring for the
full reasoning).

Usage:
    uv run python tests/eval/run_report_quality_judge.py

Requires: the `claude` CLI on PATH and already logged in.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
GOLD_PATH = Path(__file__).parent / "gold_answers.jsonl"
RUBRIC_PATH = Path(__file__).parent / "rubric.md"
RESULTS_PATH = Path(__file__).parent / "report_quality_results.json"
TIMEOUT_SECONDS = 180

MCP_CONFIG = {
    "mcpServers": {
        "market-signal": {
            "command": "uv",
            "args": ["run", "--directory", str(REPO_ROOT), "server.py"],
        }
    }
}

JUDGE_SCORE_RE = re.compile(r"^SCORE:\s*([\d.]+)", re.MULTILINE)
JUDGE_PASS_RE = re.compile(r"^PASS:\s*(true|false)", re.MULTILINE | re.IGNORECASE)
JUDGE_REASONING_RE = re.compile(r"^REASONING:\s*(.+)", re.MULTILINE | re.DOTALL)


def _mcp_config_file():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(MCP_CONFIG, f)
        return f.name


def generate_report(query: str) -> str:
    """Runs the real /market-signal skill against the real server, returns
    the final text output (the SIGNAL REPORT, in principle)."""
    proc = subprocess.run(
        ["claude", "-p", f"/market-signal {query}", "--mcp-config", _mcp_config_file(), "--strict-mcp-config"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        cwd=REPO_ROOT,
    )
    return proc.stdout


def judge_report(report_text: str, gold_verdict: str, gold_rationale: str, query: str) -> dict:
    """Second claude -p call: score the generated report against the rubric
    and gold answer. Asks for a strict, parseable output format rather than
    free prose, since this result feeds an automated pass/fail."""
    rubric = RUBRIC_PATH.read_text()
    prompt = f"""{rubric}

## This query's gold answer

Query: {query}
Gold verdict: {gold_verdict}
Gold rationale: {gold_rationale}

## The report to score

{report_text}

## Your task

Score the report above against the rubric and gold answer. Output EXACTLY
these three lines, nothing else before or after:

SCORE: <weighted average as a decimal, e.g. 4.17>
PASS: <true or false, per the rubric's >= 4.0 threshold>
REASONING: <one paragraph citing which dimension(s), if any, fell short and why>
"""
    proc = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        cwd=REPO_ROOT,
    )
    output = proc.stdout
    score_match = JUDGE_SCORE_RE.search(output)
    pass_match = JUDGE_PASS_RE.search(output)
    reasoning_match = JUDGE_REASONING_RE.search(output)
    if not (score_match and pass_match):
        return {"parse_error": True, "raw_output": output}
    return {
        "score": float(score_match.group(1)),
        "judge_pass": pass_match.group(1).lower() == "true",
        "reasoning": reasoning_match.group(1).strip() if reasoning_match else "",
        "parse_error": False,
    }


def _load_gold():
    with open(GOLD_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    entries = _load_gold()
    results = []
    passed = 0

    for entry in entries:
        print(f"Generating report for {entry['id']}: {entry['query']}")
        try:
            report = generate_report(entry["query"])
        except subprocess.TimeoutExpired:
            results.append({"id": entry["id"], "pass": False, "error": "generation timeout"})
            print(f"[FAIL] {entry['id']}: report generation timed out")
            continue

        judged = judge_report(report, entry["gold_verdict"], entry["gold_rationale"], entry["query"])
        ok = judged.get("judge_pass", False) and not judged.get("parse_error", True)
        if ok:
            passed += 1

        results.append({"id": entry["id"], "query": entry["query"], "gold_verdict": entry["gold_verdict"], **judged})
        status = "PASS" if ok else "FAIL"
        score_str = judged.get("score", "unparseable")
        print(f"[{status}] {entry['id']}: score={score_str}")

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    rate = passed / len(entries) if entries else 0
    print(f"\n{passed}/{len(entries)} passed ({rate:.1%}) -- saved to {RESULTS_PATH}")
    sys.exit(0 if passed == len(entries) else 1)


if __name__ == "__main__":
    main()
