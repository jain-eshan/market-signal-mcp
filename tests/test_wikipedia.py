import pytest

import server


def test_parse_duration_days():
    assert server._parse_duration_days("P1Y") == 365
    assert server._parse_duration_days("P6M") == 180
    assert server._parse_duration_days("P90D") == 90


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        server._parse_duration_days("bogus")


@pytest.mark.vcr
def test_wikipedia_pageviews_concise_caps_at_12_months():
    records = server.wikipedia_pageviews("Artificial_intelligence", response_format="concise")
    assert isinstance(records, list)
    assert len(records) <= 12
    for r in records:
        assert "month" in r and "views" in r
        assert isinstance(r["views"], int)


@pytest.mark.vcr
def test_wikipedia_pageviews_handles_space_in_title():
    records = server.wikipedia_pageviews("Machine learning", timeframe="P6M", response_format="full")
    assert isinstance(records, list)
    assert len(records) > 0


@pytest.mark.vcr
def test_wikipedia_pageviews_nonexistent_article_returns_clean_error():
    result = server.wikipedia_pageviews("Thisarticledoesnotexistxyz123", response_format="concise")
    assert isinstance(result, str)
    assert "not found" in result.lower()
