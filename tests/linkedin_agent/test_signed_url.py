"""Tests for HMAC-signed approve/reject URLs."""

from __future__ import annotations

import pytest

from linkedin_agent.signed_url import build_url, sign, verify

SECRET = "test-secret-do-not-use-in-prod"
DRAFT_ID = "2026-05-22"


def test_sign_is_deterministic() -> None:
    a = sign(SECRET, "approve", DRAFT_ID)
    b = sign(SECRET, "approve", DRAFT_ID)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_verify_round_trip_approve() -> None:
    sig = sign(SECRET, "approve", DRAFT_ID)
    assert verify(SECRET, "approve", DRAFT_ID, sig) is True


def test_verify_round_trip_reject() -> None:
    sig = sign(SECRET, "reject", DRAFT_ID)
    assert verify(SECRET, "reject", DRAFT_ID, sig) is True


def test_action_swap_fails_verification() -> None:
    sig = sign(SECRET, "approve", DRAFT_ID)
    assert verify(SECRET, "reject", DRAFT_ID, sig) is False


def test_draft_id_swap_fails_verification() -> None:
    sig = sign(SECRET, "approve", DRAFT_ID)
    assert verify(SECRET, "approve", "2026-05-23", sig) is False


def test_secret_swap_fails_verification() -> None:
    sig = sign(SECRET, "approve", DRAFT_ID)
    assert verify("other-secret", "approve", DRAFT_ID, sig) is False


def test_invalid_action_rejected() -> None:
    with pytest.raises(ValueError):
        sign(SECRET, "delete", DRAFT_ID)


def test_build_url_format_approve() -> None:
    url = build_url("https://x.workers.dev/", "approve", DRAFT_ID, SECRET)
    assert url.startswith("https://x.workers.dev/a?d=2026-05-22&s=")
    assert "//a" not in url  # no double slash from trailing slash on base


def test_build_url_format_reject() -> None:
    url = build_url("https://x.workers.dev", "reject", DRAFT_ID, SECRET)
    assert url.startswith("https://x.workers.dev/r?d=2026-05-22&s=")


def test_build_url_signature_validates() -> None:
    """The URL emitted by build_url should be verifiable by verify()."""
    url = build_url("https://x.workers.dev", "approve", DRAFT_ID, SECRET)
    sig = url.rsplit("s=", 1)[1]
    assert verify(SECRET, "approve", DRAFT_ID, sig) is True
