import functools
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from mcp.server.fastmcp import FastMCP
from pytrends.request import TrendReq

mcp = FastMCP("market-signal")

# Lazy singleton - TrendReq()'s constructor makes a real network call (fetching a
# Google cookie) on instantiation. Eagerly constructing it at import time means
# every test run (and every MCP server boot) makes an uncounted, unrecordable
# network call before any test/tool even runs - the exact flakiness issue #8's
# recorded-fixture testing is meant to eliminate. Deferring construction to first
# use means that call happens inside whichever test's cassette scope needs it.
_pytrends = None


def get_pytrends():
    global _pytrends
    if _pytrends is None:
        _pytrends = TrendReq(hl="en-US", tz=330)
    return _pytrends

RESPONSE_FORMATS = ("concise", "full")

# Wikimedia requires a descriptive User-Agent identifying the app and a contact
# URL, or it returns 403 - https://meta.wikimedia.org/wiki/User-Agent_policy
WIKI_USER_AGENT = "market-signal-mcp/0.1.0 (https://github.com/jain-eshan/market-signal-mcp)"
REDDIT_USER_AGENT = "market-signal-mcp/0.1.0 by /u/jain-eshan"
PRODUCTHUNT_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"


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
    """Convert a pytrends DataFrame (or None) to plain JSON-safe records. Only
    folds the index into the output when it's meaningfully named (e.g. "date",
    "geoName") — related_queries' DataFrame carries a bare ranking index with
    no name, and unconditionally reset_index()-ing it leaks a stray "index"
    field into the API contract (caught by test_related_queries_shape_and_truncation
    once that test asserted an exact key set instead of just membership)."""
    if df is None or df.empty:
        return []
    if df.index.name is not None:
        df = df.reset_index()
    return json.loads(df.to_json(orient="records", date_format="iso"))


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
    get_pytrends().build_payload(keywords[:5], timeframe=timeframe, geo=geo)
    df = get_pytrends().interest_over_time()
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
    get_pytrends().build_payload([keyword], timeframe=timeframe, geo=geo)
    # Patch pytrends to handle empty rankedList (IndexError when Google has no related queries data)
    try:
        result = get_pytrends().related_queries()[keyword]
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
    get_pytrends().build_payload([keyword], timeframe=timeframe, geo=geo)
    # Patch pytrends to handle empty rankedList (IndexError when Google has no related topics data)
    try:
        result = get_pytrends().related_topics()[keyword]
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
    get_pytrends().build_payload([keyword], timeframe=timeframe, geo=geo)
    # inc_low_vol=True includes regions Google would otherwise omit for low search volume
    df = get_pytrends().interest_by_region(resolution="REGION", inc_low_vol=True)
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
    df = get_pytrends().trending_searches(pn=geo)
    terms = df[0].tolist()
    return terms[:10] if response_format == "concise" else terms


