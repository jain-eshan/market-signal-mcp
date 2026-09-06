"""Contract tests for the 3 tools that require credentials (company_registration,
reddit_signal, and the Product Hunt half of builder_activity).

Known gap: no real API tokens are available in this test environment, so only
the missing-credential and structural (always-a-list) contracts are covered
here. The success path for each (a real OpenCorporates match, a real Reddit
OAuth call, a real Product Hunt query) needs to be verified by whoever sets
the corresponding env var - see README. Hacker News needs no auth and is
covered live/via cassette below."""
import os

import pytest

import server


def test_company_registration_missing_token_returns_setup_instructions(monkeypatch):
    monkeypatch.delenv("OPENCORPORATES_API_TOKEN", raising=False)
    result = server.company_registration("Stripe")
    assert isinstance(result, str)
    assert "opencorporates.com/api_accounts/new" in result


@pytest.mark.vcr
def test_company_registration_invalid_token_returns_clean_message(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_TOKEN", "obviously-fake-token")
    result = server.company_registration("Stripe")
    assert isinstance(result, str)
    assert "rejected" in result.lower()


def test_reddit_signal_missing_credentials_returns_setup_instructions(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    result = server.reddit_signal("AI resume builder")
    assert isinstance(result, str)
    assert "reddit.com/prefs/apps" in result


@pytest.mark.vcr
def test_builder_activity_always_returns_both_keys_as_lists(monkeypatch):
    monkeypatch.delenv("PRODUCTHUNT_TOKEN", raising=False)
    result = server.builder_activity("AI resume builder")
    assert isinstance(result["hn"], list)
    assert isinstance(result["product_hunt"], list)
    assert result["product_hunt"] == []
    assert "product_hunt_note" in result
    assert "producthunt.com" in result["product_hunt_note"]
