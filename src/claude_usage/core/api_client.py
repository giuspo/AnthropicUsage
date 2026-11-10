"""Async HTTP Client for Anthropic OAuth and Admin Usage APIs."""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from claude_usage.core.models import AuthProviderType, AuthState, UsageSnapshot, UsageWindow

logger = logging.getLogger(__name__)

OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
ADMIN_USAGE_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"


class ApiClient:
    """Queries official and OAuth quota endpoints with rate-limit and backoff handling."""

    def __init__(self, auth_manager: Optional[object] = None, timeout_sec: float = 8.0):
        self.auth_manager = auth_manager
        self.timeout = timeout_sec
        self.last_status_code: Optional[int] = None
        self.retry_after_until: Optional[datetime] = None
        self.last_429_time: Optional[datetime] = None
        self.last_successful_snapshot: Optional[UsageSnapshot] = None
        self.last_request_time: Optional[datetime] = None
        self.min_interval_sec: float = 240.0  # Safe 4-minute minimum between automatic API calls

    async def fetch_usage(
        self, auth: AuthState, mock: bool = False, force: bool = False
    ) -> UsageSnapshot:
        """Fetches quota utilization snapshot based on auth credentials."""
        if mock or auth.provider == AuthProviderType.MOCK:
            return self._generate_mock_snapshot()

        now = datetime.now(timezone.utc)

        # If user forces manual refresh, only clear cooldown if at least 60s have passed since last 429
        # (prevents rapid manual clicks during a 429 from triggering Cloudflare anti-abuse bans)
        if force:
            if not self.last_429_time or (now - self.last_429_time).total_seconds() >= 60.0:
                self.retry_after_until = None

        # Check if currently rate-limited by Retry-After
        if self.retry_after_until and now < self.retry_after_until:
            wait_rem = int((self.retry_after_until - now).total_seconds())
            logger.info(f"In cooldown rate-limit, waiting {wait_rem}s")
            if self.last_successful_snapshot:
                cached = copy.deepcopy(self.last_successful_snapshot)
                cached.is_rate_limited = True
                cached.status_label = f"Cooldown API ({wait_rem}s)"
                return cached
            snap = UsageSnapshot()
            snap.is_rate_limited = True
            snap.status_label = f"Cooldown API ({wait_rem}s)"
            return snap

        # Throttle frequent polling to protect Anthropic OAuth endpoint
        if (
            not force
            and self.last_request_time
            and (now - self.last_request_time).total_seconds() < self.min_interval_sec
            and self.last_successful_snapshot is not None
        ):
            logger.debug("Returning throttled cached snapshot to prevent 429")
            return copy.deepcopy(self.last_successful_snapshot)

        if not auth.is_valid:
            snap = UsageSnapshot()
            snap.status_label = auth.error_message or "Disconnesso"
            snap.is_offline = True
            return snap

        if auth.provider in (AuthProviderType.OAUTH_CLI, AuthProviderType.OAUTH_ENV):
            return await self._fetch_oauth_usage(auth)
        elif auth.provider == AuthProviderType.ADMIN_API_KEY:
            return await self._fetch_admin_usage(auth)

        return UsageSnapshot(status_label="Provider sconosciuto", is_offline=True)

    async def _get_oauth_usage(self, headers: dict) -> tuple[int, dict, Optional[str]]:
        """Internal helper to execute GET request against Anthropic OAuth usage API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(OAUTH_USAGE_URL, headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = {}
            retry_header = resp.headers.get("retry-after")
            return resp.status_code, data, retry_header

    async def _fetch_oauth_usage(self, auth: AuthState, retry_on_401: bool = True) -> UsageSnapshot:
        headers = {
            "Authorization": f"Bearer {auth.access_token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
            "User-Agent": "claude-code/1.0",
        }

        try:
            status_code, data, retry_header = await self._get_oauth_usage(headers)
            self.last_status_code = status_code

            if status_code == 200:
                five_h = UsageWindow.from_api(data.get("five_hour"))
                seven_d = UsageWindow.from_api(data.get("seven_day"))
                sonnet = (
                    UsageWindow.from_api(data.get("seven_day_sonnet"))
                    if data.get("seven_day_sonnet")
                    else None
                )
                opus = (
                    UsageWindow.from_api(data.get("seven_day_opus"))
                    if data.get("seven_day_opus")
                    else None
                )

                snap = UsageSnapshot(
                    five_hour=five_h,
                    seven_day=seven_d,
                    seven_day_sonnet=sonnet,
                    seven_day_opus=opus,
                    workspace_name=auth.workspace_name,
                    status_label=f"🟢 Connesso via OAuth ({auth.subscription_type.capitalize()})",
                )
                self.last_successful_snapshot = snap
                self.last_request_time = datetime.now(timezone.utc)
                return snap

            elif status_code == 429:
                delay = int(retry_header) if retry_header and retry_header.isdigit() else 300
                # Respect Anthropic's Retry-After (between 3 min and 30 min) to avoid anti-abuse penalties
                delay = min(max(delay, 180), 1800)
                now_utc = datetime.now(timezone.utc)
                self.last_429_time = now_utc
                self.retry_after_until = now_utc + timedelta(seconds=delay)
                logger.warning(f"HTTP 429 on OAuth usage API. Cooldown for {delay}s")
                if self.last_successful_snapshot:
                    cached = copy.deepcopy(self.last_successful_snapshot)
                    cached.is_rate_limited = True
                    cached.status_label = f"Cooldown API ({delay}s)"
                    return cached
                return UsageSnapshot(
                    is_rate_limited=True,
                    status_label=f"Cooldown API ({delay}s)",
                    workspace_name=auth.workspace_name,
                )
            elif status_code == 401:
                logger.info("HTTP 401 on OAuth usage API (token expired).")
                if retry_on_401 and self.auth_manager and hasattr(self.auth_manager, "refresh_token"):
                    logger.info("Attempting automatic silent OAuth token refresh for Claude Code...")
                    refreshed = await self.auth_manager.refresh_token(force=True)
                    if refreshed:
                        fresh_auth = self.auth_manager.get_credentials()
                        logger.info("Auto-refresh succeeded! Retrying quota request with new token...")
                        return await self._fetch_oauth_usage(fresh_auth, retry_on_401=False)

                if self.last_successful_snapshot:
                    cached = copy.deepcopy(self.last_successful_snapshot)
                    cached.is_offline = True
                    cached.status_label = "🔴 Token Scaduto / Riconnetti"
                    return cached
                return UsageSnapshot(
                    is_offline=True,
                    status_label="🔴 Token Scaduto / Riconnetti",
                    workspace_name=auth.workspace_name,
                )
            else:
                if self.last_successful_snapshot:
                    cached = copy.deepcopy(self.last_successful_snapshot)
                    cached.is_offline = True
                    cached.status_label = f"Errore API ({status_code})"
                    return cached
                return UsageSnapshot(
                    is_offline=True,
                    status_label=f"Errore API ({status_code})",
                    workspace_name=auth.workspace_name,
                )
        except Exception as e:
            logger.debug(f"HTTP request error: {e}")
            if self.last_successful_snapshot:
                cached = copy.deepcopy(self.last_successful_snapshot)
                cached.is_offline = True
                cached.status_label = "Offline / Errore Rete"
                return cached
            return UsageSnapshot(is_offline=True, status_label="Offline / Errore Rete")

    async def _fetch_admin_usage(self, auth: AuthState) -> UsageSnapshot:
        headers = {
            "x-api-key": auth.admin_api_key or "",
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        }
        # Fetch usage report for past 24 hours
        now_dt = datetime.now(timezone.utc)
        start_dt = now_dt - timedelta(hours=24)
        params = {
            "starting_at": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ending_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bucket_width": "1h",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(ADMIN_USAGE_URL, headers=headers, params=params)
                self.last_status_code = resp.status_code

                if resp.status_code == 200:
                    data = resp.json()
                    buckets = data.get("data", [])
                    total_in = sum(int(b.get("input_tokens", 0)) for b in buckets)
                    total_out = sum(int(b.get("output_tokens", 0)) for b in buckets)

                    # Admin API does not enforce 5h rolling window, we synthesize a daily snapshot
                    window = UsageWindow(
                        utilization_pct=min(100.0, round((total_in + total_out) / 1_000_000 * 100, 1)),
                        resets_at=now_dt + timedelta(hours=4),
                        time_remaining_str="24h Rolling",
                    )
                    return UsageSnapshot(
                        five_hour=window,
                        seven_day=window,
                        workspace_name=auth.workspace_name,
                        status_label="🟣 Enterprise Admin API",
                    )
                else:
                    return UsageSnapshot(
                        is_offline=True,
                        status_label=f"Errore Admin API ({resp.status_code})",
                    )
        except Exception as e:
            logger.debug(f"Admin API error: {e}")
            return UsageSnapshot(is_offline=True, status_label="Offline / Errore Rete")

    def _generate_mock_snapshot(self) -> UsageSnapshot:
        """Simulates realistic data for UI testing and demonstration."""
        reset_time = datetime.now(timezone.utc) + timedelta(hours=2, minutes=15)
        five_h = UsageWindow(utilization_pct=68.5, resets_at=reset_time, time_remaining_str="2h 15m")
        seven_d = UsageWindow(
            utilization_pct=42.0,
            resets_at=datetime.now(timezone.utc) + timedelta(days=4),
            time_remaining_str="4d",
        )
        sonnet = UsageWindow(utilization_pct=55.0, time_remaining_str="4d")
        return UsageSnapshot(
            five_hour=five_h,
            seven_day=seven_d,
            seven_day_sonnet=sonnet,
            workspace_name="Progetto Mock Demo",
            status_label="🧪 Modalità Simulazione (Mock)",
        )