def handle_http_errors(func):
    """Catch HTTP/network failures (used by tools that call plain REST APIs, not
    pytrends) and return them as a plain error string instead of crashing."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return f"Not found: {e.request.url}"
            return f"Request failed: {e}"
        except Exception as e:
            return f"Request failed: {e}"
    return wrapper


def _parse_duration_days(duration: str) -> int:
    """Parse a simple ISO-8601-style duration like "P1Y", "P6M", "P90D" into a day
    count. Only whole-number Y/M/D forms are supported (no weeks, no combined
    P1Y6M) - this tool only needs "roughly how far back", not a full ISO-8601
    duration parser."""
    match = re.fullmatch(r"P(\d+)([YMD])", duration.upper())
    if not match:
        raise ValueError(f'Unrecognized timeframe "{duration}" - expected a form like "P1Y", "P6M", or "P90D"')
    n, unit = int(match.group(1)), match.group(2)
    return {"Y": 365, "M": 30, "D": 1}[unit] * n


@mcp.tool()
@handle_http_errors
def wikipedia_pageviews(article: str, timeframe: str = "P1Y", response_format: str = "concise") -> list:
    """Monthly Wikipedia pageview counts for an article - a free, no-auth reference/reading
    interest signal that complements Google Trends' search-interest signal. The two diverging
    (e.g. a term trending in search but flat on Wikipedia) can itself be a signal worth flagging.

    Args:
        article: an English Wikipedia article title, e.g. "Artificial_intelligence" or
            "Machine learning" (spaces are handled automatically).
        timeframe: how far back to request, as a simple duration - "P1Y" (1 year, default),
            "P6M" (6 months), "P90D" (90 days). Only whole Y/M/D forms are supported.
        response_format: "concise" (default) returns only the most recent 12 months.
            "full" returns the entire requested timeframe.

    Returns:
        A list of records, one per month, each containing:
        - "month": "YYYY-MM"
        - "views": total pageviews that month (all access methods, human traffic only -
          bot traffic is excluded by Wikimedia's "user" agent filter)
    """
    days = _parse_duration_days(timeframe)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    encoded_article = quote(article.strip().replace(" ", "_"), safe="")
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia/all-access/user/{encoded_article}/monthly/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    resp = requests.get(url, headers={"User-Agent": WIKI_USER_AGENT}, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    records = [{"month": f"{item['timestamp'][:4]}-{item['timestamp'][4:6]}", "views": item["views"]} for item in items]
    if response_format == "concise":
        records = records[-12:]
    return records


@mcp.tool()
@handle_http_errors
def company_registration(name: str, jurisdiction: str | None = None) -> list:
    """Company registration lookup via OpenCorporates - registration facts only
    (incorporation date, status, company number). Does NOT cover funding, valuation,
    or traction data - no free API exists for that (see README for why).

    Requires a free OpenCorporates API token: as of 2026 OpenCorporates requires a
    token on every request, even on the free tier (roughly 50 requests/day, 200/month).
    Register at https://opencorporates.com/api_accounts/new and set
    OPENCORPORATES_API_TOKEN in your environment.

    Args:
        name: company name to search for.
        jurisdiction: optional OpenCorporates jurisdiction code (e.g. "in", "us_de") to narrow results.

    Returns:
        A list of up to 5 matches, each containing "company_name", "jurisdiction_code",
        "incorporation_date", "company_number", "current_status", "opencorporates_url".
        Empty list if no matches. A setup-instructions string if OPENCORPORATES_API_TOKEN
        is unset, or OpenCorporates' own rejection message if the token is invalid/expired.
    """
    token = os.environ.get("OPENCORPORATES_API_TOKEN")
    if not token:
        return (
            "company_registration requires a free OpenCorporates API token. Register at "
            "https://opencorporates.com/api_accounts/new and set OPENCORPORATES_API_TOKEN "
            "in your environment, then restart the MCP server."
        )
    params = {"q": name, "api_token": token}
    if jurisdiction:
        params["jurisdiction_code"] = jurisdiction
    resp = requests.get("https://api.opencorporates.com/v0.4/companies/search", params=params, timeout=15)
    if resp.status_code == 401:
        message = resp.json().get("error", {}).get("message", "invalid token")
        return f"OpenCorporates rejected the API token: {message}"
    resp.raise_for_status()
    companies = resp.json().get("results", {}).get("companies", [])[:5]
    return [
        {
            "company_name": c.get("company", {}).get("name"),
            "jurisdiction_code": c.get("company", {}).get("jurisdiction_code"),
            "incorporation_date": c.get("company", {}).get("incorporation_date"),
            "company_number": c.get("company", {}).get("company_number"),
            "current_status": c.get("company", {}).get("current_status"),
            "opencorporates_url": c.get("company", {}).get("opencorporates_url"),
        }
        for c in companies
    ]


def _reddit_access_token(client_id: str, client_secret: str) -> str:
    """Reddit's app-only OAuth flow (client_credentials) - no user login needed,
    just the app's own id/secret."""
    resp = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@mcp.tool()
@handle_http_errors
def reddit_signal(query: str, subreddits: list[str] | None = None, limit: int = 25) -> list:
    """Qualitative community signal from Reddit - what people are actually saying,
    complaining about, or asking for, as opposed to Trends/Wikipedia's passive
    search/reading signal. This is the --deep tier (issue #7), not a default source,
    because it's the one source in this tool that requires a registered app.

    Requires a free Reddit app: create one at https://www.reddit.com/prefs/apps
    (type "script"), then set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.

    Args:
        query: search terms.
        subreddits: optional list of subreddit names to restrict the search to
            (e.g. ["startups", "SaaS"]). Omit to search all of Reddit.
        limit: max results, capped at 100 by Reddit's API.

    Returns:
        A list of records, each containing "title", "subreddit", "score",
        "num_comments", "permalink", "created_utc". A setup-instructions string
        if REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are unset.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return (
            "reddit_signal requires a free Reddit app. Create one at "
            "https://www.reddit.com/prefs/apps (type \"script\"), then set "
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in your environment."
        )
    token = _reddit_access_token(client_id, client_secret)
    scope = "+".join(subreddits) if subreddits else "all"
    resp = requests.get(
        f"https://oauth.reddit.com/r/{scope}/search",
        params={"q": query, "sort": "relevance", "limit": min(limit, 100), "restrict_sr": bool(subreddits)},
        headers={"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    children = resp.json().get("data", {}).get("children", [])
    return [
        {
            "title": c["data"].get("title"),
            "subreddit": c["data"].get("subreddit"),
            "score": c["data"].get("score"),
            "num_comments": c["data"].get("num_comments"),
            "permalink": f"https://reddit.com{c['data'].get('permalink', '')}",
            "created_utc": c["data"].get("created_utc"),
        }
        for c in children
    ]


@mcp.tool()
@handle_http_errors
def builder_activity(query: str) -> dict:
    """Builder/launch-activity signal from Hacker News + Product Hunt - are people
    actually building and shipping in this space, as opposed to just searching or
    talking about it. Part of the --deep tier (issue #7).

    Hacker News (via its Algolia search API) needs no auth. Product Hunt's API
    requires a free developer token even for public read access (confirmed 2026 -
    there is no unauthenticated tier) - create one at
    https://api.producthunt.com/v2/oauth/applications and set PRODUCTHUNT_TOKEN
    to enable that half; HN results are returned regardless.

    Args:
        query: search terms.

    Returns:
        {"hn": [...], "product_hunt": [...]} - both keys are always present as
        lists (empty if no results, or if PRODUCTHUNT_TOKEN is unset), plus a
        "product_hunt_note" key with setup instructions when the token is unset.
    """
    hn_resp = requests.get("https://hn.algolia.com/api/v1/search", params={"query": query, "tags": "story"}, timeout=15)
    hn_resp.raise_for_status()
    hn_records = [
        {
            "title": h.get("title"),
            "points": h.get("points"),
            "num_comments": h.get("num_comments"),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "created_at": h.get("created_at"),
        }
        for h in hn_resp.json().get("hits", [])[:10]
    ]

    result = {"hn": hn_records, "product_hunt": []}
    ph_token = os.environ.get("PRODUCTHUNT_TOKEN")
    if not ph_token:
        result["product_hunt_note"] = (
            "Product Hunt requires a free developer token. Create one at "
            "https://api.producthunt.com/v2/oauth/applications and set PRODUCTHUNT_TOKEN."
        )
        return result

    gql = {
        "query": "query($first: Int!) { posts(first: $first, order: VOTES) { edges { node { name tagline votesCount commentsCount url createdAt } } } }",
        "variables": {"first": 20},
    }
    ph_resp = requests.post(
        PRODUCTHUNT_GRAPHQL_URL,
        json=gql,
        headers={"Authorization": f"Bearer {ph_token}", "Content-Type": "application/json"},
        timeout=15,
    )
    ph_resp.raise_for_status()
    edges = ph_resp.json().get("data", {}).get("posts", {}).get("edges", [])
    q_lower = query.lower()
    result["product_hunt"] = [
        {
            "name": e["node"].get("name"),
            "tagline": e["node"].get("tagline"),
            "votes": e["node"].get("votesCount"),
            "comments": e["node"].get("commentsCount"),
            "url": e["node"].get("url"),
            "created_at": e["node"].get("createdAt"),
        }
        for e in edges
        if q_lower in f"{e['node'].get('name', '')} {e['node'].get('tagline', '')}".lower()
    ]
    return result


if __name__ == "__main__":
    mcp.run()
