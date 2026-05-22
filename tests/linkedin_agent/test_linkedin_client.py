"""Tests for the LinkedIn API client (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from linkedin_agent.linkedin_client import LinkedInClient, LinkedInError


def test_constructor_requires_token() -> None:
    with pytest.raises(ValueError, match="access_token"):
        LinkedInClient(access_token="", member_urn="urn:li:person:x")


def test_constructor_requires_member_urn() -> None:
    with pytest.raises(ValueError, match="member_urn is required"):
        LinkedInClient(access_token="t", member_urn="")


def test_constructor_validates_urn_shape() -> None:
    with pytest.raises(ValueError, match="urn:li:person"):
        LinkedInClient(access_token="t", member_urn="not-a-urn")


def test_fetch_userinfo_401_raises_linkedin_error() -> None:
    client = LinkedInClient(access_token="t", member_urn="urn:li:person:abc")
    mock_resp = MagicMock(status_code=401)
    with patch("linkedin_agent.linkedin_client.requests.get", return_value=mock_resp):
        with pytest.raises(LinkedInError, match="401"):
            client.fetch_userinfo()


def test_fetch_userinfo_success_returns_json() -> None:
    client = LinkedInClient(access_token="t", member_urn="urn:li:person:abc")
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"sub": "abc", "name": "Test User"}
    mock_resp.raise_for_status = MagicMock()
    with patch("linkedin_agent.linkedin_client.requests.get", return_value=mock_resp):
        info = client.fetch_userinfo()
    assert info["sub"] == "abc"


def test_create_post_empty_commentary_rejected() -> None:
    client = LinkedInClient(access_token="t", member_urn="urn:li:person:abc")
    with pytest.raises(ValueError):
        client.create_post("   \n  ")


def test_create_post_sends_expected_payload() -> None:
    client = LinkedInClient(access_token="tok", member_urn="urn:li:person:abc")
    mock_resp = MagicMock(status_code=201)
    mock_resp.headers = {"x-restli-id": "urn:li:share:9999"}
    mock_resp.json.return_value = {}
    with patch(
        "linkedin_agent.linkedin_client.requests.post", return_value=mock_resp
    ) as mock_post:
        urn = client.create_post("Hello world post.")

    assert urn == "urn:li:share:9999"
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/rest/posts")
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok"
    assert headers["LinkedIn-Version"] == "202405"
    assert headers["X-Restli-Protocol-Version"] == "2.0.0"
    payload = kwargs["json"]
    assert payload["author"] == "urn:li:person:abc"
    assert payload["commentary"] == "Hello world post."
    assert payload["lifecycleState"] == "PUBLISHED"
    assert payload["visibility"] == "PUBLIC"


def test_create_post_4xx_raises() -> None:
    client = LinkedInClient(access_token="tok", member_urn="urn:li:person:abc")
    mock_resp = MagicMock(status_code=403, text="forbidden")
    with patch("linkedin_agent.linkedin_client.requests.post", return_value=mock_resp):
        with pytest.raises(LinkedInError, match="403"):
            client.create_post("Hello.")


def test_post_url_from_urn() -> None:
    url = LinkedInClient.post_url_from_urn("urn:li:share:9999")
    assert url == "https://www.linkedin.com/feed/update/urn:li:share:9999/"
    assert LinkedInClient.post_url_from_urn("") == ""
