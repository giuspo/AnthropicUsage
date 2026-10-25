"""Unit tests for Burn-Rate & Anomaly Detection."""

import time
import pytest
from unittest.mock import AsyncMock, patch

from claude_usage.core.engine import UsageFusionEngine
from claude_usage.core.models import AppConfig, TokenBreakdown, UsageSnapshot, UsageWindow
from claude_usage.core.notifier import AlertEngine


def test_burn_rate_normal_velocity():
    config = AppConfig(burn_rate_spike_pct=15.0, burn_rate_window_minutes=10)
    engine = UsageFusionEngine(config)

    now = time.time()
    # 8 minutes ago: 10%
    engine._history = [(now - 480, 10.0, 5000)]
    engine._current_snapshot = UsageSnapshot(
        five_hour=UsageWindow(utilization_pct=13.0),
        tokens=TokenBreakdown(total_tokens=6000),
    )

    engine._evaluate_burn_rate()
    assert engine._current_snapshot.is_burn_rate_abnormal is False
    assert engine._current_snapshot.burn_rate_per_min < 1.0
    assert engine._current_snapshot.anomaly_reason is None


def test_burn_rate_rapid_spike_anomaly():
    config = AppConfig(burn_rate_spike_pct=15.0, burn_rate_window_minutes=10)
    engine = UsageFusionEngine(config)

    now = time.time()
    # 5 minutes ago: 20%
    engine._history = [(now - 300, 20.0, 10000)]
    # Now: 38% (+18% in 5 minutes!)
    engine._current_snapshot = UsageSnapshot(
        five_hour=UsageWindow(utilization_pct=38.0),
        tokens=TokenBreakdown(total_tokens=15000),
    )

    engine._evaluate_burn_rate()
    assert engine._current_snapshot.is_burn_rate_abnormal is True
    assert engine._current_snapshot.burn_rate_per_min >= 3.0
    assert "Salto quota anomalo" in engine._current_snapshot.anomaly_reason


def test_burn_rate_token_volume_surge():
    config = AppConfig(heavy_turn_token_limit=30000)
    engine = UsageFusionEngine(config)

    now = time.time()
    # 2 minutes ago: 5,000 tokens
    engine._history = [(now - 120, 10.0, 5000)]
    # Now: 45,000 tokens (+40,000 token spike!)
    engine._current_snapshot = UsageSnapshot(
        five_hour=UsageWindow(utilization_pct=14.0),
        tokens=TokenBreakdown(total_tokens=45000),
    )

    engine._evaluate_burn_rate()
    assert engine._current_snapshot.is_burn_rate_abnormal is True
    assert "Picco token anomalo" in engine._current_snapshot.anomaly_reason


@pytest.mark.asyncio
async def test_notifier_anomaly_cooldown():
    alert_engine = AlertEngine()
    fake_notifier = AsyncMock()
    alert_engine._notifier = fake_notifier

    # 1. First trigger -> Sends notification
    res1 = await alert_engine.notify_anomaly(
        workspace_name="TestProject",
        reason="Quota surge +20%",
        current_pct=50.0,
        cooldown_seconds=600,
        enabled=True,
    )
    assert res1 is True
    assert fake_notifier.send.call_count == 1

    # 2. Immediate second trigger -> Suppressed by cooldown
    res2 = await alert_engine.notify_anomaly(
        workspace_name="TestProject",
        reason="Quota surge +25%",
        current_pct=55.0,
        cooldown_seconds=600,
        enabled=True,
    )
    assert res2 is False
    assert fake_notifier.send.call_count == 1

