"""Micro-Flyout borderless popup window for Claude Code Usage Widget."""

from __future__ import annotations

import asyncio
import webbrowser
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from claude_usage import __version__
from claude_usage.config import AppConfig, save_config
from claude_usage.core.login_helper import ClaudeLoginHelper
from claude_usage.core.models import UsageSnapshot
from claude_usage.ui.icon_renderer import IconRenderer
from claude_usage.ui.positioner import WindowPositioner
from claude_usage.ui.theme import COLOR_CRITICAL, COLOR_WARNING


def format_number(val: int) -> str:
    """Formats large token counts into human readable strings."""
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}k"
    return str(val)


class SemiCircleGauge(QWidget):
    """Custom paint widget rendering a semi-circular radial gauge for 5-hour usage."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(260, 130)
        self.pct: float = 0.0

    def set_percentage(self, pct: float) -> None:
        self.pct = max(0.0, min(100.0, pct))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRect(20, 15, 220, 220)
        start_angle = 180 * 16
        full_span = -180 * 16

        # Background Arc
        bg_pen = QPen(QColor(255, 255, 255, 25), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, start_angle, full_span)

        # Progress Arc
        if self.pct >= 90.0:
            color = QColor(*COLOR_CRITICAL)
        elif self.pct >= 75.0:
            color = QColor(*COLOR_WARNING)
        else:
            color = QColor(56, 189, 248)  # Sky blue

        span_angle = int((-180 * 16) * (self.pct / 100.0))
        if abs(span_angle) > 0:
            fg_pen = QPen(color, 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(fg_pen)
            painter.drawArc(rect, start_angle, span_angle)


class MicroFlyoutWindow(QWidget):
    """Borderless, frameless pop-up window anchored above/below the system tray."""

    refresh_requested = pyqtSignal()
    logout_requested = pyqtSignal()

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.config = config
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 530)

        app_icon_path = IconRenderer.get_app_icon_path()
        if app_icon_path.exists():
            self.setWindowIcon(QIcon(str(app_icon_path)))

        # Listen for window focus events to auto-dismiss on click outside
        self.installEventFilter(self)

        self._init_ui()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self and event.type() == QEvent.Type.WindowDeactivate:
            # Clicked outside flyout: dismiss
            self.hide()
            return True
        return super().eventFilter(obj, event)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        self.card = QFrame(self)
        self.card.setObjectName("MainCard")
        self.card.setStyleSheet(
            """
            #MainCard {
                background-color: #121214;
                border: 1px solid #27272A;
                border-radius: 16px;
            }
            QLabel {
                color: #F4F4F5;
                font-family: 'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif;
            }
        """
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.status_pill = QLabel("🟢 Connesso via OAuth", self.card)
        self.status_pill.setStyleSheet(
            """
            background-color: #1E1E22;
            color: #A1A1AA;
            padding: 5px 10px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 500;
            border: 1px solid #2E2E34;
        """
        )
        header_layout.addWidget(self.status_pill)
        header_layout.addStretch()

        self.version_pill = QLabel(f"v{__version__}", self.card)
        self.version_pill.setStyleSheet(
            """
            background-color: #1E1E24;
            color: #A1A1AA;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid #2E2E38;
        """
        )
        self.version_pill.setToolTip(f"Versione applicazione: {__version__} (Major.Minor.Compilation)")
        header_layout.addWidget(self.version_pill)

        self.btn_refresh = QPushButton("↻", self.card)
        self.btn_refresh.setFixedSize(30, 30)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(
            """
            QPushButton {
                background-color: #1E1E22;
                color: #FAFAFA;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                border: 1px solid #2E2E34;
            }
            QPushButton:hover {
                background-color: #2E2E34;
            }
        """
        )
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self.btn_refresh)
        card_layout.addLayout(header_layout)

        # Workspace Title
        self.lbl_workspace = QLabel("Claude Code", self.card)
        self.lbl_workspace.setStyleSheet("font-size: 17px; font-weight: 700; color: #FFFFFF;")
        card_layout.addWidget(self.lbl_workspace)

        # Critical Alert Banner (Shown when 5h or 7d limit is reached)
        self.alert_banner = QFrame(self.card)
        self.alert_banner.setStyleSheet(
            """
            QFrame {
                background-color: rgba(239, 68, 68, 0.15);
                border: 1px solid #EF4444;
                border-radius: 8px;
            }
        """
        )
        alert_layout = QHBoxLayout(self.alert_banner)
        alert_layout.setContentsMargins(8, 6, 8, 6)
        alert_layout.setSpacing(6)
        lbl_alert_icon = QLabel("🚨", self.alert_banner)
        lbl_alert_icon.setStyleSheet("font-size: 15px;")
        alert_layout.addWidget(lbl_alert_icon)

        self.lbl_alert_text = QLabel("Limite Settimanale Raggiunto (100%)\nReset tra 24h 31m", self.alert_banner)
        self.lbl_alert_text.setStyleSheet("color: #FCA5A5; font-size: 11px; font-weight: 600;")
        alert_layout.addWidget(self.lbl_alert_text)
        alert_layout.addStretch()
        self.alert_banner.setVisible(False)
        card_layout.addWidget(self.alert_banner)

        # Anomaly / Burn-rate Alert Banner (Shown on abnormal consumption or loop)
        self.anomaly_banner = QFrame(self.card)
        self.anomaly_banner.setStyleSheet(
            """
            QFrame {
                background-color: rgba(245, 158, 11, 0.15);
                border: 1px solid #F59E0B;
                border-radius: 8px;
            }
        """
        )
        anomaly_layout = QHBoxLayout(self.anomaly_banner)
        anomaly_layout.setContentsMargins(8, 6, 8, 6)
        anomaly_layout.setSpacing(6)
        lbl_anomaly_icon = QLabel("🔥", self.anomaly_banner)
        lbl_anomaly_icon.setStyleSheet("font-size: 15px;")
        anomaly_layout.addWidget(lbl_anomaly_icon)

        self.lbl_anomaly_text = QLabel("Consumo anomalo rilevato", self.anomaly_banner)
        self.lbl_anomaly_text.setStyleSheet("color: #FCD34D; font-size: 11px; font-weight: 600;")
        anomaly_layout.addWidget(self.lbl_anomaly_text)
        anomaly_layout.addStretch()
        self.anomaly_banner.setVisible(False)
        card_layout.addWidget(self.anomaly_banner)

        # Stacked Layout: Page 0 = Metrics View, Page 1 = Settings View
        self.stacked_widget = QWidget(self.card)
        self.stacked_layout = QStackedLayout(self.stacked_widget)

        # =========================================================================
        # PAGE 0: METRICS VIEW
        # =========================================================================
        self.metrics_view = QWidget()
        vbox_metrics = QVBoxLayout(self.metrics_view)
        vbox_metrics.setContentsMargins(0, 2, 0, 0)
        vbox_metrics.setSpacing(8)

        # Segmented Control: [ ⏱️ Finestra 5 Ore ]  [ 📅 Limite Settimanale ]
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(6)

        self.btn_tab_5h = QPushButton("⏱️ Finestra 5 Ore", self.metrics_view)
        self.btn_tab_5h.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_7d = QPushButton("📅 Limite Settimanale", self.metrics_view)
        self.btn_tab_7d.setCursor(Qt.CursorShape.PointingHandCursor)

        self.active_tab = "bottleneck"  # "5h", "7d", or "bottleneck"
        self.btn_tab_5h.clicked.connect(lambda: self._select_window_tab("5h"))
        self.btn_tab_7d.clicked.connect(lambda: self._select_window_tab("7d"))

        tab_layout.addWidget(self.btn_tab_5h)
        tab_layout.addWidget(self.btn_tab_7d)
        vbox_metrics.addLayout(tab_layout)

        # Semi-circular gauge container
        gauge_container = QWidget()
        gauge_layout = QVBoxLayout(gauge_container)
        gauge_layout.setContentsMargins(0, 0, 0, 0)
        gauge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gauge = SemiCircleGauge(gauge_container)
        gauge_layout.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_pct = QLabel("0%", gauge_container)
        self.lbl_pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pct.setStyleSheet("font-size: 28px; font-weight: 700; color: #FFFFFF; margin-top: -46px;")
        gauge_layout.addWidget(self.lbl_pct)

        self.lbl_reset_timer = QLabel("Reset in --", gauge_container)
        self.lbl_reset_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_reset_timer.setStyleSheet("font-size: 12px; color: #A1A1AA; margin-bottom: 2px;")
        gauge_layout.addWidget(self.lbl_reset_timer)

        self.lbl_gauge_title = QLabel("Sessione 5 Ore", gauge_container)
        self.lbl_gauge_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_gauge_title.setStyleSheet("font-size: 10px; color: #71717A; text-transform: uppercase; letter-spacing: 1px;")
        gauge_layout.addWidget(self.lbl_gauge_title)

        vbox_metrics.addWidget(gauge_container)

        # Dual Quota Overview Card (5h + 7d side-by-side)
        dual_card = QFrame(self.metrics_view)
        dual_card.setStyleSheet(
            """
            QFrame {
                background-color: #1A1A1E;
                border: 1px solid #2E2E34;
                border-radius: 8px;
            }
        """
        )
        dual_layout = QVBoxLayout(dual_card)
        dual_layout.setContentsMargins(10, 6, 10, 6)
        dual_layout.setSpacing(4)

        self.lbl_row_5h = QLabel("⏱️ Sessione 5h: 0%  (Reset in 0m)", dual_card)
        self.lbl_row_5h.setStyleSheet("color: #D4D4D8; font-size: 11px;")
        dual_layout.addWidget(self.lbl_row_5h)

        self.lbl_row_7d = QLabel("📅 Settimanale: 0%  (Reset in --)", dual_card)
        self.lbl_row_7d.setStyleSheet("color: #D4D4D8; font-size: 11px;")
        dual_layout.addWidget(self.lbl_row_7d)

        vbox_metrics.addWidget(dual_card)

        # Token Cards Grid (Input, Output, Thinking)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(8)

        self.card_in = self._create_metric_card("Input", "0", "0% cache")
        self.card_out = self._create_metric_card("Output", "0", "token")
        self.card_think = self._create_metric_card("Thinking 🧠", "0", "token")

        cards_layout.addWidget(self.card_in)
        cards_layout.addWidget(self.card_out)
        cards_layout.addWidget(self.card_think)
        vbox_metrics.addLayout(cards_layout)

        vbox_metrics.addStretch()
        self.stacked_layout.addWidget(self.metrics_view)

        # =========================================================================
        # PAGE 1: SETTINGS VIEW (Clean Structured Layout with ScrollArea)
        # =========================================================================
        self.settings_view = QWidget()
        settings_outer_layout = QVBoxLayout(self.settings_view)
        settings_outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self.settings_view)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            """
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #18181B;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #3F3F46;
                min-height: 20px;
                border-radius: 3px;
            }
        """
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        vbox_settings = QVBoxLayout(scroll_content)
        vbox_settings.setContentsMargins(2, 4, 6, 8)
        vbox_settings.setSpacing(12)

        # --- SECTION 1: ACCOUNT & AUTENTICAZIONE ---
        card_auth = QFrame(scroll_content)
        card_auth.setStyleSheet(
            """
            QFrame {
                background-color: #1A1A1E;
                border: 1px solid #2E2E34;
                border-radius: 10px;
                padding: 10px;
            }
        """
        )
        layout_auth = QVBoxLayout(card_auth)
        layout_auth.setContentsMargins(8, 8, 8, 8)
        layout_auth.setSpacing(8)

        lbl_auth_sec = QLabel("🔐 Account Claude Code", card_auth)
        lbl_auth_sec.setStyleSheet("font-size: 13px; font-weight: 600; color: #FFFFFF;")
        layout_auth.addWidget(lbl_auth_sec)

        # 1-Click Login and Cancel Button Layout
        auth_btn_layout = QHBoxLayout()
        auth_btn_layout.setSpacing(6)

        self.btn_login = QPushButton("🔑 Accedi con Claude (Login 1-Click)", card_auth)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet(
            """
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                border: none;
                min-height: 38px;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #27272A; color: #71717A; }
        """
        )
        self.btn_login.clicked.connect(self._start_quick_login)
        auth_btn_layout.addWidget(self.btn_login, stretch=3)

        self.btn_cancel_login = QPushButton("✕ Annulla", card_auth)
        self.btn_cancel_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_login.setStyleSheet(
            """
            QPushButton {
                background-color: #27272A;
                color: #A1A1AA;
                padding: 8px 12px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
                border: 1px solid #3F3F46;
                min-height: 38px;
            }
            QPushButton:hover { background-color: #3F3F46; color: #FFFFFF; }
        """
        )
        self.btn_cancel_login.clicked.connect(self._cancel_quick_login)
        self.btn_cancel_login.setVisible(False)
        auth_btn_layout.addWidget(self.btn_cancel_login, stretch=1)

        layout_auth.addLayout(auth_btn_layout)

        # Logout Button
        self.btn_logout = QPushButton("🚪 Disconnetti Account", card_auth)
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setStyleSheet(
            """
            QPushButton {
                background-color: #222226;
                color: #F87171;
                padding: 8px 12px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
                border: 1px solid #3F2323;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #381A1A;
                border-color: #5C2424;
            }
        """
        )
        self.btn_logout.clicked.connect(self._perform_logout)
        layout_auth.addWidget(self.btn_logout)

        self.lbl_login_status = QLabel("", card_auth)
        self.lbl_login_status.setStyleSheet("color: #38BDF8; font-size: 11px;")
        self.lbl_login_status.setWordWrap(True)
        layout_auth.addWidget(self.lbl_login_status)

        vbox_settings.addWidget(card_auth)

        # --- SECTION 2: NOTIFICHE DESKTOP ---
        card_notif = QFrame(scroll_content)
        card_notif.setStyleSheet(
            """
            QFrame {
                background-color: #1A1A1E;
                border: 1px solid #2E2E34;
                border-radius: 10px;
                padding: 10px;
            }
        """
        )
        layout_notif = QVBoxLayout(card_notif)
        layout_notif.setContentsMargins(8, 8, 8, 8)
        layout_notif.setSpacing(8)

        lbl_notif_sec = QLabel("🔔 Notifiche & Alert", card_notif)
        lbl_notif_sec.setStyleSheet("font-size: 13px; font-weight: 600; color: #FFFFFF;")
        layout_notif.addWidget(lbl_notif_sec)

        self.chk_notif = QCheckBox("Abilita Notifiche Push Native", card_notif)
        self.chk_notif.setChecked(self.config.notifications_enabled)
        self.chk_notif.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_notif.setStyleSheet("color: #E4E4E7; font-size: 12px;")
        layout_notif.addWidget(self.chk_notif)

        lbl_thresh_title = QLabel("Soglie di avviso (% di quota):", card_notif)
        lbl_thresh_title.setStyleSheet("color: #A1A1AA; font-size: 11px; margin-top: 2px;")
        layout_notif.addWidget(lbl_thresh_title)

        self.txt_thresholds = QLineEdit(card_notif)
        self.txt_thresholds.setText(", ".join(str(t) for t in sorted(self.config.thresholds)))
        self.txt_thresholds.setPlaceholderText("es. 50, 75, 80, 95, 100")
        self.txt_thresholds.setStyleSheet(
            """
            QLineEdit {
                background-color: #121214;
                border: 1px solid #3F3F46;
                border-radius: 8px;
                color: #FFFFFF;
                padding: 7px 10px;
                font-size: 12px;
                min-height: 34px;
            }
            QLineEdit:focus { border-color: #3B82F6; }
        """
        )
        layout_notif.addWidget(self.txt_thresholds)

        # Quick-toggle chips grid (2 rows of 3 buttons)
        lbl_chips_hint = QLabel("Tocca una soglia per attivarla / disattivarla:", card_notif)
        lbl_chips_hint.setStyleSheet("color: #71717A; font-size: 10px;")
        layout_notif.addWidget(lbl_chips_hint)

        grid_chips = QGridLayout()
        grid_chips.setSpacing(6)
        self._threshold_chips: dict[int, QPushButton] = {}
        preset_values = [50, 75, 80, 90, 95, 100]

        for idx, val in enumerate(preset_values):
            btn = QPushButton(f"{val}%", card_notif)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, v=val: self._toggle_threshold_chip(v))
            row = idx // 3
            col = idx % 3
            grid_chips.addWidget(btn, row, col)
            self._threshold_chips[val] = btn

        layout_notif.addLayout(grid_chips)
        self.txt_thresholds.textChanged.connect(self._sync_threshold_chips)
        self._sync_threshold_chips()

        # Burn-rate & Loop Detection Toggle
        self.chk_burn_rate = QCheckBox("🔥 Avviso Consumo Rapido (Spike & Loop)", card_notif)
        self.chk_burn_rate.setChecked(self.config.burn_rate_alert_enabled)
        self.chk_burn_rate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_burn_rate.setStyleSheet("color: #E4E4E7; font-size: 12px; margin-top: 8px;")
        layout_notif.addWidget(self.chk_burn_rate)

        lbl_burn_desc = QLabel("Avvisa se la quota sale oltre +15% in <10m o con turni enormi", card_notif)
        lbl_burn_desc.setStyleSheet("color: #71717A; font-size: 10px;")
        layout_notif.addWidget(lbl_burn_desc)

        vbox_settings.addWidget(card_notif)

        # --- SECTION 3: CHIAVE API O ENTERPRISE (OPZIONALE) ---
        card_key = QFrame(scroll_content)
        card_key.setStyleSheet(
            """
            QFrame {
                background-color: #1A1A1E;
                border: 1px solid #2E2E34;
                border-radius: 10px;
                padding: 10px;
            }
        """
        )
        layout_key = QVBoxLayout(card_key)
        layout_key.setContentsMargins(8, 8, 8, 8)
        layout_key.setSpacing(6)

        lbl_key_sec = QLabel("⚙️ Inserimento Manuale (Opzionale)", card_key)
        lbl_key_sec.setStyleSheet("font-size: 13px; font-weight: 600; color: #FFFFFF;")
        layout_key.addWidget(lbl_key_sec)

        lbl_key_desc = QLabel("Admin Key (sk-ant-admin-...) o Token OAuth:", card_key)
        lbl_key_desc.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        layout_key.addWidget(lbl_key_desc)

        self.txt_admin_key = QLineEdit(card_key)
        self.txt_admin_key.setPlaceholderText("Incolla chiave sk-ant-admin-... o token")
        self.txt_admin_key.setEchoMode(QLineEdit.EchoMode.Password)
        if self.config.admin_api_key:
            self.txt_admin_key.setText(self.config.admin_api_key)
        self.txt_admin_key.setStyleSheet(
            """
            QLineEdit {
                background-color: #121214;
                border: 1px solid #3F3F46;
                border-radius: 8px;
                color: #FFFFFF;
                padding: 8px 12px;
                font-size: 12px;
                min-height: 36px;
            }
            QLineEdit:focus { border-color: #3B82F6; }
        """
        )
        layout_key.addWidget(self.txt_admin_key)

        self.chk_mock = QCheckBox("Simulazione Demo (Mock Mode)", card_key)
        self.chk_mock.setChecked(self.config.mock_mode)
        self.chk_mock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_mock.setStyleSheet("color: #A1A1AA; font-size: 11px; margin-top: 4px;")
        layout_key.addWidget(self.chk_mock)

        vbox_settings.addWidget(card_key)

        # Save Settings Action Button
        btn_save_settings = QPushButton("💾 Salva Impostazioni", scroll_content)
        btn_save_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_settings.setStyleSheet(
            """
            QPushButton {
                background-color: #3B82F6;
                color: #FFFFFF;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                border: none;
                min-height: 38px;
            }
            QPushButton:hover { background-color: #2563EB; }
        """
        )
        btn_save_settings.clicked.connect(self._save_settings_action)
        vbox_settings.addWidget(btn_save_settings)

        # --- SECTION 4: INFORMAZIONI, HELP & CREDITI ---
        card_about = QFrame(scroll_content)
        card_about.setStyleSheet(
            """
            QFrame {
                background-color: #1A1A1E;
                border: 1px solid #2E2E34;
                border-radius: 10px;
                padding: 10px;
            }
        """
        )
        layout_about = QVBoxLayout(card_about)
        layout_about.setContentsMargins(10, 10, 10, 10)
        layout_about.setSpacing(8)

        # Header con Titolo e Badge Versione
        row_about_title = QHBoxLayout()
        lbl_about_sec = QLabel("ℹ️ Guida & Informazioni", card_about)
        lbl_about_sec.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        row_about_title.addWidget(lbl_about_sec)
        row_about_title.addStretch()

        lbl_version_badge = QLabel(f"v{__version__}", card_about)
        lbl_version_badge.setStyleSheet(
            """
            background-color: #0369A1;
            color: #F0F9FF;
            font-weight: 700;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 6px;
            border: 1px solid #38BDF8;
            """
        )
        lbl_version_badge.setToolTip(f"Versione build: {__version__}")
        row_about_title.addWidget(lbl_version_badge)
        layout_about.addLayout(row_about_title)

        lbl_creator = QLabel("Creato con cura e dedizione da giuspo 🚀", card_about)
        lbl_creator.setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: 600;")
        layout_about.addWidget(lbl_creator)

        lbl_ver_detail = QLabel(
            f"📦 <b>Versione {__version__}</b> &nbsp;•&nbsp; <span style='color: #71717A;'>Schema Major.Minor.Compilation</span>",
            card_about,
        )
        lbl_ver_detail.setStyleSheet("color: #D4D4D8; font-size: 11px; margin-bottom: 2px;")
        layout_about.addWidget(lbl_ver_detail)

        # Scopo del programma
        lbl_purpose_title = QLabel("🎯 Scopo dell'Applicazione", card_about)
        lbl_purpose_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #E4E4E7; margin-top: 4px;")
        layout_about.addWidget(lbl_purpose_title)

        lbl_desc = QLabel(
            "Claude Code Usage Widget è progettato per monitorare in tempo reale "
            "le quote di utilizzo e il consumo di token (Input, Output, Thinking 🧠) "
            "del tuo account Anthropic, senza dover aprire il browser o interrompere "
            "il lavoro nel terminale. Ti avvisa prima che la quota si esaurisca.",
            card_about,
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #A1A1AA; font-size: 11px; line-height: 16px;")
        layout_about.addWidget(lbl_desc)

        # Come si utilizza
        lbl_usage_title = QLabel("💡 Come si Utilizza", card_about)
        lbl_usage_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #E4E4E7; margin-top: 4px;")
        layout_about.addWidget(lbl_usage_title)

        lbl_guide = QLabel(
            "1. Barra di Sistema (Tray):\n"
            "   L'icona mostra a colpo d'occhio un anello circolare colorato (Verde <75%, Giallo 75-90%, Rosso >90%). "
            "Passando il mouse sopra leggi la percentuale e l'orario esatto di reset.\n\n"
            "2. Visualizzazione Metriche (Click sinistro):\n"
            "   Clicca sull'icona per aprire la finestra con il tachimetro, i token spacchettati e passare "
            "dalla sessione '5 Ore' al limite 'Settimanale'.\n\n"
            "3. Connessione Account (1-Click):\n"
            "   Nella sezione 'Account' clicca su 'Accedi con Claude': si aprirà il browser per autorizzare l'accesso in automatico.\n\n"
            "4. Alert e Notifiche Anti-Loop:\n"
            "   Il widget ti avvisa con notifiche push quando superi le soglie scelte o se rileva un picco anomalo di token improvvisi.",
            card_about,
        )
        lbl_guide.setWordWrap(True)
        lbl_guide.setStyleSheet("color: #9CA3AF; font-size: 10px; line-height: 15px;")
        layout_about.addWidget(lbl_guide)

        # Licenza Open Source Copyleft
        lbl_license = QLabel("📜 Licenza: GNU General Public License v3 (GPL-3.0) • Open Source Copyleft", card_about)
        lbl_license.setStyleSheet("color: #71717A; font-size: 10px; margin-top: 4px; font-style: italic;")
        layout_about.addWidget(lbl_license)

        vbox_settings.addWidget(card_about)

        vbox_settings.addStretch()
        scroll.setWidget(scroll_content)
        settings_outer_layout.addWidget(scroll)

        self.stacked_layout.addWidget(self.settings_view)
        card_layout.addWidget(self.stacked_widget)

        # Footer Actions
        footer_layout = QHBoxLayout()
        self.btn_toggle_settings = QPushButton("⚙️ Impostazioni", self.card)
        self.btn_toggle_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_settings.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #A1A1AA;
                font-size: 12px;
                border: none;
                text-align: left;
                padding: 4px 0px;
            }
            QPushButton:hover { color: #FFFFFF; }
        """
        )
        self.btn_toggle_settings.clicked.connect(self._toggle_settings_page)
        footer_layout.addWidget(self.btn_toggle_settings)

        btn_help = QPushButton("ℹ️ Help", self.card)
        btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_help.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #71717A;
                font-size: 12px;
                border: none;
                padding: 4px 6px;
            }
            QPushButton:hover { color: #38BDF8; }
        """
        )
        btn_help.clicked.connect(self._show_help_section)
        footer_layout.addWidget(btn_help)

        footer_layout.addStretch()

        btn_console = QPushButton("Console ↗", self.card)
        btn_console.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_console.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #38BDF8;
                font-size: 12px;
                border: none;
                padding: 4px 0px;
            }
            QPushButton:hover { text-decoration: underline; }
        """
        )
        btn_console.clicked.connect(self._open_console)
        footer_layout.addWidget(btn_console)

        card_layout.addLayout(footer_layout)
        main_layout.addWidget(self.card)

    def _create_metric_card(self, title: str, value: str, subtitle: str) -> QFrame:
        f = QFrame(self.card)
        f.setStyleSheet(
            """
            QFrame {
                background-color: #1A1A1E;
                border: 1px solid #2E2E34;
                border-radius: 10px;
                padding: 10px 8px;
            }
        """
        )
        layout = QVBoxLayout(f)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        lbl_t = QLabel(title, f)
        lbl_t.setStyleSheet("font-size: 11px; color: #A1A1AA; font-weight: 500;")
        layout.addWidget(lbl_t)

        lbl_v = QLabel(value, f)
        lbl_v.setObjectName("val")
        lbl_v.setStyleSheet("font-size: 16px; font-weight: 700; color: #FAFAFA;")
        layout.addWidget(lbl_v)

        lbl_s = QLabel(subtitle, f)
        lbl_s.setObjectName("sub")
        lbl_s.setStyleSheet("font-size: 10px; color: #71717A;")
        layout.addWidget(lbl_s)

        return f

    def update_snapshot(self, snap: UsageSnapshot) -> None:
        """Updates all UI components from a UsageSnapshot."""
        self._last_snapshot = snap

        # Critical Blocked State Banner
        if snap.is_blocked:
            self.lbl_alert_text.setText(
                f"Limite {snap.bottleneck_label} Raggiunto ({int(snap.primary_utilization)}%)\nReset: {snap.primary_friendly_reset_str}"
            )
            self.alert_banner.setVisible(True)
            self.status_pill.setText(f"🚨 Quota Esaurita ({int(snap.primary_utilization)}%)")
            self.status_pill.setStyleSheet(
                """
                background-color: #3B1212;
                color: #FCA5A5;
                padding: 5px 10px;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #7F1D1D;
            """
            )
        else:
            self.alert_banner.setVisible(False)
            self.status_pill.setText(snap.status_label)
            self.status_pill.setStyleSheet(
                """
                background-color: #1E1E22;
                color: #A1A1AA;
                padding: 5px 10px;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 500;
                border: 1px solid #2E2E34;
            """
            )

        # Anomaly / Burn-rate Alert Banner
        if snap.is_burn_rate_abnormal and snap.anomaly_reason:
            self.anomaly_banner.setVisible(True)
            self.lbl_anomaly_text.setText(
                f"Consumo Anomalo Rilevato!\n{snap.anomaly_reason}"
            )
        else:
            self.anomaly_banner.setVisible(False)

        self.lbl_workspace.setText(snap.workspace_name)

        # Update Dual Row labels with friendly Italian timestamps
        pct_5h = int(snap.five_hour.utilization_pct)
        color_5h = "#EF4444" if pct_5h >= 90 else ("#F59E0B" if pct_5h >= 75 else "#D4D4D8")
        self.lbl_row_5h.setText(f"⏱️ Sessione 5h: {pct_5h}%  ({snap.five_hour.friendly_reset_str})")
        self.lbl_row_5h.setStyleSheet(f"color: {color_5h}; font-size: 11px; font-weight: {'600' if pct_5h >= 90 else '400'};")

        pct_7d = int(snap.seven_day.utilization_pct)
        color_7d = "#EF4444" if pct_7d >= 90 else ("#F59E0B" if pct_7d >= 75 else "#D4D4D8")
        self.lbl_row_7d.setText(f"📅 Settimanale: {pct_7d}%  ({snap.seven_day.friendly_reset_str})")
        self.lbl_row_7d.setStyleSheet(f"color: {color_7d}; font-size: 11px; font-weight: {'600' if pct_7d >= 90 else '400'};")

        # Determine which window to display on main gauge
        if self.active_tab == "7d" or (self.active_tab == "bottleneck" and snap.is_weekly_bottleneck):
            target_pct = snap.seven_day.utilization_pct
            target_friendly = snap.seven_day.friendly_reset_str
            self.lbl_gauge_title.setText("Limite Settimanale (7 Giorni)")
            self._style_tab_buttons(active="7d")
        else:
            target_pct = snap.five_hour.utilization_pct
            target_friendly = snap.five_hour.friendly_reset_str
            self.lbl_gauge_title.setText("Sessione Corrente (5 Ore)")
            self._style_tab_buttons(active="5h")

        self.gauge.set_percentage(target_pct)
        self.lbl_pct.setText(f"{int(target_pct)}%")
        if target_pct <= 0.0:
            self.lbl_reset_timer.setText("Plafond disponibile (nessun consumo)")
        else:
            burn_suffix = f" • 🔥 +{snap.burn_rate_per_min}%/m" if snap.burn_rate_per_min >= 0.5 else ""
            self.lbl_reset_timer.setText(f"Reset: {target_friendly}{burn_suffix}")

        # Update Tokens Cards
        val_in = self.card_in.findChild(QLabel, "val")
        sub_in = self.card_in.findChild(QLabel, "sub")
        if val_in and sub_in:
            val_in.setText(format_number(snap.tokens.input_tokens))
            sub_in.setText(f"{snap.tokens.cache_read_pct}% cache")

        val_out = self.card_out.findChild(QLabel, "val")
        if val_out:
            val_out.setText(format_number(snap.tokens.output_tokens))

        val_think = self.card_think.findChild(QLabel, "val")
        if val_think:
            val_think.setText(format_number(snap.tokens.thinking_tokens))

        # Context-aware button visibility
        is_connected = not snap.is_offline and not (
            snap.status_label and "Nessuna sessione" in snap.status_label
        )
        self.btn_logout.setVisible(is_connected)
        if is_connected:
            self.btn_login.setText("🔄 Riconnetti con Claude (1-Click)")
        else:
            self.btn_login.setText("🔑 Accedi con Claude (Login 1-Click)")

    def _select_window_tab(self, tab: str) -> None:
        """Switches the main gauge between 5-Hour and 7-Day window views."""
        self.active_tab = tab
        if hasattr(self, "_last_snapshot") and self._last_snapshot:
            self.update_snapshot(self._last_snapshot)

    def _style_tab_buttons(self, active: str) -> None:
        active_style = """
            QPushButton {
                background-color: #27272A;
                color: #FFFFFF;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 600;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: transparent;
                color: #71717A;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                color: #A1A1AA;
                background-color: #1A1A1E;
            }
        """
        if active == "7d":
            self.btn_tab_7d.setStyleSheet(active_style)
            self.btn_tab_5h.setStyleSheet(inactive_style)
        else:
            self.btn_tab_5h.setStyleSheet(active_style)
            self.btn_tab_7d.setStyleSheet(inactive_style)

    def toggle_at_tray(self, tray_geo: QRect) -> None:
        """Shows/hides the flyout positioned relative to the tray icon."""
        if self.isVisible():
            self.hide()
        else:
            pos = WindowPositioner.calculate_flyout_position(self.width(), self.height(), tray_geo)
            self.move(pos)
            self.show()
            self.activateWindow()

    def _toggle_settings_page(self) -> None:
        if self.stacked_layout.currentIndex() == 0:
            self.stacked_layout.setCurrentIndex(1)
            self.btn_toggle_settings.setText("⬅ Torna a Metriche")
        else:
            self.stacked_layout.setCurrentIndex(0)
            self.btn_toggle_settings.setText("⚙️ Impostazioni")

    def _show_help_section(self) -> None:
        """Navigates to the Settings & Help page."""
        self.stacked_layout.setCurrentIndex(1)
        self.btn_toggle_settings.setText("⬅ Torna a Metriche")

    def _toggle_threshold_chip(self, val: int) -> None:
        """Toggles a percentage value in the thresholds input field."""
        current = self._parse_current_thresholds()
        if val in current:
            current.remove(val)
        else:
            current.append(val)
        current.sort()
        self.txt_thresholds.setText(", ".join(str(x) for x in current))
        self._sync_threshold_chips()

    def _parse_current_thresholds(self) -> list[int]:
        raw = self.txt_thresholds.text()
        parsed: list[int] = []
        for part in raw.replace(";", ",").replace(" ", ",").split(","):
            part = part.strip()
            if part.isdigit():
                v = int(part)
                if 1 <= v <= 100 and v not in parsed:
                    parsed.append(v)
        return sorted(parsed)

    def _sync_threshold_chips(self) -> None:
        """Highlights the chip buttons that are currently active in the text field."""
        if not hasattr(self, "_threshold_chips") or not self._threshold_chips:
            return
        current = self._parse_current_thresholds()
        active_style = """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: 1px solid #3B82F6;
                border-radius: 6px;
                padding: 4px 6px;
                font-size: 11px;
                font-weight: 600;
                min-height: 26px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """
        inactive_style = """
            QPushButton {
                background-color: #222226;
                color: #A1A1AA;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 4px 6px;
                font-size: 11px;
                font-weight: 500;
                min-height: 26px;
            }
            QPushButton:hover {
                background-color: #2E2E34;
                color: #FAFAFA;
            }
        """
        for val, btn in self._threshold_chips.items():
            btn.setStyleSheet(active_style if val in current else inactive_style)

    def _save_settings_action(self) -> None:
        self.config.notifications_enabled = self.chk_notif.isChecked()
        self.config.burn_rate_alert_enabled = self.chk_burn_rate.isChecked()
        self.config.mock_mode = self.chk_mock.isChecked()
        parsed_thresh = self._parse_current_thresholds()
        self.config.thresholds = parsed_thresh if parsed_thresh else [80, 95, 100]
        admin_key = self.txt_admin_key.text().strip()
        self.config.admin_api_key = admin_key if admin_key else None
        save_config(self.config)
        self._toggle_settings_page()
        self.refresh_requested.emit()

    def _open_console(self) -> None:
        url = (
            "https://console.anthropic.com/settings/usage"
            if self.config.admin_api_key
            else "https://claude.ai/settings/usage"
        )
        webbrowser.open(url)

    def _start_quick_login(self) -> None:
        """Launches the 1-click official Claude Code browser login in background."""
        self.btn_login.setEnabled(False)
        self.btn_login.setText("⏳ In attesa login...")
        self.btn_cancel_login.setVisible(True)
        self.lbl_login_status.setText("Apertura finestra di login in corso...")

        def update_status(text: str) -> None:
            self.lbl_login_status.setText(text)

        async def login_task() -> None:
            success = await ClaudeLoginHelper.execute_login(status_callback=update_status)
            self.btn_login.setEnabled(True)
            self.btn_cancel_login.setVisible(False)
            if success:
                self.btn_login.setText("✅ Accesso Completato!")
                self.lbl_login_status.setText("Sessione Claude Code registrata con successo.")
                self.btn_logout.setVisible(True)
                self.refresh_requested.emit()
            else:
                self.btn_login.setText("🔑 Accedi con Claude (Login 1-Click)")

        asyncio.create_task(login_task())

    def _cancel_quick_login(self) -> None:
        """Cancels the active login attempt."""
        ClaudeLoginHelper.cancel_login()
        self.btn_login.setEnabled(True)
        self.btn_login.setText("🔑 Accedi con Claude (Login 1-Click)")
        self.btn_cancel_login.setVisible(False)
        self.lbl_login_status.setText("Login annullato. Puoi riprovare in qualsiasi momento.")

    def _perform_logout(self) -> None:
        """Clears local credentials and triggers logout state."""
        ClaudeLoginHelper.logout()
        self.btn_login.setText("🔑 Accedi con Claude (Login 1-Click)")
        self.btn_login.setEnabled(True)
        self.btn_logout.setVisible(False)
        self.lbl_login_status.setText("Disconnessione effettuata. Clicca su 'Accedi' per riconnetterti.")
        self.logout_requested.emit()
