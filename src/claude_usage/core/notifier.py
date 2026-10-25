"""Native cross-platform desktop notifications with threshold hysteresis."""

from __future__ import annotations

import logging
from typing import Optional, Set

from desktop_notifier import DesktopNotifier, Icon, Urgency

from claude_usage.ui.icon_renderer import IconRenderer

logger = logging.getLogger(__name__)

APP_NAME = "Claude Code Usage"


class AlertEngine:
    """Delivers native push notifications for configurable usage thresholds (e.g. 80%, 95%, 100%)."""

    def __init__(self, app_name: str = APP_NAME):
        self.app_name = app_name
        self._notifier: Optional[DesktopNotifier] = None
        self._notified_thresholds: Set[int] = set()
        self._active_window_id: Optional[str] = None

    def _ensure_notifier(self) -> DesktopNotifier:
        if self._notifier is None:
            icon_path = IconRenderer.get_app_icon_path()
            app_icon = Icon(path=icon_path) if icon_path.exists() else None
            self._notifier = DesktopNotifier(app_name=self.app_name, app_icon=app_icon)
        return self._notifier

    async def evaluate_and_notify(
        self,
        utilization_pct: float,
        window_id: Optional[str],
        workspace_name: str,
        time_remaining_str: str,
        thresholds: list[int],
        enabled: bool = True,
    ) -> Optional[int]:
        """Evaluates whether to trigger a notification based on thresholds and hysteresis."""
        if not enabled:
            return None

        # Reset notified thresholds if window changed (new 5-hour cycle)
        if window_id and window_id != self._active_window_id:
            self._active_window_id = window_id
            self._notified_thresholds.clear()

        # Check sorted thresholds
        for threshold in sorted(thresholds):
            if utilization_pct >= threshold and threshold not in self._notified_thresholds:
                self._notified_thresholds.add(threshold)
                await self._send_notification(threshold, utilization_pct, workspace_name, time_remaining_str)
                return threshold

        return None

    async def _send_notification(
        self,
        threshold: int,
        current_pct: float,
        workspace_name: str,
        time_remaining_str: str,
    ) -> None:
        """Sends native OS Toast or DBus alert."""
        notifier = self._ensure_notifier()

        if threshold >= 95:
            urgency = Urgency.Critical
            icon_emoji = "🚨"
            title = f"{icon_emoji} Claude Code: Quota Critica ({int(current_pct)}%)"
        elif threshold >= 80:
            urgency = Urgency.Normal
            icon_emoji = "⚠️"
            title = f"{icon_emoji} Claude Code: Soglia Raggiunta ({int(current_pct)}%)"
        else:
            urgency = Urgency.Low
            title = f"ℹ️ Claude Code: Utilizzo al {int(current_pct)}%"

        message = f"[{workspace_name}] Hai raggiunto il {int(current_pct)}% del limite.\nReset previsto tra {time_remaining_str}."

        icon_path = IconRenderer.get_app_icon_path()
        toast_icon = Icon(path=icon_path) if icon_path.exists() else None

        try:
            await notifier.send(
                title=title,
                message=message,
                urgency=urgency,
                icon=toast_icon,
            )
            logger.info(f"Sent native alert for threshold {threshold}%")
        except Exception as e:
            logger.warning(f"Could not dispatch desktop notification: {e}")

