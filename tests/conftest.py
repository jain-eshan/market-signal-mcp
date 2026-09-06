import pytest


@pytest.fixture(scope="module")
def vcr_config():
    """Scrub anything credential-shaped before a cassette is ever written -
    these fixtures get committed to a public repo."""
    return {
        "filter_headers": ["authorization", "user-agent"],
        "filter_query_parameters": ["api_token", "client_id", "client_secret"],
        "filter_post_data_parameters": ["client_id", "client_secret"],
    }
