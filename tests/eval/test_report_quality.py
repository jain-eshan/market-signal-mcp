"""Eval layer 3, LLM-as-judge half (issue #10): is the SUBSTANCE of a
generated SIGNAL REPORT actually correct - right verdict, no hallucinated
numbers, real caveats - not just the right shape (that's
test_report_structure.py, which needs no LLM).

Same execution gap as tests/eval/test_tool_selection.py: this drives a real
LLM agent (to generate the report) and a real LLM judge (to score it), both
via mcp-eval, and needs a configured API key in mcpeval.secrets.yaml. Not
run end-to-end in the environment this was written in - see the #10 comment
thread. Whoever runs this with a real key should treat that first run as the
actual verification of this issue's acceptance criteria, including the
"deliberately wrong report scores lower" check (AC #5), which needs a live
judge and could not be verified here.

    cd tests/eval
    cp mcpeval.secrets.yaml.example mcpeval.secrets.yaml  # fill in your key
    uv run mcp-eval run test_report_quality.py -v
"""
import json
from pathlib import Path

from mcp_agent.agents.agent_spec import AgentSpec

from mcp_eval import Case, Dataset, Expect

GOLD_PATH = Path(__file__).parent / "gold_answers.jsonl"
RUBRIC = (Path(__file__).parent / "rubric.md").read_text()

# The agent needs the full SIGNAL REPORT format instructions to produce
# something scoreable - condensed from .claude/skills/market-signal/SKILL.md
# Step 2 (routing) and Step 4 (report template).
AGENT_INSTRUCTION = """You are researching market signal for an idea using the market-signal MCP tools.
Default tier: call interest_over_time, related_queries, and wikipedia_pageviews. Add
reddit_signal and builder_activity only if the request says "--deep" or asks for a
deeper/community look. Call company_registration only for an explicit company-registration
question.

Produce your answer as a SIGNAL REPORT with exactly these fields, in this order: Idea,
Verdict (one of STRONG_SIGNAL, MODERATE_SIGNAL, WEAK_SIGNAL, MIXED_SIGNAL,
INSUFFICIENT_DATA), Confidence, one block per source you called ending in an interpretive
line (not just raw numbers), a Caveats section (required, at least one real limitation),
Sources used, Tokens spent (your own estimate), and a quoted Pitch line."""


def _load_cases() -> list[Case]:
    cases = []
    with open(GOLD_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            rubric_for_case = (
                f"{RUBRIC}\n\n## This query's gold answer\n\n"
                f"Gold verdict: {entry['gold_verdict']}\n"
                f"Gold rationale: {entry['gold_rationale']}\n\n"
                "Score the report above against this rubric and gold answer. "
                "Report the weighted average and the pass/fail per the rubric's threshold."
            )
            cases.append(
                Case(
                    name=entry["id"],
                    inputs=entry["query"],
                    evaluators=[
                        Expect.judge.llm(
                            rubric=rubric_for_case,
                            min_score=4.0 / 5.0,  # rubric's own pass threshold, normalized to 0-1
                            include_input=True,
                            require_reasoning=True,
                        )
                    ],
                    metadata={"gold_verdict": entry["gold_verdict"]},
                )
            )
    return cases


dataset = Dataset(
    name="market-signal report-quality eval",
    cases=_load_cases(),
    agent_spec=AgentSpec(
        name="MarketSignalReporter",
        instruction=AGENT_INSTRUCTION,
        server_names=["market-signal"],
    ),
)


async def _run_case(inputs: str, agent, session) -> str:
    return await agent.generate_str(inputs)


if __name__ == "__main__":
    import asyncio

    async def main():
        report = await dataset.evaluate(_run_case, max_concurrency=2)
        print(f"\n{report.passed_cases}/{report.total_cases} cases passed ({report.success_rate:.1%})")

    asyncio.run(main())
