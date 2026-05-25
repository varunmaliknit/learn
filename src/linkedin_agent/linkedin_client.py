"""LinkedIn Posts API client + token health check.

Posting endpoint: POST https://api.linkedin.com/rest/posts
Required header: LinkedIn-Version: 202405 (configurable)
Scope needed: w_member_social

Tokens: we use the long-lived access token directly. Refresh tokens are not
generally available for the "Share on LinkedIn" product on personal apps, so
the agent verifies the token is still valid before each run and emails a clear
re-auth notice when it isn't.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class LinkedInError(RuntimeError):
    pass


class LinkedInClient:
    BASE = "https://api.linkedin.com"

    def __init__(self, access_token: str, member_urn: str, api_version: str = "202405") -> None:
        if not access_token:
            raise ValueError("LinkedIn access_token is required")
        if not member_urn:
            raise ValueError("LinkedIn member_urn is required (e.g. 'urn:li:person:...')")
        if not member_urn.startswith("urn:li:person:") and not member_urn.startswith(
            "urn:li:organization:"
        ):
            raise ValueError(
                f"member_urn must look like 'urn:li:person:XXX'; got: {member_urn!r}"
            )
        self.access_token = access_token
        self.member_urn = member_urn
        self.api_version = api_version

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "LinkedIn-Version": self.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def fetch_userinfo(self, timeout: int = 15) -> dict[str, Any]:
        """Call /v2/userinfo to verify the token is still valid."""
        r = requests.get(
            f"{self.BASE}/v2/userinfo",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=timeout,
        )
        if r.status_code == 401:
            raise LinkedInError("LinkedIn token expired or invalid (401 on /v2/userinfo)")
        r.raise_for_status()
        return r.json()

    def create_post(self, commentary: str, timeout: int = 30) -> str:
        """Create a text-only LinkedIn post. Returns the post URN."""
        if not commentary.strip():
            raise ValueError("commentary is empty")
        body = {
            "author": self.member_urn,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        r = requests.post(
            f"{self.BASE}/rest/posts",
            headers=self._headers(),
            json=body,
            timeout=timeout,
        )
        if r.status_code >= 400:
            raise LinkedInError(
                f"LinkedIn /rest/posts failed: {r.status_code} {r.text[:500]}"
            )
        urn = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id") or ""
        if not urn:
            # Fall back to body parsing if header isn't present.
            try:
                urn = r.json().get("id", "")
            except Exception:  # noqa: BLE001
                urn = ""
        return urn

    @staticmethod
    def post_url_from_urn(urn: str) -> str:
        """Best-effort public URL for a post URN."""
        if not urn:
            return ""
        # urn:li:share:1234567 or urn:li:ugcPost:1234567
        return f"https://www.linkedin.com/feed/update/{urn}/"
