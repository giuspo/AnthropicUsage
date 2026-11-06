"""Entry point for Claude Code Usage Widget."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
import qasync

from claude_usage.autostart import cleanup_duplicate_autostart
from claude_usage.config import load_config
from claude_usage.core.engine import UsageFusionEngine
from claude_usage.core.single_instance import SingleInstanceManager
from claude_usage.i18n import set_language
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
        # On Linux Wayland, prefer XWayland (xcb) if DISPLAY is available so frameless flyouts position accurately,
        # otherwise use native Wayland with xcb fallback.
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" and "QT_QPA_PLATFORM" not in os.environ:
            if os.environ.get("DISPLAY"):
                os.environ["QT_QPA_PLATFORM"] = "xcb"
                logger.info("Enforced QT_QPA_PLATFORM=xcb for Wayland tray anchoring via XWayland")
            else:
                os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
                logger.info("Configured QT_QPA_PLATFORM=wayland;xcb for Wayland session")

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
    app.setApplicationName("Claude & Antigravity Usage")
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
    set_language(getattr(config, "language", "auto"))
    if "--mock" in sys.argv:
        config.mock_mode = True
        logger.info("Mock simulation mode activated via CLI flag '--mock'")
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

    is_shutting_down = False

    def on_quit() -> None:
        nonlocal is_shutting_down
        if is_shutting_down:
            return
        is_shutting_down = True
        logger.info("Application shutdown requested: cleaning up system tray and background tasks...")

        # 1. Immediately hide and unregister tray icons from OS panel / D-Bus
        tray.cleanup()
        flyout.close()
        flyout.hide()
        app.processEvents()

        # 2. Asynchronous graceful engine shutdown & termination
        async def _graceful_exit() -> None:
            try:
                await engine.stop()
            except Exception as e:
                logger.debug(f"Error during engine stop: {e}")
            finally:
                single_instance.release()
                app.quit()
                os._exit(0)

        if loop.is_running():
            asyncio.create_task(_graceful_exit())
        else:
            single_instance.release()
            app.quit()
            os._exit(0)

    tray.quit_requested.connect(on_quit)

    # Wire OS termination signals (SIGINT, SIGTERM) to graceful exit
    def _sig_handler(_sig: int, _frame: object) -> None:
        on_quit()

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

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
            tray.cleanup()
            single_instance.release()
            os._exit(0)


if __name__ == "__main__":
    main()
