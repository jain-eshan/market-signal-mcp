---
name: market-signal
description: Conversational market-signal research for a startup idea, feature, or product — Google Trends, Wikipedia, and (--deep) community/builder activity, blended with native web search, closing in a fixed-format SIGNAL REPORT and a real back-and-forth. Handles multi-sided ideas entity-by-entity and can render a shareable HTML report. Use when the user wants to gauge demand, validate an idea, or research a topic for a case competition.
---

# Market Signal Research

Research **$ARGUMENTS**, produce a SIGNAL REPORT, then talk through it. This skill gathers and interprets evidence for one stated question only — if a request drifts into defining a customer segment, pricing tier, or business model, see **Guardrail** below rather than answering it here.

The `market-signal` MCP tools return raw structured data with no interpretation baked in — the verdict, the caveats, and the pitch line are all decided here, not in `server.py`. Every run follows the same steps and produces the same fixed report shape, which is what makes results comparable across ideas and across sessions.

## Guardrail: staying in one lane

If the conversation drifts into customer-segment, pricing-tier, or business-model territory:

1. Try calling the `idea-validator` or `office-hours` skill (whichever fits the drift) via the Skill tool, passing the drifted question as its argument. Detect availability by attempting this call, not by checking the filesystem — a presence-check misses plugin-namespaced installs and global-vs-project-local differences that the Skill tool's own resolution already handles correctly.
2. If that call succeeds, it's a real handoff — let it run and don't duplicate its work here.
3. If it fails or errors (skill not found, or any other error), fall back to asking exactly **one** pointed clarifying question — the single most load-bearing question that skill would have started with (e.g. "who specifically is the customer for this?" for a segment drift, "what's the target price point and why?" for a pricing drift). Note the answer as context in the eventual report, then say plainly this tool doesn't go further than that. No multi-question gauntlet, no synthesis engine — this skill stays narrow either way.

## Step 0: Parse arguments and scope

`$ARGUMENTS` is the idea/topic, optionally followed by flags:
- `--deep` — use the deep tier (Step 2) instead of default-only. Strip the flag to get the plain idea text.
- `--company <name>` — note the company name separately; it's the signal for calling `company_registration` in Step 2, independent of tier.

Check whether the idea names **2 or more distinct impacted entities/stakeholders/sides** (e.g. a two-sided marketplace, an enablement product, a multi-stakeholder workflow — the classic case: a waste-management product naming waste generator, waste collector, and waste treatment as separately impacted parties). If so, this is **multi-entity mode** — research each entity separately in Step 2 and close with a per-entity comparison in Step 4. A request naming only one customer is never multi-entity mode, no matter how deep the research goes. Cap at 3 entities — if the idea names more, research the 3 the user's own framing mentions first or dwells on longest, and note the rest as out of scope for this pass.

Then decide if scoping is needed. Ask **at most 2** clarifying questions, and only when the request is genuinely ambiguous — skip entirely if it's already answered by what the user said.

- *Ask:* "is there demand for this" (no decision named, no timeframe, no geography) → ask what decision this informs and what would change the user's mind.
- *Ask:* "research UPI payments" (topic given, but unclear if this is a demand check, a competitive scan, or a pricing question) → ask which.
- *Don't ask:* "run market-signal on lab-grown diamond jewellery in India, I'm deciding whether to keep funding the brand this quarter" — decision, topic, and stakes are already stated; go straight to research.

Budget: this adds at most ~200 tokens beyond the tier ceiling in Step 2 — it's a scoping check, not a new research phase.

## Step 1: Update check + prior-check lookup (run once, before calling any tool)

```bash
mkdir -p ~/.config/market-signal-mcp
SCRIPT="$(find / -maxdepth 6 -path '*/market-signal-mcp/scripts/check_update.sh' 2>/dev/null | head -1)"
[ -n "$SCRIPT" ] && bash "$SCRIPT" || true

HISTORY=~/.config/market-signal-mcp/history.jsonl
touch "$HISTORY"
```

