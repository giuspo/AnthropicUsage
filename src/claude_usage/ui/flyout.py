"""Micro-Flyout borderless popup window for Claude Code Usage Widget."""

from __future__ import annotations

import asyncio
import webbrowser
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QRect, QTimer, Qt, pyqtSignal
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
from claude_usage.autostart import is_autostart_enabled, set_autostart
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
    """Custom paint widget rendering a semi-circular radial gauge with centered percentage."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(240, 122)
        self.pct: float = 0.0

    def set_percentage(self, pct: float) -> None:
        self.pct = max(0.0, min(100.0, pct))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = QRect(20, 14, 200, 196)
        start_angle = 180 * 16
        full_span = -180 * 16

        # Background Arc
        bg_pen = QPen(QColor(255, 255, 255, 25), 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
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
            fg_pen = QPen(color, 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(fg_pen)
            painter.drawArc(rect, start_angle, span_angle)

        # Draw Percentage Text crisply inside the center of the semi-circle
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 24, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = QRect(0, 48, self.width(), 54)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{int(round(self.pct))}%")


class MicroFlyoutWindow(QWidget):
    """Borderless floating panel anchored near the system tray icon.

    Structured in 3 distinct views via a bottom segmented navigation bar:
      - Page 0: 📊 Metriche (Gauge, 5h/7d switch, Tokens, Alert banners)
      - Page 1: ⚙️ Impostazioni (Account 1-Click, Thresholds, Anti-Loop, API Key)
      - Page 2: ℹ️ Info & Help (Version badge, Creator giuspo, Purpose, 4-Step Guide, GPLv3)
    """

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
        self.setFixedSize(392, 560)

        app_icon_path = IconRenderer.get_app_icon_path()
        if app_icon_path.exists():
            self.setWindowIcon(QIcon(str(app_icon_path)))

        # Listen for window focus events to auto-dismiss on click outside
        self.installEventFilter(self)

        self._init_ui()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self and event.type() == QEvent.Type.WindowDeactivate:
            self.hide()
            return True
        return super().eventFilter(obj, event)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        self.card = QFrame(self)
        self.card.setObjectName("MainCard")
        # IMPORTANT: Use explicit ID/class selectors (#SectionCard, #AlertBanner, etc.)
        # so QFrame rules NEVER cascade onto child QLabels (since QLabel inherits QFrame).
        self.card.setStyleSheet(
            """
            QFrame#MainCard {
                background-color: #121214;
                border: 1px solid #27272A;
                border-radius: 16px;
            }
            QFrame#SectionCard {
                background-color: #18181C;
                border: 1px solid #27272A;
                border-radius: 10px;
            }
            QFrame#HeroCard {
                background-color: #161F2C;
                border: 1px solid #1E3A5F;
                border-radius: 12px;
            }
            QFrame#StepCard {
                background-color: #18181C;
                border: 1px solid #26262B;
                border-radius: 8px;
            }
            QFrame#AlertBanner {
                background-color: rgba(239, 68, 68, 0.14);
                border: 1px solid #EF4444;
                border-radius: 8px;
            }
            QFrame#AnomalyBanner {
                background-color: rgba(245, 158, 11, 0.14);
                border: 1px solid #F59E0B;
                border-radius: 8px;
            }
            QFrame#NavFooter {
                background-color: #18181C;
                border: 1px solid #27272A;
                border-radius: 10px;
            }
            QLabel {
                color: #F4F4F5;
                background: transparent;
                border: none;
                padding: 0px;
                font-family: 'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif;
            }
            QCheckBox {
                color: #E4E4E7;
                font-size: 12px;
                spacing: 8px;
                background: transparent;
                border: none;
            }
        """
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        # =====================================================================
        # 1. TOP HEADER BAR (Persistent across views)
        # =====================================================================
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
        self.version_pill.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.version_pill.setToolTip(f"Versione {__version__} (Major.Minor.Compilation)")
        header_layout.addWidget(self.version_pill)

        btn_console = QPushButton("Console ↗", self.card)
        btn_console.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_console.setToolTip("Apri dashboard consumi Anthropic nel browser")
        btn_console.setStyleSheet(
            """
            QPushButton {
                background-color: #1E1E22;
                color: #38BDF8;
                font-size: 11px;
                font-weight: 600;
                border-radius: 7px;
                border: 1px solid #2E2E34;
                padding: 4px 8px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #27272E;
                color: #7DD3FC;
            }
        """
        )
        btn_console.clicked.connect(self._open_console)
        header_layout.addWidget(btn_console)

        self.btn_refresh = QPushButton("↻", self.card)
        self.btn_refresh.setFixedSize(28, 28)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setToolTip("Aggiorna metriche adesso")
        self.btn_refresh.setStyleSheet(
            """
            QPushButton {
                background-color: #1E1E22;
                color: #FAFAFA;
                border-radius: 7px;
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

        # =====================================================================
        # 2. STACKED CONTENT AREA (3 Dedicated Pages)
        # =====================================================================
        self.stacked_widget = QWidget(self.card)
        self.stacked_layout = QStackedLayout(self.stacked_widget)

        self._init_metrics_page()   # Index 0: 📊 Metriche
        self._init_settings_page()  # Index 1: ⚙️ Impostazioni
        self._init_help_page()      # Index 2: ℹ️ Info & Help

        card_layout.addWidget(self.stacked_widget, stretch=1)

        # =====================================================================
        # 3. BOTTOM NAVIGATION BAR (3 Equal-Width Segmented Tabs)
        # =====================================================================
        nav_frame = QFrame(self.card)
        nav_frame.setObjectName("NavFooter")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(4)

        self.btn_nav_metrics = QPushButton("📊 Metriche", nav_frame)
        self.btn_nav_metrics.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_metrics.clicked.connect(lambda: self.switch_page(0))

        self.btn_nav_settings = QPushButton("⚙️ Impostazioni", nav_frame)
        self.btn_nav_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_settings.clicked.connect(lambda: self.switch_page(1))

        self.btn_nav_help = QPushButton("ℹ️ Guida && Info", nav_frame)
        self.btn_nav_help.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_help.clicked.connect(lambda: self.switch_page(2))

        nav_layout.addWidget(self.btn_nav_metrics, stretch=1)
        nav_layout.addWidget(self.btn_nav_settings, stretch=1)
        nav_layout.addWidget(self.btn_nav_help, stretch=1)

        # Legacy alias for backwards compatibility
        self.btn_toggle_settings = self.btn_nav_settings

        card_layout.addWidget(nav_frame)
        main_layout.addWidget(self.card)

        self._update_nav_styles(0)

    # =========================================================================
    # PAGE 0: METRICS VIEW
    # =========================================================================
    def _init_metrics_page(self) -> None:
        self.metrics_view = QWidget()
        vbox_metrics = QVBoxLayout(self.metrics_view)
        vbox_metrics.setContentsMargins(0, 0, 0, 0)
        vbox_metrics.setSpacing(8)

        # Workspace Title (Inside Metrics Page so it doesn't clutter Settings/Help)
        self.lbl_workspace = QLabel("Claude Code", self.metrics_view)
        self.lbl_workspace.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        vbox_metrics.addWidget(self.lbl_workspace)

        # Critical Alert Banner (Shown when 5h or 7d limit is reached)
        self.alert_banner = QFrame(self.metrics_view)
        self.alert_banner.setObjectName("AlertBanner")
        alert_layout = QHBoxLayout(self.alert_banner)
        alert_layout.setContentsMargins(10, 7, 10, 7)
        alert_layout.setSpacing(8)

        lbl_alert_icon = QLabel("🚨", self.alert_banner)
        lbl_alert_icon.setStyleSheet("font-size: 15px;")
        alert_layout.addWidget(lbl_alert_icon)

        self.lbl_alert_text = QLabel("Limite Settimanale Raggiunto (100%)\nReset tra --", self.alert_banner)
        self.lbl_alert_text.setWordWrap(True)
        self.lbl_alert_text.setStyleSheet("color: #FCA5A5; font-size: 11px; font-weight: 600;")
        alert_layout.addWidget(self.lbl_alert_text, stretch=1)
        self.alert_banner.setVisible(False)
        vbox_metrics.addWidget(self.alert_banner)

        # Anomaly / Burn-rate Alert Banner
        self.anomaly_banner = QFrame(self.metrics_view)
        self.anomaly_banner.setObjectName("AnomalyBanner")
        anomaly_layout = QHBoxLayout(self.anomaly_banner)
        anomaly_layout.setContentsMargins(10, 7, 10, 7)
        anomaly_layout.setSpacing(8)

        lbl_anomaly_icon = QLabel("🔥", self.anomaly_banner)
        lbl_anomaly_icon.setStyleSheet("font-size: 15px;")
        anomaly_layout.addWidget(lbl_anomaly_icon)

        self.lbl_anomaly_text = QLabel("Consumo anomalo rilevato", self.anomaly_banner)
        self.lbl_anomaly_text.setWordWrap(True)
        self.lbl_anomaly_text.setStyleSheet("color: #FCD34D; font-size: 11px; font-weight: 600;")
        anomaly_layout.addWidget(self.lbl_anomaly_text, stretch=1)
        self.anomaly_banner.setVisible(False)
        vbox_metrics.addWidget(self.anomaly_banner)

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
        gauge_container = QWidget(self.metrics_view)
        gauge_layout = QVBoxLayout(gauge_container)
        gauge_layout.setContentsMargins(0, 0, 0, 0)
        gauge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gauge = SemiCircleGauge(gauge_container)
        gauge_layout.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_pct = QLabel("0%", gauge_container)
        self.lbl_pct.setVisible(False)

        self.lbl_reset_timer = QLabel("Reset in --", gauge_container)
        self.lbl_reset_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_reset_timer.setStyleSheet("font-size: 12px; color: #A1A1AA; margin-top: 2px; margin-bottom: 1px;")
        gauge_layout.addWidget(self.lbl_reset_timer)

        self.lbl_gauge_title = QLabel("Sessione 5 Ore", gauge_container)
        self.lbl_gauge_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_gauge_title.setStyleSheet(
            "font-size: 10px; color: #71717A; text-transform: uppercase; letter-spacing: 1px;"
        )
        gauge_layout.addWidget(self.lbl_gauge_title)

        vbox_metrics.addWidget(gauge_container)

        # Dual Quota Overview Card (5h + 7d side-by-side summary)
        dual_card = QFrame(self.metrics_view)
        dual_card.setObjectName("SectionCard")
        dual_layout = QVBoxLayout(dual_card)
        dual_layout.setContentsMargins(12, 8, 12, 8)
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
    # PAGE 1: SETTINGS VIEW (Clean, Direct Full-Width Layout, Zero Clipping)
    # =========================================================================
    def _init_settings_page(self) -> None:
        self.settings_view = QWidget()
        vbox_settings = QVBoxLayout(self.settings_view)
        vbox_settings.setContentsMargins(0, 0, 0, 0)
        vbox_settings.setSpacing(8)

        # --- CARD 1: ACCOUNT & AUTENTICAZIONE ---
        card_auth = QFrame(self.settings_view)
        card_auth.setObjectName("SectionCard")
        layout_auth = QVBoxLayout(card_auth)
        layout_auth.setContentsMargins(10, 8, 10, 8)
        layout_auth.setSpacing(6)

        lbl_auth_sec = QLabel("🔐 Account Claude Code", card_auth)
        lbl_auth_sec.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        layout_auth.addWidget(lbl_auth_sec)

        auth_btn_layout = QHBoxLayout()
        auth_btn_layout.setSpacing(6)

        self.btn_login = QPushButton("🔑 Accedi con Claude (1-Click)", card_auth)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFixedHeight(30)
        self.btn_login.setStyleSheet(
            """
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                padding: 0px 10px;
                border-radius: 7px;
                font-size: 11px;
                font-weight: 600;
                border: none;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #27272A; color: #71717A; }
        """
        )
        self.btn_login.clicked.connect(self._start_quick_login)
        auth_btn_layout.addWidget(self.btn_login, stretch=3)

        self.btn_cancel_login = QPushButton("✕ Annulla", card_auth)
        self.btn_cancel_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_login.setFixedHeight(30)
        self.btn_cancel_login.setStyleSheet(
            """
            QPushButton {
                background-color: #27272A;
                color: #A1A1AA;
                padding: 0px 8px;
                border-radius: 7px;
                font-size: 11px;
                font-weight: 500;
                border: 1px solid #3F3F46;
            }
            QPushButton:hover { background-color: #3F3F46; color: #FFFFFF; }
        """
        )
        self.btn_cancel_login.clicked.connect(self._cancel_quick_login)
        self.btn_cancel_login.setVisible(False)
        auth_btn_layout.addWidget(self.btn_cancel_login, stretch=1)

        self.btn_logout = QPushButton("🚪 Disconnetti", card_auth)
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setFixedHeight(30)
        self.btn_logout.setStyleSheet(
            """
            QPushButton {
                background-color: #222226;
                color: #F87171;
                padding: 0px 10px;
                border-radius: 7px;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #3F2323;
            }
            QPushButton:hover {
                background-color: #381A1A;
                border-color: #5C2424;
            }
        """
        )
        self.btn_logout.clicked.connect(self._perform_logout)
        auth_btn_layout.addWidget(self.btn_logout, stretch=2)

        layout_auth.addLayout(auth_btn_layout)

        self.lbl_login_status = QLabel("", card_auth)
        self.lbl_login_status.setStyleSheet("color: #38BDF8; font-size: 10px;")
        self.lbl_login_status.setWordWrap(True)
        self.lbl_login_status.setVisible(False)
        layout_auth.addWidget(self.lbl_login_status)

        vbox_settings.addWidget(card_auth)

        # --- CARD 2: NOTIFICHE & SOGLIE ---
        card_notif = QFrame(self.settings_view)
        card_notif.setObjectName("SectionCard")
        layout_notif = QVBoxLayout(card_notif)
        layout_notif.setContentsMargins(10, 8, 10, 8)
        layout_notif.setSpacing(6)

        lbl_notif_sec = QLabel("🔔 Notifiche & Soglie di Alert", card_notif)
        lbl_notif_sec.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        layout_notif.addWidget(lbl_notif_sec)

        self.chk_notif = QCheckBox("Abilita Notifiche Push Native", card_notif)
        self.chk_notif.setChecked(self.config.notifications_enabled)
        self.chk_notif.setCursor(Qt.CursorShape.PointingHandCursor)
        layout_notif.addWidget(self.chk_notif)

        lbl_thresh_title = QLabel("Soglie attive (% di quota) — clicca sui chip o digita:", card_notif)
        lbl_thresh_title.setWordWrap(True)
        lbl_thresh_title.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        layout_notif.addWidget(lbl_thresh_title)

        # Quick-toggle chips row (6 compact pills on 1 row)
        grid_chips = QHBoxLayout()
        grid_chips.setContentsMargins(0, 0, 0, 0)
        grid_chips.setSpacing(5)
        self._threshold_chips: dict[int, QPushButton] = {}
        preset_values = [50, 75, 80, 90, 95, 100]

        for val in preset_values:
            btn = QPushButton(f"{val}%", card_notif)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, v=val: self._toggle_threshold_chip(v))
            grid_chips.addWidget(btn, stretch=1)
            self._threshold_chips[val] = btn

        layout_notif.addLayout(grid_chips)

        self.txt_thresholds = QLineEdit(card_notif)
        self.txt_thresholds.setFixedHeight(28)
        self.txt_thresholds.setText(", ".join(str(t) for t in sorted(self.config.thresholds)))
        self.txt_thresholds.setPlaceholderText("Valori separati da virgola, es. 50, 75, 80, 95, 100")
        self.txt_thresholds.setStyleSheet(
            """
            QLineEdit {
                background-color: #121214;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 0px 8px;
                font-size: 11px;
            }
            QLineEdit:focus { border-color: #3B82F6; }
        """
        )
        layout_notif.addWidget(self.txt_thresholds)
        self.txt_thresholds.textChanged.connect(self._sync_threshold_chips)
        self._sync_threshold_chips()

        # Note: Use '&&' to escape ampersand in Qt QCheckBox so it displays '&' properly
        self.chk_burn_rate = QCheckBox("🔥 Avviso Consumo Rapido (Spike && Loop)", card_notif)
        self.chk_burn_rate.setChecked(self.config.burn_rate_alert_enabled)
        self.chk_burn_rate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_burn_rate.setToolTip(
            "Invia un avviso se il consumo cresce oltre +15% in meno di 10 minuti o oltre 35k token in un singolo turno."
        )
        layout_notif.addWidget(self.chk_burn_rate)

        lbl_burn_desc = QLabel("Avvisa se la quota sale oltre +15% in <10m o per picchi anomali di token.", card_notif)
        lbl_burn_desc.setWordWrap(True)
        lbl_burn_desc.setStyleSheet("color: #71717A; font-size: 10px;")
        layout_notif.addWidget(lbl_burn_desc)

        vbox_settings.addWidget(card_notif)

        # --- CARD 3: AVANZATE & TOKEN MANUALE ---
        card_key = QFrame(self.settings_view)
        card_key.setObjectName("SectionCard")
        layout_key = QVBoxLayout(card_key)
        layout_key.setContentsMargins(10, 8, 10, 8)
        layout_key.setSpacing(5)

        lbl_key_sec = QLabel("🛠️ Avanzate & Chiave API (Opzionale)", card_key)
        lbl_key_sec.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        layout_key.addWidget(lbl_key_sec)

        self.txt_admin_key = QLineEdit(card_key)
        self.txt_admin_key.setFixedHeight(28)
        self.txt_admin_key.setPlaceholderText("Admin Key (sk-ant-admin-...) o Token OAuth manuale")
        self.txt_admin_key.setEchoMode(QLineEdit.EchoMode.Password)
        if self.config.admin_api_key:
            self.txt_admin_key.setText(self.config.admin_api_key)
        self.txt_admin_key.setStyleSheet(
            """
            QLineEdit {
                background-color: #121214;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 0px 8px;
                font-size: 11px;
            }
            QLineEdit:focus { border-color: #3B82F6; }
        """
        )
        layout_key.addWidget(self.txt_admin_key)

        self.chk_mock = QCheckBox("Modalità Simulazione Demo (Mock Mode)", card_key)
        self.chk_mock.setChecked(self.config.mock_mode)
        self.chk_mock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_mock.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        layout_key.addWidget(self.chk_mock)

        self.chk_autostart = QCheckBox("🚀 Avvia all'accesso di Windows (Autostart)", card_key)
        self.chk_autostart.setChecked(is_autostart_enabled())
        self.chk_autostart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autostart.setStyleSheet("color: #E4E4E7; font-size: 11px;")
        layout_key.addWidget(self.chk_autostart)

        vbox_settings.addWidget(card_key)
        vbox_settings.addStretch()

        # Pinned Save Button at the bottom of Settings Page
        self.btn_save_settings = QPushButton("💾 Salva Impostazioni", self.settings_view)
        self.btn_save_settings.setFixedHeight(32)
        self.btn_save_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_settings.setStyleSheet(
            """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                padding: 0px 14px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                border: none;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """
        )
        self.btn_save_settings.clicked.connect(self._save_settings_action)
        vbox_settings.addWidget(self.btn_save_settings)

        self.stacked_layout.addWidget(self.settings_view)

    # =========================================================================
    # PAGE 2: HELP & ABOUT VIEW (Dedicated Separate Page)
    # =========================================================================
    def _init_help_page(self) -> None:
        self.help_view = QWidget()
        vbox_help = QVBoxLayout(self.help_view)
        vbox_help.setContentsMargins(0, 0, 0, 0)
        vbox_help.setSpacing(7)

        # --- HERO CARD: APP IDENTITY, VERSION & AUTHOR ---
        hero_card = QFrame(self.help_view)
        hero_card.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(12, 9, 12, 9)
        hero_layout.setSpacing(4)

        top_hero_row = QHBoxLayout()
        lbl_app_title = QLabel("Claude Code Usage Widget", hero_card)
        lbl_app_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        top_hero_row.addWidget(lbl_app_title)
        top_hero_row.addStretch()

        lbl_ver_badge = QLabel(f"v{__version__}", hero_card)
        lbl_ver_badge.setStyleSheet(
            """
            background-color: #0284C7;
            color: #F0F9FF;
            font-weight: 700;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 6px;
            border: 1px solid #38BDF8;
        """
        )
        top_hero_row.addWidget(lbl_ver_badge)
        hero_layout.addLayout(top_hero_row)

        lbl_creator = QLabel("Ideato e sviluppato da <b>giuspo</b> 🚀", hero_card)
        lbl_creator.setStyleSheet("color: #38BDF8; font-size: 11px;")
        hero_layout.addWidget(lbl_creator)

        lbl_schema = QLabel(
            f"📦 <b>Versione {__version__}</b> &nbsp;•&nbsp; <span style='color:#94A3B8;'>Schema: Major.Minor.Compilation</span>",
            hero_card,
        )
        lbl_schema.setStyleSheet("color: #E2E8F0; font-size: 10px;")
        hero_layout.addWidget(lbl_schema)

        lbl_license = QLabel("🛡️ Licenza: GNU GPLv3 (GPL-3.0) • Open Source Copyleft", hero_card)
        lbl_license.setWordWrap(True)
        lbl_license.setStyleSheet("color: #94A3B8; font-size: 10px;")
        hero_layout.addWidget(lbl_license)

        vbox_help.addWidget(hero_card)

        # --- CARD: SCOPO DELL'APPLICAZIONE ---
        purpose_card = QFrame(self.help_view)
        purpose_card.setObjectName("SectionCard")
        purpose_layout = QVBoxLayout(purpose_card)
        purpose_layout.setContentsMargins(10, 8, 10, 8)
        purpose_layout.setSpacing(4)

        lbl_purpose_title = QLabel("🎯 Scopo del Programma", purpose_card)
        lbl_purpose_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #FFFFFF;")
        purpose_layout.addWidget(lbl_purpose_title)

        lbl_purpose_body = QLabel(
            "Monitora in tempo reale dalla barra di sistema le quote d'uso (Sessione 5h e Settimanale 7g) "
            "e i token (Input, Output, Thinking 🧠) del tuo account Claude Code, avvisandoti prima "
            "di esaurire il plafond senza dover aprire il browser.",
            purpose_card,
        )
        lbl_purpose_body.setWordWrap(True)
        lbl_purpose_body.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        purpose_layout.addWidget(lbl_purpose_body)

        vbox_help.addWidget(purpose_card)

        # --- CARD: COME SI UTILIZZA (4 STEP CHIARI) ---
        guide_card = QFrame(self.help_view)
        guide_card.setObjectName("SectionCard")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(10, 8, 10, 8)
        guide_layout.setSpacing(5)

        lbl_guide_title = QLabel("💡 Come si Utilizza", guide_card)
        lbl_guide_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #FFFFFF;")
        guide_layout.addWidget(lbl_guide_title)

        steps = [
            (
                "1. Anello nella Tray",
                "Verde (<75%), Giallo (75-90%), Rosso (>90%). Passa il mouse sopra per l'orario di reset.",
            ),
            (
                "2. Metriche 5h & 7g",
                "Clicca sull'icona per vedere il tachimetro, i token Thinking e passare tra 5h e Settimanale.",
            ),
            (
                "3. Login 1-Click",
                "In 'Impostazioni' clicca su 'Accedi (1-Click)' per autenticarti via browser in automatico.",
            ),
            (
                "4. Alert & Anti-Loop",
                "Attiva i chip percentuali: riceverai notifiche push per soglie o picchi anomali di token.",
            ),
        ]

        steps_grid = QGridLayout()
        steps_grid.setContentsMargins(0, 0, 0, 0)
        steps_grid.setHorizontalSpacing(6)
        steps_grid.setVerticalSpacing(6)

        for idx, (step_title, step_desc) in enumerate(steps):
            step_box = QFrame(guide_card)
            step_box.setObjectName("StepCard")
            step_v = QVBoxLayout(step_box)
            step_v.setContentsMargins(8, 6, 8, 6)
            step_v.setSpacing(2)

            lbl_st = QLabel(step_title, step_box)
            lbl_st.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 700;")
            step_v.addWidget(lbl_st)

            lbl_sd = QLabel(step_desc, step_box)
            lbl_sd.setWordWrap(True)
            lbl_sd.setStyleSheet("color: #D4D4D8; font-size: 10px;")
            step_v.addWidget(lbl_sd)
            step_v.addStretch()

            steps_grid.addWidget(step_box, idx // 2, idx % 2)

        guide_layout.addLayout(steps_grid)

        vbox_help.addWidget(guide_card)
        vbox_help.addStretch()

        self.stacked_layout.addWidget(self.help_view)

    def _create_metric_card(self, title: str, value: str, subtitle: str) -> QFrame:
        f = QFrame(self.metrics_view)
        f.setObjectName("SectionCard")
        layout = QVBoxLayout(f)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

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

    # =========================================================================
    # NAVIGATION & STATE UPDATES
    # =========================================================================
    def switch_page(self, index: int) -> None:
        """Switches the main stacked layout to page 0 (Metrics), 1 (Settings), or 2 (Help)."""
        self.stacked_layout.setCurrentIndex(index)
        self._update_nav_styles(index)

    def _update_nav_styles(self, active_index: int) -> None:
        active_qss = """
            QPushButton {
                background-color: #27272E;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 700;
                border: 1px solid #3B82F6;
                border-radius: 7px;
                padding: 6px 4px;
            }
        """
        inactive_qss = """
            QPushButton {
                background-color: transparent;
                color: #A1A1AA;
                font-size: 11px;
                font-weight: 500;
                border: 1px solid transparent;
                border-radius: 7px;
                padding: 6px 4px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: #202025;
            }
        """
        buttons = [self.btn_nav_metrics, self.btn_nav_settings, self.btn_nav_help]
        for idx, btn in enumerate(buttons):
            btn.setStyleSheet(active_qss if idx == active_index else inactive_qss)

    def _toggle_settings_page(self) -> None:
        if self.stacked_layout.currentIndex() == 1:
            self.switch_page(0)
        else:
            self.switch_page(1)

    def _show_settings_section(self) -> None:
        self.switch_page(1)

    def _show_help_section(self) -> None:
        self.switch_page(2)

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
            self.btn_login.setText("🔄 Riconnetti (1-Click)")
        else:
            self.btn_login.setText("🔑 Accedi con Claude (1-Click)")

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
                padding: 0px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """
        inactive_style = """
            QPushButton {
                background-color: #222226;
                color: #A1A1AA;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 0px;
                font-size: 11px;
                font-weight: 500;
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
        
        # Update autostart if toggled
        new_autostart = self.chk_autostart.isChecked()
        if new_autostart != is_autostart_enabled():
            set_autostart(new_autostart)
        self.config.autostart_enabled = new_autostart

        parsed_thresh = self._parse_current_thresholds()
        self.config.thresholds = parsed_thresh if parsed_thresh else [80, 95, 100]
        admin_key = self.txt_admin_key.text().strip()
        self.config.admin_api_key = admin_key if admin_key else None
        save_config(self.config)

        # Visual confirmation before returning to Metrics
        self.btn_save_settings.setText("✅ Impostazioni Salvate!")
        QTimer.singleShot(450, lambda: self.btn_save_settings.setText("💾 Salva Impostazioni"))
        QTimer.singleShot(450, lambda: self.switch_page(0))
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
        self.lbl_login_status.setVisible(True)
        self.lbl_login_status.setText("Apertura finestra di login in corso...")

        def update_status(text: str) -> None:
            self.lbl_login_status.setVisible(True)
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
                self.btn_login.setText("🔑 Accedi con Claude (1-Click)")

        asyncio.create_task(login_task())

    def _cancel_quick_login(self) -> None:
        """Cancels the active login attempt."""
        ClaudeLoginHelper.cancel_login()
        self.btn_login.setEnabled(True)
        self.btn_login.setText("🔑 Accedi con Claude (1-Click)")
        self.btn_cancel_login.setVisible(False)
        self.lbl_login_status.setVisible(True)
        self.lbl_login_status.setText("Login annullato. Puoi riprovare in qualsiasi momento.")

    def _perform_logout(self) -> None:
        """Clears local credentials and triggers logout state."""
        ClaudeLoginHelper.logout()
        self.btn_login.setText("🔑 Accedi con Claude (1-Click)")
        self.btn_login.setEnabled(True)
        self.btn_logout.setVisible(False)
        self.lbl_login_status.setVisible(True)
        self.lbl_login_status.setText("Disconnessione effettuata. Clicca su 'Accedi' per riconnetterti.")
        self.logout_requested.emit()
