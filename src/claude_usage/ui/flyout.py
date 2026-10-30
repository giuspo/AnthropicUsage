"""Micro-Flyout borderless popup window for Claude & Antigravity Usage Widget."""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from claude_usage import __version__
from claude_usage.autostart import is_autostart_enabled, set_autostart
from claude_usage.config import AppConfig, save_config
from claude_usage.core.antigravity_auth import AntigravityAuthManager, AntigravityLoginHelper
from claude_usage.core.login_helper import ClaudeLoginHelper
from claude_usage.core.models import (
    AntigravityUsageSnapshot,
    CompositeUsageSnapshot,
    PartnerModelQuota,
    UsageSnapshot,
)
from claude_usage.ui.icon_renderer import IconRenderer
from claude_usage.ui.positioner import WindowPositioner
from claude_usage.ui.theme import COLOR_CRITICAL, COLOR_WARNING

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
CHECK_SVG_PATH = RESOURCES_DIR / "check.svg"


def format_number(val: int) -> str:
    """Formats large token counts into human readable strings."""
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}k"
    return str(val)


class SemiCircleGauge(QWidget):
    """Custom paint widget rendering a semi-circular radial gauge with centered percentage."""

    def __init__(self, color_theme: str = "cyan", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(240, 122)
        self.pct: float = 0.0
        self.color_theme = color_theme  # "cyan" or "blue"

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
            if self.color_theme == "blue":
                color = QColor(96, 165, 250)  # Google Azure
            else:
                color = QColor(56, 189, 248)  # Electric Cyan

        span_angle = int((-180 * 16) * (self.pct / 100.0))
        if abs(span_angle) > 0:
            fg_pen = QPen(color, 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(fg_pen)
            painter.drawArc(rect, start_angle, span_angle)

        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 24, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = QRect(0, 48, self.width(), 54)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{int(round(self.pct))}%")


class MicroFlyoutWindow(QWidget):
    """Borderless floating panel anchored near the system tray icon.

    Structured into:
      - Page 0: 📊 Metriche (Panoramica, Claude Code, Google Antigravity)
      - Page 1: ⚙️ Impostazioni (Servizi, Account 1-Click, Soglie, Stile Icona)
      - Page 2: ℹ️ Info & Help (v2.0.0, Autore giuspo, Guida Operativa, GPLv3)
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
        self.setFixedSize(416, 626)

        self._active_metrics_subview = "overview"  # "overview", "claude", "antigravity"
        self._active_claude_tab = "5h"             # "5h" or "7d"
        self._last_composite: Optional[CompositeUsageSnapshot] = None
        self._last_snapshot: Optional[UsageSnapshot] = None

        app_icon_path = IconRenderer.get_app_icon_path()
        if app_icon_path.exists():
            self.setWindowIcon(QIcon(str(app_icon_path)))

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

        chk_svg_str = CHECK_SVG_PATH.as_posix() if CHECK_SVG_PATH.exists() else ""

        self.card = QFrame(self)
        self.card.setObjectName("MainCard")
        self.card.setStyleSheet(
            f"""
            QFrame#MainCard {{
                background-color: #121214;
                border: 1px solid #27272A;
                border-radius: 16px;
            }}
            QFrame#SectionCard {{
                background-color: #18181C;
                border: 1px solid #27272A;
                border-radius: 10px;
            }}
            QFrame#HeroCard {{
                background-color: #161F2C;
                border: 1px solid #1E3A5F;
                border-radius: 12px;
            }}
            QFrame#AlertBanner {{
                background-color: rgba(239, 68, 68, 0.14);
                border: 1px solid #EF4444;
                border-radius: 8px;
            }}
            QFrame#AnomalyBanner {{
                background-color: rgba(245, 158, 11, 0.14);
                border: 1px solid #F59E0B;
                border-radius: 8px;
            }}
            QFrame#NavFooter {{
                background-color: #18181C;
                border: 1px solid #27272A;
                border-radius: 10px;
            }}
            QLabel {{
                color: #F4F4F5;
                background: transparent;
                border: none;
                padding: 0px;
                font-family: 'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #3F3F46;
                min-height: 24px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #52525B;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QCheckBox {{
                color: #E4E4E7;
                font-size: 11px;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #3F3F46;
                background-color: #18181B;
            }}
            QCheckBox::indicator:hover {{
                border-color: #3B82F6;
            }}
            QCheckBox::indicator:checked {{
                background-color: #2563EB;
                border-color: #3B82F6;
                image: url("{chk_svg_str}");
            }}
        """
        )
        main_layout.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 10)
        card_layout.setSpacing(6)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        self.status_pill = QLabel("🟢 Connesso", self.card)
        self.status_pill.setStyleSheet(
            """
            background-color: #1E1E22;
            color: #A1A1AA;
            padding: 4px 8px;
            border-radius: 7px;
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
            color: #38BDF8;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            border: 1px solid #2E2E38;
        """
        )
        header_layout.addWidget(self.version_pill)

        self.btn_refresh = QPushButton("↻", self.card)
        self.btn_refresh.setFixedSize(28, 28)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setToolTip("Aggiorna quote adesso")
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
            QPushButton:hover { background-color: #2E2E34; }
        """
        )
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self.btn_refresh)
        card_layout.addLayout(header_layout)

        # 2. Stacked Content Pages
        self.stacked_widget = QWidget(self.card)
        self.stacked_layout = QStackedLayout(self.stacked_widget)

        self._init_metrics_page()
        self._init_settings_page()
        self._init_help_page()

        card_layout.addWidget(self.stacked_widget, stretch=1)

        # 3. Bottom Nav Bar
        nav_frame = QFrame(self.card)
        nav_frame.setObjectName("NavFooter")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(4)

        self.btn_nav_metrics = QPushButton("📊 Metriche", nav_frame)
        self.btn_nav_settings = QPushButton("⚙️ Impostazioni", nav_frame)
        self.btn_nav_help = QPushButton("ℹ️ Guida & Info", nav_frame)

        for btn in (self.btn_nav_metrics, self.btn_nav_settings, self.btn_nav_help):
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_nav_metrics.clicked.connect(lambda: self.switch_page(0))
        self.btn_nav_settings.clicked.connect(lambda: self.switch_page(1))
        self.btn_nav_help.clicked.connect(lambda: self.switch_page(2))

        nav_layout.addWidget(self.btn_nav_metrics, stretch=1)
        nav_layout.addWidget(self.btn_nav_settings, stretch=1)
        nav_layout.addWidget(self.btn_nav_help, stretch=1)
        card_layout.addWidget(nav_frame)

        self.switch_page(0)

    # =========================================================================
    # PAGE 0: METRICS PAGE (Panoramica, Claude Code, Google Antigravity)
    # =========================================================================
    def _init_metrics_page(self) -> None:
        self.metrics_view = QWidget()
        vbox_metrics = QVBoxLayout(self.metrics_view)
        vbox_metrics.setContentsMargins(0, 0, 0, 0)
        vbox_metrics.setSpacing(6)

        # Sub-tab switcher bar for multi-provider view
        self.subbar_frame = QFrame(self.metrics_view)
        self.subbar_frame.setObjectName("SectionCard")
        subbar_layout = QHBoxLayout(self.subbar_frame)
        subbar_layout.setContentsMargins(4, 3, 4, 3)
        subbar_layout.setSpacing(4)

        self.btn_sub_overview = QPushButton("⚖️ Panoramica", self.subbar_frame)
        self.btn_sub_claude = QPushButton("✴️ Claude Code", self.subbar_frame)
        self.btn_sub_antigravity = QPushButton("✨ Antigravity", self.subbar_frame)

        for btn in (self.btn_sub_overview, self.btn_sub_claude, self.btn_sub_antigravity):
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_sub_overview.clicked.connect(lambda: self._select_metrics_subview("overview"))
        self.btn_sub_claude.clicked.connect(lambda: self._select_metrics_subview("claude"))
        self.btn_sub_antigravity.clicked.connect(lambda: self._select_metrics_subview("antigravity"))

        subbar_layout.addWidget(self.btn_sub_overview, stretch=1)
        subbar_layout.addWidget(self.btn_sub_claude, stretch=1)
        subbar_layout.addWidget(self.btn_sub_antigravity, stretch=1)
        vbox_metrics.addWidget(self.subbar_frame)

        # Stacked layout for the 3 sub-views
        self.sub_stacked_layout = QStackedLayout()

        # --- SUB-VIEW 0: PANORAMICA COMPARATIVA ---
        self._init_subview_overview()
        # --- SUB-VIEW 1: DETTAGLIO CLAUDE CODE ---
        self._init_subview_claude()
        # --- SUB-VIEW 2: DETTAGLIO GOOGLE ANTIGRAVITY ---
        self._init_subview_antigravity()

        vbox_metrics.addLayout(self.sub_stacked_layout, stretch=1)
        self.stacked_layout.addWidget(self.metrics_view)

    def _init_subview_overview(self) -> None:
        self.subview_overview = QWidget()
        layout = QVBoxLayout(self.subview_overview)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        # Top comparative cards side-by-side
        hbox_cards = QHBoxLayout()
        hbox_cards.setSpacing(8)

        # Card Left: Claude Code
        self.card_comp_claude = QFrame(self.subview_overview)
        self.card_comp_claude.setObjectName("SectionCard")
        cl_layout = QVBoxLayout(self.card_comp_claude)
        cl_layout.setContentsMargins(10, 10, 10, 10)
        cl_layout.setSpacing(6)

        lbl_cl_head = QLabel("✴️ Claude Code", self.card_comp_claude)
        lbl_cl_head.setStyleSheet("color: #F87171; font-weight: 700; font-size: 12px;")
        cl_layout.addWidget(lbl_cl_head)

        self.lbl_cl_pct = QLabel("0%", self.card_comp_claude)
        self.lbl_cl_pct.setStyleSheet("font-size: 26px; font-weight: 800; color: #38BDF8;")
        cl_layout.addWidget(self.lbl_cl_pct)

        self.lbl_cl_5h = QLabel("⏱️ 5h: 0% (Libero)", self.card_comp_claude)
        self.lbl_cl_5h.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        cl_layout.addWidget(self.lbl_cl_5h)

        self.lbl_cl_7d = QLabel("📅 7g: 0% (Libero)", self.card_comp_claude)
        self.lbl_cl_7d.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        cl_layout.addWidget(self.lbl_cl_7d)

        self.lbl_cl_reset = QLabel("Reset in --", self.card_comp_claude)
        self.lbl_cl_reset.setStyleSheet("color: #71717A; font-size: 10px; margin-top: 4px;")
        cl_layout.addWidget(self.lbl_cl_reset)
        cl_layout.addStretch()

        btn_go_claude = QPushButton("Dettaglio Claude ↗", self.card_comp_claude)
        btn_go_claude.setFixedHeight(24)
        btn_go_claude.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go_claude.setStyleSheet("font-size: 10px; background-color: #222226; color: #38BDF8; border-radius: 5px;")
        btn_go_claude.clicked.connect(lambda: self._select_metrics_subview("claude"))
        cl_layout.addWidget(btn_go_claude)

        # Card Right: Google Antigravity
        self.card_comp_agy = QFrame(self.subview_overview)
        self.card_comp_agy.setObjectName("SectionCard")
        ag_layout = QVBoxLayout(self.card_comp_agy)
        ag_layout.setContentsMargins(10, 10, 10, 10)
        ag_layout.setSpacing(6)

        lbl_ag_head = QLabel("✨ Antigravity", self.card_comp_agy)
        lbl_ag_head.setStyleSheet("color: #60A5FA; font-weight: 700; font-size: 12px;")
        ag_layout.addWidget(lbl_ag_head)

        self.lbl_ag_pct = QLabel("0%", self.card_comp_agy)
        self.lbl_ag_pct.setStyleSheet("font-size: 26px; font-weight: 800; color: #60A5FA;")
        ag_layout.addWidget(self.lbl_ag_pct)

        self.lbl_ag_gem = QLabel("✨ Gemini 5h: 0%", self.card_comp_agy)
        self.lbl_ag_gem.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        ag_layout.addWidget(self.lbl_ag_gem)

        self.lbl_ag_prt = QLabel("🤝 Partner 5h: 0%", self.card_comp_agy)
        self.lbl_ag_prt.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        ag_layout.addWidget(self.lbl_ag_prt)

        self.lbl_ag_reset = QLabel("Reset in --", self.card_comp_agy)
        self.lbl_ag_reset.setStyleSheet("color: #71717A; font-size: 10px; margin-top: 4px;")
        ag_layout.addWidget(self.lbl_ag_reset)
        ag_layout.addStretch()

        btn_go_agy = QPushButton("Dettaglio Google ↗", self.card_comp_agy)
        btn_go_agy.setFixedHeight(24)
        btn_go_agy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go_agy.setStyleSheet("font-size: 10px; background-color: #222226; color: #60A5FA; border-radius: 5px;")
        btn_go_agy.clicked.connect(lambda: self._select_metrics_subview("antigravity"))
        ag_layout.addWidget(btn_go_agy)

        hbox_cards.addWidget(self.card_comp_claude, stretch=1)
        hbox_cards.addWidget(self.card_comp_agy, stretch=1)
        layout.addLayout(hbox_cards)

        # Bottom summary recommendation card
        card_summary = QFrame(self.subview_overview)
        card_summary.setObjectName("SectionCard")
        sum_layout = QVBoxLayout(card_summary)
        sum_layout.setContentsMargins(12, 10, 12, 10)
        sum_layout.setSpacing(4)

        lbl_sum_title = QLabel("💡 Stato di Utilizzo Parallelo", card_summary)
        lbl_sum_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #FFFFFF;")
        sum_layout.addWidget(lbl_sum_title)

        self.lbl_sum_desc = QLabel(
            "Entrambi i servizi sono monitorati contemporaneamente sulla barra delle attività.",
            card_summary,
        )
        self.lbl_sum_desc.setWordWrap(True)
        self.lbl_sum_desc.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        sum_layout.addWidget(self.lbl_sum_desc)
        layout.addWidget(card_summary)
        layout.addStretch()

        self.sub_stacked_layout.addWidget(self.subview_overview)

    def _init_subview_claude(self) -> None:
        self.subview_claude = QWidget()
        vbox = QVBoxLayout(self.subview_claude)
        vbox.setContentsMargins(0, 4, 0, 0)
        vbox.setSpacing(6)

        # Workspace title row
        self.lbl_claude_workspace = QLabel("Claude Code", self.subview_claude)
        self.lbl_claude_workspace.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        vbox.addWidget(self.lbl_claude_workspace)

        # Window selector tabs (5h vs 7d)
        tab_container = QFrame(self.subview_claude)
        tab_container.setObjectName("SectionCard")
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(4, 3, 4, 3)
        tab_layout.setSpacing(4)

        self.btn_tab_5h = QPushButton("⏱️ Sessione 5h", tab_container)
        self.btn_tab_7d = QPushButton("📅 Settimanale (7g)", tab_container)
        for b in (self.btn_tab_5h, self.btn_tab_7d):
            b.setFixedHeight(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_5h.clicked.connect(lambda: self._select_claude_window("5h"))
        self.btn_tab_7d.clicked.connect(lambda: self._select_claude_window("7d"))
        tab_layout.addWidget(self.btn_tab_5h)
        tab_layout.addWidget(self.btn_tab_7d)
        vbox.addWidget(tab_container)

        # Gauge container
        gauge_container = QWidget(self.subview_claude)
        gauge_layout = QVBoxLayout(gauge_container)
        gauge_layout.setContentsMargins(0, 2, 0, 2)
        gauge_layout.setSpacing(1)

        self.claude_gauge = SemiCircleGauge(color_theme="cyan", parent=gauge_container)
        gauge_layout.addWidget(self.claude_gauge, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_claude_reset_timer = QLabel("Reset in --", gauge_container)
        self.lbl_claude_reset_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_claude_reset_timer.setStyleSheet("font-size: 11px; color: #A1A1AA;")
        gauge_layout.addWidget(self.lbl_claude_reset_timer)
        vbox.addWidget(gauge_container)

        # Dual row overview
        dual_card = QFrame(self.subview_claude)
        dual_card.setObjectName("SectionCard")
        dual_layout = QVBoxLayout(dual_card)
        dual_layout.setContentsMargins(10, 6, 10, 6)
        dual_layout.setSpacing(3)

        self.lbl_cl_row_5h = QLabel("⏱️ Sessione 5h: 0%", dual_card)
        self.lbl_cl_row_5h.setStyleSheet("color: #D4D4D8; font-size: 11px;")
        dual_layout.addWidget(self.lbl_cl_row_5h)

        self.lbl_cl_row_7d = QLabel("📅 Settimanale: 0%", dual_card)
        self.lbl_cl_row_7d.setStyleSheet("color: #D4D4D8; font-size: 11px;")
        dual_layout.addWidget(self.lbl_cl_row_7d)
        vbox.addWidget(dual_card)

        # Tokens grid
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(6)
        self.card_in = self._create_metric_card("Input", "0", "0% cache")
        self.card_out = self._create_metric_card("Output", "0", "token")
        self.card_think = self._create_metric_card("Thinking 🧠", "0", "token")
        cards_layout.addWidget(self.card_in)
        cards_layout.addWidget(self.card_out)
        cards_layout.addWidget(self.card_think)
        vbox.addLayout(cards_layout)
        vbox.addStretch()

        self.sub_stacked_layout.addWidget(self.subview_claude)

    def _init_subview_antigravity(self) -> None:
        self.subview_antigravity = QWidget()
        vbox = QVBoxLayout(self.subview_antigravity)
        vbox.setContentsMargins(0, 4, 0, 0)
        vbox.setSpacing(6)

        # Workspace title
        self.lbl_agy_title = QLabel("Google Antigravity (Google AI Pro)", self.subview_antigravity)
        self.lbl_agy_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        vbox.addWidget(self.lbl_agy_title)

        # Card 1: Gemini Pool
        card_gem = QFrame(self.subview_antigravity)
        card_gem.setObjectName("SectionCard")
        gem_layout = QVBoxLayout(card_gem)
        gem_layout.setContentsMargins(12, 8, 12, 8)
        gem_layout.setSpacing(4)

        lbl_gem_title = QLabel("✨ Pool Gemini (Flash, Pro, Next)", card_gem)
        lbl_gem_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #60A5FA;")
        gem_layout.addWidget(lbl_gem_title)

        self.lbl_gem_5h = QLabel("⏱️ Sessione 5h: 0%  (Reset in --)", card_gem)
        self.lbl_gem_5h.setStyleSheet("color: #D4D4D8; font-size: 11px;")
        gem_layout.addWidget(self.lbl_gem_5h)

        self.lbl_gem_7d = QLabel("📅 Settimanale: 0%  (Reset in --)", card_gem)
        self.lbl_gem_7d.setStyleSheet("color: #D4D4D8; font-size: 11px;")
        gem_layout.addWidget(self.lbl_gem_7d)
        vbox.addWidget(card_gem)

        # Card 2: Partner Models Breakdown (All models)
        self.card_partner_models = QFrame(self.subview_antigravity)
        self.card_partner_models.setObjectName("SectionCard")
        self.layout_partner_models = QVBoxLayout(self.card_partner_models)
        self.layout_partner_models.setContentsMargins(12, 8, 12, 8)
        self.layout_partner_models.setSpacing(5)

        lbl_prt_title = QLabel("🤝 Modelli Partner (Claude & GPT su Antigravity)", self.card_partner_models)
        lbl_prt_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #10B981;")
        self.layout_partner_models.addWidget(lbl_prt_title)

        # Dynamic container for partner model rows
        self.partner_rows_widget = QWidget(self.card_partner_models)
        self.partner_rows_layout = QVBoxLayout(self.partner_rows_widget)
        self.partner_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.partner_rows_layout.setSpacing(4)
        self.layout_partner_models.addWidget(self.partner_rows_widget)
        vbox.addWidget(self.card_partner_models)

        # Card 3: Google Account & Credits
        card_credits = QFrame(self.subview_antigravity)
        card_credits.setObjectName("SectionCard")
        cred_layout = QHBoxLayout(card_credits)
        cred_layout.setContentsMargins(12, 8, 12, 8)
        cred_layout.setSpacing(8)

        self.lbl_credits_info = QLabel("💳 AI Credits: Disponibili  •  Account: giuliosporti@gmail.com", card_credits)
        self.lbl_credits_info.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        cred_layout.addWidget(self.lbl_credits_info)
        vbox.addWidget(card_credits)

        vbox.addStretch()
        self.sub_stacked_layout.addWidget(self.subview_antigravity)

    def _select_metrics_subview(self, view_id: str) -> None:
        self._active_metrics_subview = view_id
        active_css = "QPushButton { background-color: #27272A; color: #FFFFFF; border-radius: 5px; font-weight: 700; font-size: 11px; border: 1px solid #3F3F46; }"
        inactive_css = "QPushButton { background-color: transparent; color: #71717A; border-radius: 5px; font-weight: 500; font-size: 11px; border: none; } QPushButton:hover { color: #D4D4D8; }"

        self.btn_sub_overview.setStyleSheet(active_css if view_id == "overview" else inactive_css)
        self.btn_sub_claude.setStyleSheet(active_css if view_id == "claude" else inactive_css)
        self.btn_sub_antigravity.setStyleSheet(active_css if view_id == "antigravity" else inactive_css)

        idx_map = {"overview": 0, "claude": 1, "antigravity": 2}
        self.sub_stacked_layout.setCurrentIndex(idx_map.get(view_id, 0))

    def _select_claude_window(self, tab: str) -> None:
        self._active_claude_tab = tab
        active_css = "QPushButton { background-color: #27272A; color: #FFFFFF; border-radius: 5px; font-weight: 600; font-size: 11px; border: 1px solid #3F3F46; }"
        inactive_css = "QPushButton { background-color: transparent; color: #71717A; border-radius: 5px; font-weight: 500; font-size: 11px; border: none; } QPushButton:hover { color: #D4D4D8; }"

        if tab == "7d":
            self.btn_tab_7d.setStyleSheet(active_css)
            self.btn_tab_5h.setStyleSheet(inactive_css)
        else:
            self.btn_tab_5h.setStyleSheet(active_css)
            self.btn_tab_7d.setStyleSheet(inactive_css)

        if self._last_composite:
            self._update_claude_subview(self._last_composite.claude)

    # =========================================================================
    # PAGE 1: SETTINGS VIEW (Multi-Provider Configuration, Zero Clipping)
    # =========================================================================
    def _init_settings_page(self) -> None:
        self.settings_view = QWidget()
        vbox_settings = QVBoxLayout(self.settings_view)
        vbox_settings.setContentsMargins(0, 0, 0, 0)
        vbox_settings.setSpacing(6)

        # Responsive Scroll Area: guarantees zero layout squashing or overlapping
        scroll_area = QScrollArea(self.settings_view)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(8)

        # --- CARD 1: SERVIZI ATTIVI & TASKBAR ---
        card_services = QFrame(scroll_content)
        card_services.setObjectName("SectionCard")
        layout_srv = QVBoxLayout(card_services)
        layout_srv.setContentsMargins(12, 10, 12, 10)
        layout_srv.setSpacing(8)

        lbl_srv_title = QLabel("🔌 Servizi Attivi & Icone Taskbar (v2.0.0)", card_services)
        lbl_srv_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        layout_srv.addWidget(lbl_srv_title)

        # Service toggle buttons (clean interactive cards)
        row_toggles = QHBoxLayout()
        row_toggles.setSpacing(8)

        self.btn_toggle_claude = QPushButton(card_services)
        self.btn_toggle_antigravity = QPushButton(card_services)
        for b in (self.btn_toggle_claude, self.btn_toggle_antigravity):
            b.setFixedHeight(30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_toggle_claude.clicked.connect(self._toggle_claude_service)
        self.btn_toggle_antigravity.clicked.connect(self._toggle_antigravity_service)

        row_toggles.addWidget(self.btn_toggle_claude, stretch=1)
        row_toggles.addWidget(self.btn_toggle_antigravity, stretch=1)
        layout_srv.addLayout(row_toggles)

        # Hidden QCheckBox for backwards compatibility & config sync
        self.chk_enable_claude = QCheckBox(card_services)
        self.chk_enable_claude.setVisible(False)
        self.chk_enable_claude.setChecked(getattr(self.config, "enable_claude", True))

        self.chk_enable_antigravity = QCheckBox(card_services)
        self.chk_enable_antigravity.setVisible(False)
        self.chk_enable_antigravity.setChecked(getattr(self.config, "enable_antigravity", True))

        # Antigravity Taskbar Mode Selection Container
        self.agy_mode_container = QWidget(card_services)
        layout_agy_mode = QVBoxLayout(self.agy_mode_container)
        layout_agy_mode.setContentsMargins(0, 2, 0, 0)
        layout_agy_mode.setSpacing(6)

        lbl_agy_mode = QLabel("Visualizzazione Taskbar per Antigravity:", self.agy_mode_container)
        lbl_agy_mode.setStyleSheet("color: #A1A1AA; font-size: 10px; font-weight: 600;")
        layout_agy_mode.addWidget(lbl_agy_mode)

        row_mode_btns = QHBoxLayout()
        row_mode_btns.setSpacing(6)

        self._agy_tray_mode = getattr(self.config, "antigravity_tray_mode", "single_icon")
        self.btn_tray_single = QPushButton("1 Icona (Unificata)", self.agy_mode_container)
        self.btn_tray_split = QPushButton("2 Icone (+ Partner)", self.agy_mode_container)

        for b in (self.btn_tray_single, self.btn_tray_split):
            b.setFixedHeight(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_tray_single.clicked.connect(lambda: self._set_agy_tray_mode("single_icon"))
        self.btn_tray_split.clicked.connect(lambda: self._set_agy_tray_mode("split_partner_icon"))
        row_mode_btns.addWidget(self.btn_tray_single, stretch=1)
        row_mode_btns.addWidget(self.btn_tray_split, stretch=1)
        layout_agy_mode.addLayout(row_mode_btns)

        # Single Pool Option Box (framed container when single_icon is selected)
        self.pool_select_container = QFrame(self.agy_mode_container)
        self.pool_select_container.setStyleSheet(
            "QFrame { background-color: #141417; border: 1px solid #27272A; border-radius: 6px; }"
        )
        layout_pool_box = QVBoxLayout(self.pool_select_container)
        layout_pool_box.setContentsMargins(8, 7, 8, 7)
        layout_pool_box.setSpacing(5)

        lbl_which_pool = QLabel("Pool visualizzato nell'icona singola:", self.pool_select_container)
        lbl_which_pool.setStyleSheet("color: #71717A; font-size: 10px; font-weight: 500; border: none; background: transparent;")
        layout_pool_box.addWidget(lbl_which_pool)

        row_pools = QHBoxLayout()
        row_pools.setSpacing(5)

        self._agy_single_pool = getattr(self.config, "antigravity_single_pool", "gemini")
        self.btn_pool_gemini = QPushButton("✨ Gemini", self.pool_select_container)
        self.btn_pool_partner = QPushButton("🤝 Partner", self.pool_select_container)
        self.btn_pool_max = QPushButton("🔥 Max Consumo", self.pool_select_container)

        for pb in (self.btn_pool_gemini, self.btn_pool_partner, self.btn_pool_max):
            pb.setFixedHeight(24)
            pb.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_pool_gemini.clicked.connect(lambda: self._set_agy_single_pool("gemini"))
        self.btn_pool_partner.clicked.connect(lambda: self._set_agy_single_pool("partner"))
        self.btn_pool_max.clicked.connect(lambda: self._set_agy_single_pool("max_used"))

        row_pools.addWidget(self.btn_pool_gemini, stretch=1)
        row_pools.addWidget(self.btn_pool_partner, stretch=1)
        row_pools.addWidget(self.btn_pool_max, stretch=1)
        layout_pool_box.addLayout(row_pools)
        layout_agy_mode.addWidget(self.pool_select_container)

        # Split Mode Hint Label (shown when split_partner_icon is selected)
        self.lbl_split_hint = QLabel("💡 Verranno mostrate 2 icone separate: Gemini (Azzurro) e Partner (Smeraldo).", self.agy_mode_container)
        self.lbl_split_hint.setStyleSheet("color: #10B981; font-size: 10px; padding: 2px 0px;")
        self.lbl_split_hint.setWordWrap(True)
        self.lbl_split_hint.setVisible(False)
        layout_agy_mode.addWidget(self.lbl_split_hint)

        layout_srv.addWidget(self.agy_mode_container)
        self._update_service_toggle_buttons()
        self._update_agy_mode_buttons()
        scroll_layout.addWidget(card_services)

        # --- CARD 2: ACCOUNT & LOGIN 1-CLICK ---
        card_auth = QFrame(scroll_content)
        card_auth.setObjectName("SectionCard")
        layout_auth = QVBoxLayout(card_auth)
        layout_auth.setContentsMargins(12, 10, 12, 10)
        layout_auth.setSpacing(6)

        lbl_auth_title = QLabel("🔐 Account Connessi", card_auth)
        lbl_auth_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        layout_auth.addWidget(lbl_auth_title)

        # Sub-selector for account tab
        row_acc_tabs = QHBoxLayout()
        row_acc_tabs.setSpacing(5)
        self.btn_acc_claude = QPushButton("✴️ Claude Code", card_auth)
        self.btn_acc_google = QPushButton("✨ Google Antigravity", card_auth)
        for b in (self.btn_acc_claude, self.btn_acc_google):
            b.setFixedHeight(24)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_acc_claude.clicked.connect(lambda: self._switch_auth_view("claude"))
        self.btn_acc_google.clicked.connect(lambda: self._switch_auth_view("google"))
        row_acc_tabs.addWidget(self.btn_acc_claude)
        row_acc_tabs.addWidget(self.btn_acc_google)
        layout_auth.addLayout(row_acc_tabs)

        # Auth action buttons row
        auth_btn_row = QHBoxLayout()
        auth_btn_row.setSpacing(6)

        self.btn_login = QPushButton("🔑 Accedi (1-Click)", card_auth)
        self.btn_login.setFixedHeight(28)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet("background-color: #10B981; color: #FFFFFF; font-weight: 600; font-size: 11px; border-radius: 6px;")
        self.btn_login.clicked.connect(self._handle_login_click)
        auth_btn_row.addWidget(self.btn_login, stretch=3)

        self.btn_logout = QPushButton("🚪 Disconnetti", card_auth)
        self.btn_logout.setFixedHeight(28)
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setStyleSheet("background-color: #222226; color: #F87171; font-weight: 600; font-size: 11px; border-radius: 6px; border: 1px solid #3F2323;")
        self.btn_logout.clicked.connect(self._handle_logout_click)
        auth_btn_row.addWidget(self.btn_logout, stretch=2)
        layout_auth.addLayout(auth_btn_row)

        self.lbl_login_status = QLabel("", card_auth)
        self.lbl_login_status.setStyleSheet("color: #38BDF8; font-size: 10px;")
        self.lbl_login_status.setWordWrap(True)
        self.lbl_login_status.setVisible(False)
        layout_auth.addWidget(self.lbl_login_status)

        self._active_auth_tab = "claude"
        self._switch_auth_view("claude")
        scroll_layout.addWidget(card_auth)

        # --- CARD 3: NOTIFICHE & SOGLIE ALERT ---
        card_notif = QFrame(scroll_content)
        card_notif.setObjectName("SectionCard")
        layout_notif = QVBoxLayout(card_notif)
        layout_notif.setContentsMargins(12, 10, 12, 10)
        layout_notif.setSpacing(6)

        notif_hdr = QHBoxLayout()
        lbl_notif_sec = QLabel("🔔 Notifiche & Soglie Alert", card_notif)
        lbl_notif_sec.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        notif_hdr.addWidget(lbl_notif_sec)
        notif_hdr.addStretch()

        self.chk_notif = QCheckBox("Notifiche Push", card_notif)
        self.chk_notif.setChecked(self.config.notifications_enabled)
        self.chk_notif.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_notif.setStyleSheet("color: #E4E4E7; font-size: 11px;")
        notif_hdr.addWidget(self.chk_notif)
        layout_notif.addLayout(notif_hdr)

        # Chips row
        grid_chips = QHBoxLayout()
        grid_chips.setSpacing(5)
        self._threshold_chips: dict[int, QPushButton] = {}
        for val in [50, 75, 80, 90, 95, 100]:
            btn = QPushButton(f"{val}%", card_notif)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, v=val: self._toggle_threshold_chip(v))
            grid_chips.addWidget(btn, stretch=1)
            self._threshold_chips[val] = btn
        layout_notif.addLayout(grid_chips)

        thresh_input_row = QHBoxLayout()
        thresh_input_row.setSpacing(8)
        lbl_tin = QLabel("Soglie attive (%):", card_notif)
        lbl_tin.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        thresh_input_row.addWidget(lbl_tin)

        self.txt_thresholds = QLineEdit(card_notif)
        self.txt_thresholds.setFixedHeight(24)
        self.txt_thresholds.setText(", ".join(str(t) for t in sorted(self.config.thresholds)))
        self.txt_thresholds.setStyleSheet("background-color: #121214; border: 1px solid #3F3F46; border-radius: 6px; color: #FFFFFF; padding: 0px 8px; font-size: 11px;")
        thresh_input_row.addWidget(self.txt_thresholds, stretch=1)
        layout_notif.addLayout(thresh_input_row)
        self.txt_thresholds.textChanged.connect(self._sync_threshold_chips)
        self._sync_threshold_chips()

        self.chk_burn_rate = QCheckBox("🔥 Alert Consumo Rapido (+15% in <10m / Loop)", card_notif)
        self.chk_burn_rate.setChecked(self.config.burn_rate_alert_enabled)
        self.chk_burn_rate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_burn_rate.setStyleSheet("color: #E4E4E7; font-size: 11px;")
        layout_notif.addWidget(self.chk_burn_rate)
        scroll_layout.addWidget(card_notif)

        # --- CARD 4: STILE ICONA & SISTEMA ---
        card_style = QFrame(scroll_content)
        card_style.setObjectName("SectionCard")
        layout_st = QVBoxLayout(card_style)
        layout_st.setContentsMargins(12, 10, 12, 10)
        layout_st.setSpacing(6)

        lbl_st_title = QLabel("🎨 Stile Icone Taskbar & Sistema", card_style)
        lbl_st_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        layout_st.addWidget(lbl_st_title)

        hbox_styles = QHBoxLayout()
        hbox_styles.setSpacing(5)
        self._current_tray_style = getattr(self.config, "tray_icon_style", "concentric")
        self.btn_style_concentric = QPushButton("⭕ Anelli\n(5h / 7g)", card_style)
        self.btn_style_split = QPushButton("🌗 Archi Split\n(Sx 5h / Dx 7g)", card_style)
        self.btn_style_bars = QPushButton("📊 Doppie Barre\n(Colonne 5h / 7g)", card_style)

        for sb in (self.btn_style_concentric, self.btn_style_split, self.btn_style_bars):
            sb.setFixedHeight(34)
            sb.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_style_concentric.clicked.connect(lambda: self._select_tray_style("concentric"))
        self.btn_style_split.clicked.connect(lambda: self._select_tray_style("split"))
        self.btn_style_bars.clicked.connect(lambda: self._select_tray_style("bars"))

        hbox_styles.addWidget(self.btn_style_concentric, stretch=1)
        hbox_styles.addWidget(self.btn_style_split, stretch=1)
        hbox_styles.addWidget(self.btn_style_bars, stretch=1)
        layout_st.addLayout(hbox_styles)
        self._update_tray_style_buttons()

        # System row
        sys_row = QHBoxLayout()
        self.chk_autostart = QCheckBox("🚀 Avvia con Windows", card_style)
        self.chk_autostart.setChecked(is_autostart_enabled())
        self.chk_autostart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autostart.setStyleSheet("color: #E4E4E7; font-size: 11px;")
        sys_row.addWidget(self.chk_autostart)

        self.chk_mock = QCheckBox("🧪 Simulazione Demo (Mock)", card_style)
        self.chk_mock.setChecked(self.config.mock_mode)
        self.chk_mock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_mock.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        sys_row.addWidget(self.chk_mock)
        sys_row.addStretch()
        layout_st.addLayout(sys_row)

        scroll_layout.addWidget(card_style)
        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        vbox_settings.addWidget(scroll_area, stretch=1)

        # Pinned save button at the bottom of settings page
        self.btn_save_settings = QPushButton("💾 Salva Impostazioni", self.settings_view)
        self.btn_save_settings.setFixedHeight(34)
        self.btn_save_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_settings.setStyleSheet(
            "QPushButton { background-color: #2563EB; color: #FFFFFF; font-size: 12px; font-weight: 700; border-radius: 7px; border: none; } QPushButton:hover { background-color: #1D4ED8; }"
        )
        self.btn_save_settings.clicked.connect(self._save_settings_action)
        vbox_settings.addWidget(self.btn_save_settings)

        self.stacked_layout.addWidget(self.settings_view)

    def _toggle_claude_service(self) -> None:
        new_val = not self.chk_enable_claude.isChecked()
        if not new_val and not self.chk_enable_antigravity.isChecked():
            return
        self.chk_enable_claude.setChecked(new_val)
        self._update_service_toggle_buttons()

    def _toggle_antigravity_service(self) -> None:
        new_val = not self.chk_enable_antigravity.isChecked()
        if not new_val and not self.chk_enable_claude.isChecked():
            return
        self.chk_enable_antigravity.setChecked(new_val)
        self._update_service_toggle_buttons()

    def _update_service_toggle_buttons(self) -> None:
        c_active = self.chk_enable_claude.isChecked()
        ag_active = self.chk_enable_antigravity.isChecked()

        if c_active:
            self.btn_toggle_claude.setText("✴️ Claude Code  ✓")
            self.btn_toggle_claude.setStyleSheet(
                "QPushButton { background-color: #261614; color: #F87171; border: 1px solid #7F1D1D; border-radius: 6px; font-weight: 700; font-size: 11px; } "
                "QPushButton:hover { background-color: #381E1B; }"
            )
        else:
            self.btn_toggle_claude.setText("✴️ Claude Code  (Inattivo)")
            self.btn_toggle_claude.setStyleSheet(
                "QPushButton { background-color: #18181B; color: #71717A; border: 1px solid #27272A; border-radius: 6px; font-weight: 500; font-size: 11px; } "
                "QPushButton:hover { background-color: #222226; color: #A1A1AA; }"
            )

        if ag_active:
            self.btn_toggle_antigravity.setText("✨ Antigravity  ✓")
            self.btn_toggle_antigravity.setStyleSheet(
                "QPushButton { background-color: #132036; color: #60A5FA; border: 1px solid #1E3A8A; border-radius: 6px; font-weight: 700; font-size: 11px; } "
                "QPushButton:hover { background-color: #1A2B47; }"
            )
        else:
            self.btn_toggle_antigravity.setText("✨ Antigravity  (Inattivo)")
            self.btn_toggle_antigravity.setStyleSheet(
                "QPushButton { background-color: #18181B; color: #71717A; border: 1px solid #27272A; border-radius: 6px; font-weight: 500; font-size: 11px; } "
                "QPushButton:hover { background-color: #222226; color: #A1A1AA; }"
            )

        self.agy_mode_container.setVisible(ag_active)

    def _set_agy_tray_mode(self, mode: str) -> None:
        self._agy_tray_mode = mode
        self._update_agy_mode_buttons()

    def _set_agy_single_pool(self, pool: str) -> None:
        self._agy_single_pool = pool
        self._update_agy_mode_buttons()

    def _update_agy_mode_buttons(self) -> None:
        active_css = "QPushButton { background-color: #2563EB; color: #FFFFFF; border-radius: 5px; font-weight: 600; font-size: 10px; border: 1px solid #3B82F6; }"
        inactive_css = "QPushButton { background-color: #18181B; color: #A1A1AA; border-radius: 5px; font-size: 10px; border: 1px solid #3F3F46; } QPushButton:hover { background-color: #27272A; }"

        is_single = (self._agy_tray_mode == "single_icon")
        self.btn_tray_single.setStyleSheet(active_css if is_single else inactive_css)
        self.btn_tray_split.setStyleSheet(inactive_css if is_single else active_css)

        self.pool_select_container.setVisible(is_single)
        self.lbl_split_hint.setVisible(not is_single)

        chip_active = "QPushButton { background-color: #2563EB; color: #FFFFFF; border-radius: 4px; font-weight: 600; font-size: 10px; border: 1px solid #3B82F6; }"
        chip_inactive = "QPushButton { background-color: #1E1E22; color: #A1A1AA; border-radius: 4px; font-size: 10px; border: 1px solid #2E2E34; } QPushButton:hover { background-color: #2A2A30; }"

        self.btn_pool_gemini.setStyleSheet(chip_active if self._agy_single_pool == "gemini" else chip_inactive)
        self.btn_pool_partner.setStyleSheet(chip_active if self._agy_single_pool == "partner" else chip_inactive)
        self.btn_pool_max.setStyleSheet(chip_active if self._agy_single_pool == "max_used" else chip_inactive)

    def _switch_auth_view(self, auth_type: str) -> None:
        self._active_auth_tab = auth_type
        active_css = "QPushButton { background-color: #27272A; color: #FFFFFF; border-radius: 5px; font-weight: 600; font-size: 11px; border: 1px solid #3F3F46; }"
        inactive_css = "QPushButton { background-color: transparent; color: #71717A; border-radius: 5px; font-size: 11px; border: none; }"

        self.btn_acc_claude.setStyleSheet(active_css if auth_type == "claude" else inactive_css)
        self.btn_acc_google.setStyleSheet(active_css if auth_type == "google" else inactive_css)

        if auth_type == "google":
            self.btn_login.setText("🔑 Accedi con Google AI (1-Click)")
            self.btn_logout.setVisible(True)
        else:
            self.btn_login.setText("🔑 Accedi con Claude (1-Click)")
            self.btn_logout.setVisible(True)

    def _handle_login_click(self) -> None:
        if self._active_auth_tab == "google":
            self._start_google_login()
        else:
            self._start_quick_login()

    def _handle_logout_click(self) -> None:
        if self._active_auth_tab == "google":
            AntigravityLoginHelper.logout()
            self.lbl_login_status.setVisible(True)
            self.lbl_login_status.setText("Disconnessione Google AI effettuata.")
            self.refresh_requested.emit()
        else:
            self._perform_logout()

    def _start_google_login(self) -> None:
        self.btn_login.setEnabled(False)
        self.btn_login.setText("⏳ In attesa login Google...")
        self.lbl_login_status.setVisible(True)
        self.lbl_login_status.setText("Apertura terminale agy...")

        def on_status(txt: str):
            self.lbl_login_status.setText(txt)

        async def run_glogin():
            res = await AntigravityLoginHelper.execute_login(status_callback=on_status)
            self.btn_login.setEnabled(True)
            self.btn_login.setText("🔑 Accedi con Google AI (1-Click)")
            if res:
                self.refresh_requested.emit()

        asyncio.create_task(run_glogin())

    # =========================================================================
    # PAGE 2: HELP & ABOUT VIEW (v2.0.0 Dedicated Page)
    # =========================================================================
    def _init_help_page(self) -> None:
        self.help_view = QWidget()
        vbox_help = QVBoxLayout(self.help_view)
        vbox_help.setContentsMargins(0, 0, 0, 0)
        vbox_help.setSpacing(7)

        hero_card = QFrame(self.help_view)
        hero_card.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(12, 9, 12, 9)
        hero_layout.setSpacing(4)

        top_hero_row = QHBoxLayout()
        lbl_app_title = QLabel("Claude & Antigravity Usage Widget", hero_card)
        lbl_app_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        top_hero_row.addWidget(lbl_app_title)
        top_hero_row.addStretch()

        lbl_ver_badge = QLabel(f"v{__version__}", hero_card)
        lbl_ver_badge.setStyleSheet(
            "background-color: #0284C7; color: #F0F9FF; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 6px; border: 1px solid #38BDF8;"
        )
        top_hero_row.addWidget(lbl_ver_badge)
        hero_layout.addLayout(top_hero_row)

        lbl_creator = QLabel("Ideato e sviluppato da <b>giuspo</b> 🚀", hero_card)
        lbl_creator.setStyleSheet("color: #38BDF8; font-size: 11px;")
        hero_layout.addWidget(lbl_creator)

        lbl_schema = QLabel(
            f"📦 <b>Versione {__version__} Multi-Provider</b> &nbsp;•&nbsp; <span style='color:#94A3B8;'>Schema: Major.Minor.Compilation</span>",
            hero_card,
        )
        lbl_schema.setStyleSheet("color: #E2E8F0; font-size: 10px;")
        hero_layout.addWidget(lbl_schema)

        lbl_license = QLabel("🛡️ Licenza: GNU GPLv3 (Copyleft Forte)", hero_card)
        lbl_license.setStyleSheet("color: #94A3B8; font-size: 10px;")
        hero_layout.addWidget(lbl_license)
        vbox_help.addWidget(hero_card)

        # Purpose card
        purpose_card = QFrame(self.help_view)
        purpose_card.setObjectName("SectionCard")
        p_layout = QVBoxLayout(purpose_card)
        p_layout.setContentsMargins(10, 8, 10, 8)
        p_layout.setSpacing(4)

        lbl_p_title = QLabel("🎯 Scopo dell'Applicazione Multi-Provider", purpose_card)
        lbl_p_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #FFFFFF;")
        p_layout.addWidget(lbl_p_title)

        lbl_p_body = QLabel(
            "Monitora in tempo reale dalla barra delle attività le quote d'uso sia di <b>Claude Code (Anthropic)</b> "
            "sia di <b>Google Antigravity (Google AI Pro)</b>, inclusi i modelli Gemini e i modelli Partner (Claude Sonnet/Opus, GPT-OSS). "
            "Puoi visualizzare le icone affiancate o scegliere solo uno dei due servizi.",
            purpose_card,
        )
        lbl_p_body.setWordWrap(True)
        lbl_p_body.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        p_layout.addWidget(lbl_p_body)
        vbox_help.addWidget(purpose_card)

        vbox_help.addStretch()
        self.stacked_layout.addWidget(self.help_view)

    # =========================================================================
    # DATA UPDATES & RENDERING
    # =========================================================================
    def update_snapshot(self, snap: object) -> None:
        """Central update handler for composite or single snapshot."""
        if isinstance(snap, CompositeUsageSnapshot):
            self._last_composite = snap
            self._last_snapshot = snap.claude
            self._update_composite_view(snap)
        elif isinstance(snap, UsageSnapshot):
            self._last_snapshot = snap
            self._update_claude_subview(snap)

    def _update_composite_view(self, comp: CompositeUsageSnapshot) -> None:
        enable_cl = getattr(self.config, "enable_claude", True)
        enable_ag = getattr(self.config, "enable_antigravity", True)

        # Show/hide subbar if both enabled
        self.subbar_frame.setVisible(enable_cl and enable_ag)

        if enable_cl and not enable_ag:
            self._select_metrics_subview("claude")
        elif enable_ag and not enable_cl:
            self._select_metrics_subview("antigravity")

        # 1. Update Overview Card
        cl = comp.claude
        ag = comp.antigravity

        self.lbl_cl_pct.setText(f"{int(round(cl.primary_utilization))}%")
        self.lbl_cl_5h.setText(f"⏱️ 5h: {int(round(cl.five_hour.utilization_pct))}% ({cl.five_hour.time_remaining_str})")
        self.lbl_cl_7d.setText(f"📅 7g: {int(round(cl.seven_day.utilization_pct))}% ({cl.seven_day.time_remaining_str})")
        self.lbl_cl_reset.setText(cl.primary_friendly_reset_str)

        ag_max = max(ag.primary_gemini_utilization, ag.primary_partner_utilization)
        self.lbl_ag_pct.setText(f"{int(round(ag_max))}%")
        self.lbl_ag_gem.setText(f"✨ Gemini 5h: {int(round(ag.gemini_5h.utilization_pct))}% ({ag.gemini_5h.time_remaining_str})")
        self.lbl_ag_prt.setText(f"🤝 Partner 5h: {int(round(ag.partner_5h.utilization_pct))}% ({ag.partner_5h.time_remaining_str})")
        self.lbl_ag_reset.setText(ag.gemini_5h.friendly_reset_str)

        # Status pill in header
        if enable_cl and enable_ag:
            self.status_pill.setText("🟢 Claude & Google AI Pro Attivi")
        elif enable_ag:
            self.status_pill.setText(ag.status_label)
        else:
            self.status_pill.setText(cl.status_label)

        # 2. Update Claude subview
        self._update_claude_subview(cl)

        # 3. Update Antigravity subview
        self._update_antigravity_subview(ag)

    def _update_claude_subview(self, snap: UsageSnapshot) -> None:
        self.lbl_claude_workspace.setText(snap.workspace_name)
        active_win = snap.seven_day if self._active_claude_tab == "7d" else snap.five_hour
        self.claude_gauge.set_percentage(active_win.utilization_pct)
        self.lbl_claude_reset_timer.setText(active_win.friendly_reset_str)

        self.lbl_cl_row_5h.setText(f"⏱️ Sessione 5h: {int(round(snap.five_hour.utilization_pct))}%  (Reset in {snap.five_hour.time_remaining_str})")
        self.lbl_cl_row_7d.setText(f"📅 Settimanale: {int(round(snap.seven_day.utilization_pct))}%  (Reset in {snap.seven_day.time_remaining_str})")

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

    def _update_antigravity_subview(self, ag: AntigravityUsageSnapshot) -> None:
        self.lbl_gem_5h.setText(f"⏱️ Sessione 5h: {int(round(ag.gemini_5h.utilization_pct))}%  (Reset in {ag.gemini_5h.time_remaining_str})")
        self.lbl_gem_7d.setText(f"📅 Settimanale: {int(round(ag.gemini_7d.utilization_pct))}%  (Reset in {ag.gemini_7d.time_remaining_str})")

        # Repopulate partner models rows dynamically
        while self.partner_rows_layout.count():
            item = self.partner_rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if ag.partner_models:
            for m in ag.partner_models:
                row = QFrame(self.partner_rows_widget)
                r_layout = QHBoxLayout(row)
                r_layout.setContentsMargins(0, 1, 0, 1)
                r_layout.setSpacing(6)

                lbl_name = QLabel(m.display_name, row)
                lbl_name.setStyleSheet("color: #E4E4E7; font-size: 11px; font-weight: 500;")
                r_layout.addWidget(lbl_name, stretch=3)

                pct_int = int(round(m.five_hour.utilization_pct))
                lbl_val = QLabel(f"{pct_int}% (5h)", row)
                col_hex = "#EF4444" if pct_int >= 90 else ("#F59E0B" if pct_int >= 75 else "#10B981")
                lbl_val.setStyleSheet(f"color: {col_hex}; font-weight: 700; font-size: 11px;")
                r_layout.addWidget(lbl_val, stretch=1)

                lbl_time = QLabel(m.five_hour.time_remaining_str, row)
                lbl_time.setStyleSheet("color: #71717A; font-size: 10px;")
                r_layout.addWidget(lbl_time, stretch=1)

                self.partner_rows_layout.addWidget(row)
        else:
            lbl_none = QLabel("Nessun limite attivo per i modelli Partner", self.partner_rows_widget)
            lbl_none.setStyleSheet("color: #71717A; font-size: 10px; font-style: italic;")
            self.partner_rows_layout.addWidget(lbl_none)

        # Credits & Email info
        email_str = ag.account_email or "Google Account"
        credits_str = f"{ag.ai_credits_balance} Crediti" if ag.ai_credits_balance is not None else "Disponibili"
        self.lbl_credits_info.setText(f"💳 AI Credits: {credits_str}  •  Account: {email_str}")

    def _create_metric_card(self, title: str, val: str, sub: str) -> QFrame:
        card = QFrame()
        card.setObjectName("SectionCard")
        card.setFixedHeight(68)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(1)

        lbl_t = QLabel(title, card)
        lbl_t.setStyleSheet("font-size: 10px; color: #A1A1AA; font-weight: 500;")
        card_layout.addWidget(lbl_t)

        lbl_v = QLabel(val, card)
        lbl_v.setObjectName("val")
        lbl_v.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        card_layout.addWidget(lbl_v)

        lbl_s = QLabel(sub, card)
        lbl_s.setObjectName("sub")
        lbl_s.setStyleSheet("font-size: 9px; color: #71717A;")
        card_layout.addWidget(lbl_s)
        return card

    def switch_page(self, index: int) -> None:
        self.stacked_layout.setCurrentIndex(index)
        active_css = "background-color: #27272A; color: #FFFFFF; font-weight: 700; border-radius: 6px; border: 1px solid #3F3F46; font-size: 11px;"
        inactive_css = "background-color: transparent; color: #71717A; font-weight: 500; border-radius: 6px; border: none; font-size: 11px;"

        self.btn_nav_metrics.setStyleSheet(active_css if index == 0 else inactive_css)
        self.btn_nav_settings.setStyleSheet(active_css if index == 1 else inactive_css)
        self.btn_nav_help.setStyleSheet(active_css if index == 2 else inactive_css)

    def toggle_at_tray(self, tray_geo: QRect, target_tab: str = "overview") -> None:
        if self.isVisible():
            self.hide()
        else:
            if target_tab == "claude":
                self._select_metrics_subview("claude")
            elif target_tab == "antigravity" or target_tab == "antigravity_partner":
                self._select_metrics_subview("antigravity")
            else:
                self._select_metrics_subview("overview")

            pos = WindowPositioner.calculate_flyout_position(self.width(), self.height(), tray_geo)
            self.move(pos)
            self.show()
            self.activateWindow()

    def _toggle_threshold_chip(self, val: int) -> None:
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
        if not hasattr(self, "_threshold_chips") or not self._threshold_chips:
            return
        current = self._parse_current_thresholds()
        active_style = "background-color: #2563EB; color: #FFFFFF; border: 1px solid #3B82F6; border-radius: 5px; font-weight: 700; font-size: 11px;"
        inactive_style = "background-color: #222226; color: #A1A1AA; border: 1px solid #3F3F46; border-radius: 5px; font-weight: 500; font-size: 11px;"
        for val, btn in self._threshold_chips.items():
            btn.setStyleSheet(active_style if val in current else inactive_style)

    def _select_tray_style(self, style_name: str) -> None:
        self._current_tray_style = style_name
        self._update_tray_style_buttons()
        self.config.tray_icon_style = style_name
        save_config(self.config)
        self.refresh_requested.emit()

    def _update_tray_style_buttons(self) -> None:
        active_css = "background-color: #2563EB; color: #FFFFFF; border: 1px solid #3B82F6; border-radius: 6px; font-size: 10px; font-weight: 700; padding: 2px 3px;"
        inactive_css = "background-color: #18181B; color: #A1A1AA; border: 1px solid #3F3F46; border-radius: 6px; font-size: 10px; font-weight: 500; padding: 2px 3px;"
        cur = getattr(self, "_current_tray_style", "concentric")
        self.btn_style_concentric.setStyleSheet(active_css if cur == "concentric" else inactive_css)
        self.btn_style_split.setStyleSheet(active_css if cur == "split" else inactive_css)
        self.btn_style_bars.setStyleSheet(active_css if cur == "bars" else inactive_css)

    def _save_settings_action(self) -> None:
        # Enforce at least one provider active
        enable_cl = self.chk_enable_claude.isChecked()
        enable_ag = self.chk_enable_antigravity.isChecked()
        if not enable_cl and not enable_ag:
            enable_cl = True
            self.chk_enable_claude.setChecked(True)

        self.config.enable_claude = enable_cl
        self.config.enable_antigravity = enable_ag
        self.config.antigravity_tray_mode = getattr(self, "_agy_tray_mode", "single_icon")
        self.config.antigravity_single_pool = getattr(self, "_agy_single_pool", "gemini")

        self.config.notifications_enabled = self.chk_notif.isChecked()
        self.config.burn_rate_alert_enabled = self.chk_burn_rate.isChecked()
        self.config.mock_mode = self.chk_mock.isChecked()
        self.config.tray_icon_style = getattr(self, "_current_tray_style", "concentric")

        new_autostart = self.chk_autostart.isChecked()
        if new_autostart != is_autostart_enabled():
            set_autostart(new_autostart)
        self.config.autostart_enabled = new_autostart

        parsed_thresh = self._parse_current_thresholds()
        self.config.thresholds = parsed_thresh if parsed_thresh else [80, 95, 100]

        save_config(self.config)

        self.btn_save_settings.setText("✅ Impostazioni Salvate!")
        QTimer.singleShot(450, lambda: self.btn_save_settings.setText("💾 Salva Impostazioni"))
        QTimer.singleShot(450, lambda: self.switch_page(0))
        self.refresh_requested.emit()

    def _start_quick_login(self) -> None:
        self.btn_login.setEnabled(False)
        self.btn_login.setText("⏳ In attesa login Claude...")
        self.lbl_login_status.setVisible(True)
        self.lbl_login_status.setText("Apertura finestra di login in corso...")

        def update_status(text: str) -> None:
            self.lbl_login_status.setVisible(True)
            self.lbl_login_status.setText(text)

        async def login_task() -> None:
            success = await ClaudeLoginHelper.execute_login(status_callback=update_status)
            self.btn_login.setEnabled(True)
            if success:
                self.btn_login.setText("✅ Accesso Claude Completato!")
                self.refresh_requested.emit()
            else:
                self.btn_login.setText("🔑 Accedi con Claude (1-Click)")

        asyncio.create_task(login_task())

    def _perform_logout(self) -> None:
        ClaudeLoginHelper.logout()
        self.btn_login.setText("🔑 Accedi con Claude (1-Click)")
        self.btn_logout.setVisible(False)
        self.lbl_login_status.setVisible(True)
        self.lbl_login_status.setText("Disconnessione Claude effettuata.")
        self.logout_requested.emit()
