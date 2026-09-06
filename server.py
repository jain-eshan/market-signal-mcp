import functools
import json
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP
from pytrends.request import TrendReq

mcp = FastMCP("market-signal")
pytrends = TrendReq(hl="en-US", tz=330)

RESPONSE_FORMATS = ("concise", "full")


def handle_trends_errors(func):
    """Catch pytrends/network failures and return them as a plain error string
    instead of crashing the server (Google Trends is a scraped, rate-limited endpoint)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return f"Google Trends request failed: {e}"
    return wrapper


def df_to_records(df):
    """Convert a pytrends DataFrame (or None) to plain JSON-safe records."""
    if df is None or df.empty:
        return []
    return json.loads(df.reset_index().to_json(orient="records", date_format="iso"))


def apply_format(records, response_format, *, sort_key=None, limit=None, recent_days=None):
    """Shrink a list of dict records for response_format="concise". No-op for "full"
    or an empty/non-list input. recent_days filters by an ISO "date" field (used for
    time-series data); sort_key + limit implement top-N truncation (used for ranked
    lists like related queries/topics/regions). Concise mode also rounds floats to
    whole numbers and drops isPartial when False (it's the common case - only worth
    stating when True)."""
    if response_format != "concise" or not records:
        return records
    if recent_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).date().isoformat()
        records = [r for r in records if r.get("date", "") >= cutoff]
    if sort_key is not None:
        records = sorted(records, key=lambda r: r.get(sort_key) or 0, reverse=True)
    if limit is not None:
        records = records[:limit]
    for r in records:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = round(v)
        if r.get("isPartial") is False:
            del r["isPartial"]
    return records


@mcp.tool()
@handle_trends_errors
def interest_over_time(
    keywords: list[str], timeframe: str = "today 12-m", geo: str = "IN", response_format: str = "concise"
) -> list:
    """Relative Google search interest (0-100) over time for up to 5 keywords, compared side by side.

    Args:
        keywords: 1-5 search terms to compare. Only the first 5 are used; additional keywords are silently dropped.
        timeframe: pytrends timeframe string, e.g. "today 12-m", "today 5-y", "now 7-d", or "YYYY-MM-DD YYYY-MM-DD".
        geo: ISO country code (e.g. "IN", "US"), or "" for worldwide.
        response_format: "concise" (default) returns only the most recent 90 days of records,
            rounded to whole numbers, to keep token cost low. "full" returns every record in
            the requested timeframe, unrounded - use it when you actually need the long history.

    Returns:
        A list of records, one per date, each containing:
        - "date": ISO date string
        - "isPartial": present and true only when the period is incomplete (most recent point) -
          omitted when false in "concise" mode, since false is the common case.
        - One numeric key per keyword (0-100 relative interest value)
    """
    pytrends.build_payload(keywords[:5], timeframe=timeframe, geo=geo)
    df = pytrends.interest_over_time()
    records = df_to_records(df)
    return apply_format(records, response_format, recent_days=90)


@mcp.tool()
@handle_trends_errors
def related_queries(
    keyword: str, timeframe: str = "today 12-m", geo: str = "IN", response_format: str = "concise"
) -> dict:
    """Top and rising related search queries for a single keyword.

    Args:
        keyword: a single search term.
        timeframe: pytrends timeframe string, e.g. "today 12-m".
        geo: ISO country code (e.g. "IN"), or "" for worldwide.
        response_format: "concise" (default) returns only the top 10 of each list, sorted by
            "value" descending, rounded to whole numbers. "full" returns every row Google Trends
            provides (often 25), unrounded.

    Returns:
        A dict with two keys, each containing a list of query records:
        - "top": most-searched related queries. Each record has "query" and "value"
          (0-100 relative interest on Google Trends scale).
        - "rising": fastest-growing related queries. Each record has "query" and "value"
          (percent increase in search interest). IMPORTANT: a value of 5000% is Google's
          "Breakout" marker, indicating explosive new growth from near-zero baseline,
          NOT a literal 5000% increase. This is Google's way of saying the data cannot
          be assigned a meaningful numeric value.
    """
    pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
    # Patch pytrends to handle empty rankedList (IndexError when Google has no related queries data)
    try:
        result = pytrends.related_queries()[keyword]
    except IndexError:
        # Google Trends doesn't have related queries data for this keyword/geo combination
        result = {"top": None, "rising": None}
    return {
        "top": apply_format(df_to_records(result.get("top")), response_format, sort_key="value", limit=10),
        "rising": apply_format(df_to_records(result.get("rising")), response_format, sort_key="value", limit=10),
    }


@mcp.tool()
@handle_trends_errors
def related_topics(
    keyword: str, timeframe: str = "today 12-m", geo: str = "IN", response_format: str = "concise"
) -> dict:
    """Top and rising related topics (Google's topic clusters, not raw query strings) for a single keyword.

    Args:
        keyword: a single search term.
        timeframe: pytrends timeframe string, e.g. "today 12-m".
        geo: ISO country code (e.g. "IN"), or "" for worldwide.
        response_format: "concise" (default) returns only the top 10 of each list, sorted by
            "value" descending, rounded to whole numbers. "full" returns every row, unrounded.

    Returns:
        A dict with two keys, each containing a list of topic records:
        - "top": most-searched related topics. Each record has "topic_title", "topic_type", "value"
          (0-100 relative interest on Google Trends scale).
        - "rising": fastest-growing related topics. Each record has "topic_title", "topic_type", "value".
          IMPORTANT: a value of 5000% is Google's "Breakout" marker, indicating explosive new growth
          from near-zero baseline, NOT a literal 5000% increase. This is the same convention as "rising"
          queries.
    """
    pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
    # Patch pytrends to handle empty rankedList (IndexError when Google has no related topics data)
    try:
        result = pytrends.related_topics()[keyword]
    except IndexError:
        # Google Trends doesn't have related topics data for this keyword/geo combination
        result = {"top": None, "rising": None}
    return {
        "top": apply_format(df_to_records(result.get("top")), response_format, sort_key="value", limit=10),
        "rising": apply_format(df_to_records(result.get("rising")), response_format, sort_key="value", limit=10),
    }


@mcp.tool()
@handle_trends_errors
def interest_by_region(
    keyword: str, timeframe: str = "today 12-m", geo: str = "IN", response_format: str = "concise"
) -> list:
    """Search interest for a keyword broken down by state/region within the given geo.

    Args:
        keyword: a single search term.
        timeframe: pytrends timeframe string, e.g. "today 12-m".
        geo: ISO country code (e.g. "IN"), or "" for worldwide.
        response_format: "concise" (default) returns only the top 10 regions by interest,
            rounded to whole numbers. "full" returns every region, unrounded.

    Returns:
        A list of records, one per state/region within the specified geo, each containing:
        - "geoName": the name of the state or region (e.g. "Maharashtra", "Delhi", "Karnataka" for India)
        - A column with the keyword name as the key: relative search interest (0-100 scale) for that
          region. Higher values indicate higher relative interest in that region compared to others
          in the same country. This is Google Trends' standard region-relative scale.
    """
    pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
    # inc_low_vol=True includes regions Google would otherwise omit for low search volume
    df = pytrends.interest_by_region(resolution="REGION", inc_low_vol=True)
    records = df_to_records(df)
    return apply_format(records, response_format, sort_key=keyword, limit=10)


@mcp.tool()
@handle_trends_errors
def trending_now(geo: str = "india", response_format: str = "concise") -> list:
    """Today's top trending searches for a country.

    Args:
        geo: full lowercase country name as used by Google Trends' trending-searches
            endpoint, e.g. "india", "united_states" — NOT an ISO code (unlike the
            other 4 tools in this server).
        response_format: "concise" (default) returns only the top 10 terms. "full" returns
            the entire list (typically ~20 terms).

    Returns:
        A list of trending search term strings, ordered by trend rank (most-trending first).
    """
    df = pytrends.trending_searches(pn=geo)
    terms = df[0].tolist()
    return terms[:10] if response_format == "concise" else terms


if __name__ == "__main__":
    mcp.run()
