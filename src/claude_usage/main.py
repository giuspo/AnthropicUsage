"""Entry point for Claude Code Usage Widget."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
import qasync

from claude_usage.autostart import cleanup_duplicate_autostart
from claude_usage.config import load_config
from claude_usage.core.engine import UsageFusionEngine
from claude_usage.core.single_instance import SingleInstanceManager
from claude_usage.ui.flyout import MicroFlyoutWindow
from claude_usage.ui.icon_renderer import IconRenderer
from claude_usage.ui.tray import TrayController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("claude_usage")


def apply_os_quirks() -> None:
    """Configures platform-specific flags for Windows 11 and Linux Wayland."""
    if sys.platform.startswith("linux"):
        # On Linux Wayland, enforce XWayland (xcb) so frameless flyouts can position accurately
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" and "QT_QPA_PLATFORM" not in os.environ:
            os.environ["QT_QPA_PLATFORM"] = "xcb"
            logger.info("Enforced QT_QPA_PLATFORM=xcb for Wayland tray anchoring")

    if sys.platform == "win32":
        # Ensure proper AppUserModelID for Windows 11 Toast notifications
        try:
            import ctypes

            app_id = "ClaudeCode.UsageWidget"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception as e:
            logger.debug(f"Could not set AppUserModelID: {e}")


def main() -> None:
    apply_os_quirks()

    # Clean up redundant startup shortcuts from legacy installer versions
    cleanup_duplicate_autostart()

    app = QApplication(sys.argv)
    app.setApplicationName("Claude Code Usage")
    app.setQuitOnLastWindowClosed(False)  # Keep running in system tray

    # Enforce Single-Instance application (prevents duplicate tray icons)
    single_instance = SingleInstanceManager()
    if not single_instance.acquire():
        logger.info("Claude Usage Widget is already running. Existing instance focused; exiting this process.")
        sys.exit(0)

    # Set official app icon
    app_icon_path = IconRenderer.get_app_icon_path()
    if app_icon_path.exists():
        app.setWindowIcon(QIcon(str(app_icon_path)))

    # Integrate asyncio with Qt event loop via qasync
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    config = load_config()
    engine = UsageFusionEngine(config)
    flyout = MicroFlyoutWindow(config)
    tray = TrayController(flyout)

    # Bring existing window to front if a secondary instance attempts to launch
    single_instance.instance_activated.connect(tray.show_flyout)

    # Signal wiring
    engine.snapshot_updated.connect(flyout.update_snapshot)
    engine.snapshot_updated.connect(tray.update_snapshot)

    def trigger_refresh() -> None:
        asyncio.create_task(engine.refresh())

    def on_logout() -> None:
        engine.auth_manager.clear()
        asyncio.create_task(engine.refresh())

    flyout.refresh_requested.connect(trigger_refresh)
    flyout.logout_requested.connect(on_logout)
    tray.refresh_requested.connect(trigger_refresh)

    def on_quit() -> None:
        single_instance.release()
        asyncio.create_task(engine.stop())
        app.quit()

    tray.quit_requested.connect(on_quit)

    # Show system tray icon
    tray.show()

    # Launch engine tasks within the loop
    async def run_async() -> None:
        await engine.start()

    with loop:
        loop.create_task(run_async())
        try:
            loop.run_forever()
        finally:
            single_instance.release()


if __name__ == "__main__":
    main()
