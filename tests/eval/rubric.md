# SIGNAL REPORT quality rubric

Used by `test_report_quality.py`'s LLM-as-judge evaluator. Score each dimension 1-5 against the report generated for a query in `gold_answers.jsonl`, compared to that entry's `gold_verdict` and `gold_rationale`.

## 1. Verdict correctness (weight 3x)

- **5**: Verdict matches `gold_verdict` exactly, and the report's reasoning matches the gold rationale's logic (not just a lucky guess at the same label).
- **3**: Verdict is defensible given the data pulled, even if it differs from `gold_verdict` — Trends data is noisy and two reasonable readers could land on adjacent verdicts (e.g. MODERATE vs WEAK). Score 3, not 1, for a defensible near-miss.
- **1**: Verdict contradicts what the actual data in the report's own source blocks shows (e.g. calls something STRONG_SIGNAL while every source block describes flat/declining interest).

## 2. Hallucination absence (weight 2x)

- **5**: No invented numbers, no misread Trends conventions (e.g. correctly treats a `5000%` rising-query value as the Breakout marker, not a literal percentage; correctly treats `isPartial: true` as provisional, not a real drop).
- **3**: Minor imprecision (e.g. rounds a number oddly) but no invented facts.
- **1**: States a number, trend direction, or source finding that doesn't appear anywhere in the actual tool outputs the report claims to be summarizing.

## 3. Caveat completeness (weight 1x)

- **5**: Caveats section names every real limitation present in the gold rationale's "known limitations for this query" (e.g. default-tier-only when deep signal would matter, a partial-month data point, a source that returned an error).
- **3**: Caveats section exists and names at least one real limitation, but misses one the gold rationale flags as important.
- **1**: Caveats section is missing, generic boilerplate, or contradicted by the report's own claims.

## Pass threshold

A report passes if the weighted average (`3×verdict + 2×hallucination + 1×caveats) / 6`) is **≥ 4.0**. Below that, the judge should also output which dimension(s) failed and why, not just the number.
