"""Core Usage Fusion Engine orchestrating APIs, local logs, and alerts."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from claude_usage.config import AppConfig
from claude_usage.core.api_client import ApiClient
from claude_usage.core.auth_manager import AuthManager
from claude_usage.core.jsonl_parser import JsonlParser
from claude_usage.core.models import UsageSnapshot
from claude_usage.core.notifier import AlertEngine

logger = logging.getLogger(__name__)


class UsageFusionEngine(QObject):
    """Central engine fusing live API quota data, local transcript metrics, and notifications."""

    # Qt Signals for UI updates
    snapshot_updated = pyqtSignal(object)  # UsageSnapshot

    def __init__(self, config: AppConfig, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self.auth_manager = AuthManager(admin_api_key=config.admin_api_key)
        self.api_client = ApiClient()
        self.jsonl_parser = JsonlParser()
        self.alert_engine = AlertEngine()

        self._current_snapshot = UsageSnapshot()
        self._is_running = False
        self._watcher_task: Optional[asyncio.Task] = None
        self._poller_task: Optional[asyncio.Task] = None
        self._last_fs_activity: float = 0.0
        self._history: list[tuple[float, float, int]] = []  # (timestamp, utilization_pct, total_tokens)

    @property
    def current_snapshot(self) -> UsageSnapshot:
        return self._current_snapshot

    async def start(self) -> None:
        """Starts background monitoring and scheduling."""
        self._is_running = True
        # Perform initial sync
        await self.refresh()

        # Start periodic polling task
        self._poller_task = asyncio.create_task(self._poll_loop())

        # Start file-system watcher for ~/.claude/projects/
        self._watcher_task = asyncio.create_task(self._watch_fs_loop())

    async def stop(self) -> None:
        """Stops background tasks."""
        self._is_running = False
        if self._poller_task:
            self._poller_task.cancel()
        if self._watcher_task:
            self._watcher_task.cancel()

    async def refresh(self) -> UsageSnapshot:
        """Executes a full data refresh cycle."""
        try:
            # 1. Resolve Auth
            auth = await self.auth_manager.refresh_if_expired()

            # 2. Fetch Quota from API (or Mock)
            api_snap = await self.api_client.fetch_usage(auth, mock=self.config.mock_mode)

            # 3. Parse local JSONL transcripts for detailed tokens (Input, Output, Thinking)
            tokens, project_name = self.jsonl_parser.parse_recent_window(window_hours=5)

            # 4. Fuse data
            if not api_snap.is_rate_limited:
                self._current_snapshot = api_snap
            else:
                self._current_snapshot.is_rate_limited = True
                self._current_snapshot.status_label = api_snap.status_label

            self._current_snapshot.tokens = tokens
            if project_name and project_name != "Claude Code":
                self._current_snapshot.workspace_name = project_name

            # 5. Check notification thresholds
            if self._current_snapshot.is_weekly_bottleneck and self._current_snapshot.seven_day.resets_at:
                win_id = self._current_snapshot.seven_day.resets_at.isoformat()
            elif self._current_snapshot.five_hour.resets_at:
                win_id = self._current_snapshot.five_hour.resets_at.isoformat()
            else:
                win_id = None

            await self.alert_engine.evaluate_and_notify(
                utilization_pct=self._current_snapshot.primary_utilization,
                window_id=win_id,
                workspace_name=self._current_snapshot.workspace_name,
                time_remaining_str=self._current_snapshot.primary_reset_str,
                thresholds=self.config.thresholds,
                enabled=self.config.notifications_enabled,
            )

            # 6. Evaluate Burn-Rate and Anomaly Detection
            self._evaluate_burn_rate()
            if self._current_snapshot.is_burn_rate_abnormal and self._current_snapshot.anomaly_reason:
                await self.alert_engine.notify_anomaly(
                    workspace_name=self._current_snapshot.workspace_name,
                    reason=self._current_snapshot.anomaly_reason,
                    current_pct=self._current_snapshot.primary_utilization,
                    enabled=self.config.burn_rate_alert_enabled and self.config.notifications_enabled,
                )

            # 7. Emit signal to UI
            self.snapshot_updated.emit(self._current_snapshot)
            return self._current_snapshot

        except Exception as e:
            logger.error(f"Error during usage refresh: {e}", exc_info=True)
            self._current_snapshot.status_label = "Errore Aggiornamento"
            self.snapshot_updated.emit(self._current_snapshot)
            return self._current_snapshot

    def _evaluate_burn_rate(self) -> None:
        """Calculates consumption burn rate and flags abnormal velocity or token spikes."""
        import time

        now = time.time()
        curr_util = self._current_snapshot.primary_utilization
        curr_tokens = self._current_snapshot.tokens.total_tokens

        # Record point if valid
        if not self._current_snapshot.is_offline and not self._current_snapshot.is_rate_limited:
            self._history.append((now, curr_util, curr_tokens))

        # Prune points older than window
        window_sec = max(60, int(self.config.burn_rate_window_minutes * 60))
        self._history = [h for h in self._history if (now - h[0]) <= window_sec]

        if len(self._history) < 2:
            self._current_snapshot.burn_rate_per_min = 0.0
            self._current_snapshot.is_burn_rate_abnormal = False
            self._current_snapshot.anomaly_reason = None
            return

        oldest_time, oldest_util, oldest_tokens = self._history[0]
        delta_t_min = (now - oldest_time) / 60.0

        if delta_t_min >= 0.5:
            delta_pct = curr_util - oldest_util
            rate = delta_pct / delta_t_min
            self._current_snapshot.burn_rate_per_min = max(0.0, round(rate, 2))

            # 1. Check for rapid quota surge (+15% in <10m)
            if delta_pct >= self.config.burn_rate_spike_pct:
                self._current_snapshot.is_burn_rate_abnormal = True
                self._current_snapshot.anomaly_reason = (
                    f"Salto quota anomalo: +{delta_pct:.0f}% in {delta_t_min:.1f} min (+{rate:.1f}%/min)"
                )
                return

            # 2. Check for abnormal token volume surge in short window
            delta_tokens = curr_tokens - oldest_tokens
            if delta_tokens >= self.config.heavy_turn_token_limit and delta_t_min <= 5.0:
                self._current_snapshot.is_burn_rate_abnormal = True
                self._current_snapshot.anomaly_reason = (
                    f"Picco token anomalo: +{delta_tokens:,} token in {delta_t_min:.1f} min"
                )
                return

        self._current_snapshot.is_burn_rate_abnormal = False
        self._current_snapshot.anomaly_reason = None

    async def _poll_loop(self) -> None:
        """Background adaptive polling heartbeat."""
        while self._is_running:
            # If recent filesystem activity occurred within 2 minutes, poll at active interval
            interval = self.config.poll_interval_idle_sec
            try:
                await asyncio.sleep(interval)
                if self._is_running:
                    await self.refresh()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Poller loop error: {e}")
                await asyncio.sleep(30)

    async def _watch_fs_loop(self) -> None:
        """Watches local ~/.claude/projects/ directory for real-time turn activity."""
        projects_dir = self.jsonl_parser.projects_dir
        if not projects_dir.exists():
            # Create if absent to allow watching
            try:
                projects_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                return

        try:
            from watchfiles import awatch

            async for changes in awatch(projects_dir):
                if not self._is_running:
                    break
                # Filter for .jsonl changes
                has_jsonl = any(path.endswith(".jsonl") for _, path in changes)
                if has_jsonl:
                    # Debounce: wait 15 seconds after typing before polling API
                    await asyncio.sleep(15)
                    await self.refresh()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Filesystem watcher error: {e}")

