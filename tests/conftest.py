import pytest


@pytest.fixture(autouse=True)
def reset_ai_rate_limiter():
    """The AI endpoints are rate limited per IP (30/min). Tests share one 'IP', so start each test clean."""
    from app import main
    main._ip_request_timestamps.clear()
    yield
    main._ip_request_timestamps.clear()
