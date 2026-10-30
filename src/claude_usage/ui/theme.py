"""Theme and styling definitions for Claude & Antigravity Usage Widget."""

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
COLOR_WARNING = (251, 191, 36)  # #FBBF24 Bright Amber
COLOR_CRITICAL = (239, 68, 68)  # #EF4444 Red
COLOR_MUTED = (107, 114, 128)  # #6B7280 Grey

# Provider Base Central Glyphs
COLOR_CLAUDE_ICON = (218, 119, 86)     # #DA7756 Iconic Claude Terracotta
COLOR_GEMINI_ICON = (66, 133, 244)     # #4285F4 Google Blue
COLOR_PARTNER_ICON = (16, 185, 129)    # #10B981 Emerald Green

# Claude Code Colors (< 75% Normal State)
COLOR_5H_DARK_BAR = (56, 189, 248)    # #38BDF8 Electric Cyan (5h Session)
COLOR_5H_LIGHT_BAR = (2, 132, 199)    # #0284C7 Deep Cyan for Light Taskbars
COLOR_7D_DARK_BAR = (192, 132, 252)   # #C084FC Vivid Violet (7d Weekly)
COLOR_7D_LIGHT_BAR = (147, 51, 234)   # #9333EA Deep Purple for Light Taskbars

# Antigravity Gemini Colors (< 75% Normal State)
COLOR_GEMINI_5H_DARK = (96, 165, 250)   # #60A5FA Azure Blue
COLOR_GEMINI_5H_LIGHT = (37, 99, 235)   # #2563EB Deep Blue
COLOR_GEMINI_7D_DARK = (129, 140, 248)  # #818CF8 Indigo
COLOR_GEMINI_7D_LIGHT = (79, 70, 229)   # #4F46E5 Deep Indigo

# Antigravity Partner Colors (< 75% Normal State)
COLOR_PARTNER_5H_DARK = (52, 211, 153)  # #34D399 Light Emerald
COLOR_PARTNER_5H_LIGHT = (5, 150, 105)  # #059669 Deep Emerald
COLOR_PARTNER_7D_DARK = (45, 212, 191)  # #2DD4BF Teal
COLOR_PARTNER_7D_LIGHT = (13, 148, 136) # #0D9488 Deep Teal

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


def get_channel_color(
    utilization_pct: float,
    is_weekly: bool = False,
    is_offline: bool = False,
    provider_type: str = "claude",
) -> Tuple[int, int, int]:
    """Returns distinct RGB color for 5h vs 7d in normal state, escalating on warning/critical."""
    if is_offline:
        return COLOR_MUTED
    if utilization_pct >= 90.0:
        return COLOR_CRITICAL
    if utilization_pct >= 75.0:
        return COLOR_WARNING

    light_bar = is_system_taskbar_light()

    if provider_type == "antigravity_gemini" or provider_type == "gemini":
        if is_weekly:
            return COLOR_GEMINI_7D_LIGHT if light_bar else COLOR_GEMINI_7D_DARK
        return COLOR_GEMINI_5H_LIGHT if light_bar else COLOR_GEMINI_5H_DARK

    if provider_type == "antigravity_partner" or provider_type == "partner":
        if is_weekly:
            return COLOR_PARTNER_7D_LIGHT if light_bar else COLOR_PARTNER_7D_DARK
        return COLOR_PARTNER_5H_LIGHT if light_bar else COLOR_PARTNER_5H_DARK

    # Default: Claude Code
    if is_weekly:
        return COLOR_7D_LIGHT_BAR if light_bar else COLOR_7D_DARK_BAR
    return COLOR_5H_LIGHT_BAR if light_bar else COLOR_5H_DARK_BAR
