"""Configuration loading for the LinkedIn post agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class EmailConfig:
    enabled: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: list[str] = field(default_factory=list)


@dataclass
class VoiceConfig:
    """Voice / style anchors for the writer."""

    persona: str = (
        "An educated, pragmatic AI practitioner. First-person but not self-promotional. "
        "Conversational, not hypey. Values concrete examples over abstractions."
    )
    sample_posts: list[str] = field(default_factory=list)
    avoid_phrases: list[str] = field(
        default_factory=lambda: [
            "game-changer",
            "game changer",
            "revolutionize",
            "in today's fast-paced world",
            "thoughts? 👇",
            "let's dive in",
            "i'm thrilled to share",
            "i'm excited to share",
        ]
    )


@dataclass
class FormattingConfig:
    bullet_marker: str = "🔹"  # bullets-as-emoji only
    max_chars: int = 1800
    min_chars: int = 900
    max_trends: int = 3
    hashtags_min: int = 4
    hashtags_max: int = 6
    evergreen_hashtags: list[str] = field(default_factory=lambda: ["AI", "MachineLearning"])


@dataclass
class LinkedInConfig:
    access_token: str = ""
    member_urn: str = ""  # e.g. "urn:li:person:xxxxx"
    client_id: str = ""
    client_secret: str = ""
    api_version: str = "202405"


@dataclass
class GitHubConfig:
    repo_owner: str = ""
    repo_name: str = ""
    token: str = ""
    issue_label: str = "linkedin-draft"


@dataclass
class ApprovalConfig:
    hmac_secret: str = ""
    worker_url: str = ""  # https://<name>.<sub>.workers.dev


@dataclass
class AppConfig:
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    email: EmailConfig = field(default_factory=EmailConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    formatting: FormattingConfig = field(default_factory=FormattingConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    min_impact_score_to_post: float = 6.0
    # Per-trend quality floor. EVERY one of the 3 trends in a post must score
    # at least this, otherwise skip the day rather than padding with weak news.
    min_trend_quality_floor: float = 5.0
    extra_rss_feeds: list[str] = field(default_factory=list)


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name, default)
    return val if val is not None else default


def load_config(voice_path: str | Path | None = "voice.yaml") -> AppConfig:
    """Load configuration from environment + optional voice.yaml file."""
    voice = VoiceConfig()
    if voice_path is not None:
        p = Path(voice_path)
        if p.exists():
            with open(p) as f:
                raw = yaml.safe_load(f) or {}
            if "persona" in raw:
                voice.persona = raw["persona"]
            if "sample_posts" in raw:
                voice.sample_posts = list(raw["sample_posts"])
            if "avoid_phrases" in raw:
                voice.avoid_phrases = list(raw["avoid_phrases"])

    email = EmailConfig(
        smtp_host=_env("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(_env("SMTP_PORT", "587")),
        smtp_user=_env("SMTP_USER"),
        smtp_password=_env("SMTP_PASSWORD"),
        from_address=_env("EMAIL_FROM") or _env("SMTP_USER"),
        to_addresses=[a.strip() for a in _env("EMAIL_TO").split(",") if a.strip()],
    )

    linkedin = LinkedInConfig(
        access_token=_env("LINKEDIN_ACCESS_TOKEN"),
        member_urn=_env("LINKEDIN_MEMBER_URN"),
        client_id=_env("LINKEDIN_CLIENT_ID"),
        client_secret=_env("LINKEDIN_CLIENT_SECRET"),
        api_version=_env("LINKEDIN_API_VERSION", "202405"),
    )

    # GITHUB_REPOSITORY is "<owner>/<name>" when running inside Actions
    repo_full = _env("GITHUB_REPOSITORY")
    if repo_full and "/" in repo_full:
        repo_owner, repo_name = repo_full.split("/", 1)
    else:
        repo_owner = _env("LINKEDIN_AGENT_REPO_OWNER")
        repo_name = _env("LINKEDIN_AGENT_REPO_NAME")

    github = GitHubConfig(
        repo_owner=repo_owner,
        repo_name=repo_name,
        token=_env("GITHUB_TOKEN") or _env("GH_TOKEN"),
    )

    approval = ApprovalConfig(
        hmac_secret=_env("APPROVAL_HMAC_SECRET"),
        worker_url=_env("APPROVER_WORKER_URL").rstrip("/"),
    )

    return AppConfig(
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("LINKEDIN_AGENT_MODEL", "gpt-4o"),
        email=email,
        voice=voice,
        linkedin=linkedin,
        github=github,
        approval=approval,
        min_impact_score_to_post=float(_env("LINKEDIN_AGENT_MIN_IMPACT", "6.0")),
        min_trend_quality_floor=float(_env("LINKEDIN_AGENT_QUALITY_FLOOR", "5.0")),
    )
