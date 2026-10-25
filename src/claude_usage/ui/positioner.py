"""Window positioning logic for Tray Flyout across Multi-Monitor setups."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QCursor, QGuiApplication


class WindowPositioner:
    """Calculates optimal (x, y) coordinates for the frameless flyout near the system tray."""

    MARGIN = 12

    @classmethod
    def calculate_flyout_position(
        cls,
        flyout_width: int,
        flyout_height: int,
        tray_geometry: QRect,
    ) -> QPoint:
        """Determines pixel coordinates to anchor the flyout without clipping screen edges."""
        # Detect active screen
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        if not screen:
            return QPoint(100, 100)

        screen_geo = screen.availableGeometry()  # Work area excluding taskbar

        # Check if tray_geometry is valid and lies within screen
        has_valid_tray = (
            tray_geometry.isValid()
            and not tray_geometry.isNull()
            and screen_geo.contains(tray_geometry.center())
        )

        if has_valid_tray:
            tray_center = tray_geometry.center()
            target_x = tray_center.x() - (flyout_width // 2)

            # Determine whether taskbar is at bottom, top, left, or right
            if tray_geometry.bottom() >= screen_geo.bottom():
                # Taskbar at bottom (Standard Windows 11)
                target_y = screen_geo.bottom() - flyout_height - cls.MARGIN
            elif tray_geometry.top() <= screen_geo.top():
                # Taskbar / Panel at top (Ubuntu GNOME)
                target_y = screen_geo.top() + cls.MARGIN
            elif tray_geometry.right() >= screen_geo.right():
                # Taskbar at right
                target_x = screen_geo.right() - flyout_width - cls.MARGIN
                target_y = tray_center.y() - (flyout_height // 2)
            else:
                # Taskbar at left
                target_x = screen_geo.left() + cls.MARGIN
                target_y = tray_center.y() - (flyout_height // 2)
        else:
            # Fallback to cursor position
            target_x = cursor_pos.x() - (flyout_width // 2)
            target_y = cursor_pos.y() - flyout_height - cls.MARGIN

        # Clamping within available screen geometry
        min_x = screen_geo.left() + cls.MARGIN
        max_x = screen_geo.right() - flyout_width - cls.MARGIN
        clamped_x = max(min_x, min(max_x, target_x))

        min_y = screen_geo.top() + cls.MARGIN
        max_y = screen_geo.bottom() - flyout_height - cls.MARGIN
        clamped_y = max(min_y, min(max_y, target_y))

        return QPoint(clamped_x, clamped_y)

