"""Data models for Claude Code Usage Widget."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class AuthProviderType(str, Enum):
    OAUTH_CLI = "oauth_cli"
    OAUTH_ENV = "oauth_env"
    ADMIN_API_KEY = "admin_api_key"
    MOCK = "mock"
    NONE = "none"


@dataclass
class AuthState:
    provider: AuthProviderType = AuthProviderType.NONE
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None  # Unix timestamp in milliseconds
    subscription_type: str = "unknown"  # "pro", "max", "team", "enterprise"
    rate_limit_tier: str = "default"
    admin_api_key: Optional[str] = None
    workspace_name: str = "Claude Code"
    is_valid: bool = False
    error_message: Optional[str] = None

    def is_expired(self, skew_seconds: int = 300) -> bool:
        if not self.expires_at:
            return False
        now_ms = int(datetime.now().timestamp() * 1000)
        return now_ms >= (self.expires_at - skew_seconds * 1000)


@dataclass
class TokenBreakdown:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0

    @property
    def cache_read_pct(self) -> float:
        total_in = self.input_tokens + self.cache_read_tokens
        if total_in <= 0:
            return 0.0
        return round((self.cache_read_tokens / total_in) * 100, 1)


def format_friendly_reset(resets_at: Optional[datetime], utilization_pct: float) -> str:
    """Formats resets_at into human-readable local time (e.g. 'Domani alle 21:00 (tra 24h 31m)')."""
    if utilization_pct <= 0.0:
        return "Nessun limite attivo"

    if not resets_at:
        return "--"

    try:
        local_dt = resets_at.astimezone()
        now_local = datetime.now().astimezone()
        diff = local_dt - now_local
        total_seconds = int(diff.total_seconds())

        if total_seconds <= 0:
            if utilization_pct >= 90.0:
                return "Reset in corso..."
            return "Nessun limite attivo"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        days = hours // 24

        if days > 0:
            rem_str = f"{days}g {hours % 24}h"
        elif hours > 0:
            rem_str = f"{hours}h {minutes}m"
        else:
            rem_str = f"{minutes}m"

        local_date = local_dt.date()
        today = now_local.date()
        time_str = local_dt.strftime("%H:%M")

        if local_date == today:
            day_label = "Oggi"
        elif local_date == today + timedelta(days=1):
            day_label = "Domani"
        else:
            weekdays = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
            day_label = f"{weekdays[local_dt.weekday()]} {local_dt.day}"

        return f"{day_label} alle {time_str} (tra {rem_str})"
    except Exception:
        return "--"


@dataclass
class UsageWindow:
    utilization_pct: float = 0.0
    resets_at: Optional[datetime] = None
    time_remaining_str: str = "--"
    friendly_reset_str: str = "Nessun limite attivo"

    @classmethod
    def from_api(cls, data: Optional[dict]) -> UsageWindow:
        if not data:
            return cls()
        util = float(data.get("utilization", 0.0))
        resets_at_str = data.get("resets_at")
        resets_at = None
        rem_str = "--"

        if resets_at_str:
            try:
                clean_str = resets_at_str.replace("Z", "+00:00")
                resets_at = datetime.fromisoformat(clean_str)
                now_utc = datetime.now(resets_at.tzinfo)
                diff = resets_at - now_utc
                total_seconds = int(diff.total_seconds())
                if total_seconds > 0:
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    days = hours // 24
                    if days > 0:
                        rem_str = f"{days}g {hours % 24}h"
                    elif hours > 0:
                        rem_str = f"{hours}h {minutes}m"
                    else:
                        rem_str = f"{minutes}m"
                else:
                    rem_str = "Adesso"
            except Exception:
                rem_str = "--"
        elif util <= 0.0:
            rem_str = "Libero"

        friendly = format_friendly_reset(resets_at, util)

        return cls(
            utilization_pct=util,
            resets_at=resets_at,
            time_remaining_str=rem_str,
            friendly_reset_str=friendly,
        )


@dataclass
class UsageSnapshot:
    five_hour: UsageWindow = field(default_factory=UsageWindow)
    seven_day: UsageWindow = field(default_factory=UsageWindow)
    seven_day_sonnet: Optional[UsageWindow] = None
    seven_day_opus: Optional[UsageWindow] = None
    tokens: TokenBreakdown = field(default_factory=TokenBreakdown)
    workspace_name: str = "Claude Code"
    status_label: str = "Inizializzazione..."
    is_rate_limited: bool = False
    is_offline: bool = False
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def is_blocked(self) -> bool:
        return self.five_hour.utilization_pct >= 100.0 or self.seven_day.utilization_pct >= 100.0

    @property
    def is_weekly_bottleneck(self) -> bool:
        return self.seven_day.utilization_pct >= self.five_hour.utilization_pct and self.seven_day.utilization_pct > 0

    @property
    def primary_utilization(self) -> float:
        return max(self.five_hour.utilization_pct, self.seven_day.utilization_pct)

    @property
    def primary_reset_str(self) -> str:
        if self.is_weekly_bottleneck:
            return self.seven_day.time_remaining_str
        return self.five_hour.time_remaining_str

    @property
    def primary_friendly_reset_str(self) -> str:
        if self.is_weekly_bottleneck:
            return self.seven_day.friendly_reset_str
        return self.five_hour.friendly_reset_str

    @property
    def bottleneck_label(self) -> str:
        if self.is_weekly_bottleneck:
            return "Settimanale (7 Giorni)"
        return "Sessione (5 Ore)"


@dataclass
class AppConfig:
    thresholds: list[int] = field(default_factory=lambda: [80, 95, 100])
    notifications_enabled: bool = True
    poll_interval_active_sec: int = 90
    poll_interval_idle_sec: int = 900
    autostart_enabled: bool = False
    mock_mode: bool = False
    admin_api_key: Optional[str] = None

