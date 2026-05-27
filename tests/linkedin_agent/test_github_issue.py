"""Tests for the GitHub Issue body builder / parser."""

from __future__ import annotations

import pytest

from linkedin_agent.github_issue import (
    HASHTAGS_END,
    HASHTAGS_START,
    POST_END,
    POST_START,
    assemble_final_post,
    build_issue_body,
    extract_post_from_body,
)
from linkedin_agent.models import Draft, Trend


def _sample_draft() -> Draft:
    return Draft(
        draft_id="2026-05-22",
        body="Hook.\n\nBridge.\n\n🔹 One. Why it matters: stuff.\n   → https://a.com",
        hashtags=["AI", "MachineLearning", "LLM"],
        trends=[
            Trend(
                title="Sample trend",
                url="https://a.com",
                source="Lab",
                one_line_summary="A thing happened",
                why_it_matters="because",
                impact_score=8.5,
            ),
        ],
    )


def test_build_issue_body_contains_markers() -> None:
    draft = _sample_draft()
    body = build_issue_body(draft, "https://approve.example", "https://reject.example")
    assert POST_START in body and POST_END in body
    # Hashtag markers only render when the draft actually has hashtags.
    assert HASHTAGS_START in body and HASHTAGS_END in body
    assert "https://approve.example" in body
    assert "https://reject.example" in body
    assert "🔹 What to do" in body  # bullet marker in instructions section


def test_build_issue_body_omits_hashtag_block_when_empty() -> None:
    """Default writer no longer generates hashtags; verify the issue body
    does not render an empty <!-- linkedin-hashtags --> block in that
    case (clean issue, no dangling markers)."""
    draft = _sample_draft()
    draft.hashtags = []
    body = build_issue_body(draft, "https://approve.example", "https://reject.example")
    assert POST_START in body and POST_END in body
    assert HASHTAGS_START not in body
    assert HASHTAGS_END not in body


def test_extract_post_from_body_round_trip() -> None:
    draft = _sample_draft()
    body = build_issue_body(draft, "https://a", "https://r")
    post, tags = extract_post_from_body(body)
    assert post.startswith("Hook.")
    assert "🔹 One" in post
    assert tags == ["AI", "MachineLearning", "LLM"]


def test_extract_post_handles_user_edits() -> None:
    body = f"""
Some chatter from the user above.

{POST_START}
This is the edited post body.

🔹 Bullet
{POST_END}

{HASHTAGS_START}
#AI #NewTag #MachineLearning
{HASHTAGS_END}

Trailing notes.
"""
    post, tags = extract_post_from_body(body)
    assert post.startswith("This is the edited")
    assert "🔹 Bullet" in post
    assert tags == ["AI", "NewTag", "MachineLearning"]


def test_extract_post_missing_markers_raises() -> None:
    with pytest.raises(ValueError):
        extract_post_from_body("no markers here")


def test_assemble_final_post_appends_hashtags() -> None:
    out = assemble_final_post("Body text here.", ["AI", "LLM"])
    assert out.endswith("#AI #LLM")
    assert "Body text here." in out


def test_assemble_final_post_no_hashtags() -> None:
    out = assemble_final_post("Just body.", [])
    assert out == "Just body."
