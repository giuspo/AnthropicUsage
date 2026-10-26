"""System Tray Controller for Claude Code Usage Widget."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from claude_usage import __version__
from claude_usage.core.models import UsageSnapshot
from claude_usage.ui.flyout import MicroFlyoutWindow
from claude_usage.ui.icon_renderer import IconRenderer

logger = logging.getLogger(__name__)

MAX_WIN32_TOOLTIP_LEN = 127


def format_tray_tooltip(
    workspace_name: str,
    utilization_pct: float,
    time_remaining: str,
    window_label: str = "",
) -> str:
    """Formats the tooltip guaranteeing compliance with the Win32 128-char limit."""
    pct_int = int(round(utilization_pct))
    suffix = f"Claude Code: {pct_int}%"
    if window_label:
        suffix += f" ({window_label})"
    suffix += f" - Reset in {time_remaining}"

    # Leave room for [ ] and a space
    avail_len = MAX_WIN32_TOOLTIP_LEN - len(suffix) - 4
    if len(workspace_name) > avail_len:
        truncated_name = workspace_name[: max(3, avail_len - 3)] + "..."
    else:
        truncated_name = workspace_name

    return f"[{truncated_name}] {suffix}"


class TrayController(QSystemTrayIcon):
    """Integrates with the operating system tray, handles tooltips, clicks, and menus."""

    refresh_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, flyout: MicroFlyoutWindow, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.flyout = flyout

        self._init_menu()
        self.activated.connect(self._on_tray_activated)

        # Set initial icon at 0%
        initial_icon = IconRenderer.render_tray_icon(0.0)
        self.setIcon(initial_icon)
        self.setToolTip(f"Claude Code v{__version__}: Inizializzazione...")

    def _init_menu(self) -> None:
        menu = QMenu()

        act_app_info = QAction(f"Claude Usage Widget  v{__version__}", menu)
        act_app_info.setEnabled(False)
        menu.addAction(act_app_info)
        menu.addSeparator()

        act_show = QAction("📊 Mostra Widget", menu)
        act_show.triggered.connect(self._toggle_flyout)
        menu.addAction(act_show)

        act_refresh = QAction("↻ Aggiorna Adesso", menu)
        act_refresh.triggered.connect(self.refresh_requested.emit)
        menu.addAction(act_refresh)

        menu.addSeparator()

        act_settings = QAction("⚙️ Impostazioni", menu)
        act_settings.triggered.connect(self._open_settings)
        menu.addAction(act_settings)

        act_help = QAction(f"ℹ️ Informazioni & Help (v{__version__} - giuspo)", menu)
        act_help.triggered.connect(self._open_help)
        menu.addAction(act_help)

        menu.addSeparator()

        act_quit = QAction("❌ Esci", menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Trigger on standard left-click or middle-click
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        ):
            self._toggle_flyout()

    def _toggle_flyout(self) -> None:
        self.flyout.toggle_at_tray(self.geometry())

    def _open_settings(self) -> None:
        if not self.flyout.isVisible():
            self.flyout.toggle_at_tray(self.geometry())
        self.flyout.switch_page(1)

    def _open_help(self) -> None:
        if not self.flyout.isVisible():
            self.flyout.toggle_at_tray(self.geometry())
        self.flyout.switch_page(2)

    def update_snapshot(self, snap: UsageSnapshot) -> None:
        """Updates the tray icon and formatted tooltip."""
        # 1. Update dynamic icon
        icon = IconRenderer.render_tray_icon(snap.primary_utilization, is_offline=snap.is_offline)
        self.setIcon(icon)

        # 2. Update formatted tooltip (<128 char limit)
        tip = format_tray_tooltip(
            workspace_name=snap.workspace_name,
            utilization_pct=snap.primary_utilization,
            time_remaining=snap.primary_reset_str,
            window_label="Settimanale" if snap.is_weekly_bottleneck else "5h",
        )
        self.setToolTip(tip)

