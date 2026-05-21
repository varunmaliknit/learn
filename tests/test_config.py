"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stock_agent.config import load_config


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_file = tmp_path / "portfolio.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file


def test_load_config_basic(tmp_path: Path) -> None:
    data = {
        "stocks": [
            {"symbol": "AAPL", "name": "Apple", "alert_thresholds": {"price_change_pct": 3.0}},
            {"symbol": "MSFT"},
        ],
        "defaults": {"price_change_pct": 2.0, "volume_spike": 1.5},
    }
    config_file = _write_config(tmp_path, data)
    config = load_config(config_file)

    assert len(config.stocks) == 2
    assert config.stocks[0].symbol == "AAPL"
    assert config.stocks[0].name == "Apple"
    assert config.stocks[0].price_change_pct == 3.0
    assert config.stocks[1].symbol == "MSFT"
    assert config.stocks[1].price_change_pct == 2.0  # from defaults


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path.yaml")


def test_load_config_scheduler_defaults(tmp_path: Path) -> None:
    data = {"stocks": [{"symbol": "AAPL"}]}
    config_file = _write_config(tmp_path, data)
    config = load_config(config_file)

    assert config.scheduler.daily_digest_hour == 8
    assert config.scheduler.daily_digest_minute == 0
    assert config.scheduler.timezone == "Europe/London"


def test_load_config_custom_scheduler(tmp_path: Path) -> None:
    data = {
        "stocks": [{"symbol": "AAPL"}],
        "scheduler": {
            "daily_digest_hour": 9,
            "daily_digest_minute": 30,
            "timezone": "US/Eastern",
        },
    }
    config_file = _write_config(tmp_path, data)
    config = load_config(config_file)

    assert config.scheduler.daily_digest_hour == 9
    assert config.scheduler.daily_digest_minute == 30
    assert config.scheduler.timezone == "US/Eastern"
