"""Manage the approval GitHub Issue.

The issue body IS the draft post — editing the issue body edits the post.
We delimit the post text with HTML comment markers so we can extract it
deterministically when publishing.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from linkedin_agent.models import Draft

logger = logging.getLogger(__name__)


POST_START = "<!-- linkedin-post START -->"
POST_END = "<!-- linkedin-post END -->"
HASHTAGS_START = "<!-- linkedin-hashtags START -->"
HASHTAGS_END = "<!-- linkedin-hashtags END -->"


def build_issue_body(draft: Draft, approve_url: str, reject_url: str) -> str:
    """Build the markdown body for the approval issue."""
    tag_line = " ".join(f"#{h}" for h in draft.hashtags)
    sources = "\n".join(
        f"- [{t.title}]({t.url}) — impact {t.impact_score:.1f} ({t.short_source()})"
        for t in draft.trends
    )
    return f"""{POST_START}
{draft.body.strip()}
{POST_END}

{HASHTAGS_START}
{tag_line}
{HASHTAGS_END}

---

### 🔹 What to do

- **[Approve & post]({approve_url})** — one click, publishes to LinkedIn
- **Edit** — change the text above (between the START/END markers), then click
  Approve OR comment `/approve` on this issue
- **[Reject]({reject_url})** — skip today

You can also approve from inside this issue by commenting `/approve` or `/reject`.

<details><summary>Sources used</summary>

{sources}

</details>
"""


_POST_RE = re.compile(
    re.escape(POST_START) + r"\s*(?P<body>.*?)\s*" + re.escape(POST_END),
    re.DOTALL,
)
_TAGS_RE = re.compile(
    re.escape(HASHTAGS_START) + r"\s*(?P<tags>.*?)\s*" + re.escape(HASHTAGS_END),
    re.DOTALL,
)


def extract_post_from_body(issue_body: str) -> tuple[str, list[str]]:
    """Extract (post_text, hashtags) from the issue body."""
    body_match = _POST_RE.search(issue_body)
    if not body_match:
        raise ValueError("could not find linkedin-post markers in issue body")
    post_body = body_match.group("body").strip()

    hashtags: list[str] = []
    tag_match = _TAGS_RE.search(issue_body)
    if tag_match:
        for token in tag_match.group("tags").split():
            if token.startswith("#"):
                hashtags.append(token[1:])
    return post_body, hashtags


def assemble_final_post(post_body: str, hashtags: list[str]) -> str:
    """Combine extracted body + hashtags into the exact LinkedIn commentary."""
    if not hashtags:
        return post_body.strip()
    tags = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    return f"{post_body.strip()}\n\n{tags}"


class GitHubIssueClient:
    BASE = "https://api.github.com"

    def __init__(self, token: str, owner: str, repo: str) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        self.token = token
        self.owner = owner
        self.repo = repo

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
        timeout: int = 20,
    ) -> dict[str, Any]:
        r = requests.post(
            f"{self.BASE}/repos/{self.owner}/{self.repo}/issues",
            headers=self._headers(),
            json={"title": title, "body": body, "labels": labels or []},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_issue(self, number: int, timeout: int = 20) -> dict[str, Any]:
        r = requests.get(
            f"{self.BASE}/repos/{self.owner}/{self.repo}/issues/{number}",
            headers=self._headers(),
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    def comment_on_issue(self, number: int, body: str, timeout: int = 20) -> dict[str, Any]:
        r = requests.post(
            f"{self.BASE}/repos/{self.owner}/{self.repo}/issues/{number}/comments",
            headers=self._headers(),
            json={"body": body},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    def close_issue(
        self,
        number: int,
        reason: str = "completed",
        timeout: int = 20,
    ) -> dict[str, Any]:
        r = requests.patch(
            f"{self.BASE}/repos/{self.owner}/{self.repo}/issues/{number}",
            headers=self._headers(),
            json={"state": "closed", "state_reason": reason},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    def add_label(self, number: int, label: str, timeout: int = 20) -> dict[str, Any]:
        r = requests.post(
            f"{self.BASE}/repos/{self.owner}/{self.repo}/issues/{number}/labels",
            headers=self._headers(),
            json={"labels": [label]},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    def find_open_draft_issue(
        self,
        draft_id: str,
        label: str = "linkedin-draft",
        timeout: int = 20,
    ) -> dict[str, Any] | None:
        """Find an open issue whose title contains the draft_id."""
        r = requests.get(
            f"{self.BASE}/repos/{self.owner}/{self.repo}/issues",
            headers=self._headers(),
            params={"state": "open", "labels": label, "per_page": 50},
            timeout=timeout,
        )
        r.raise_for_status()
        for issue in r.json():
            if draft_id in (issue.get("title") or ""):
                return issue
        return None
