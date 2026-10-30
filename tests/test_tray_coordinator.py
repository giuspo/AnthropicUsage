"""Tests for TrayController / TrayCoordinator multi-icon functionality."""

import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication

from claude_usage.core.models import (
    AntigravityUsageSnapshot,
    AppConfig,
    CompositeUsageSnapshot,
    PartnerModelQuota,
    UsageSnapshot,
    UsageWindow,
)
from claude_usage.ui.tray import TrayController, truncate_tooltip


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_truncate_tooltip():
    res = truncate_tooltip("Claude Code", "5h: 30% (2h) | 7g: 50% (3d)")
    assert "[Claude Code]" in res
    assert len(res) <= 127

    very_long_title = "A" * 150
    res_trunc = truncate_tooltip(very_long_title, "short text")
    assert len(res_trunc) <= 127


def test_tray_coordinator_multi_icon(qapp):
    config = AppConfig(
        enable_claude=True,
        enable_antigravity=True,
        antigravity_tray_mode="split_partner_icon",
    )

    fake_flyout = MagicMock()
    fake_flyout.config = config

    tray = TrayController(fake_flyout)

    composite = CompositeUsageSnapshot(
        claude=UsageSnapshot(
            five_hour=UsageWindow(utilization_pct=30.0, time_remaining_str="3h"),
            seven_day=UsageWindow(utilization_pct=45.0, time_remaining_str="2d"),
            workspace_name="TestWorkspace",
        ),
        antigravity=AntigravityUsageSnapshot(
            gemini_5h=UsageWindow(utilization_pct=15.0, time_remaining_str="4h"),
            gemini_7d=UsageWindow(utilization_pct=10.0, time_remaining_str="5d"),
            partner_5h=UsageWindow(utilization_pct=60.0, time_remaining_str="1h"),
            partner_7d=UsageWindow(utilization_pct=50.0, time_remaining_str="3d"),
            partner_models=[
                PartnerModelQuota(
                    model_id="claude-sonnet-5-5",
                    display_name="Claude Sonnet 5.5",
                    five_hour=UsageWindow(utilization_pct=60.0, time_remaining_str="1h"),
                )
            ],
        ),
    )

    tray.update_snapshot(composite)

    # In split_partner_icon mode, secondary tray icons are populated
    assert "TestWorkspace" in tray.toolTip()
    assert "Gemini" in tray.tray_antigravity.toolTip()
    assert "Partner" in tray.tray_partner.toolTip()

