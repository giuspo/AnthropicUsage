"""Tests for AlertEngine notification threshold evaluation and hysteresis."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest

from claude_usage.core.models import format_friendly_reset
from claude_usage.core.notifier import AlertEngine


def test_format_friendly_reset():
    # 0% utilization -> Nessun limite attivo
    assert format_friendly_reset(None, 0.0) == "Nessun limite attivo"

    # Reset tomorrow at 21:00
    now = datetime.now().astimezone()
    tomorrow_21 = (now + timedelta(days=1)).replace(hour=21, minute=0, second=0)
    res_str = format_friendly_reset(tomorrow_21, 100.0)
    assert "Domani alle 21:00" in res_str
    assert "tra " in res_str


@pytest.mark.asyncio
async def test_alert_engine_hysteresis():
    engine = AlertEngine()
    thresholds = [80, 95, 100]

    with patch.object(engine, "_send_notification", new_callable=AsyncMock) as mock_send:
        # 1. 60% -> No notification
        t1 = await engine.evaluate_and_notify(
            utilization_pct=60.0,
            window_id="win_01",
            workspace_name="Test",
            time_remaining_str="2h",
            thresholds=thresholds,
            enabled=True,
        )
        assert t1 is None
        assert mock_send.call_count == 0

        # 2. 82% -> Triggers 80% threshold
        t2 = await engine.evaluate_and_notify(
            utilization_pct=82.0,
            window_id="win_01",
            workspace_name="Test",
            time_remaining_str="2h",
            thresholds=thresholds,
            enabled=True,
        )
        assert t2 == 80
        assert mock_send.call_count == 1

        # 3. 85% in the same window -> Hysteresis suppresses repeated alert
        t3 = await engine.evaluate_and_notify(
            utilization_pct=85.0,
            window_id="win_01",
            workspace_name="Test",
            time_remaining_str="1h",
            thresholds=thresholds,
            enabled=True,
        )
        assert t3 is None
        assert mock_send.call_count == 1

        # 4. 96% in the same window -> Triggers 95% threshold
        t4 = await engine.evaluate_and_notify(
            utilization_pct=96.0,
            window_id="win_01",
            workspace_name="Test",
            time_remaining_str="30m",
            thresholds=thresholds,
            enabled=True,
        )
        assert t4 == 95
        assert mock_send.call_count == 2

        # 5. Window changes (new 5-hour cycle) -> Triggers again if above threshold
        t5 = await engine.evaluate_and_notify(
            utilization_pct=81.0,
            window_id="win_02",  # new window!
            workspace_name="Test",
            time_remaining_str="5h",
            thresholds=thresholds,
            enabled=True,
        )
        assert t5 == 80
        assert mock_send.call_count == 3

