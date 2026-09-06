# Google Trends MCP

A local [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) query Google Trends directly — search interest over time, related queries and topics, regional breakdowns, and real-time trending searches — so you can do market research inside a conversation instead of tab-switching to trends.google.com and pasting screenshots back in.

Built for personal/self-use market research. No API key required — Google Trends has no official public API, so this wraps [pytrends](https://github.com/GeneralMills/pytrends), the standard unofficial Python client, in an MCP server.

## Tools

All tools default `geo="IN"` (India) unless noted — pass `geo=""` for worldwide, or any ISO country code (`"US"`, `"GB"`, etc.). `timeframe` accepts pytrends' format, e.g. `"today 12-m"`, `"today 5-y"`, `"now 7-d"`, or an explicit range `"2024-01-01 2024-06-01"`.

### `interest_over_time(keywords, timeframe="today 12-m", geo="IN")`
Relative search interest (0–100) over time for up to 5 keywords, compared side by side. Keywords beyond the first 5 are silently dropped. Each record includes `isPartial` — `true` on the most recent data point means that period isn't finished yet and its value is provisional; don't read a dip on that point as a real trend change.

### `related_queries(keyword, timeframe="today 12-m", geo="IN")`
Top and rising related search queries for a single keyword. Returns `{"top": [...], "rising": [...]}`, each a list of `{"query": ..., "value": ...}` records. `top` values are 0–100 relative interest. `rising` values are percent increase — **except** a value of `5000%`, which is Google's "Breakout" marker for explosive growth from a near-zero baseline, not a literal percentage.

### `related_topics(keyword, timeframe="today 12-m", geo="IN")`
Same as `related_queries`, but topic clusters (Google's own topic groupings) instead of raw query strings — records have `topic_title` and `topic_type` alongside `value`. Same Breakout convention applies to `rising`.

### `interest_by_region(keyword, timeframe="today 12-m", geo="IN")`
Search interest for a keyword broken down by state/region within the given `geo`. Returns a list of `{"geoName": ..., "<keyword>": 0-100}` records, one per region.

### `trending_now(geo="india")`
Today's top trending searches for a country. **Note the `geo` format is different here** — it's a full lowercase country name (`"india"`, `"united_states"`), not an ISO code like the other four tools. This is a real inconsistency in Google's own endpoints, not a bug.

> **Known limitation:** as of this writing, `trending_now` fails with an HTTP 404. Google appears to have retired the legacy endpoint (`hottrends`/`dailytrends`/`realtimetrends`) that pytrends' trending-search methods depend on — confirmed by testing all three variants pytrends offers. This is an upstream issue, not fixable in this codebase; it fails cleanly with a readable error string rather than crashing. The other 4 tools use a different, still-functional endpoint family and are unaffected. If Google restores the endpoint or pytrends patches around it, this will start working again with no changes needed here.

All tools catch failures (rate limits, network errors, the above) and return a plain error string instead of crashing — Google Trends is a scraped endpoint, not a stable API, so this is expected behavior, not exceptional.

### `wikipedia_pageviews(article, timeframe="P1Y", response_format="concise")`
Monthly Wikipedia pageview counts — a free, no-auth reading/reference-interest signal that complements Trends' search-interest signal. No API key required.

### `company_registration(name, jurisdiction=None)`
Company registration lookup (incorporation date, status, company number) via OpenCorporates. **Scope note: this covers registration facts only — it does NOT cover funding, valuation, or traction data.** No free API exists for that (Tracxn, Crunchbase, and similar are sales-gated enterprise products). Requires a free OpenCorporates API token — register at https://opencorporates.com/api_accounts/new and set `OPENCORPORATES_API_TOKEN` in your environment. Free tier is roughly 50 requests/day, 200/month.

## Setup

Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jain-eshan/market-signal-mcp.git
cd market-signal-mcp
uv sync
```

## Register with Claude Code

```bash
claude mcp add market-signal -- uv run --directory /absolute/path/to/market-signal-mcp server.py
```

Verify it connected:

```bash
claude mcp list
```

You should see `market-signal` listed as `✔ Connected`. Start a **new** Claude Code conversation after registering — sessions already running won't pick up a newly added server.

## Usage

Once registered, just ask Claude to use it — e.g.:

> "Use the google-trends MCP to compare interest in 'lab grown diamonds' vs 'diamond jewellery' in India over the last 12 months, and show me related queries."

### Optional: `/trends` skill

This repo includes a Claude Code skill at `.claude/skills/market-signal/SKILL.md` that wraps the raw tools into a research-and-synthesize workflow — it decides which tools are relevant to your topic and writes up a plain-language summary instead of dumping raw JSON. If you're using Claude Code, this skill is picked up automatically from this repo; just run:

```
/trends <your topic>
```

## Design notes

- **Data only, no synthesis in the server.** Every tool returns raw, structured data — the interpretation (is this trend real, what does a Breakout marker mean here, what's worth flagging) happens in the calling conversation, not baked into the server. This keeps the server simple and lets whatever's calling it (Claude, another MCP client) apply its own judgment.
- **No dependencies beyond `mcp[cli]` and `pytrends`.** No database, no config file, no API key.
- **No formal test suite.** This wraps a scraped third-party endpoint; a test suite would mostly be testing pytrends and Google's current response shape, not this code. Each tool was verified against live Google Trends data during development instead.

## License

MIT — see [LICENSE](LICENSE).
