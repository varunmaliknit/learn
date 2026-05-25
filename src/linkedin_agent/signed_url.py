"""HMAC-signed URL helpers for one-click approve/reject buttons.

The Cloudflare Worker verifies these signatures before dispatching an event
to GitHub Actions. The shared secret is `APPROVAL_HMAC_SECRET`, set both in
GitHub Actions and in the Worker's environment.

URL shape: <worker>/a?d=<draft_id>&s=<sig>   (approve)
           <worker>/r?d=<draft_id>&s=<sig>   (reject)

Signature is the lowercase hex HMAC-SHA256 of "<action>|<draft_id>".
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from urllib.parse import quote


def _digest(secret: str, action: str, draft_id: str) -> str:
    msg = f"{action}|{draft_id}".encode()
    return hmac.new(secret.encode(), msg, sha256).hexdigest()


def sign(secret: str, action: str, draft_id: str) -> str:
    """Return the hex signature for the (action, draft_id) tuple."""
    if action not in {"approve", "reject"}:
        raise ValueError(f"invalid action: {action}")
    return _digest(secret, action, draft_id)


def verify(secret: str, action: str, draft_id: str, signature: str) -> bool:
    """Constant-time check that `signature` is valid for (action, draft_id)."""
    expected = _digest(secret, action, draft_id)
    return hmac.compare_digest(expected, signature)


def build_url(worker_base: str, action: str, draft_id: str, secret: str) -> str:
    """Build the full clickable URL for the given action."""
    path = {"approve": "a", "reject": "r"}[action]
    sig = sign(secret, action, draft_id)
    return f"{worker_base.rstrip('/')}/{path}?d={quote(draft_id)}&s={sig}"
