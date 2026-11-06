"""Window positioning logic for Tray Flyout across Multi-Monitor setups."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QCursor, QGuiApplication


class WindowPositioner:
    """Calculates optimal (x, y) coordinates for the frameless flyout near the system tray."""

    MARGIN = 12

    @classmethod
    def _resolve_linux_tray_center_x(cls, tray_geometry: QRect, primary) -> int | None:
        """Converts X11/Clutter stage tray coordinates on Linux to primary screen Qt coordinates."""
        if not tray_geometry.isValid() or tray_geometry.isNull() or tray_geometry.width() <= 0:
            return None

        primary_full = primary.geometry()
        dpr = primary.devicePixelRatio() or 1.0

        # Case 1: tray_geometry is already in primary screen's Qt logical coordinates
        if primary_full.left() <= tray_geometry.center().x() <= primary_full.right():
            return tray_geometry.center().x()

        # Case 2: Under GNOME Wayland + XWayland, Mutter's na_xembed_set_root_position
        # reports Clutter stage logical coordinates, which Qt divides by devicePixelRatio.
        stage_x = int(round(tray_geometry.center().x() * dpr))
        primary_stage_x = int(round(primary_full.left() / dpr))
        offset_x = stage_x - primary_stage_x
        if 0 <= offset_x <= primary_full.width():
            return primary_full.left() + offset_x

        return tray_geometry.center().x()

    @classmethod
    def calculate_flyout_position(
        cls,
        flyout_width: int,
        flyout_height: int,
        tray_geometry: QRect,
    ) -> QPoint:
        """Determines pixel coordinates to anchor the flyout without clipping screen edges."""
        cursor_pos = QCursor.pos()

        # Linux / Ubuntu GNOME: the top bar with system tray icons lives on primaryScreen().
        # Under Wayland + XWayland, QCursor.pos() freezes on the last X11 window if the user
        # clicks the native Wayland top panel on another monitor.
        if sys.platform.startswith("linux"):
            primary = QGuiApplication.primaryScreen()
            if not primary:
                return QPoint(100, 100)

            screen = primary
            screen_geo = screen.availableGeometry()
            screen_full = screen.geometry()

            tray_center_x = cls._resolve_linux_tray_center_x(tray_geometry, primary)
            if tray_center_x is not None:
                target_x = tray_center_x - (flyout_width // 2)
            elif screen_full.contains(cursor_pos) and cursor_pos.y() <= screen_full.top() + 60:
                target_x = cursor_pos.x() - (flyout_width // 2)
            else:
                # Top-right indicator area on the primary screen
                target_x = screen_geo.right() - flyout_width - 90

            target_y = screen_geo.top() + cls.MARGIN

            min_x = screen_geo.left() + cls.MARGIN
            max_x = screen_geo.right() - flyout_width - cls.MARGIN
            clamped_x = max(min_x, min(max_x, target_x))

            min_y = screen_geo.top() + cls.MARGIN
            max_y = screen_geo.bottom() - flyout_height - cls.MARGIN
            clamped_y = max(min_y, min(max_y, target_y))

            return QPoint(clamped_x, clamped_y)

        # Windows / macOS
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
                # Taskbar / Panel at top
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

    @classmethod
    def calculate_menu_position(cls, tray_geometry: QRect, menu_width: int = 240) -> QPoint:
        """Determines pixel coordinates for the right-click context menu on Linux."""
        primary = QGuiApplication.primaryScreen()
        if not primary:
            return QCursor.pos()

        screen_geo = primary.availableGeometry()
        tray_center_x = cls._resolve_linux_tray_center_x(tray_geometry, primary)
        if tray_center_x is not None:
            target_x = tray_center_x - (menu_width // 2)
        else:
            target_x = screen_geo.right() - menu_width - 90

        min_x = screen_geo.left() + cls.MARGIN
        max_x = screen_geo.right() - menu_width - cls.MARGIN
        clamped_x = max(min_x, min(max_x, target_x))
        target_y = 36  # Directly below the 32px GNOME top bar
        return QPoint(clamped_x, target_y)


