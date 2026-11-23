"""Smoke test for MicroFlyoutWindow initialization to prevent missing imports or UI build errors."""

from PyQt6.QtWidgets import QApplication
from claude_usage.config import AppConfig
from claude_usage.ui.flyout import MicroFlyoutWindow


def test_flyout_window_initialization():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    flyout = MicroFlyoutWindow(config=config)
    assert flyout is not None
    assert flyout.chk_autostart is not None
    assert "Esegui all'avvio" in flyout.chk_autostart.text() or "Launch at system startup" in flyout.chk_autostart.text()
    assert flyout.burn_rate_box is not None
    assert flyout.spin_spike_pct.value() == int(round(config.burn_rate_spike_pct))
    assert flyout.spin_spike_window.value() == config.burn_rate_window_minutes
    assert flyout.spin_token_limit.value() == config.heavy_turn_token_limit // 1000
    flyout.close()
