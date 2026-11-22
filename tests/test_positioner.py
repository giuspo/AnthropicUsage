"""Unit tests for Linux/GNOME WindowPositioner and TrayController geometry fallback."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtWidgets import QApplication

from claude_usage.core.models import AppConfig
from claude_usage.ui.positioner import WindowPositioner
from claude_usage.ui.tray import TrayController


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def _make_screen(full_rect: QRect, avail_rect: QRect, dpr: float = 1.0) -> MagicMock:
    screen = MagicMock()
    screen.geometry.return_value = full_rect
    screen.availableGeometry.return_value = avail_rect
    screen.devicePixelRatio.return_value = dpr
    return screen


def test_resolve_linux_tray_center_x_rejects_unanchored_xembed_rects():
    primary = _make_screen(QRect(0, 0, 1920, 1080), QRect(64, 32, 1856, 1048), dpr=1.0)

    assert WindowPositioner._resolve_linux_tray_center_x(QRect(0, 0, 16, 16), primary) is None
    assert WindowPositioner._resolve_linux_tray_center_x(QRect(0, 0, 32, 32), primary) is None
    assert WindowPositioner._resolve_linux_tray_center_x(QRect(2, 8, 16, 16), primary) is None
    assert WindowPositioner._resolve_linux_tray_center_x(QRect(), primary) is None


def test_resolve_linux_tray_center_x_accepts_valid_and_clutter_stage_coords():
    primary_1x = _make_screen(QRect(0, 0, 1920, 1080), QRect(64, 32, 1856, 1048), dpr=1.0)
    rect_1x = QRect(1700, 0, 16, 16)
    assert WindowPositioner._resolve_linux_tray_center_x(rect_1x, primary_1x) == rect_1x.center().x()

    # Multi-monitor HiDPI Clutter stage conversion (Case 2)
    primary_2x = _make_screen(QRect(3840, 0, 1920, 1080), QRect(3840, 32, 1920, 1048), dpr=2.0)
    # Tray center on primary monitor at offset +1500 in logical stage coords -> qt x = (1920 + 1500) / 2 = 1710
    stage_tray = QRect(1702, 4, 16, 16)
    resolved = WindowPositioner._resolve_linux_tray_center_x(stage_tray, primary_2x)
    assert resolved == 3840 + (int(round(stage_tray.center().x() * 2.0)) - 1920)


def test_calculate_flyout_position_linux_ignores_frozen_topleft_cursor_and_xembed_zero(monkeypatch):
    primary = _make_screen(QRect(0, 0, 1920, 1080), QRect(64, 32, 1856, 1048), dpr=1.0)
    monkeypatch.setattr("claude_usage.ui.positioner.sys.platform", "linux")
    monkeypatch.setattr("claude_usage.ui.positioner.QGuiApplication.primaryScreen", lambda: primary)
    monkeypatch.setattr("claude_usage.ui.positioner.QCursor.pos", lambda: QPoint(0, 0))

    pos = WindowPositioner.calculate_flyout_position(416, 626, QRect(0, 0, 16, 16))
    # Must fall back to top-right indicator area, never clamp to top-left behind the dock
    expected_x = primary.availableGeometry().right() - 416 - 90
    assert pos == QPoint(expected_x, primary.availableGeometry().top() + WindowPositioner.MARGIN)


def test_tray_controller_caches_and_reuses_valid_tray_x(qapp, monkeypatch):
    primary = _make_screen(QRect(0, 0, 1920, 1080), QRect(64, 32, 1856, 1048), dpr=1.0)
    monkeypatch.setattr("claude_usage.ui.tray.QGuiApplication.primaryScreen", lambda: primary)

    fake_flyout = MagicMock()
    fake_flyout.config = AppConfig()
    controller = TrayController(fake_flyout)
    controller._use_x11_tray = True

    # First call sees valid docked geometry and caches its center_x
    valid_geo = QRect(1720, 8, 16, 16)
    controller.tray_antigravity.geometry = MagicMock(return_value=valid_geo)
    first_geo = controller._get_tray_geometry(controller.tray_antigravity)
    assert first_geo == valid_geo
    expected_cx = valid_geo.center().x()
    assert controller._last_valid_tray_x[id(controller.tray_antigravity)] == expected_cx

    # Transient XEmbed reset to (0, 0, 16, 16) reuses cached center_x instead of (0, 0)
    controller.tray_antigravity.geometry = MagicMock(return_value=QRect(0, 0, 16, 16))
    fallback_geo = controller._get_tray_geometry(controller.tray_antigravity)
    assert fallback_geo == QRect(expected_cx - 8, 8, 16, 16)

    # Display topology change invalidates cached X
    controller._on_screens_changed()
    assert controller._last_valid_tray_x == {}
    assert controller._get_tray_geometry(controller.tray_antigravity) == QRect()
