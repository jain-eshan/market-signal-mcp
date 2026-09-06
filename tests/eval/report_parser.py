"""Parses a SIGNAL REPORT (the fixed output format from
.claude/skills/market-signal/SKILL.md Step 4) into a dict, and raises
ValueError with a specific message for each way it can be malformed. This is
the shared structural checker used by both the eval and, potentially, by the
skill itself in the future to self-check before presenting a report."""
import re

VERDICT_ENUM = {"STRONG_SIGNAL", "MODERATE_SIGNAL", "WEAK_SIGNAL", "MIXED_SIGNAL", "INSUFFICIENT_DATA"}

REQUIRED_FIELDS = {
    "idea": re.compile(r"^Idea:\s*(.+)$", re.MULTILINE),
    "verdict": re.compile(r"^Verdict:\s*(\S+)", re.MULTILINE),
    "confidence": re.compile(r"^Confidence:\s*(.+)$", re.MULTILINE),
    "sources_used": re.compile(r"^Sources used:\s*(.+)$", re.MULTILINE),
    "tokens_spent": re.compile(r"^Tokens spent:\s*(.+)$", re.MULTILINE),
}
PITCH_LINE_RE = re.compile(r'^Pitch line:\s*"(.+)"', re.MULTILINE)
CAVEATS_RE = re.compile(r"^Caveats:\s*$", re.MULTILINE)


def parse_signal_report(text: str) -> dict:
    """Returns a dict with keys: idea, verdict, confidence, sources_used,
    tokens_spent, pitch_line, has_caveats_section, approx_tokens.
    Raises ValueError naming the specific missing/invalid field."""
    if "SIGNAL REPORT" not in text:
        raise ValueError("missing SIGNAL REPORT header")

    result = {}
    for field, pattern in REQUIRED_FIELDS.items():
        match = pattern.search(text)
        if not match:
            raise ValueError(f"missing required field: {field}")
        result[field] = match.group(1).strip()

    if result["verdict"] not in VERDICT_ENUM:
        raise ValueError(f"verdict '{result['verdict']}' is not one of {sorted(VERDICT_ENUM)}")

    if not CAVEATS_RE.search(text):
        raise ValueError("missing required Caveats: section")

    pitch_match = PITCH_LINE_RE.search(text)
    if not pitch_match:
        raise ValueError("missing required Pitch line: (must be quoted)")
    result["pitch_line"] = pitch_match.group(1)

    result["approx_tokens"] = len(text) // 4
    return result
