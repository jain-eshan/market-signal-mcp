---
name: trends
description: Research market/consumer search-interest trends for a topic using the google-trends MCP server, then synthesize findings. Use when the user wants to gauge demand, interest direction, or search trends for a product, feature, or market idea.
---

# Trends Research

Use the `google-trends` MCP tools to research **$ARGUMENTS** and synthesize the findings. The tools return raw data only — no interpretation — so the synthesis happens here, in this skill.

## What to pull

Not every tool applies to every topic — call the ones that make sense, skip the rest.

1. **interest_over_time** — compare the core keyword(s) for the topic over the last 12 months (`geo="IN"` by default, unless the request implies otherwise). Note direction (rising/falling/flat), and flag if the latest point has `isPartial: true` — that value is provisional, don't read it as a real drop.
2. **related_queries** — what people search alongside the core keyword. A "rising" value of `5000%` is Google's "Breakout" marker (explosive growth from near-zero), not a literal percentage — call that out as the strongest signal of an emerging sub-trend, not a number to quote.
3. **related_topics** — same idea, but topic clusters instead of raw query strings — useful for spotting adjacent categories the user might not have thought to search for directly.
4. **interest_by_region** — where interest concentrates, if geography is relevant to the question being asked.
5. **trending_now** — only call this for an explicit "what's hot right now" question, not general interest research. Known limitation: this one currently fails (Google retired the endpoint it depends on) — that's expected, not a bug, and no reason to skip the other tools.

## Output

Plain-language summary: is interest growing or shrinking, what's driving it (related queries/topics), where it's concentrated, and any breakout signals worth flagging. Don't just dump raw numbers — say what they mean for the actual question being asked.
