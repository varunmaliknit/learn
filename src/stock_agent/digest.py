"""Daily digest builder — gathers all data and formats the email."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from stock_agent.ai.summarizer import summarize_news
from stock_agent.config import AppConfig
from stock_agent.models import (
    Alert,
    DividendInfo,
    EarningsEvent,
    NewsSummary,
    PriceData,
    Sentiment,
)
from stock_agent.monitors.dividends import fetch_dividend_info
from stock_agent.monitors.earnings import fetch_upcoming_earnings
from stock_agent.monitors.news import fetch_all_news
from stock_agent.monitors.price import check_price_alerts, fetch_price_data

logger = logging.getLogger(__name__)


def _sentiment_emoji(s: Sentiment) -> str:
    return {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(s.value, "⚪")


def _sentiment_label(s: Sentiment) -> str:
    return {"bullish": "Bullish", "bearish": "Bearish", "neutral": "Neutral"}.get(s.value, "Neutral")


def _sentiment_bg(s: Sentiment) -> str:
    return {"bullish": "#dcfce7", "bearish": "#fee2e2", "neutral": "#f3f4f6"}.get(s.value, "#f3f4f6")


def _sentiment_border(s: Sentiment) -> str:
    return {"bullish": "#22c55e", "bearish": "#ef4444", "neutral": "#d1d5db"}.get(s.value, "#d1d5db")


def _change_color(pct: float) -> str:
    if pct > 0:
        return "#22c55e"
    if pct < 0:
        return "#ef4444"
    return "#6b7280"


def _format_number(n: float | None) -> str:
    if n is None:
        return "N/A"
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{n:,.0f}"


def gather_digest(config: AppConfig) -> dict:
    prices: list[PriceData] = []
    alerts: list[Alert] = []
    news_summaries: list[NewsSummary] = []
    earnings: list[EarningsEvent] = []
    dividends: list[DividendInfo] = []

    for stock in config.stocks:
        logger.info("Processing %s (%s)...", stock.name or stock.symbol, stock.symbol)

        price = fetch_price_data(stock)
        if price:
            prices.append(price)
            stock_alerts = check_price_alerts(stock, price)
            alerts.extend(stock_alerts)

        articles = fetch_all_news(stock)
        summary = summarize_news(
            symbol=stock.symbol,
            name=stock.name or stock.symbol,
            articles=articles,
            api_key=config.openai_api_key,
        )
        news_summaries.append(summary)

        earning = fetch_upcoming_earnings(stock)
        if earning:
            earnings.append(earning)

        div = fetch_dividend_info(stock)
        if div:
            dividends.append(div)

    return {
        "prices": prices,
        "alerts": alerts,
        "news_summaries": news_summaries,
        "earnings": earnings,
        "dividends": dividends,
        "generated_at": datetime.now(timezone.utc),
    }


def build_html_digest(data: dict, config: AppConfig) -> str:
    generated_at: datetime = data["generated_at"]
    prices: list[PriceData] = data["prices"]
    alerts: list[Alert] = data["alerts"]
    news_summaries: list[NewsSummary] = data["news_summaries"]
    earnings: list[EarningsEvent] = data["earnings"]
    dividends: list[DividendInfo] = data["dividends"]

    date_str = generated_at.strftime("%A, %B %d, %Y")

    # --- Action Items (stocks flagged by AI as needing attention) ---
    action_items = [ns for ns in news_summaries if "⚡ ACTION:" in ns.ai_summary]
    action_html = ""
    if action_items:
        items_html = ""
        for ns in action_items:
            action_line = ns.ai_summary.split("\n")[0].replace("⚡ ACTION: ", "")
            bg = _sentiment_bg(ns.sentiment)
            border = _sentiment_border(ns.sentiment)
            items_html += f"""
            <div style="border-left:4px solid {border};padding:10px 14px;margin-bottom:8px;background:{bg};border-radius:0 6px 6px 0;">
              <strong style="color:#1f2937;">{ns.name} ({ns.symbol})</strong>
              <span style="margin-left:8px;font-size:12px;padding:2px 8px;border-radius:10px;background:{border};color:#fff;">{_sentiment_label(ns.sentiment)}</span>
              <p style="margin:6px 0 0 0;color:#374151;font-size:14px;">{action_line}</p>
            </div>"""
        action_html = f"""
        <div style="margin-bottom:28px;">
          <h2 style="color:#dc2626;font-size:18px;margin-bottom:12px;">🔔 Needs Your Attention</h2>
          {items_html}
        </div>"""

    # --- Price table rows ---
    price_rows = ""
    for p in prices:
        color = _change_color(p.change_pct)
        arrow = "▲" if p.change_pct > 0 else "▼" if p.change_pct < 0 else "–"
        price_rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-weight:600;">{p.name}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;">{p.symbol}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{p.currency} {p.current_price:.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:{color};font-weight:600;">
            {arrow} {abs(p.change_pct):.2f}%
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{_format_number(p.volume)}</td>
        </tr>"""

    # --- Alerts section ---
    alerts_html = ""
    if alerts:
        alert_items = ""
        for a in alerts:
            border_color = {"critical": "#ef4444", "warning": "#f59e0b"}.get(a.severity, "#3b82f6")
            alert_items += f"""
            <div style="border-left:4px solid {border_color};padding:10px 14px;margin-bottom:8px;background:#f9fafb;border-radius:0 6px 6px 0;">
              <strong>{a.headline}</strong><br>
              <span style="color:#6b7280;font-size:13px;">{a.details}</span>
            </div>"""
        alerts_html = f"""
        <div style="margin-bottom:28px;">
          <h2 style="color:#1f2937;font-size:18px;margin-bottom:12px;">⚠️ Price & Volume Alerts</h2>
          {alert_items}
        </div>"""

    # --- News summaries (redesigned) ---
    news_html = ""
    for ns in news_summaries:
        if not ns.articles and not ns.ai_summary:
            continue
        emoji = _sentiment_emoji(ns.sentiment)
        bg = _sentiment_bg(ns.sentiment)
        border = _sentiment_border(ns.sentiment)

        summary_text = ns.ai_summary
        summary_parts = summary_text.split("\n\n", 1)
        action_banner = ""
        main_summary = summary_text
        if len(summary_parts) == 2 and summary_parts[0].startswith("⚡"):
            action_banner = f"""<div style="background:#fef3c7;padding:6px 10px;border-radius:4px;margin-bottom:8px;font-size:13px;color:#92400e;font-weight:600;">{summary_parts[0]}</div>"""
            main_summary = summary_parts[1]

        key_points_html = ""
        if ns.key_points:
            pts = ""
            for kp in ns.key_points:
                tag_color = "#6b7280"
                if kp.startswith("[EARNINGS]"):
                    tag_color = "#7c3aed"
                elif kp.startswith("[ANALYST]"):
                    tag_color = "#2563eb"
                elif kp.startswith("[CORPORATE]"):
                    tag_color = "#0891b2"
                elif kp.startswith("[MARKET]"):
                    tag_color = "#059669"
                elif kp.startswith("[RISK]"):
                    tag_color = "#dc2626"
                elif kp.startswith("[DIVIDEND]"):
                    tag_color = "#ca8a04"
                pts += f"<li style='margin-bottom:4px;color:#374151;'><span style='color:{tag_color};font-weight:600;'>{kp.split(']')[0]}]</span>{kp.split(']', 1)[1] if ']' in kp else kp}</li>"
            key_points_html = f"<ul style='margin:8px 0 0 0;padding-left:20px;font-size:13px;'>{pts}</ul>"

        source_links = ""
        if ns.articles:
            links = "".join(
                f"<a href='{a.url}' style='color:#2563eb;text-decoration:none;font-size:12px;margin-right:12px;'>{a.source}</a>"
                for a in ns.articles[:3]
            )
            source_links = f"<div style='margin-top:8px;padding-top:6px;border-top:1px solid #e5e7eb;'><span style='color:#9ca3af;font-size:11px;'>Sources: </span>{links}</div>"

        news_html += f"""
        <div style="margin-bottom:16px;padding:14px;background:{bg};border-radius:8px;border:1px solid {border};">
          <div style="display:flex;align-items:center;margin-bottom:8px;">
            <span style="font-size:16px;margin-right:6px;">{emoji}</span>
            <strong style="font-size:15px;color:#1f2937;">{ns.name} ({ns.symbol})</strong>
            <span style="margin-left:8px;font-size:11px;padding:2px 8px;border-radius:10px;background:{border};color:#fff;">{_sentiment_label(ns.sentiment)}</span>
          </div>
          {action_banner}
          <p style="margin:0 0 4px 0;color:#374151;font-size:14px;line-height:1.5;">{main_summary}</p>
          {key_points_html}
          {source_links}
        </div>"""

    # --- Earnings ---
    earnings_html = ""
    if earnings:
        earn_items = ""
        for e in earnings:
            date_fmt = e.date.strftime("%b %d, %Y")
            eps_str = f"EPS Est: {e.eps_estimate:.2f}" if e.eps_estimate else ""
            rev_str = f"Rev Est: {_format_number(e.revenue_estimate)}" if e.revenue_estimate else ""
            extra = " | ".join(filter(None, [eps_str, rev_str]))
            earn_items += f"""
            <tr>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;">{e.name} ({e.symbol})</td>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;">{date_fmt}</td>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;">{extra}</td>
            </tr>"""
        earnings_html = f"""
        <div style="margin-bottom:28px;">
          <h2 style="color:#1f2937;font-size:18px;margin-bottom:12px;">📅 Upcoming Earnings</h2>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#f3f4f6;">
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Stock</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Date</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Estimates</th>
            </tr>
            {earn_items}
          </table>
        </div>"""

    # --- Dividends ---
    dividends_html = ""
    if dividends:
        div_items = ""
        for d in dividends:
            ex_str = d.ex_date.strftime("%b %d, %Y") if d.ex_date else "N/A"
            yield_str = f"{d.dividend_yield:.2f}%" if d.dividend_yield else "N/A"
            rate_str = f"{d.dividend_rate:.2f}" if d.dividend_rate else "N/A"
            div_items += f"""
            <tr>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;">{d.name} ({d.symbol})</td>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;">{yield_str}</td>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;">{rate_str}</td>
              <td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;">{ex_str}</td>
            </tr>"""
        dividends_html = f"""
        <div style="margin-bottom:28px;">
          <h2 style="color:#1f2937;font-size:18px;margin-bottom:12px;">💰 Dividend Info</h2>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#f3f4f6;">
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Stock</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Yield</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Rate</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Ex-Date</th>
            </tr>
            {div_items}
          </table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:680px;margin:20px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px 28px;color:#ffffff;">
      <h1 style="margin:0;font-size:22px;">📊 Daily Portfolio Digest</h1>
      <p style="margin:6px 0 0 0;opacity:0.85;font-size:14px;">{date_str}</p>
    </div>

    <div style="padding:24px 28px;">

      {action_html}

      <!-- Portfolio Overview -->
      <div style="margin-bottom:28px;">
        <h2 style="color:#1f2937;font-size:18px;margin-bottom:12px;">Portfolio Overview</h2>
        <table style="width:100%;border-collapse:collapse;">
          <tr style="background:#f3f4f6;">
            <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Name</th>
            <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Symbol</th>
            <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Price</th>
            <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Change</th>
            <th style="padding:8px 12px;text-align:left;font-size:13px;color:#6b7280;">Volume</th>
          </tr>
          {price_rows}
        </table>
      </div>

      {alerts_html}

      <!-- News Summaries -->
      <div style="margin-bottom:28px;">
        <h2 style="color:#1f2937;font-size:18px;margin-bottom:12px;">📰 AI News Analysis</h2>
        {news_html}
      </div>

      {earnings_html}
      {dividends_html}

    </div>

    <!-- Footer -->
    <div style="padding:16px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center;color:#9ca3af;font-size:12px;">
      Generated by Stock Portfolio Agent | {generated_at.strftime("%H:%M UTC")}
    </div>

  </div>
</body>
</html>"""

    return html


