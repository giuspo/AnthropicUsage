"""Async HTTP Client for Google Antigravity and Cloud Code Quota APIs."""

from __future__ import annotations

import logging
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

    def __init__(self, timeout_sec: float = 8.0):
        self.timeout = timeout_sec
        self.last_status_code: Optional[int] = None
        self.retry_after_until: Optional[datetime] = None

    async def fetch_usage(self, auth: AuthState, mock: bool = False) -> AntigravityUsageSnapshot:
        """Fetches quota utilization snapshot for Google AI Pro."""
        if mock or auth.provider == AuthProviderType.MOCK:
            return self._generate_mock_snapshot()

        now = datetime.now(timezone.utc)
        if self.retry_after_until and now < self.retry_after_until:
            wait_rem = int((self.retry_after_until - now).total_seconds())
            return AntigravityUsageSnapshot(
                is_rate_limited=True,
                status_label=f"Cooldown Google API ({wait_rem}s)",
            )

        if not auth.is_valid or not auth.access_token:
            return AntigravityUsageSnapshot(
                is_offline=True,
                status_label=auth.error_message or "Disconnesso da Google Antigravity",
            )

        headers = {
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity/1.2.13 (Windows)",
            "X-Client-Version": "1.2.13",
            "X-Goog-Api-Client": "antigravity/1.2.13",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 1. Query retrieveUserQuotaSummary
                quota_summary = await self._post_endpoint(
                    client, "v1internal:retrieveUserQuotaSummary", headers
                )

                # 2. Query fetchAvailableModels for granular model quota
                models_data = await self._post_endpoint(
                    client, "v1internal:fetchAvailableModels", headers
                )

                return self._parse_responses(auth, quota_summary, models_data)

        except Exception as e:
            logger.debug(f"AntigravityApiClient request error: {e}")
            return AntigravityUsageSnapshot(
                is_offline=True,
                status_label="Offline / Errore Rete Google",
            )

    async def _post_endpoint(
        self, client: httpx.AsyncClient, endpoint: str, headers: dict
    ) -> Optional[dict]:
        for base in [PRIMARY_BASE_URL, FALLBACK_BASE_URL]:
            try:
                resp = await client.post(f"{base}/{endpoint}", headers=headers, json={})
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
    ) -> AntigravityUsageSnapshot:
        snap = AntigravityUsageSnapshot(
            plan_name="Google AI Pro",
            status_label="🟢 Connesso via Google AI Pro",
            last_updated=datetime.now(),
        )

        # 1. Parse Groups from retrieveUserQuotaSummary
        if quota_summary and "groups" in quota_summary:
            for grp in quota_summary.get("groups", []):
                buckets = grp.get("buckets", [])
                for b in buckets:
                    w = b.get("window", "")
                    rem_frac = float(b.get("remainingFraction", 1.0))
                    util_pct = round((1.0 - max(0.0, min(1.0, rem_frac))) * 100.0, 1)
                    reset_str = b.get("resetTime")

                    win = self._build_usage_window(util_pct, reset_str)

                    # Check if bucket belongs to partner pool (3p) or gemini
                    bid = b.get("bucketId", "")
                    if "3p" in bid or "partner" in bid or "claude" in grp.get("displayName", "").lower():
                        if w == "5h":
                            snap.partner_5h = win
                        elif w == "weekly":
                            snap.partner_7d = win
                    else:
                        if w == "5h":
                            snap.gemini_5h = win
                        elif w == "weekly":
                            snap.gemini_7d = win

        # 2. Parse granular model quotas from fetchAvailableModels
        if models_data and "models" in models_data:
            models_dict = models_data.get("models", {})
            partner_models_map: dict[str, PartnerModelQuota] = {}

            gemini_utils_5h = []
            gemini_resets = []

            for mid, mdata in models_dict.items():
                dname = mdata.get("displayName", mid)
                provider = str(mdata.get("modelProvider", ""))
                qinfo = mdata.get("quotaInfo", {})

                rem_frac = qinfo.get("remainingFraction")
                if rem_frac is None:
                    continue

                rem_val = float(rem_frac)
                util_pct = round((1.0 - max(0.0, min(1.0, rem_val))) * 100.0, 1)
                reset_time_str = qinfo.get("resetTime")

                if provider == "MODEL_PROVIDER_GOOGLE":
                    gemini_utils_5h.append(util_pct)
                    if reset_time_str:
                        gemini_resets.append(reset_time_str)
                else:
                    # Partner models (Anthropic, OpenAI)
                    # Group variants by base name (e.g. Claude Sonnet 5.5)
                    clean_dname = dname.replace(" (Low)", "").replace(" (Medium)", "").replace(" (High)", "")
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

            # If gemini_5h was not populated by quota summary, populate from models
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

        # Weekly default fallback if 0
        if snap.gemini_7d.utilization_pct == 0.0:
            # Gemini typically has very generous or 5h-dominant rolling window
            snap.gemini_7d = UsageWindow(
                utilization_pct=round(snap.gemini_5h.utilization_pct * 0.6, 1),
                resets_at=datetime.now(timezone.utc) + timedelta(days=6),
                time_remaining_str="6g",
                friendly_reset_str="Nessun limite settimanale attivo",
            )

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
            utilization_pct=22.0,
            resets_at=rst_7d,
            time_remaining_str="4g 8h",
            friendly_reset_str="Martedì alle 14:00 (tra 4g 8h)",
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
            partner_5h=prt_5h,
            partner_7d=prt_7d,
            partner_models=models,
            ai_credits_balance=250,
            use_g1_credits=True,
            plan_name="Google AI Pro (Simulazione)",
            status_label="🧪 Modalità Simulazione (Google AI Pro)",
            last_updated=datetime.now(),
        )

