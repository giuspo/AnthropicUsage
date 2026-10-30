"""System Tray Coordinator managing dynamic multi-provider tray icons (Claude, Gemini, Partner)."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from claude_usage import __version__
from claude_usage.core.models import (
    AntigravityUsageSnapshot,
    CompositeUsageSnapshot,
    UsageSnapshot,
)
from claude_usage.ui.flyout import MicroFlyoutWindow
from claude_usage.ui.icon_renderer import IconRenderer

logger = logging.getLogger(__name__)

MAX_WIN32_TOOLTIP_LEN = 127


def truncate_tooltip(title: str, text: str) -> str:
    """Guarantees tooltip stays strictly under Win32 128 character limit."""
    max_title = 30
    if len(title) > max_title:
        title = title[: max_title - 3] + "..."
    full = f"[{title}] {text}"
    if len(full) > MAX_WIN32_TOOLTIP_LEN:
        avail = MAX_WIN32_TOOLTIP_LEN - len(title) - 6
        text = text[: max(3, avail)] + "..."
        full = f"[{title}] {text}"
    return full[:MAX_WIN32_TOOLTIP_LEN]


class TrayController(QSystemTrayIcon):
    """Coordinates up to three system tray icons for Claude, Antigravity, and Partner models."""

    refresh_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, flyout: MicroFlyoutWindow, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.flyout = flyout

        # Secondary tray icons for Antigravity and Partner models
        self.tray_antigravity = QSystemTrayIcon(parent)
        self.tray_partner = QSystemTrayIcon(parent)

        self._shared_menu = self._create_menu()
        self.setContextMenu(self._shared_menu)
        self.tray_antigravity.setContextMenu(self._shared_menu)
        self.tray_partner.setContextMenu(self._shared_menu)

        # Wire activation signals
        self.activated.connect(self._on_claude_activated)
        self.tray_antigravity.activated.connect(self._on_antigravity_activated)
        self.tray_partner.activated.connect(self._on_partner_activated)

        # Initial placeholder icons
        initial_claude = IconRenderer.render_tray_icon(0.0, provider_type="claude")
        self.setIcon(initial_claude)
        self.setToolTip(f"Claude Code v{__version__}: Inizializzazione...")

        initial_gemini = IconRenderer.render_tray_icon(0.0, provider_type="antigravity_gemini")
        self.tray_antigravity.setIcon(initial_gemini)
        self.tray_antigravity.setToolTip("Google Antigravity: Inizializzazione...")

        initial_partner = IconRenderer.render_tray_icon(0.0, provider_type="antigravity_partner")
        self.tray_partner.setIcon(initial_partner)
        self.tray_partner.setToolTip("Antigravity Partner: Inizializzazione...")

    def _create_menu(self) -> QMenu:
        menu = QMenu()

        act_app_info = QAction(f"Claude & Antigravity Usage v{__version__}", menu)
        act_app_info.setEnabled(False)
        menu.addAction(act_app_info)
        menu.addSeparator()

        act_show = QAction("📊 Mostra Widget", menu)
        act_show.triggered.connect(lambda: self.show_flyout())
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

        return menu

    def show(self) -> None:
        """Shows active tray icons based on user configuration."""
        cfg = getattr(self.flyout, "config", None)
        enable_claude = getattr(cfg, "enable_claude", True)
        enable_antigravity = getattr(cfg, "enable_antigravity", True)
        tray_mode = getattr(cfg, "antigravity_tray_mode", "single_icon")

        if enable_claude:
            super().show()
        else:
            self.hide()

        if enable_antigravity:
            self.tray_antigravity.show()
            if tray_mode == "split_partner_icon":
                self.tray_partner.show()
            else:
                self.tray_partner.hide()
        else:
            self.tray_antigravity.hide()
            self.tray_partner.hide()

    def hide(self) -> None:
        super().hide()
        self.tray_antigravity.hide()
        self.tray_partner.hide()

    def _on_claude_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.MiddleClick):
            self.flyout.toggle_at_tray(self.geometry(), target_tab="claude")

    def _on_antigravity_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.MiddleClick):
            self.flyout.toggle_at_tray(self.tray_antigravity.geometry(), target_tab="antigravity")

    def _on_partner_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.MiddleClick):
            self.flyout.toggle_at_tray(self.tray_partner.geometry(), target_tab="antigravity_partner")

    def show_flyout(self, target_tab: str = "overview") -> None:
        """Brings the flyout to front and activates it."""
        geom = self.geometry() if self.isVisible() else self.tray_antigravity.geometry()
        if not self.flyout.isVisible():
            self.flyout.toggle_at_tray(geom, target_tab=target_tab)
        else:
            self.flyout.raise_()
            self.flyout.activateWindow()

    def _open_settings(self) -> None:
        geom = self.geometry() if self.isVisible() else self.tray_antigravity.geometry()
        if not self.flyout.isVisible():
            self.flyout.toggle_at_tray(geom)
        self.flyout.switch_page(1)

    def _open_help(self) -> None:
        geom = self.geometry() if self.isVisible() else self.tray_antigravity.geometry()
        if not self.flyout.isVisible():
            self.flyout.toggle_at_tray(geom)
        self.flyout.switch_page(2)

    def update_snapshot(self, snap: object) -> None:
        """Updates tray icons and tooltips according to active configuration."""
        cfg = getattr(self.flyout, "config", None)
        enable_claude = getattr(cfg, "enable_claude", True)
        enable_antigravity = getattr(cfg, "enable_antigravity", True)
        tray_mode = getattr(cfg, "antigravity_tray_mode", "single_icon")
        single_pool = getattr(cfg, "antigravity_single_pool", "gemini")
        style = getattr(cfg, "tray_icon_style", "concentric")

        claude_snap: Optional[UsageSnapshot] = None
        antigravity_snap: Optional[AntigravityUsageSnapshot] = None

        if isinstance(snap, CompositeUsageSnapshot):
            claude_snap = snap.claude
            antigravity_snap = snap.antigravity
        elif isinstance(snap, UsageSnapshot):
            claude_snap = snap

        # 1. Update Claude Icon
        if enable_claude and claude_snap:
            super().show()
            icon_claude = IconRenderer.render_tray_icon(
                five_hour_pct=claude_snap.five_hour.utilization_pct,
                seven_day_pct=claude_snap.seven_day.utilization_pct,
                is_offline=claude_snap.is_offline,
                style=style,
                provider_type="claude",
            )
            self.setIcon(icon_claude)

            p5 = int(round(claude_snap.five_hour.utilization_pct))
            p7 = int(round(claude_snap.seven_day.utilization_pct))
            txt = f"5h: {p5}% ({claude_snap.five_hour.time_remaining_str}) | 7g: {p7}% ({claude_snap.seven_day.time_remaining_str})"
            self.setToolTip(truncate_tooltip(claude_snap.workspace_name, txt))
        else:
            self.hide()

        # 2. Update Antigravity Icon(s)
        if enable_antigravity and antigravity_snap:
            self.tray_antigravity.show()

            if tray_mode == "split_partner_icon":
                self.tray_partner.show()

                # Icon 2: Gemini
                icon_gemini = IconRenderer.render_tray_icon(
                    five_hour_pct=antigravity_snap.gemini_5h.utilization_pct,
                    seven_day_pct=antigravity_snap.gemini_7d.utilization_pct,
                    is_offline=antigravity_snap.is_offline,
                    style=style,
                    provider_type="antigravity_gemini",
                )
                self.tray_antigravity.setIcon(icon_gemini)
                g5 = int(round(antigravity_snap.gemini_5h.utilization_pct))
                g7 = int(round(antigravity_snap.gemini_7d.utilization_pct))
                gtxt = f"5h: {g5}% ({antigravity_snap.gemini_5h.time_remaining_str}) | 7g: {g7}% ({antigravity_snap.gemini_7d.time_remaining_str})"
                self.tray_antigravity.setToolTip(truncate_tooltip("Antigravity Gemini", gtxt))

                # Icon 3: Partner
                icon_partner = IconRenderer.render_tray_icon(
                    five_hour_pct=antigravity_snap.partner_5h.utilization_pct,
                    seven_day_pct=antigravity_snap.partner_7d.utilization_pct,
                    is_offline=antigravity_snap.is_offline,
                    style=style,
                    provider_type="antigravity_partner",
                )
                self.tray_partner.setIcon(icon_partner)
                prt5 = int(round(antigravity_snap.partner_5h.utilization_pct))
                prt7 = int(round(antigravity_snap.partner_7d.utilization_pct))
                ptxt = f"5h: {prt5}% ({antigravity_snap.partner_5h.time_remaining_str}) | 7g: {prt7}% ({antigravity_snap.partner_7d.time_remaining_str})"
                self.tray_partner.setToolTip(truncate_tooltip("Antigravity Partner", ptxt))

            else:
                self.tray_partner.hide()

                # Single Icon: selected pool
                p5_val, p7_val, pool_lbl = antigravity_snap.get_single_pool_utilization(single_pool)
                prov_t = "antigravity_partner" if pool_lbl == "Partner" else "antigravity_gemini"

                icon_single = IconRenderer.render_tray_icon(
                    five_hour_pct=p5_val,
                    seven_day_pct=p7_val,
                    is_offline=antigravity_snap.is_offline,
                    style=style,
                    provider_type=prov_t,
                )
                self.tray_antigravity.setIcon(icon_single)

                p5_int = int(round(p5_val))
                p7_int = int(round(p7_val))
                time_str = (
                    antigravity_snap.partner_5h.time_remaining_str
                    if pool_lbl == "Partner"
                    else antigravity_snap.gemini_5h.time_remaining_str
                )
                stxt = f"5h: {p5_int}% ({time_str}) | 7g: {p7_int}%"
                self.tray_antigravity.setToolTip(truncate_tooltip(f"Antigravity {pool_lbl}", stxt))
        else:
            self.tray_antigravity.hide()
            self.tray_partner.hide()


# Alias for architectural clarity
TrayCoordinator = TrayController
