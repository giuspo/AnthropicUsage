"""Configuration manager for Claude Code Usage Widget."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import keyring

from claude_usage.core.models import AppConfig

APP_NAME = "ClaudeUsageWidget"
KEYRING_SERVICE = "com.anthropic-usage.widget"
KEYRING_ADMIN_KEY_ACCOUNT = "admin_api_key"


def get_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        cfg_dir = Path(base) / APP_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        cfg_dir = Path(base) / "claude-usage-widget"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def get_config_file_path() -> Path:
    return get_config_dir() / "config.json"


def load_config() -> AppConfig:
    config_file = get_config_file_path()
    cfg = AppConfig()

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg.thresholds = data.get("thresholds", [80, 95, 100])
            cfg.notifications_enabled = data.get("notifications_enabled", True)
            cfg.burn_rate_alert_enabled = data.get("burn_rate_alert_enabled", True)
            cfg.burn_rate_spike_pct = float(data.get("burn_rate_spike_pct", 15.0))
            cfg.burn_rate_window_minutes = int(data.get("burn_rate_window_minutes", 10))
            cfg.heavy_turn_token_limit = int(data.get("heavy_turn_token_limit", 35000))
            cfg.poll_interval_active_sec = data.get("poll_interval_active_sec", 90)
            cfg.poll_interval_idle_sec = data.get("poll_interval_idle_sec", 900)
            cfg.autostart_enabled = data.get("autostart_enabled", False)
            cfg.tray_icon_style = data.get("tray_icon_style", "concentric")
            cfg.mock_mode = data.get("mock_mode", False)
        except Exception:
            pass

    # Read Admin API key from secure Keyring
    try:
        admin_key = keyring.get_password(KEYRING_SERVICE, KEYRING_ADMIN_KEY_ACCOUNT)
        if admin_key:
            cfg.admin_api_key = admin_key
    except Exception:
        pass

    return cfg


def save_config(cfg: AppConfig) -> None:
    config_file = get_config_file_path()
    data = {
        "thresholds": cfg.thresholds,
        "notifications_enabled": cfg.notifications_enabled,
        "burn_rate_alert_enabled": cfg.burn_rate_alert_enabled,
        "burn_rate_spike_pct": cfg.burn_rate_spike_pct,
        "burn_rate_window_minutes": cfg.burn_rate_window_minutes,
        "heavy_turn_token_limit": cfg.heavy_turn_token_limit,
        "poll_interval_active_sec": cfg.poll_interval_active_sec,
        "poll_interval_idle_sec": cfg.poll_interval_idle_sec,
        "autostart_enabled": cfg.autostart_enabled,
        "tray_icon_style": cfg.tray_icon_style,
        "mock_mode": cfg.mock_mode,
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Store Admin API key securely
    if cfg.admin_api_key:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_ADMIN_KEY_ACCOUNT, cfg.admin_api_key)
        except Exception:
            pass
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_ADMIN_KEY_ACCOUNT)
        except Exception:
            pass

