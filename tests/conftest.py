import re

import pytest

# Several tools build request URLs with a "today"-relative date embedded
# either in the path (Wikipedia's per-article/.../monthly/{start}/{end}, as
# YYYYMMDD) or in the query string (pytrends resolves "today 12-m" into a
# literal "YYYY-MM-DD YYYY-MM-DD" range before sending). A cassette recorded
# on day N therefore has a different URL than the same test run on day N+1,
# and VCR's default exact path/query match fails — not a real bug, just
# cassette staleness baked into the matcher. Treat both date shapes as
# wildcards when comparing the full request URL instead.
_DATE_RE = re.compile(r"(?<![0-9])\d{8}(?![0-9])|\d{4}-\d{2}-\d{2}")


def _request_ignoring_dates(r1, r2):
    def normalize(url):
        return _DATE_RE.sub("DATE", url)

    return normalize(r1.url) == normalize(r2.url)


def pytest_recording_configure(config, vcr):
    vcr.register_matcher("request_ignoring_dates", _request_ignoring_dates)


@pytest.fixture(scope="module")
def vcr_config():
    """Scrub anything credential-shaped before a cassette is ever written -
    these fixtures get committed to a public repo. Also swaps the default
    exact path+query matchers for one combined matcher that ignores embedded
    dates (see above) — both path-encoded and query-encoded date shapes."""
    return {
        "filter_headers": ["authorization", "user-agent"],
        "filter_query_parameters": ["api_token", "client_id", "client_secret"],
        "filter_post_data_parameters": ["client_id", "client_secret"],
        "match_on": ["method", "scheme", "host", "port", "request_ignoring_dates"],
    }