def build_text_digest(data: dict, config: AppConfig) -> str:
    generated_at: datetime = data["generated_at"]
    prices: list[PriceData] = data["prices"]
    alerts: list[Alert] = data["alerts"]
    news_summaries: list[NewsSummary] = data["news_summaries"]
    earnings: list[EarningsEvent] = data["earnings"]
    dividends: list[DividendInfo] = data["dividends"]

    lines: list[str] = []
    lines.append(f"DAILY PORTFOLIO DIGEST — {generated_at.strftime('%A, %B %d, %Y')}")
    lines.append("=" * 60)

    # Action items first
    action_items = [ns for ns in news_summaries if "⚡ ACTION:" in ns.ai_summary]
    if action_items:
        lines.append("\n🔔 NEEDS YOUR ATTENTION")
        lines.append("-" * 40)
        for ns in action_items:
            action_line = ns.ai_summary.split("\n")[0]
            lines.append(f"  {ns.name} ({ns.symbol}) — {action_line}")

    lines.append("\nPORTFOLIO OVERVIEW")
    lines.append("-" * 40)
    for p in prices:
        arrow = "▲" if p.change_pct > 0 else "▼" if p.change_pct < 0 else "–"
        lines.append(
            f"  {p.name} ({p.symbol}): {p.currency} {p.current_price:.2f} "
            f"{arrow} {abs(p.change_pct):.2f}%  Vol: {_format_number(p.volume)}"
        )

    if alerts:
        lines.append("\n⚠️  PRICE & VOLUME ALERTS")
        lines.append("-" * 40)
        for a in alerts:
            lines.append(f"  [{a.severity.upper()}] {a.headline}")
            lines.append(f"    {a.details}")

    lines.append("\n📰 AI NEWS ANALYSIS")
    lines.append("-" * 40)
    for ns in news_summaries:
        if not ns.articles and not ns.ai_summary:
            continue
        lines.append(f"\n  {_sentiment_emoji(ns.sentiment)} {ns.name} ({ns.symbol}) — {ns.sentiment.value.title()}")
        lines.append(f"  {ns.ai_summary}")
        if ns.key_points:
            for kp in ns.key_points:
                lines.append(f"    • {kp}")

    if earnings:
        lines.append("\n📅 UPCOMING EARNINGS")
        lines.append("-" * 40)
        for e in earnings:
            lines.append(f"  {e.name} ({e.symbol}): {e.date.strftime('%b %d, %Y')}")

    if dividends:
        lines.append("\n💰 DIVIDEND INFO")
        lines.append("-" * 40)
        for d in dividends:
            yield_str = f"{d.dividend_yield:.2f}%" if d.dividend_yield else "N/A"
            lines.append(f"  {d.name} ({d.symbol}): Yield {yield_str}")

    lines.append(f"\nGenerated at {generated_at.strftime('%H:%M UTC')}")
    return "\n".join(lines)
