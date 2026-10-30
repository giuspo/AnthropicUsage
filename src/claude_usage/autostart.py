"""Autostart and desktop environment integration for Windows 11 and Linux."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "ClaudeUsageWidget"
DESKTOP_ENTRY_NAME = "claude-usage-widget.desktop"


def is_autostart_enabled() -> bool:
    """Checks whether autostart is currently enabled in the OS."""
    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, APP_NAME)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception as e:
            logger.debug(f"Error querying Windows autostart: {e}")
            return False
    elif sys.platform.startswith("linux"):
        desktop_file = Path.home() / ".config" / "autostart" / DESKTOP_ENTRY_NAME
        return desktop_file.exists()
    return False


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
            exe_path = sys.executable
            if getattr(sys, "frozen", False):
                # Running as a compiled PyInstaller executable
                entry_cmd = f'"{exe_path}"'
            elif "python.exe" in exe_path.lower():
                # Running from Python script / venv
                pythonw = exe_path.lower().replace("python.exe", "pythonw.exe")
                if os.path.exists(pythonw):
                    exe_path = pythonw
                entry_cmd = f'"{exe_path}" -m claude_usage.main'
            else:
                entry_cmd = f'"{exe_path}"'

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
            if getattr(sys, "frozen", False):
                exec_cmd = sys.executable
            else:
                exec_cmd = f"{sys.executable} -m claude_usage.main"

            content = f"""[Desktop Entry]
Type=Application
Name=Claude Code Usage Widget
Comment=System Tray monitor for Claude Code usage and rate limits
Exec={exec_cmd}
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


def cleanup_duplicate_autostart() -> None:
    """Removes obsolete or duplicate startup shortcuts from the user Startup folder.

    Previous installer versions created both a shortcut in %APPDATA%\\...\\Startup
    and a registry entry in HKCU\\...\\Run, causing two instances to launch on boot.
    This method cleans up the redundant file to ensure only the registry autostart remains.
    """
    if sys.platform == "win32":
        try:
            appdata = os.environ.get("APPDATA")
            if appdata:
                startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                if startup_dir.exists():
                    redundant_names = [
                        "Claude Code Usage Widget.lnk",
                        "ClaudeUsageWidget.lnk",
                        "Claude Code Usage.lnk",
                    ]
                    for name in redundant_names:
                        link_file = startup_dir / name
                        if link_file.exists():
                            try:
                                link_file.unlink()
                                logger.info(f"Cleaned up redundant startup shortcut: {link_file}")
                            except Exception as e:
                                logger.warning(f"Could not remove redundant shortcut {link_file}: {e}")
        except Exception as e:
            logger.debug(f"Error checking startup folder: {e}")
