# 📊 Personal Agents

Two scheduled agents that run as GitHub Actions:

1. **Stock Portfolio Agent** — daily email digest of price moves, news, earnings, and dividends. See below.
2. **LinkedIn AI-Trends Post Agent** — drafts a weekly LinkedIn post on the last 7 days of AI trends, emails you a one-click approval, and posts it for you. See [`docs/LINKEDIN_AGENT.md`](docs/LINKEDIN_AGENT.md). (Cadence is configurable — flip to daily via `LINKEDIN_AGENT_LOOKBACK_HOURS=24`.)

---

## 📊 Stock Portfolio Notification Agent

A Python agent that monitors your stock portfolio and sends you a **daily email digest** at 8 AM UK time with price movements, news summaries (powered by OpenAI), earnings calendar, dividend info, and alerts.

## Portfolio

Pre-configured for an international portfolio:

| Stock | Symbol | Exchange | Country |
|-------|--------|----------|---------|
| ASML Holding | ASML | NASDAQ | Netherlands |
| BAE Systems | BA.L | LSE | UK |
| Cochlear | COH.AX | ASX | Australia |
| Experian | EXPN.L | LSE | UK |
| Games Workshop | GAW.L | LSE | UK |
| MercadoLibre | MELI | NASDAQ | Argentina/LatAm |
| Nike | NKE | NYSE | US |
| RELX | REL.L | LSE | UK |
| Yum China | YUMC | NYSE | China |
| Gold | GC=F | Futures | Global |
| Silver | SI=F | Futures | Global |
| Copper | HG=F | Futures | Global |

## Features

- **Price Monitoring** — tracks daily price changes and volume spikes with configurable thresholds
- **AI News Summaries** — OpenAI-powered summarisation and sentiment analysis (bullish/bearish/neutral) for each stock
- **News Aggregation** — pulls from Yahoo Finance and Google News RSS for global coverage
- **Earnings Calendar** — alerts for upcoming earnings reports
- **Dividend Tracking** — yield, rate, and ex-dividend dates
- **Beautiful HTML Emails** — responsive, styled daily digest delivered at 8 AM UK time
- **Plain Text Fallback** — text version included for all email clients

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Configure

```bash
cp portfolio.yaml.example portfolio.yaml
cp .env.example .env
```

Edit `.env` with your API keys and SMTP settings:

```env
OPENAI_API_KEY=sk-...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
```

Edit `portfolio.yaml` to customise stocks and alert thresholds.

### 3. Run

```bash
# Run the scheduler (sends digest daily at 8 AM UK time)
stock-agent

# Or send a digest immediately
stock-agent --run-once

# Or preview the digest in your terminal (no email sent)
stock-agent --dry-run
```

### Docker

```bash
docker build -t stock-agent .
docker run --env-file .env -v $(pwd)/portfolio.yaml:/app/portfolio.yaml stock-agent
```

## Configuration

### portfolio.yaml

```yaml
stocks:
  - symbol: ASML
    name: ASML Holding
    alert_thresholds:
      price_change_pct: 3.0   # alert if price moves ±3% in a day
      volume_spike: 2.0       # alert if volume is 2x average

defaults:
  price_change_pct: 2.0
  volume_spike: 1.5

scheduler:
  daily_digest_hour: 8
  daily_digest_minute: 0
  timezone: "Europe/London"
```

### Gmail App Password

If using Gmail, you'll need an [App Password](https://support.google.com/accounts/answer/185833):
1. Enable 2-Factor Authentication on your Google account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a password for "Mail"
4. Use that password as `SMTP_PASSWORD`

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## Architecture

```
src/stock_agent/
├── main.py              # CLI entry point
├── config.py            # YAML + env config loading
├── models.py            # Data classes
├── digest.py            # Digest builder (HTML + text)
├── scheduler.py         # APScheduler daily trigger
├── monitors/
│   ├── price.py         # Price & volume monitoring (yfinance)
│   ├── news.py          # News aggregation (yfinance + Google RSS)
│   ├── earnings.py      # Earnings calendar (yfinance)
│   └── dividends.py     # Dividend info (yfinance)
├── notifiers/
│   ├── base.py          # Notifier interface
│   └── email.py         # SMTP email sender
└── ai/
    └── summarizer.py    # OpenAI news summarisation
```
