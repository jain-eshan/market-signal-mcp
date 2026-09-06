"""Eval layer 3, structural half (issue #10): does a SIGNAL REPORT follow the
fixed format from SKILL.md - no LLM judge needed for this part, it's pure
string structure. The substantive "is the verdict actually right" half is
test_report_quality.py."""
from pathlib import Path

import pytest

from report_parser import parse_signal_report

FIXTURE = (Path(__file__).parent / "fixtures" / "sample_report_default.txt").read_text()


def test_valid_report_parses_cleanly():
    result = parse_signal_report(FIXTURE)
    assert result["idea"] == "AI resume builder for Indian college students"
    assert result["verdict"] == "MODERATE_SIGNAL"
    assert result["confidence"].startswith("MEDIUM")
    assert "interest_over_time" in result["sources_used"]
    assert result["pitch_line"].startswith("Demand for AI resume tools")


def test_valid_report_stays_under_default_tier_token_budget():
    result = parse_signal_report(FIXTURE)
    # SKILL.md documents ~600-1000 tokens for the default tier; this checks the
    # REPORT TEXT itself (prose + caveats), which naturally runs higher than the
    # raw tool payload measured in issue #7 - budget it generously at 2x that.
    assert result["approx_tokens"] < 2000


@pytest.mark.parametrize(
    "mutation,expected_error_substring",
    [
        (lambda t: t.replace("Verdict:         MODERATE_SIGNAL", ""), "missing required field: verdict"),
        (lambda t: t.replace("MODERATE_SIGNAL", "PROBABLY_GOOD"), "is not one of"),
        (lambda t: t.replace("Caveats:", "Notes:"), "missing required Caveats"),
        (lambda t: t.replace('Pitch line: "Demand for AI resume tools is steady but crowded with generic entrants - the real question worth digging into next is who\'s actually complaining about existing tools, which needs the --deep tier to answer."', ""), "missing required Pitch line"),
        (lambda t: t.replace("Tokens spent:    ~620 (default tier)", ""), "missing required field: tokens_spent"),
        (lambda t: t.replace("SIGNAL REPORT", "Here's what I found:"), "missing SIGNAL REPORT header"),
    ],
)
def test_each_required_element_is_actually_enforced(mutation, expected_error_substring):
    """Mutation testing: prove the parser doesn't just pass on well-formed input
    by accident - each required element's removal must produce a specific,
    correctly-attributed error."""
    broken = mutation(FIXTURE)
    with pytest.raises(ValueError, match=expected_error_substring):
        parse_signal_report(broken)
