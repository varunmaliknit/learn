"""One-time OAuth helper to obtain a LinkedIn access token and member URN.

Usage:
    linkedin-agent oauth

Walks you through:
  1. Visiting LinkedIn's authorize URL in your browser
  2. Pasting back the `code` query parameter from the redirect
  3. Exchanging it for an access_token
  4. Calling /v2/userinfo to get your member URN

It prints, in copy-pasteable form, the GitHub Secrets you need to set.
"""

from __future__ import annotations

import logging
import os
import sys
import urllib.parse

import requests

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

# Out-of-band redirect for CLI flow. LinkedIn requires whitelisting it in your
# Developer app's "Authorized redirect URLs" — use http://localhost:8000/callback
# (you don't actually need to run a server; LinkedIn just redirects there with
# the code in the URL, and you copy it from the address bar).
DEFAULT_REDIRECT = "http://localhost:8000/callback"
SCOPES = "openid profile email w_member_social"


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val or default


def run_oauth() -> int:
    """Interactive OAuth flow. Returns process exit code."""
    print("=" * 70)
    print("LinkedIn OAuth helper")
    print("=" * 70)
    print()

    client_id = os.getenv("LINKEDIN_CLIENT_ID") or _prompt("Client ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET") or _prompt("Client Secret")
    if not client_id or not client_secret:
        print("ERROR: client id and secret required", file=sys.stderr)
        return 1

    redirect_uri = _prompt("Redirect URI", DEFAULT_REDIRECT)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": "linkedin-agent-oauth",
    }
    authorize = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    print()
    print("Step 1. Open this URL in your browser:")
    print()
    print(f"    {authorize}")
    print()
    print("Approve the permissions. You will be redirected to a URL that looks like:")
    print(f"    {redirect_uri}?code=XYZ&state=linkedin-agent-oauth")
    print()
    print("The page itself will probably fail to load — that is fine. Copy the value")
    print("of the `code=` parameter from your browser's address bar.")
    print()

    code = _prompt("Paste the `code` value")
    if not code:
        print("ERROR: code required", file=sys.stderr)
        return 1

    print()
    print("Exchanging code for access token...")
    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if token_resp.status_code != 200:
        print(f"ERROR: token exchange failed: {token_resp.status_code} {token_resp.text}",
              file=sys.stderr)
        return 1
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")
    if not access_token:
        print(f"ERROR: no access_token in response: {token_data}", file=sys.stderr)
        return 1

    print(f"  Got access token (expires in {expires_in} seconds, ~"
          f"{(expires_in or 0) // 86400} days)")

    print()
    print("Fetching member URN via /v2/userinfo...")
    info_resp = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if info_resp.status_code != 200:
        print(f"ERROR: /v2/userinfo failed: {info_resp.status_code} {info_resp.text}",
              file=sys.stderr)
        return 1
    info = info_resp.json()
    sub = info.get("sub", "")
    if not sub:
        print(f"ERROR: no 'sub' in userinfo response: {info}", file=sys.stderr)
        return 1
    member_urn = f"urn:li:person:{sub}"
    name = info.get("name", "?")
    email = info.get("email", "?")
    print(f"  Authenticated as: {name} <{email}>")
    print(f"  Member URN: {member_urn}")

    print()
    print("=" * 70)
    print("Set the following GitHub Actions secrets in your repo:")
    print("=" * 70)
    print()
    print(f"  LINKEDIN_ACCESS_TOKEN = {access_token}")
    print(f"  LINKEDIN_MEMBER_URN   = {member_urn}")
    print(f"  LINKEDIN_CLIENT_ID    = {client_id}")
    print(f"  LINKEDIN_CLIENT_SECRET = {client_secret}")
    print()
    print("Or via the gh CLI:")
    print()
    print(f'  gh secret set LINKEDIN_ACCESS_TOKEN  --body "{access_token}"')
    print(f'  gh secret set LINKEDIN_MEMBER_URN    --body "{member_urn}"')
    print(f'  gh secret set LINKEDIN_CLIENT_ID     --body "{client_id}"')
    print(f'  gh secret set LINKEDIN_CLIENT_SECRET --body "{client_secret}"')
    print()
    print("LinkedIn access tokens last about 60 days. Re-run `linkedin-agent oauth`")
    print("when the agent emails you to say the token expired.")
    return 0
