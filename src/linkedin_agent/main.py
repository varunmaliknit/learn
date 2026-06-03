"""LinkedIn AI-trends post agent — CLI entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from linkedin_agent import config as cfg_module
from linkedin_agent import (
    email_preview,
    formatter,
    github_issue,
    linkedin_client,
    ranker,
    search,
    signed_url,
    synthesizer,
    writer,
)
from linkedin_agent.models import Draft, Theme, Trend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("linkedin_agent")


def _today_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _check_token_health(cfg: cfg_module.AppConfig) -> None:
    """Soft check — log but don't crash if token isn't working in draft step."""
    if not cfg.linkedin.access_token or not cfg.linkedin.member_urn:
        logger.warning(
            "LinkedIn access token or member URN not set — publish will fail. "
            "Run `linkedin-agent oauth` to obtain them."
        )
        return
    try:
        client = linkedin_client.LinkedInClient(
            access_token=cfg.linkedin.access_token,
            member_urn=cfg.linkedin.member_urn,
            api_version=cfg.linkedin.api_version,
        )
        client.fetch_userinfo()
        logger.info("LinkedIn token is valid")
    except Exception as e:  # noqa: BLE001
        logger.warning("LinkedIn token health check failed: %s", e)


def _select_publishable_themes(
    themes: list[Theme],
    num_themes: int,
    min_evidence: int,
    min_strength: float,
) -> list[Theme] | None:
    """Return num_themes publishable themes or None if quality gates fail."""
    strong = [
        t for t in themes
        if t.evidence_count >= min_evidence and t.strength_score >= min_strength
    ]
    if len(strong) < num_themes:
        return None
    return strong[:num_themes]


def _themes_to_trends_union(themes: list[Theme]) -> list[Trend]:
    """Flatten theme supporting trends into a deduped ordered list for back-compat."""
    seen: set[str] = set()
    out: list[Trend] = []
    for theme in themes:
        for t in theme.supporting:
            key = t.url or t.title
            if key and key not in seen:
                seen.add(key)
                out.append(t)
    return out


def cmd_draft(cfg: cfg_module.AppConfig, args: argparse.Namespace) -> int:
    """Search, rank, synthesize, draft, open an issue, send the approval email."""
    draft_id = args.draft_id or _today_id()
    evidence_window = search._window_phrase(cfg.evidence_window_hours)
    logger.info(
        "Drafting LinkedIn post for %s (evidence window: %s, num_themes: %d)",
        draft_id, evidence_window, cfg.num_themes,
    )

    _check_token_health(cfg)

    # ── 1. Gather a wider evidence pool ───────────────────────────────────────
    raw = search.gather_candidate_pool(
        cfg.openai_api_key,
        cfg.openai_model,
        cfg.extra_rss_feeds,
        evidence_window_hours=cfg.evidence_window_hours,
        max_items=cfg.max_candidate_items,
    )

    pool = ranker.rank_candidates(
        raw["openai"],
        raw["rss"],
        top_n=cfg.max_candidate_items,
    )
    if not pool:
        logger.warning("No candidates found. Sending 'skipped' email and exiting.")
        return _send_skip_email(
            cfg, draft_id,
            reason=f"no AI developments found in the last {evidence_window}",
        )

    # ── 2. Synthesize themes ──────────────────────────────────────────────────
    synthesis_model = cfg.synthesis_model or cfg.openai_model
    themes = synthesizer.synthesize_themes(
        cfg.openai_api_key,
        synthesis_model,
        pool,
        num_themes=cfg.num_themes,
        min_evidence_per_theme=cfg.min_evidence_per_theme,
        temperature=cfg.synthesis_temperature,
    )

    # ── 3. Quality gates on themes ────────────────────────────────────────────
    publishable = _select_publishable_themes(
        themes,
        num_themes=cfg.num_themes,
        min_evidence=cfg.min_evidence_per_theme,
        min_strength=cfg.min_theme_strength,
    )
    if publishable is None:
        if not themes:
            reason = (
                f"synthesis found no coherent trend patterns in the last {evidence_window}. "
                f"The pool had {len(pool)} items but none clustered into a strong theme."
            )
        else:
            scores = ", ".join(
                f"{t.thesis[:40]!r}: strength={t.strength_score:.1f} evidence={t.evidence_count}"
                for t in themes
            )
            reason = (
                f"could not assemble {cfg.num_themes} theme(s) meeting the quality bar "
                f"(min_evidence={cfg.min_evidence_per_theme}, "
                f"min_strength={cfg.min_theme_strength:.1f}). "
                f"Best candidates: {scores}."
            )
        logger.info("Theme quality gate failed — skipping: %s", reason)
        return _send_skip_email(cfg, draft_id, reason=reason)

    # ── 4. Draft and format ───────────────────────────────────────────────────
    body, hashtags = writer.draft_post(
        cfg.openai_api_key,
        cfg.openai_model,
        publishable,
        cfg.voice,
        cfg.formatting,
        num_themes=cfg.num_themes,
        lookback_hours=cfg.lookback_hours,
    )
    body, hashtags = formatter.finalize(body, hashtags, cfg.formatting)

    trends_union = _themes_to_trends_union(publishable)
    draft = Draft(
        draft_id=draft_id,
        body=body,
        hashtags=hashtags,
        trends=trends_union,
        themes=publishable,
        generated_at=datetime.now(timezone.utc),
    )

    if args.dry_run:
        print("=" * 70)
        print(draft.full_text())
        print("=" * 70)
        print()
        print("Themes:")
        for i, th in enumerate(draft.themes, 1):
            print(f"  Theme {i}: {th.thesis}")
            print(f"    Direction: {th.direction}")
            print(f"    Strength={th.strength_score:.1f}  Novelty={th.novelty_score:.1f}  Evidence={th.evidence_count}")
            for t in th.supporting:
                print(f"      - {t.title}  ({t.impact_score:.1f})")
                print(f"        {t.url}")
        return 0

    return _create_issue_and_email(cfg, draft)


def _create_issue_and_email(cfg: cfg_module.AppConfig, draft: Draft) -> int:
    if not cfg.github.token or not cfg.github.repo_owner or not cfg.github.repo_name:
        logger.error("GitHub repo or token not configured; cannot open issue")
        return 2
    if not cfg.approval.hmac_secret or not cfg.approval.worker_url:
        logger.error(
            "Approval HMAC secret or worker URL not configured; "
            "set APPROVAL_HMAC_SECRET and APPROVER_WORKER_URL"
        )
        return 2

    approve_url = signed_url.build_url(
        cfg.approval.worker_url, "approve", draft.draft_id, cfg.approval.hmac_secret
    )
    reject_url = signed_url.build_url(
        cfg.approval.worker_url, "reject", draft.draft_id, cfg.approval.hmac_secret
    )

    issue_body = github_issue.build_issue_body(draft, approve_url, reject_url)
    gh = github_issue.GitHubIssueClient(
        cfg.github.token, cfg.github.repo_owner, cfg.github.repo_name
    )
    issue = gh.create_issue(
        title=f"LinkedIn draft — {draft.draft_id}",
        body=issue_body,
        labels=[cfg.github.issue_label, "needs-approval"],
    )
    issue_url = issue.get("html_url", "")
    issue_edit_url = issue_url  # GitHub doesn't have a direct edit URL; main page has Edit
    logger.info("Created approval issue: %s", issue_url)

    subject = f"LinkedIn draft — {draft.draft_id} (approve in one click)"
    html = email_preview.render_html(
        draft,
        approve_url=approve_url,
        reject_url=reject_url,
        issue_url=issue_url,
        issue_edit_url=issue_edit_url,
    )
    text = email_preview.render_text(draft, approve_url, reject_url, issue_url)
    ok = email_preview.send_email(cfg.email, subject, html, text)
    if not ok:
        logger.error("Email send failed; issue created but you won't be notified by email")
        return 3
    return 0


def _send_skip_email(cfg: cfg_module.AppConfig, draft_id: str, reason: str) -> int:
    subject = f"LinkedIn — skipped {draft_id}"
    text = (
        f"No LinkedIn post drafted for {draft_id}.\n\n"
        f"Reason: {reason}\n\n"
        "If you'd rather post every day no matter what, lower "
        "LINKEDIN_AGENT_MIN_IMPACT (default 6.0)."
    )
    html = f"<html><body><p>No LinkedIn post drafted for {draft_id}.</p>" \
           f"<p><b>Reason:</b> {reason}</p></body></html>"
    email_preview.send_email(cfg.email, subject, html, text)
    return 0


def cmd_publish(cfg: cfg_module.AppConfig, args: argparse.Namespace) -> int:
    """Read the draft from a GitHub Issue and post to LinkedIn."""
    if not cfg.github.token or not cfg.github.repo_owner or not cfg.github.repo_name:
        logger.error("GitHub repo or token not configured")
        return 2

    gh = github_issue.GitHubIssueClient(
        cfg.github.token, cfg.github.repo_owner, cfg.github.repo_name
    )
    if args.issue:
        issue = gh.get_issue(args.issue)
    else:
        draft_id = args.draft_id or _today_id()
        issue = gh.find_open_draft_issue(draft_id, cfg.github.issue_label)
        if issue is None:
            logger.error("No open draft issue found for draft_id=%s", draft_id)
            return 2

    issue_number = issue["number"]
    issue_body = issue.get("body") or ""
    try:
        post_body, hashtags = github_issue.extract_post_from_body(issue_body)
    except ValueError as e:
        logger.error("Could not parse post from issue body: %s", e)
        gh.comment_on_issue(
            issue_number, f":x: publish aborted: {e}. Edit the issue body and try again."
        )
        return 3

    final_text = github_issue.assemble_final_post(post_body, hashtags)
    if args.dry_run:
        print("=" * 70)
        print(final_text)
        print("=" * 70)
        return 0

    client = linkedin_client.LinkedInClient(
        access_token=cfg.linkedin.access_token,
        member_urn=cfg.linkedin.member_urn,
        api_version=cfg.linkedin.api_version,
    )
    try:
        urn = client.create_post(final_text)
    except Exception as e:  # noqa: BLE001
        logger.error("LinkedIn post failed: %s", e)
        gh.comment_on_issue(issue_number, f":x: LinkedIn post failed: {e}")
        gh.add_label(issue_number, "publish-failed")
        return 4

    post_url = linkedin_client.LinkedInClient.post_url_from_urn(urn)
    logger.info("Posted to LinkedIn: %s", post_url or urn)
    gh.comment_on_issue(
        issue_number, f":white_check_mark: Posted to LinkedIn.\n\nURN: `{urn}`\n{post_url}"
    )
    gh.add_label(issue_number, "published")
    gh.close_issue(issue_number)

    subject = f"LinkedIn — posted ({issue.get('title', '')})"
    text = f"Your LinkedIn post is live.\n\nURN: {urn}\n{post_url}"
    html = f"<html><body><p>Your LinkedIn post is live.</p>" \
           f"<p>URN: <code>{urn}</code></p>" \
           f"<p><a href=\"{post_url}\">{post_url}</a></p></body></html>"
    email_preview.send_email(cfg.email, subject, html, text)
    return 0


def cmd_reject(cfg: cfg_module.AppConfig, args: argparse.Namespace) -> int:
    if not cfg.github.token or not cfg.github.repo_owner or not cfg.github.repo_name:
        logger.error("GitHub repo or token not configured")
        return 2
    gh = github_issue.GitHubIssueClient(
        cfg.github.token, cfg.github.repo_owner, cfg.github.repo_name
    )
    if args.issue:
        issue = gh.get_issue(args.issue)
    else:
        draft_id = args.draft_id or _today_id()
        issue = gh.find_open_draft_issue(draft_id, cfg.github.issue_label)
        if issue is None:
            logger.error("No open draft issue found for draft_id=%s", draft_id)
            return 2

    issue_number = issue["number"]
    gh.add_label(issue_number, "rejected")
    gh.comment_on_issue(
        issue_number,
        ":x: Rejected — no LinkedIn post will be made for this draft.",
    )
    gh.close_issue(issue_number, reason="not_planned")

    subject = f"LinkedIn — rejected {issue.get('title', '')}"
    text = "Draft rejected. No LinkedIn post made."
    html = "<html><body><p>Draft rejected. No LinkedIn post made.</p></body></html>"
    email_preview.send_email(cfg.email, subject, html, text)
    return 0


def cmd_oauth(_: cfg_module.AppConfig, __: argparse.Namespace) -> int:
    from linkedin_agent import oauth_helper

    return oauth_helper.run_oauth()


def cmd_dump_secrets_template(_: cfg_module.AppConfig, args: argparse.Namespace) -> int:
    """Print the JSON template of secrets needed."""
    secrets = {
        "OPENAI_API_KEY": "sk-...",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "you@gmail.com",
        "SMTP_PASSWORD": "<gmail app password>",
        "EMAIL_FROM": "you@gmail.com",
        "EMAIL_TO": "you@gmail.com",
        "LINKEDIN_ACCESS_TOKEN": "<from `linkedin-agent oauth`>",
        "LINKEDIN_MEMBER_URN": "urn:li:person:...",
        "LINKEDIN_CLIENT_ID": "<from LinkedIn dev app>",
        "LINKEDIN_CLIENT_SECRET": "<from LinkedIn dev app>",
        "APPROVAL_HMAC_SECRET": "<32+ random bytes, base64 or hex>",
        "APPROVER_WORKER_URL": "https://<name>.<sub>.workers.dev",
    }
    json.dump(secrets, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="linkedin-agent")
    sub = p.add_subparsers(dest="command", required=True)

    draft = sub.add_parser(
        "draft",
        help="Generate a draft (covers cfg.lookback_hours of AI trends) and email it for approval",
    )
    draft.add_argument(
        "--draft-id",
        default=None,
        help="Override draft id (default: today UTC, format YYYY-MM-DD)",
    )
    draft.add_argument("--dry-run", action="store_true", help="Print to stdout; no issue/email")
    draft.set_defaults(func=cmd_draft)

    pub = sub.add_parser("publish", help="Publish the approved draft to LinkedIn")
    pub.add_argument("--issue", type=int, default=None, help="Issue number to publish from")
    pub.add_argument("--draft-id", default=None, help="Find issue by draft id instead")
    pub.add_argument(
        "--dry-run", action="store_true", help="Print final post; do not call LinkedIn"
    )
    pub.set_defaults(func=cmd_publish)

    rej = sub.add_parser("reject", help="Reject the draft and close the issue")
    rej.add_argument("--issue", type=int, default=None)
    rej.add_argument("--draft-id", default=None)
    rej.set_defaults(func=cmd_reject)

    oa = sub.add_parser("oauth", help="One-time OAuth flow to obtain a LinkedIn token")
    oa.set_defaults(func=cmd_oauth)

    sec = sub.add_parser("secrets-template", help="Print template of required env secrets")
    sec.set_defaults(func=cmd_dump_secrets_template)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    voice_path = os.getenv("LINKEDIN_AGENT_VOICE", "voice.yaml")
    cfg = cfg_module.load_config(voice_path=voice_path)
    return int(args.func(cfg, args) or 0)


if __name__ == "__main__":
    sys.exit(main())
