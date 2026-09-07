# Market Signal MCP

A local [MCP](https://modelcontextprotocol.io) server + Claude Code skill for researching whether a startup idea, product, or topic shows real market signal — search interest, reading interest, community sentiment, builder activity, and company registration — for case competitions and startup-idea validation.

Started as a single-source Google Trends wrapper; evolved into a multi-source signal aggregator with token-conscious defaults and a real eval suite, so it's something you can trust the output of, not just a demo. No database, no config file beyond optional API tokens for the tools that need them.

## `/market-signal` — the actual product

The 9 raw tools below return structured data with no interpretation. The `.claude/skills/market-signal/SKILL.md` skill is where the judgment happens: it decides which tools to call, fans them out in parallel, and writes a fixed-format **SIGNAL REPORT** so results are comparable across ideas and across sessions.

```
/market-signal AI resume builder for Indian college students
```

Real output, from a live run against Trends + Wikipedia:

```
SIGNAL REPORT
════════════════════════════════════════════════════
Idea:            AI resume builder for Indian college students
Verdict:         MODERATE_SIGNAL
Confidence:      MEDIUM (3 sources, 12mo default window)

── Google Trends (interest_over_time + related_queries, India, 12mo) ──
"AI resume builder" holds steady in the high-30s/40s over the last 90 days
(most recent point isPartial - this week isn't finished yet, don't read the
dip as real). Top related query is generic ("resume ai free") - this space
isn't short on competitors already using the obvious framing. One rising
query, "jobsuit ai", spikes to an extreme relative value - worth a manual
check on whether that's a real emerging competitor or a data artifact.

── Wikipedia (Applicant_tracking_system pageviews) ──
Steady ~4,000-4,900 monthly views for most of the window, with a step up in
Dec 2025 (6,763) - no clear correlated spike with the Trends rising-query
signal. Reading interest in "how ATS works" isn't obviously accelerating
alongside search interest in resume tools.

Caveats:
- Default tier only - no Reddit/HN/Product Hunt signal in this run.
- The "jobsuit ai" rising-query spike is unverified from this data alone.
- Wikipedia's Sept 2026 figure (735) is a partial month, not a real drop.

Sources used:    interest_over_time, related_queries, wikipedia_pageviews
Tokens spent:    ~620 (default tier)
════════════════════════════════════════════════════
Pitch line: "Demand for AI resume tools is steady but crowded with generic
entrants - the real question worth digging into next is who's actually
complaining about existing tools, which needs the --deep tier to answer."
```

Add `--deep` to also pull Reddit + Hacker News/Product Hunt (community and builder-activity signal, at higher token cost — see [Tools](#tools) below). Every run is appended to a local history file; researching a similar idea again surfaces a `Prior check:` line citing your earlier verdict.

## Tools

All 9 tools accept `response_format="concise"` (default — truncated, rounded, token-conscious) or `"full"` (complete, unrounded). `/market-signal` calls them itself; you can also call any tool directly.

**Default tier** (no credentials needed):

### `interest_over_time(keywords, timeframe="today 12-m", geo="IN", response_format="concise")`
Relative Google search interest (0–100) over time for up to 5 keywords. `concise` returns the most recent 90 days.

### `related_queries(keyword, timeframe="today 12-m", geo="IN", response_format="concise")`
Top and rising related search queries. A `rising` value of `5000%` is Google's "Breakout" marker (explosive growth from near-zero), not a literal percentage. `concise` returns the top 10 of each.

### `related_topics(keyword, timeframe="today 12-m", geo="IN", response_format="concise")`
Same as `related_queries`, but topic clusters instead of raw query strings.

### `interest_by_region(keyword, timeframe="today 12-m", geo="IN", response_format="concise")`
Search interest by state/region. `concise` returns the top 10 regions by interest.

### `trending_now(geo="india", response_format="concise")`
Today's top trending searches for a country. **Known limitation:** currently fails with HTTP 404 — Google retired the legacy endpoint this depends on. Fails cleanly with a readable error string; the other 8 tools are unaffected.

### `wikipedia_pageviews(article, timeframe="P1Y", response_format="concise")`
Monthly Wikipedia pageview counts — a free, no-auth reading/reference-interest signal that complements Trends' search-interest signal. `concise` returns the last 12 months.

**`--deep` tier** (requires free credentials):

### `reddit_signal(query, subreddits=None, limit=25)`
Qualitative community signal via Reddit search. Requires a free Reddit app — create one at https://www.reddit.com/prefs/apps (type "script") and set `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`. **As of 2026-09-07, Reddit requires manual approval for new apps** (self-service registration closed in late 2025) — expect a wait, not instant signup. Fully optional: `--deep` works fine without it, and this tool degrades to a clear setup message rather than erroring if unconfigured.

### `builder_activity(query)`
Builder/launch-activity signal: Hacker News (Algolia search, no auth) + Product Hunt (requires a free developer token — create one at https://api.producthunt.com/v2/oauth/applications and set `PRODUCTHUNT_TOKEN`). Both `hn` and `product_hunt` are always present as lists; HN works regardless of whether the PH token is set.

**Opt-in** (not part of either tier — called only when a query names a specific company):

### `company_registration(name, jurisdiction=None)`
Company registration lookup (incorporation date, status, company number) via OpenCorporates. **Scope note: registration facts only, not funding/valuation/traction data** — no free API exists for that (Tracxn, Crunchbase, and similar are sales-gated enterprise products; we looked). Requires a free OpenCorporates API token — register at https://opencorporates.com/api_accounts/new and set `OPENCORPORATES_API_TOKEN`. Free tier is roughly 50 requests/day, 200/month.

All tools catch failures (rate limits, missing credentials, network errors) and return a plain error string instead of crashing.

## Setup

**Recommended — install as a Claude Code Plugin.** Two commands, no cloning, no manual path-finding. Run these inside any Claude Code session:

```
/plugin marketplace add jain-eshan/market-signal-mcp
/plugin install market-signal
```

Start a **new** Claude Code conversation after installing — sessions already running won't pick up a newly added plugin. Check it connected:

```bash
claude mcp list
```

You should see `market-signal` listed as `✔ Connected` with 9 tools. Then run `/market-signal <your idea>` (add `--deep` for the community/builder tier).

Optional — set any of these before installing if you want the corresponding tool to work (all degrade gracefully if unset):

```bash
export REDDIT_CLIENT_ID=...
export REDDIT_CLIENT_SECRET=...
export PRODUCTHUNT_TOKEN=...
export OPENCORPORATES_API_TOKEN=...
```

**Alternative — manual clone**, if you want to read or modify the code:

```bash
git clone https://github.com/jain-eshan/market-signal-mcp.git
cd market-signal-mcp
uv sync
claude mcp add market-signal -- uv run --directory "$(pwd)" server.py
```

Same verification and env vars as above apply to this path too.

## Evals

This isn't just an API wrapper — it has a real eval suite, because "does the tool exist" and "does it produce a trustworthy answer" are different questions.

| Layer | What it checks | Status |
|---|---|---|
| **Contract tests** (`tests/`) | Every tool's output matches its documented schema; `response_format` contract holds; recorded fixtures, no live network | ✅ 15/15 passing in CI |
| **Structural report checks** (`tests/eval/test_report_structure.py`) | Every SIGNAL REPORT has all 8 required fields, a valid verdict enum, a Caveats section, under budget — includes a 6-way mutation test proving the checks actually catch violations | ✅ 8/8 passing in CI |
| **Tool-selection eval** (`tests/eval/run_tool_selection.py`) | Does `/market-signal` call the right tier of tools for a query (Tool Correctness) without calling extras (Tool-Calling Efficiency) — 16 labeled queries | ⚠️ Built, harness logic unit-verified (stream-json tool-call parsing confirmed against a simulated transcript). Not run end-to-end: the `claude` CLI on the machine this was built on has an expired OAuth session, and re-authenticating requires an interactive browser login this environment can't do. Run it yourself once `claude` is logged in: `uv run python tests/eval/run_tool_selection.py` |
| **Output-quality eval** (`tests/eval/run_report_quality_judge.py`, `rubric.md`, `gold_answers.jsonl`) | Is the report's verdict actually correct, free of hallucinated numbers, and does it name the real caveats — 5 gold-labeled queries, LLM-as-judge | ⚠️ Same gap as above — rubric and gold answers are real and committed. Run: `uv run python tests/eval/run_report_quality_judge.py` |

Both eval scripts run entirely through `claude -p` (Claude Code's own headless CLI, `--mcp-config` pointed at this repo's `server.py`) — **no separate LLM provider API key**, unlike an earlier version of this eval built on the `mcp-eval` framework. A tool meant to live inside Claude Code should use Claude Code's own capability, the same way this project's self-update check and other tooling lean on already-authenticated CLIs rather than holding credentials of their own.

CI runs the always-green contract + structural suites on every push: [![test](https://github.com/jain-eshan/market-signal-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/jain-eshan/market-signal-mcp/actions/workflows/test.yml). The two `claude -p`-driven evals aren't in CI (a runner has no authenticated `claude` CLI) — run them locally from a logged-in machine.

## Design notes

- **Data only in the server, judgment only in the skill.** Every tool returns raw structured data — the verdict, caveats, and pitch line all get decided in `.claude/skills/market-signal/SKILL.md`, not baked into `server.py`. This keeps the server simple and lets the skill's judgment evolve independently.
- **Token-conscious by default.** `response_format="concise"` (the default) truncates and rounds; the default research tier costs ~600-1000 tokens, `--deep` ~2500-3500 — both measured, not estimated, against real API responses.
- **Self-updating awareness, not self-updating.** A cached, throttled (24h) check compares your local `VERSION` against GitHub and tells you if a newer one exists — it doesn't modify your install.
- **Remembers what you've researched.** Every run appends to `~/.config/market-signal-mcp/history.jsonl`; researching something similar again surfaces what you found last time.

## Known limitations

- `trending_now` is broken upstream (see [Tools](#tools)) — not fixable here.
- `company_registration` covers registration facts only, never funding/traction/valuation data — no free API exists for that.
- The self-update check notifies only; it does not modify your local install.
- `reddit_signal`, the Product Hunt half of `builder_activity`, and `company_registration`'s success path were built and their error/setup paths verified live, but their *successful* credentialed calls haven't been verified end-to-end — no API tokens were available while building this. If you set the corresponding env var and hit an issue, please file one.
- Reddit's self-service app registration is closed (see [Tools](#tools)) — getting `reddit_signal` working involves a manual approval queue, not instant signup. Don't count on it for a same-day setup.
- The tool-selection and output-quality evals (see [Evals](#evals)) are built and their parsing/harness logic verified, but not yet run end-to-end — the `claude` CLI needs a logged-in session, which wasn't available while building this.

## License

MIT — see [LICENSE](LICENSE).
