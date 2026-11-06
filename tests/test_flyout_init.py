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
    assert "Avvia con" in flyout.chk_autostart.text()
    flyout.close()
