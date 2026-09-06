"""Eval layer 2 (issue #9): does an agent following the /market-signal skill's
routing rules call the right tools for a given query (Tool Correctness) and
avoid calling extras it doesn't need (Tool-Calling Efficiency)?

This drives a REAL LLM agent against the REAL market-signal MCP server via
mcp-eval (https://github.com/lastmile-ai/mcp-eval) - it is not a mock. That
means it needs a real LLM API key configured in tests/eval/mcpeval.secrets.yaml
(copy from mcpeval.secrets.yaml.example) to actually run:

    cd tests/eval
    cp mcpeval.secrets.yaml.example mcpeval.secrets.yaml  # fill in your key
    uv run mcp-eval run test_tool_selection.py -v

Known gap: no LLM API key was available in the environment this suite was
written in, so this has been verified for correct structure and dataset
loading, but NOT executed end-to-end against a real agent. Whoever runs it
with a real key should treat the first run as the actual verification of
issue #9's acceptance criteria, and save the resulting report (see README).
"""
import json
from pathlib import Path

from mcp_agent.agents.agent_spec import AgentSpec

from mcp_eval import Case, Dataset, Expect

QUERIES_PATH = Path(__file__).parent / "queries.jsonl"

# Every tool the routing logic can call - used to assert efficiency (a query's
# UNEXPECTED tools must show 0 calls, not just that the expected ones happened).
ALL_RESEARCH_TOOLS = [
    "interest_over_time",
    "related_queries",
    "wikipedia_pageviews",
    "reddit_signal",
    "builder_activity",
    "company_registration",
]

# Condensed version of .claude/skills/market-signal/SKILL.md's Step 2 routing
# rules - the agent needs these instructions explicitly, since a generic
# mcp-eval agent has no knowledge of our skill file.
AGENT_INSTRUCTION = """You are researching market signal for an idea using the market-signal MCP tools.

Default tier (always, unless told otherwise): call interest_over_time, related_queries,
and wikipedia_pageviews for the core idea/keyword. Do not call anything else.

Deep tier: ONLY if the request explicitly asks for a deeper look, community sentiment,
builder/launch activity, or contains the literal flag "--deep" - in that case ALSO call
reddit_signal and builder_activity, in addition to the default tier tools.

Company lookup: ONLY if the request names a specific company and asks about its
registration/incorporation status - call company_registration for that. If the request
is ONLY a company lookup (not general idea research), call company_registration and
nothing else - do not also call the default-tier research tools.

Never call related_topics, interest_by_region, trending_now, or any tool not named above."""


def _load_cases() -> list[Case]:
    cases = []
    with open(QUERIES_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            expected = set(entry["expected_tools"])
            unexpected = [t for t in ALL_RESEARCH_TOOLS if t not in expected]
            evaluators = [Expect.tools.was_called(tool) for tool in expected]
            evaluators += [Expect.tools.count(tool, 0) for tool in unexpected]
            cases.append(
                Case(
                    name=entry["id"],
                    inputs=entry["query"],
                    evaluators=evaluators,
                    metadata={"tier": entry["tier"], "note": entry["note"]},
                )
            )
    return cases


dataset = Dataset(
    name="market-signal tool-selection eval",
    cases=_load_cases(),
    agent_spec=AgentSpec(
        name="MarketSignalRouter",
        instruction=AGENT_INSTRUCTION,
        server_names=["market-signal"],
    ),
)


async def _run_case(inputs: str, agent, session) -> str:
    return await agent.generate_str(inputs)


if __name__ == "__main__":
    import asyncio

    async def main():
        report = await dataset.evaluate(_run_case, max_concurrency=3)
        print(f"\n{report.passed_cases}/{report.total_cases} cases passed ({report.success_rate:.1%})")
        for result in report.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.case_name}: {result.inputs}")
            if not result.passed:
                for ev in result.evaluation_results:
                    if not ev.passed:
                        print(f"         failed: {ev.name}")

    asyncio.run(main())
