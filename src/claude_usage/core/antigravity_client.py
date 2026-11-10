"""Async HTTP Client for Google Antigravity and Cloud Code Quota APIs."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from claude_usage.core.models import (
    AntigravityUsageSnapshot,
    AuthProviderType,
    AuthState,
    PartnerModelQuota,
    UsageWindow,
)

logger = logging.getLogger(__name__)

PRIMARY_BASE_URL = "https://cloudcode-pa.googleapis.com"
FALLBACK_BASE_URL = "https://daily-cloudcode-pa.googleapis.com"


class AntigravityApiClient:
    """Queries official Google Antigravity quota endpoints and extracts Gemini + Partner model pools."""

    def __init__(self, auth_manager: Optional[object] = None, timeout_sec: float = 8.0):
        self.auth_manager = auth_manager
        self.timeout = timeout_sec
        self.last_status_code: Optional[int] = None
        self.retry_after_until: Optional[datetime] = None
        self.last_successful_snapshot: Optional[AntigravityUsageSnapshot] = None

    def _discover_local_hub(self) -> Optional[tuple[int, str]]:
        """Discovers active local Antigravity LanguageServer daemon port and CSRF token.

        Reads ~/.gemini/antigravity/daemon/hub_*.json (or Windows equivalent).
        Verifies that process is alive, returns (http_port, csrf_token).
        """
        try:
            daemon_dir = Path.home() / ".gemini" / "antigravity" / "daemon"
            if not daemon_dir.exists():
                return None
            hub_files = sorted(
                daemon_dir.glob("hub_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for hf in hub_files:
                try:
                    with open(hf, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    port = cfg.get("httpPort")
                    csrf = cfg.get("csrfToken")
                    pid = cfg.get("pid")
                    if port and csrf:
                        if pid and sys.platform.startswith("linux"):
                            if not os.path.exists(f"/proc/{pid}"):
                                continue
                        return int(port), str(csrf)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Local hub discovery exception: {e}")
        return None

    async def fetch_usage(
        self, auth: AuthState, mock: bool = False, retry_on_401: bool = True, force: bool = False
    ) -> AntigravityUsageSnapshot:
        """Fetches quota utilization snapshot for Google AI Pro."""
        if mock or auth.provider == AuthProviderType.MOCK:
            return self._generate_mock_snapshot()

        now = datetime.now(timezone.utc)
        if force:
            self.retry_after_until = None

        if self.retry_after_until and now < self.retry_after_until:
            wait_rem = int((self.retry_after_until - now).total_seconds())
            if self.last_successful_snapshot:
                import copy
                cached = copy.deepcopy(self.last_successful_snapshot)
                cached.is_rate_limited = True
                cached.status_label = f"Cooldown Google API ({wait_rem}s)"
                return cached
            return AntigravityUsageSnapshot(
                is_rate_limited=True,
                status_label=f"Cooldown Google API ({wait_rem}s)",
            )

        # 0. Query local Antigravity daemon hub first (authoritative real-time metrics, zero cloud latency)
        hub_info = self._discover_local_hub()
        if hub_info:
            port, csrf = hub_info
            try:
                async with httpx.AsyncClient(timeout=2.5) as local_client:
                    r_summary = await local_client.post(
                        f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary",
                        json={"request": {}, "force_refresh": True},
                        headers={"X-Codeium-Csrf-Token": csrf, "Content-Type": "application/json"},
                    )
                    if r_summary.status_code == 200:
                        r_models = await local_client.post(
                            f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetAvailableModels",
                            json={},
                            headers={"X-Codeium-Csrf-Token": csrf, "Content-Type": "application/json"},
                        )
                        q_summary = r_summary.json().get("response", r_summary.json())
                        q_models = (
                            r_models.json().get("response", r_models.json())
                            if r_models.status_code == 200
                            else None
                        )
                        logger.info(f"Loaded live Antigravity quota from local LanguageServer (port {port})")
                        return self._parse_responses(auth, q_summary, q_models, None)
            except Exception as e:
                logger.debug(f"Local daemon hub query failed, falling back to remote API: {e}")

        if not auth.is_valid or not auth.access_token:
            return AntigravityUsageSnapshot(
                is_offline=True,
                status_label=auth.error_message or "Disconnesso da Google Antigravity",
            )

        headers = {
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/1.5.2 (aidev_client; os_type=linux; arch=amd64; cl=1015175089)",
            "X-Client-Version": "1.5.2",
            "X-Goog-Api-Client": "antigravity/1.5.2",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 1. Query retrieveUserQuotaSummary
                quota_summary = await self._post_endpoint(
                    client, "v1internal:retrieveUserQuotaSummary", headers
                )

                # 2. Query retrieveUserQuota for real-time model fraction
                user_quota = await self._post_endpoint(
                    client, "v1internal:retrieveUserQuota", headers
                )

                # 3. Query fetchAvailableModels for granular model quota
                models_data = await self._post_endpoint(
                    client, "v1internal:fetchAvailableModels", headers
                )

                # Check if token expired on Google Cloud Code
                if (
                    self.last_status_code in (401, 403)
                    and retry_on_401
                    and self.auth_manager
                    and hasattr(self.auth_manager, "refresh_if_expired")
                ):
                    logger.info("Google Antigravity returned 401/403. Attempting auto-refresh...")
                    fresh_auth = await self.auth_manager.refresh_if_expired()
                    if fresh_auth and fresh_auth.is_valid and fresh_auth.access_token != auth.access_token:
                        logger.info("Antigravity token auto-refreshed, retrying quota call...")
                        return await self.fetch_usage(fresh_auth, mock=mock, retry_on_401=False)

                return self._parse_responses(auth, quota_summary, models_data, user_quota)

        except Exception as e:
            logger.debug(f"AntigravityApiClient request error: {e}")
            return AntigravityUsageSnapshot(
                is_offline=True,
                status_label="Offline / Errore Rete Google",
            )

    async def _post_endpoint(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        headers: dict,
        payload: Optional[dict] = None,
    ) -> Optional[dict]:
        body = payload if payload is not None else {"project": "aicode-consumers"}
        for base in [PRIMARY_BASE_URL, FALLBACK_BASE_URL]:
            try:
                resp = await client.post(f"{base}/{endpoint}", headers=headers, json=body)
                self.last_status_code = resp.status_code
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    retry_header = resp.headers.get("retry-after")
                    delay = int(retry_header) if retry_header and retry_header.isdigit() else 120
                    self.retry_after_until = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    return None
            except Exception:
                continue
        return None

    def _parse_responses(
        self,
        auth: AuthState,
        quota_summary: Optional[dict],
        models_data: Optional[dict],
        user_quota: Optional[dict] = None,
    ) -> AntigravityUsageSnapshot:
        if not quota_summary and not models_data and not user_quota:
            return AntigravityUsageSnapshot(
                is_offline=True,
                status_label="Offline / Errore Quota Google",
                last_updated=datetime.now(),
            )

        snap = AntigravityUsageSnapshot(
            plan_name="Google AI Pro",
            status_label="🟢 Connesso via Google AI Pro",
            last_updated=datetime.now(),
        )

        # Unwrap Connect RPC 'response' wrapper if present
        if quota_summary and "response" in quota_summary:
            quota_summary = quota_summary["response"]
        if models_data and "response" in models_data:
            models_data = models_data["response"]

        # 1. Parse Groups from retrieveUserQuotaSummary
        if quota_summary and "groups" in quota_summary:
            for grp in quota_summary.get("groups", []):
                g_name = (grp.get("displayName") or "").lower()
                buckets = grp.get("buckets", [])
                for b in buckets:
                    w = b.get("window", "")
                    rem_frac = float(b.get("remainingFraction", 1.0))
                    util_pct = round((1.0 - max(0.0, min(1.0, rem_frac))) * 100.0, 1)
                    reset_str = b.get("resetTime")

                    win = self._build_usage_window(util_pct, reset_str)

                    # Distinguish Gemini 4 Argon, Partner (Claude/GPT 3p), and Gemini Models
                    bid = (b.get("bucketId") or "").lower()
                    if "argon" in bid or "argon" in g_name:
                        snap.gemini_argon_7d = win
                    elif "3p" in bid or "partner" in bid or "claude" in g_name:
                        if w == "5h":
                            snap.partner_5h = win
                        elif w == "weekly":
                            snap.partner_7d = win
                    else:
                        if w == "5h":
                            snap.gemini_5h = win
                        elif w == "weekly":
                            snap.gemini_7d = win

        # 2. Parse granular model quotas from fetchAvailableModels and retrieveUserQuota
        gemini_utils_5h = []
        gemini_resets = []

        if user_quota and "buckets" in user_quota:
            for b in user_quota.get("buckets", []):
                mid = (b.get("modelId") or "").lower()
                rem_frac = b.get("remainingFraction")
                rst = b.get("resetTime")
                if rem_frac is not None and "gemini" in mid and "argon" not in mid:
                    util_pct = round((1.0 - max(0.0, min(1.0, float(rem_frac)))) * 100.0, 1)
                    gemini_utils_5h.append(util_pct)
                    if rst:
                        gemini_resets.append(rst)

        if models_data and "models" in models_data:
            models_dict = models_data.get("models", {})
            partner_models_map: dict[str, PartnerModelQuota] = {}

            for mid, mdata in models_dict.items():
                if mid.startswith("chat_") or mid.startswith("tab_"):
                    continue
                dname = mdata.get("displayName") or mid
                provider = str(mdata.get("modelProvider") or "")
                qinfo = mdata.get("quotaInfo") or {}

                rem_frac = qinfo.get("remainingFraction")
                if rem_frac is None:
                    continue

                rem_val = float(rem_frac)
                util_pct = round((1.0 - max(0.0, min(1.0, rem_val))) * 100.0, 1)
                reset_time_str = qinfo.get("resetTime")

                if provider == "MODEL_PROVIDER_GOOGLE" or "gemini" in mid.lower():
                    if "argon" in mid.lower():
                        # Argon Medium/Low uses the dedicated Argon weekly limit
                        if "high" not in mid.lower():
                            argon_win = self._build_usage_window(util_pct, reset_time_str)
                            if snap.gemini_argon_7d is None or util_pct > snap.gemini_argon_7d.utilization_pct:
                                snap.gemini_argon_7d = argon_win
                    else:
                        gemini_utils_5h.append(util_pct)
                        if reset_time_str:
                            gemini_resets.append(reset_time_str)
                else:
                    # Partner models (Anthropic, OpenAI)
                    # Group variants by base name (e.g. Claude Sonnet 5.5)
                    clean_dname = (
                        str(dname)
                        .replace(" (Low)", "")
                        .replace(" (Medium)", "")
                        .replace(" (High)", "")
                    )
                    clean_id = mid.split("-")[0] + "-" + mid.split("-")[1] if "-" in mid else mid

                    if clean_dname not in partner_models_map:
                        partner_models_map[clean_dname] = PartnerModelQuota(
                            model_id=clean_id,
                            display_name=clean_dname,
                            five_hour=self._build_usage_window(util_pct, reset_time_str),
                            seven_day=snap.partner_7d,  # Share group weekly limit
                        )
                    else:
                        # Keep maximum utilization if variant exists
                        existing = partner_models_map[clean_dname]
                        if util_pct > existing.five_hour.utilization_pct:
                            existing.five_hour = self._build_usage_window(util_pct, reset_time_str)

            # Assign sorted partner models list
            snap.partner_models = sorted(
                partner_models_map.values(), key=lambda p: p.primary_utilization, reverse=True
            )

        # If gemini_5h was not populated by quota summary, populate from models or user_quota
        if snap.gemini_5h.utilization_pct == 0.0 and gemini_utils_5h:
            max_gem = max(gemini_utils_5h)
            rst = gemini_resets[0] if gemini_resets else None
            snap.gemini_5h = self._build_usage_window(max_gem, rst)

            # If partner_5h was not populated by summary, synthesize from partner models
            if snap.partner_5h.utilization_pct == 0.0 and snap.partner_models:
                max_prt = max(p.five_hour.utilization_pct for p in snap.partner_models)
                prt_rst = snap.partner_models[0].five_hour.resets_at
                snap.partner_5h = UsageWindow(
                    utilization_pct=max_prt,
                    resets_at=prt_rst,
                    time_remaining_str=snap.partner_models[0].five_hour.time_remaining_str,
                    friendly_reset_str=snap.partner_models[0].five_hour.friendly_reset_str,
                )

        # Weekly default fallback (scaled proportionally to 5h consumption) only if not returned by API
        if snap.gemini_7d.utilization_pct == 0.0 and snap.gemini_7d.resets_at is None:
            weekly_pct = round(snap.gemini_5h.utilization_pct * 0.35, 1) if snap.gemini_5h.utilization_pct > 0.0 else 0.0
            rst_7d = datetime.now(timezone.utc) + timedelta(days=6, hours=1)
            snap.gemini_7d = UsageWindow(
                utilization_pct=weekly_pct,
                resets_at=rst_7d,
                time_remaining_str="6g 1h",
                friendly_reset_str=f"Reset settimanale tra 6 giorni ({100.0 - weekly_pct:.0f}% rimanente)",
            )

        # Populate structured Gemini models list (including Gemini 4 Argon and Gemini 3.8 Flash)
        gem_models: list[PartnerModelQuota] = []
        if snap.gemini_argon_7d is not None:
            gem_models.append(
                PartnerModelQuota(
                    model_id="gemini-4-argon",
                    display_name="Gemini 4 Argon",
                    five_hour=snap.gemini_argon_7d,
                    seven_day=snap.gemini_argon_7d,
                )
            )
        gem_models.append(
            PartnerModelQuota(
                model_id="gemini-3.8-flash",
                display_name="Gemini 3.8 Flash",
                five_hour=snap.gemini_5h,
                seven_day=snap.gemini_7d,
            )
        )
        gem_models.append(
            PartnerModelQuota(
                model_id="gemini-3.5-flash-lite",
                display_name="Gemini 3.5 Lite",
                five_hour=snap.gemini_5h,
                seven_day=snap.gemini_7d,
            )
        )
        snap.gemini_models = gem_models
        self.last_successful_snapshot = snap
        return snap

    def _build_usage_window(self, util_pct: float, reset_time_str: Optional[str]) -> UsageWindow:
        resets_at = None
        rem_str = "--"

        if reset_time_str:
            try:
                clean_str = reset_time_str.replace("Z", "+00:00")
                resets_at = datetime.fromisoformat(clean_str)
                now_utc = datetime.now(timezone.utc)
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
        elif util_pct <= 0.0:
            rem_str = "Libero"

        from claude_usage.core.models import format_friendly_reset

        friendly = format_friendly_reset(resets_at, util_pct)
        return UsageWindow(
            utilization_pct=util_pct,
            resets_at=resets_at,
            time_remaining_str=rem_str,
            friendly_reset_str=friendly,
        )

    def _generate_mock_snapshot(self) -> AntigravityUsageSnapshot:
        """Simulates realistic Google AI Pro data for testing."""
        now = datetime.now(timezone.utc)
        rst_5h = now + timedelta(hours=2, minutes=45)
        rst_7d = now + timedelta(days=4, hours=8)

        gem_5h = UsageWindow(
            utilization_pct=38.5,
            resets_at=rst_5h,
            time_remaining_str="2h 45m",
            friendly_reset_str="Oggi alle 22:30 (tra 2h 45m)",
        )
        gem_7d = UsageWindow(
            utilization_pct=27.0,
            resets_at=rst_7d,
            time_remaining_str="3g 3h",
            friendly_reset_str="Lunedì alle 21:00 (tra 3g 3h)",
        )
        gem_argon_7d = UsageWindow(
            utilization_pct=65.0,
            resets_at=rst_7d,
            time_remaining_str="4g 4h",
            friendly_reset_str="Martedì alle 22:00 (tra 4g 4h)",
        )

        prt_5h = UsageWindow(
            utilization_pct=54.0,
            resets_at=rst_5h,
            time_remaining_str="2h 45m",
            friendly_reset_str="Oggi alle 22:30 (tra 2h 45m)",
        )
        prt_7d = UsageWindow(
            utilization_pct=46.5,
            resets_at=rst_7d,
            time_remaining_str="4g 8h",
            friendly_reset_str="Martedì alle 14:00 (tra 4g 8h)",
        )

        gem_models = [
            PartnerModelQuota(
                model_id="gemini-4-argon",
                display_name="Gemini 4 Argon",
                five_hour=gem_argon_7d,
                seven_day=gem_argon_7d,
            ),
            PartnerModelQuota(
                model_id="gemini-3.8-flash",
                display_name="Gemini 3.8 Flash",
                five_hour=gem_5h,
                seven_day=gem_7d,
            ),
            PartnerModelQuota(
                model_id="gemini-3.5-flash-lite",
                display_name="Gemini 3.5 Lite",
                five_hour=gem_5h,
                seven_day=gem_7d,
            ),
        ]

        models = [
            PartnerModelQuota(
                model_id="claude-sonnet-5-5",
                display_name="Claude Sonnet 5.5",
                five_hour=UsageWindow(utilization_pct=54.0, time_remaining_str="2h 45m"),
                seven_day=prt_7d,
            ),
            PartnerModelQuota(
                model_id="claude-opus-5-5",
                display_name="Claude Opus 5.5",
                five_hour=UsageWindow(utilization_pct=24.0, time_remaining_str="2h 45m"),
                seven_day=prt_7d,
            ),
            PartnerModelQuota(
                model_id="gpt-oss-120b",
                display_name="GPT-OSS 120B",
                five_hour=UsageWindow(utilization_pct=12.0, time_remaining_str="2h 45m"),
                seven_day=prt_7d,
            ),
        ]

        return AntigravityUsageSnapshot(
            gemini_5h=gem_5h,
            gemini_7d=gem_7d,
            gemini_argon_7d=gem_argon_7d,
            gemini_models=gem_models,
            partner_5h=prt_5h,
            partner_7d=prt_7d,
            partner_models=models,
            ai_credits_balance=250,
            use_g1_credits=True,
            plan_name="Google AI Pro (Simulazione)",
            status_label="🧪 Modalità Simulazione (Google AI Pro)",
            last_updated=datetime.now(),
        )

