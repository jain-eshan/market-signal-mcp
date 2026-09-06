---
name: market-signal
description: Research whether a startup idea, product, or topic shows real market signal, using the market-signal MCP server (Google Trends, Wikipedia, and optionally Reddit/Hacker News/Product Hunt/company registration), then produce a fixed-format SIGNAL REPORT. Use when the user wants to gauge demand, validate an idea, or research a topic for a case competition.
---

# Market Signal Research

Research **$ARGUMENTS** and produce a SIGNAL REPORT. Every run follows the same steps and produces the same output shape — that consistency is the point: a fixed report format is what makes results comparable across ideas and across sessions.

## Step 0: Parse arguments

`$ARGUMENTS` is the idea/topic, optionally followed by `--deep`. Strip the flag out to get the plain idea text. If `--deep` is present, use the deep tier (Step 2); otherwise use the default tier only.

## Step 1: Update check + prior-check lookup (run once, before calling any tool)

```bash
mkdir -p ~/.config/market-signal-mcp
SCRIPT="$(find / -maxdepth 6 -path '*/market-signal-mcp/scripts/check_update.sh' 2>/dev/null | head -1)"
[ -n "$SCRIPT" ] && bash "$SCRIPT" || true

HISTORY=~/.config/market-signal-mcp/history.jsonl
touch "$HISTORY"
```

If the update check printed a line starting with `UPDATE_AVAILABLE`, remember it — surface it as a one-line footer at the end of the report (don't let it interrupt the research itself).

Read `$HISTORY` (if non-empty). For each line (JSON: `{"idea", "verdict", "date", "key_signal", "sources_used"}`), check whether its `idea` field shares a significant keyword (a non-stopword of 4+ characters) with the current idea, case-insensitive. If the most recent match is found, note its `idea`, `verdict`, and `date` — this becomes the `Prior check:` line in the report. If no match, skip this silently (don't mention history at all).

## Step 2: Call the tools for the active tier

**Call every tool in this tier in the same turn (parallel tool calls), not one at a time waiting on each result** — they're independent and batching them keeps the report from taking N sequential round-trips.

**Default tier** (always):
- `interest_over_time(keywords=[<core keyword(s), max 5>], geo="IN")` — use `geo=""` instead if the idea is explicitly not India-specific.
- `related_queries(keyword=<core keyword>)`
- `wikipedia_pageviews(article=<best-matching Wikipedia article title for the core concept>)`

**`--deep` tier adds:**
- `reddit_signal(query=<core keyword or phrase>)`
- `builder_activity(query=<core keyword or phrase>)`

**Company lookup (opt-in, independent of tier):** only call `company_registration(name=...)` if the idea names a specific company by name (e.g. "is X Corp a real company"), not for general idea/topic research.

All 5 (or 7, with company lookup) research tools default to `response_format="concise"` — don't override this unless the concise output is clearly insufficient to answer the question (e.g. you need the full 5-year history, not just 90 days).

If any tool returns an error string (missing credentials, rate limit, 404, etc.) instead of data, treat that source as unavailable for this run — note it in `Caveats`, do not treat it as a reason to fail the whole report.

## Step 3: Interpret, don't just report numbers

For each source, write one interpretive line, not just the raw numbers — what does this number mean for the actual question being asked. Some interpretation rules carried over from the raw tools' own documentation:

- **Trends "Breakout" marker**: a `related_queries`/`related_topics` "rising" value of `5000%` means explosive growth from near-zero baseline, not a literal percentage. Call this out explicitly if present — it's usually the single strongest signal in the report.
- **`isPartial: true`** on the most recent `interest_over_time` point means that period isn't finished yet; don't read a dip there as a real trend change.
- **Trends vs. Wikipedia divergence** is itself a signal: rising search interest with flat Wikipedia reading interest can mean hype without depth; the reverse can mean a real but under-marketed trend.
- **Reddit/HN/PH (deep tier)**: look for what people are actually building or complaining about, not just volume — a specific complaint quoted verbatim is worth more than a comment count.

## Step 4: Write the SIGNAL REPORT

Use exactly this template, in this order. `Verdict` must be exactly one of the five enum values — never free text.

```
SIGNAL REPORT
════════════════════════════════════════════════════
Idea:            <the idea, as stated>
Verdict:         <STRONG_SIGNAL | MODERATE_SIGNAL | WEAK_SIGNAL | MIXED_SIGNAL | INSUFFICIENT_DATA>
Confidence:      <LOW | MEDIUM | HIGH> (<N> sources, <window> window)
[Prior check:    You researched "<prior idea>" on <date>. Verdict then: <prior verdict>. — omit this line entirely if no history match]

── <Source name> ──
<2-4 lines: key numbers + one interpretive line>

── <Source name> ──
<...>

[repeat one block per source actually called]

Caveats:
- <anything that limits confidence in this verdict - partial data, unavailable source, small sample, recency of a spike, etc. At least one caveat is required; if genuinely none apply, state why the data is unusually clean instead of omitting this section.>

Sources used:    <comma-separated list of tools actually called>
Tokens spent:    ~<estimate> (<tier> tier)
════════════════════════════════════════════════════
Pitch line: "<one sentence, portable enough to paste into a slide or a message, stating the sharpest wedge or verdict>"
```

`Tokens spent` is an estimate, not a measurement — default tier typically runs ~600-1000 tokens, `--deep` typically ~2500-3500; say roughly where this run landed and note it's approximate.

If an `UPDATE_AVAILABLE` line was captured in Step 1, add one line after the report: `A newer version of market-signal-mcp is available: <old> -> <new>. <compare_url>`

## Step 5: Persist to history

After presenting the report, append one line to `~/.config/market-signal-mcp/history.jsonl`:

```bash
python3 -c "
import json, sys
entry = {
    'idea': sys.argv[1],
    'verdict': sys.argv[2],
    'date': sys.argv[3],
    'key_signal': sys.argv[4],
    'sources_used': sys.argv[5].split(','),
}
with open(sys.argv[6], 'a') as f:
    f.write(json.dumps(entry) + '\n')
" "<idea text>" "<verdict enum>" "$(date -u +%Y-%m-%d)" "<one-line key signal>" "<comma-separated tool names>" ~/.config/market-signal-mcp/history.jsonl
```

Never overwrite or truncate this file — always append. This is what makes the `Prior check:` feature in Step 1 work on the next run.

## Design notes

- **Data only in the server, judgment only in this skill.** The MCP tools return raw structured data with no interpretation baked in - the verdict, the caveats, and the pitch line are all decided here, not in `server.py`. This keeps the server simple and lets the skill's judgment evolve independently of the tools.
- **Fixed format over free-form prose.** Every report has the same 8 elements in the same order specifically so results are comparable across ideas and diffable across sessions (via the history file) - resist the temptation to skip sections or reorder them "because this idea doesn't really need a Caveats section."
