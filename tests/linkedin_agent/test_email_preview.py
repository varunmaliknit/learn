"""Tests for the email preview renderer."""

from __future__ import annotations

from linkedin_agent.email_preview import render_html, render_text
from linkedin_agent.models import Draft, Trend


def _draft() -> Draft:
    return Draft(
        draft_id="2026-05-22",
        body=(
            "Hook.\n\nBridge.\n\n"
            "🔹 One. Why it matters: stuff.\n   → https://a.com\n"
            "🔹 Two. Why it matters: more stuff.\n   → https://b.com\n"
            "🔹 Three. Why it matters: even more.\n   → https://c.com\n\n"
            "The bigger picture: ties together.\n\n"
            "What's your take?"
        ),
        hashtags=["AI", "MachineLearning", "LLM"],
        trends=[
            Trend("First", "https://a.com/x", "Lab A", "summary 1", "matters 1", 9.0),
            Trend("Second", "https://b.com/y", "Lab B", "summary 2", "matters 2", 7.5),
            Trend("Third", "https://c.com/z", "Lab C", "summary 3", "matters 3", 6.5),
        ],
    )


def test_render_html_includes_buttons_and_preview() -> None:
    out = render_html(
        _draft(),
        approve_url="https://w.example/a?d=x&s=y",
        reject_url="https://w.example/r?d=x&s=z",
        issue_url="https://github.com/o/r/issues/42",
        issue_edit_url="https://github.com/o/r/issues/42",
    )
    assert "Approve" in out and "Reject" in out
    assert "https://w.example/a?d=x&amp;s=y" in out  # escaped in HTML
    assert "🔹 One" in out
    assert "First" in out
    assert "https://a.com/x" in out
    assert "#AI #MachineLearning #LLM" in out


def test_render_text_plain_format() -> None:
    out = render_text(
        _draft(),
        approve_url="https://w.example/a",
        reject_url="https://w.example/r",
        issue_url="https://github.com/o/r/issues/42",
    )
    assert "Approve & post: https://w.example/a" in out
    assert "Reject:         https://w.example/r" in out
    assert "Edit on GitHub: https://github.com/o/r/issues/42" in out
    assert "🔹 One" in out
    assert "First" in out  # source title


def test_render_html_escapes_unsafe_content() -> None:
    draft = _draft()
    draft.body = "<script>alert('x')</script>" + draft.body
    out = render_html(
        draft,
        approve_url="https://w.example/a",
        reject_url="https://w.example/r",
        issue_url="https://x",
        issue_edit_url="https://x",
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
