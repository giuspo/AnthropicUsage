"""Autostart and desktop environment integration for Windows 11 and Linux."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "ClaudeUsageWidget"
DESKTOP_ENTRY_NAME = "claude-usage-widget.desktop"


def set_autostart(enabled: bool) -> bool:
    """Configures or removes application autostart at system login."""
    if sys.platform == "win32":
        return _set_autostart_windows(enabled)
    elif sys.platform.startswith("linux"):
        return _set_autostart_linux(enabled)
    return False


def _set_autostart_windows(enabled: bool) -> bool:
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)

        if enabled:
            # Point to current executable or pythonw
            exe_path = sys.executable
            if "python.exe" in exe_path.lower():
                # Prefer pythonw.exe to prevent terminal window popping up
                pythonw = exe_path.lower().replace("python.exe", "pythonw.exe")
                if os.path.exists(pythonw):
                    exe_path = pythonw
            entry_cmd = f'"{exe_path}" -m claude_usage.main'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, entry_cmd)
            logger.info("Windows 11 autostart enabled in registry")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                logger.info("Windows 11 autostart removed from registry")
            except FileNotFoundError:
                pass

        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.warning(f"Error updating Windows autostart: {e}")
        return False


def _set_autostart_linux(enabled: bool) -> bool:
    try:
        config_dir = Path.home() / ".config" / "autostart"
        desktop_file = config_dir / DESKTOP_ENTRY_NAME

        if enabled:
            config_dir.mkdir(parents=True, exist_ok=True)
            content = f"""[Desktop Entry]
Type=Application
Name=Claude Code Usage Widget
Comment=System Tray monitor for Claude Code usage and rate limits
Exec={sys.executable} -m claude_usage.main
Terminal=false
Categories=Utility;Development;
X-GNOME-Autostart-enabled=true
"""
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Linux autostart written to {desktop_file}")
        else:
            if desktop_file.exists():
                desktop_file.unlink()
                logger.info(f"Linux autostart removed from {desktop_file}")

        return True
    except Exception as e:
        logger.warning(f"Error updating Linux autostart: {e}")
        return False

