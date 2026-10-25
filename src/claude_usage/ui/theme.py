"""Theme and styling definitions for Claude Code Usage Widget."""

from __future__ import annotations

import sys
from typing import Tuple


def is_system_taskbar_light() -> bool:
    """Detects if the system taskbar/tray area is using a light theme."""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            winreg.CloseKey(key)
            return bool(val == 1)
        except Exception:
            return False
    else:
        # Default Linux / GNOME top bar is typically dark
        return False


def is_apps_light_theme() -> bool:
    """Detects if desktop applications prefer a light theme."""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return bool(val == 1)
        except Exception:
            return False
    return False


# Semantic Palette
COLOR_WARNING = (245, 158, 11)  # #F59E0B Amber
COLOR_CRITICAL = (239, 68, 68)  # #EF4444 Red
COLOR_MUTED = (107, 114, 128)  # #6B7280 Grey

# Neutral colors adapting to taskbar theme
COLOR_NEUTRAL_DARK_BAR = (248, 250, 252)  # #F8FAFC White-ish for Dark Taskbars
COLOR_NEUTRAL_LIGHT_BAR = (30, 41, 59)  # #1E293B Dark Slate for Light Taskbars


def get_status_color(utilization_pct: float, is_offline: bool = False) -> Tuple[int, int, int]:
    """Returns RGB tuple corresponding to usage threshold."""
    if is_offline:
        return COLOR_MUTED
    if utilization_pct >= 90.0:
        return COLOR_CRITICAL
    if utilization_pct >= 75.0:
        return COLOR_WARNING

    if is_system_taskbar_light():
        return COLOR_NEUTRAL_LIGHT_BAR
    return COLOR_NEUTRAL_DARK_BAR