If the update check printed a line starting with `UPDATE_AVAILABLE`, remember it — surface it as a one-line footer at the end of the report (don't let it interrupt the research itself).

Read `$HISTORY` (if non-empty). Each line is JSON: `{"idea", "verdict", "date", "key_signal", "sources_used", "outcome"}` (`outcome` is optional — see Step 5). Check whether its `idea` field shares a significant keyword (a non-stopword of 4+ characters) with the current idea, case-insensitive. If the most recent match is found, note its `idea`, `verdict`, and `date` — this becomes the `Prior check:` line in the report. If no match, skip this silently (don't mention history at all).

## Step 2: Research

**Call every tool in the active tier in the same turn (parallel tool calls), not one at a time waiting on each result** — they're independent and batching them keeps the report from taking N sequential round-trips.

**Default tier** (always):
- `interest_over_time(keywords=[<core keyword(s), max 5>], geo="IN")` — use `geo=""` instead if the idea is explicitly not India-specific.
- `related_queries(keyword=<core keyword>)`
- `wikipedia_pageviews(article=<best-matching Wikipedia article title for the core concept>)`

**`--deep` tier adds:**
- `reddit_signal(query=<core keyword or phrase>)`
- `builder_activity(query=<core keyword or phrase>)`

Both degrade gracefully if their credentials are unset — a result telling you they're unconfigured is expected and not an error; note it as a caveat rather than a failure.

**Company mode** (`--company <name>` present): additionally call `company_registration(name=...)`, independent of tier — only when the idea names a specific company, since it needs its own API token and isn't a general research signal.

**Multi-entity mode** (from Step 0): run the default-tier (or `--deep`, if requested) tool calls independently for each of the up-to-3 named entities, using keywords specific to that entity rather than one shared keyword set.

All research tools default to `response_format="concise"` — don't override this unless the concise output is clearly insufficient to answer the question (e.g. you need the full 5-year history, not just 90 days).

If any tool returns an error string (missing credentials, rate limit, 404, etc.) instead of data, treat that source as unavailable for this run — note it in `Caveats`, do not treat it as a reason to fail the whole report.

**Qualitative layer, alongside the tool calls:** use native `WebSearch`/`WebFetch` for context the grounded tools can't give — competitor mentions, recent news, forum chatter. Cite what you find; never distill it into a fabricated confidence score. If `WebSearch`/`WebFetch` is unavailable or a call errors, say so plainly in the report ("web search unavailable — this report uses grounded-tool data only") and proceed with the grounded tools alone.

**Landscape mode:** if the WebSearch results surface **3 or more named competitors** for the idea (or, in multi-entity mode, for a given entity), structure those findings as a Differentiation Landscape instead of freeform prose in Step 4 — group the named players by business-model archetype (e.g. enablement/tooling, D2C marketplace, curated marketplace, distributor-led, investor/accelerator-led — adapt categories to what actually fits the idea), noting funding-to-date and website where the search results gave it. This is a formatting rule applied to data already gathered here, not a new research phase or tool call. Fewer than 3 named competitors: skip this, just cite what was found in prose as usual.

## Step 3: Interpret, don't just report numbers

For each source, write one interpretive line, not just the raw numbers — what does this number mean for the actual question being asked. Some interpretation rules carried over from the raw tools' own documentation:

- **Trends "Breakout" marker**: a `related_queries`/`related_topics` "rising" value of `5000%` means explosive growth from near-zero baseline, not a literal percentage. Call this out explicitly if present — it's usually the single strongest signal in the report.
- **`isPartial: true`** on the most recent `interest_over_time` point means that period isn't finished yet; don't read a dip there as a real trend change.
- **Trends vs. Wikipedia divergence** is itself a signal: rising search interest with flat Wikipedia reading interest can mean hype without depth; the reverse can mean a real but under-marketed trend.
- **Reddit/HN/PH (deep tier)**: look for what people are actually building or complaining about, not just volume — a specific complaint quoted verbatim is worth more than a comment count.

## Step 4: Write the SIGNAL REPORT

**Single-entity mode:** use exactly this template, in this order. `Verdict` must be exactly one of the five enum values — never free text.

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

[── Differentiation Landscape ── <only if Step 2 triggered landscape mode>
<named players grouped by business-model archetype, each with funding-to-date
and website where available>]

Caveats:
- <anything that limits confidence in this verdict - partial data, unavailable source, small sample, recency of a spike, etc. At least one caveat is required; if genuinely none apply, state why the data is unusually clean instead of omitting this section.>

Sources used:    <comma-separated list of tools/sources actually used, grounded and web>
Tokens spent:    ~<estimate> (<tier> tier)
════════════════════════════════════════════════════
Pitch line: "<one sentence, portable enough to paste into a slide or a message, stating the sharpest wedge or verdict>"
```

`Tokens spent` is an estimate, not a measurement — default tier typically runs ~600-1000 tokens, `--deep` typically ~2500-3500 (multi-entity mode multiplies this per entity, up to 3x — expected, not a budget violation); say roughly where this run landed and note it's approximate.

**Multi-entity mode:** repeat the source-block portion of the report (Idea through Caveats, minus the top-level Verdict/Confidence header) once per entity, each headed `ENTITY: <name>` with its own Verdict/Confidence, then close with one shared section:

```
Strongest entity: <name> — <its verdict>, because <one sentence>
Elevator pitch: "<What> does <What> for <Whom>"
```

Never assign a numeric score to an entity — use the same five-value verdict vocabulary as single-entity mode. The entity with the strongest verdict gets the elevator pitch; if two entities tie, say so and give both pitches rather than forcing a false tiebreak.

**Verdict guidance** (a judgment call, not a formula — but be consistent about what each value means):
- `STRONG_SIGNAL`: multiple independent sources agree, and at least one shows sustained (not just spiky) interest.
- `MODERATE_SIGNAL`: real signal exists but is narrower than the idea as stated — say what the actual wedge looks like.
- `WEAK_SIGNAL`: sources are flat, small-sample, or contradict the premise.
- `MIXED_SIGNAL`: sources genuinely disagree (e.g. rising search interest but flat community discussion) — say what the disagreement implies, don't average it away.
- `INSUFFICIENT_DATA`: too many sources failed or returned empty to say anything — this is a valid, honest verdict, not a failure of the skill.

If an `UPDATE_AVAILABLE` line was captured in Step 1, add one line after the report: `A newer version of market-signal-mcp is available: <old> -> <new>. <compare_url>`

**Shareable HTML rendering:** render the report as an HTML page and publish it via the Artifact tool (instead of, or in addition to, the in-chat text) when either:
- the user's request explicitly asks for something shareable/presentable/sendable ("can I share this," "make this presentable," "turn this into something I can send"), or
- the idea's own framing names a specific non-technical recipient ("for my dad," "to pitch to," "for the investor").

Don't fire on a bare mention of other people with no delivery ask — "for my team" or "for a friend" alone stays in-chat text; the bar is an actual request or a named delivery target, not any mention of a person. If neither signal is present, the report stays in-chat text only. If the Artifact tool is unavailable in the calling environment, say so plainly and stay in-chat text, same pattern as the WebSearch-unavailable caveat above.

**Then talk about it** — don't just present the report and stop. Open a genuine back-and-forth: what's real here, what's noise, and does this change the user's plan? Cap it at 2 exchanges before closing regardless of how the conversation is going.

## Step 5: Persist to history

After the closing conversation (not before — see Step 4), append exactly one line to `~/.config/market-signal-mcp/history.jsonl`, never edited or patched afterward:

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
if len(sys.argv) > 7 and sys.argv[7]:
    entry['outcome'] = sys.argv[7]
with open(sys.argv[6], 'a') as f:
    f.write(json.dumps(entry) + '\n')
" "<idea text>" "<verdict enum>" "$(date -u +%Y-%m-%d)" "<one-line key signal>" "<comma-separated tool names>" ~/.config/market-signal-mcp/history.jsonl "<one-line outcome, or empty string if the user didn't give a substantive answer>"
```

Include the `outcome` argument only when the user gave a substantive answer to "does this change your plan" in the Step 4 back-and-forth — pass an empty string (which the script skips) if they didn't engage. In multi-entity mode, write one line for the idea as a whole, with `key_signal` naming the strongest entity.

Never overwrite or truncate this file — always append. This is what makes the `Prior check:` feature in Step 1 work on the next run.

## Design notes

- **Data only in the server, judgment only in this skill.** The MCP tools return raw structured data with no interpretation baked in - the verdict, the caveats, and the pitch line are all decided here, not in `server.py`. This keeps the server simple and lets the skill's judgment evolve independently of the tools.
- **Fixed format over free-form prose.** Every single-entity report has the same 8 core elements in the same order specifically so results are comparable across ideas and diffable across sessions (via the history file) - resist the temptation to skip sections or reorder them "because this idea doesn't really need a Caveats section." The Differentiation Landscape block and multi-entity mode are additive, conditional structure on top of that fixed core, not a replacement for it.
- **Company registration data** (`company_registration`) covers incorporation facts only — never present it as funding, traction, or valuation data, because it isn't.
- **The guardrail hands off, it doesn't absorb.** When a request drifts into segment/pricing/business-model territory, this skill either calls a real sibling skill or asks one question and stops — it never grows a second synthesis engine of its own.
