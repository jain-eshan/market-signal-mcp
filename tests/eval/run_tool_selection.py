"""Eval layer 2 (issue #9): does /market-signal call the right tools for a
given query (Tool Correctness) and avoid calling extras it doesn't need
(Tool-Calling Efficiency)?

Runs entirely through `claude -p` (Claude Code's own headless CLI mode),
authenticated via whatever Claude Code login is already active on this
machine -- no separate LLM provider API key. This replaces an earlier
version of this eval that used the `mcp-eval` framework with a dedicated
Anthropic/OpenAI/Google API key in tests/eval/mcpeval.secrets.yaml. That
design was wrong for a tool meant to live entirely inside Claude Code: it
should use Claude Code's own capability the same way gstack drives a second
opinion through an already-authenticated CLI (`codex exec`) rather than
holding raw credentials of its own.

Usage:
    uv run python tests/eval/run_tool_selection.py

Requires: the `claude` CLI on PATH and already logged in (`claude --version`
to confirm it's installed; run any interactive `claude` session once if you
haven't logged in before). Uses --mcp-config to point directly at this
repo's server.py, so the run doesn't depend on the runner's global
`claude mcp add` state -- reproducible on a machine that's never registered
this server at all.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
QUERIES_PATH = Path(__file__).parent / "queries.jsonl"
RESULTS_PATH = Path(__file__).parent / "tool_selection_results.json"
TIMEOUT_SECONDS = 180

# Every tool the routing logic can call - used to assert efficiency (a query's
# unexpected tools must show 0 calls, not just that the expected ones happened).
ALL_RESEARCH_TOOLS = [
    "interest_over_time",
    "related_queries",
    "wikipedia_pageviews",
    "reddit_signal",
    "builder_activity",
    "company_registration",
]

MCP_CONFIG = {
    "mcpServers": {
        "market-signal": {
            "command": "uv",
            "args": ["run", "--directory", str(REPO_ROOT), "server.py"],
        }
    }
}


def _load_queries():
    with open(QUERIES_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def _extract_tool_calls(stream_json_stdout: str) -> list[str]:
    """Parses claude -p --output-format stream-json output and returns every
    MCP tool name invoked, in call order (duplicates kept - a tool called
    twice is a real efficiency finding, not noise to dedupe away)."""
    tools = []
    for line in stream_json_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = event.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                # MCP tool names arrive namespaced, e.g. "mcp__market-signal__reddit_signal"
                short_name = name.rsplit("__", 1)[-1]
                if short_name in ALL_RESEARCH_TOOLS:
                    tools.append(short_name)
    return tools


def run_query(query: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(MCP_CONFIG, f)
        config_path = f.name

    proc = subprocess.run(
        [
            "claude",
            "-p",
            f"/market-signal {query}",
            "--mcp-config",
            config_path,
            "--strict-mcp-config",
            "--output-format",
            "stream-json",
            "--verbose",
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        cwd=REPO_ROOT,
    )
    return {
        "tools_called": _extract_tool_calls(proc.stdout),
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-2000:] if proc.returncode != 0 else "",
    }


def main():
    queries = _load_queries()
    results = []
    passed = 0

    for entry in queries:
        expected = set(entry["expected_tools"])
        try:
            run = run_query(entry["query"])
        except subprocess.TimeoutExpired:
            results.append({"id": entry["id"], "query": entry["query"], "pass": False, "error": "timeout"})
            print(f"[FAIL] {entry['id']}: timed out after {TIMEOUT_SECONDS}s")
            continue

        called = set(run["tools_called"])
        missing = expected - called
        extra = called - expected
        ok = not missing and not extra and run["returncode"] == 0

        if ok:
            passed += 1
        results.append(
            {
                "id": entry["id"],
                "query": entry["query"],
                "expected": sorted(expected),
                "called": run["tools_called"],
                "missing": sorted(missing),
                "extra": sorted(extra),
                "pass": ok,
            }
        )
        print(f"[{'PASS' if ok else 'FAIL'}] {entry['id']}: {entry['query']}")
        if not ok:
            if missing:
                print(f"    missing (Tool Correctness failure): {sorted(missing)}")
            if extra:
                print(f"    extra (Tool-Calling Efficiency failure): {sorted(extra)}")
            if run["returncode"] != 0:
                print(f"    claude -p exited {run['returncode']}: {run['stderr_tail']}")

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    rate = passed / len(queries) if queries else 0
    print(f"\n{passed}/{len(queries)} passed ({rate:.1%}) -- saved to {RESULTS_PATH}")
    sys.exit(0 if passed == len(queries) else 1)


if __name__ == "__main__":
    main()
