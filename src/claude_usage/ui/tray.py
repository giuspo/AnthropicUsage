"""System Tray Coordinator managing dynamic multi-provider tray icons (Claude, Gemini, Partner)."""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import sys
import time
from typing import Optional

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QEnterEvent, QGuiApplication, QMouseEvent, QPainter, QPalette
from PyQt6.QtWidgets import QLabel, QMenu, QSystemTrayIcon, QWidget

from claude_usage import __version__
from claude_usage.core.models import (
    AntigravityUsageSnapshot,
    CompositeUsageSnapshot,
    UsageSnapshot,
)
from claude_usage.i18n import register_language_listener, t
from claude_usage.ui.flyout import MicroFlyoutWindow
from claude_usage.ui.icon_renderer import IconRenderer
from claude_usage.ui.positioner import WindowPositioner

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


def _has_x11_system_tray() -> bool:
    """Returns True on Linux/XCB when an active _NET_SYSTEM_TRAY_S0 manager is running."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        if QGuiApplication.platformName() != "xcb":
            return False
        x11 = ctypes.CDLL("libX11.so.6")
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XGetSelectionOwner.restype = ctypes.c_ulong
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return False
        atom = x11.XInternAtom(dpy, b"_NET_SYSTEM_TRAY_S0", 0)
        owner = x11.XGetSelectionOwner(dpy, atom)
        x11.XCloseDisplay(dpy)
        return bool(owner)
    except Exception as e:
        logger.debug(f"X11 system tray probe failed: {e}")
        return False


def _clear_qpa_wm_class(wm_class: str = "") -> None:
    """Resets QXcbIntegration::m_wmClass and m_instanceName so Qt generates a unique WM_CLASS from birth."""
    if not sys.platform.startswith("linux"):
        return
    if wm_class:
        os.environ["RESOURCE_NAME"] = wm_class.lower()
    candidates: list[Path | str] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "PyQt6" / "Qt6" / "lib" / "libQt6XcbQpa.so.6")
        candidates.append(Path(sys._MEIPASS) / "libQt6XcbQpa.so.6")
    try:
        import PyQt6

        candidates.append(Path(PyQt6.__file__).parent / "Qt6" / "lib" / "libQt6XcbQpa.so.6")
    except Exception:
        pass
    candidates.append("libQt6XcbQpa.so.6")

    for cand in candidates:
        try:
            lib = ctypes.CDLL(str(cand))
            xcb_inst = ctypes.c_uint64.in_dll(lib, "_ZN15QXcbIntegration10m_instanceE").value
            if xcb_inst:
                # QByteArray at m_wmClass consists of:
                # 0x48: d-pointer (ArrayDataPointer)
                # 0x50: pointer to data characters
                # 0x58: size (qptrdiff)
                # 0x60: m_instanceName (const char* to argv[0]); zeroing makes Qt read RESOURCE_NAME
                ctypes.c_uint64.from_address(xcb_inst + 0x48).value = 0
                ctypes.c_uint64.from_address(xcb_inst + 0x50).value = 0
                ctypes.c_uint64.from_address(xcb_inst + 0x58).value = 0
                ctypes.c_uint64.from_address(xcb_inst + 0x60).value = 0
                break
        except Exception:
            continue


class _LinuxTrayTooltip(QLabel):
    """Frameless dark tooltip popup for Linux/GNOME tray icons."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.BypassWindowManagerHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            """
            QLabel {
                background-color: #181825;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            """
        )
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_for_tray(self, text: str, tray_geometry: QRect, center_x: int | None = None) -> None:
        if not text:
            return
        self.setText(text)
        self.adjustSize()

        primary = QGuiApplication.primaryScreen()
        if not primary:
            return
        if center_x is None:
            pos = WindowPositioner.calculate_menu_position(tray_geometry, self.width())
            target_x = pos.x()
        else:
            target_x = center_x - (self.width() // 2)

        min_x = primary.geometry().left() + 12
        max_x = primary.geometry().right() - self.width() - 12
        clamped_x = max(min_x, min(max_x, target_x))
        target_y = 36  # Directly below the 32px top panel

        self.move(clamped_x, target_y)
        self.show()
        self.raise_()
        self._hide_timer.start(5000)


class _DarkContextMenu(QMenu):
    """Context menu with automatic closing on blur/deactivate and escape key."""

    def event(self, event: QEvent) -> bool:
        if event.type() in (
            QEvent.Type.WindowDeactivate,
            QEvent.Type.ApplicationDeactivate,
        ):
            self.close()
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class _MenuBackdrop(QWidget):
    """Transparent click-catcher that dismisses the context menu when clicking anywhere outside."""

    def __init__(self, menu: QMenu) -> None:
        super().__init__(None)
        self._menu = menu
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.01)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        self.hide()
        self._menu.close()


class _LinuxTrayHoverSensor(QWidget):
    """X11 overlay sensor spanning the entire 32px height of the GNOME Top Bar tray icons."""

    SENSOR_HEIGHT = 32

    def __init__(self, controller: TrayController) -> None:
        super().__init__(None)
        self._controller = controller
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.BypassWindowManagerHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowOpacity(0.01)

        self._current_hover_icon: Optional[QSystemTrayIcon] = None

    def update_sensor_geometry(self) -> None:
        primary = QGuiApplication.primaryScreen()
        if not primary:
            return
        centers = self._controller._get_active_tray_centers(primary)
        if not centers:
            self.hide()
            return
        xs = [c[0] for c in centers]
        min_x = min(xs) - 16
        max_x = max(xs) + 16
        target_w = max(36, max_x - min_x)
        self.setGeometry(min_x, 0, target_w, self.SENSOR_HEIGHT)
        self.move(min_x, 0)
        if not self.isVisible():
            self.show()
            self.raise_()

    def _resolve_hover_target(self, gx: int) -> tuple[int, QSystemTrayIcon] | None:
        primary = QGuiApplication.primaryScreen()
        if not primary:
            return None
        centers = self._controller._get_active_tray_centers(primary)
        if not centers:
            return None
        best = min(centers, key=lambda item: abs(item[0] - gx))
        if abs(best[0] - gx) <= 24:
            return best
        return None

    def enterEvent(self, event: QEnterEvent | None) -> None:
        if event is not None:
            self._handle_pointer_position(int(event.globalPosition().x()))
        super().enterEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None:
            self._handle_pointer_position(int(event.globalPosition().x()))
        super().mouseMoveEvent(event)

    def _handle_pointer_position(self, gx: int) -> None:
        if self._controller.flyout.isVisible() or self._controller._shared_menu.isVisible():
            if self._controller._linux_tooltip is not None:
                self._controller._linux_tooltip.hide()
            return

        target = self._resolve_hover_target(gx)
        if target is None:
            if self._controller._linux_tooltip is not None:
                self._controller._linux_tooltip.hide()
            self._current_hover_icon = None
            return

        cx, tray_icon = target
        if tray_icon != self._current_hover_icon or not (
            self._controller._linux_tooltip and self._controller._linux_tooltip.isVisible()
        ):
            self._current_hover_icon = tray_icon
            if self._controller._linux_tooltip is not None:
                self._controller._linux_tooltip.show_for_tray(
                    tray_icon.toolTip(), tray_icon.geometry(), center_x=cx
                )

    def leaveEvent(self, event) -> None:
        self._current_hover_icon = None
        if self._controller._linux_tooltip is not None:
            self._controller._linux_tooltip.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._controller._linux_tooltip is not None:
            self._controller._linux_tooltip.hide()

        # If context menu is already open, clicking on the tray area closes it
        if self._controller._shared_menu.isVisible():
            self._controller._shared_menu.close()
            return

        target = self._resolve_hover_target(int(event.globalPosition().x()))
        if target is None:
            return

        cx, tray_icon = target
        btn = event.button()

        if btn == Qt.MouseButton.LeftButton:
            if tray_icon is self._controller:
                self._controller.flyout.toggle_at_tray(tray_icon.geometry(), target_tab="claude")
            elif tray_icon is self._controller.tray_antigravity:
                self._controller.flyout.toggle_at_tray(tray_icon.geometry(), target_tab="antigravity")
            elif tray_icon is self._controller.tray_partner:
                self._controller.flyout.toggle_at_tray(tray_icon.geometry(), target_tab="antigravity_partner")
        elif btn == Qt.MouseButton.RightButton:
            self._controller._popup_context_menu(tray_icon.geometry())

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        self.mousePressEvent(event)


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

        self._use_x11_tray = sys.platform.startswith("linux") and QGuiApplication.platformName() == "xcb"
        self._x11_configured: set[int] = set()
        self._redock_attempts: dict[str, int] = {}
        self._linux_tooltip: Optional[_LinuxTrayTooltip] = None
        self._linux_hover_sensor: Optional[_LinuxTrayHoverSensor] = None
        if self._use_x11_tray:
            self._linux_tooltip = _LinuxTrayTooltip()
            self._linux_hover_sensor = _LinuxTrayHoverSensor(self)

            # Monitor system screens/displays changes (e.g. HDMI hotplug, display wake)
            app_inst = QGuiApplication.instance()
            if app_inst:
                app_inst.primaryScreenChanged.connect(self._on_screens_changed)
                app_inst.screenAdded.connect(self._on_screens_changed)
                app_inst.screenRemoved.connect(self._on_screens_changed)

            # Suspend/Resume clock-jump detection and periodic docking health check
            self._last_watchdog_tick = time.monotonic()
            self._suspend_watchdog_timer = QTimer(self)
            self._suspend_watchdog_timer.setInterval(3000)
            self._suspend_watchdog_timer.timeout.connect(self._on_suspend_watchdog_tick)
            self._suspend_watchdog_timer.start()

        self._shared_menu = self._create_menu()
        self._menu_backdrop: Optional[_MenuBackdrop] = None
        if not self._use_x11_tray:
            self.setContextMenu(self._shared_menu)
            self.tray_antigravity.setContextMenu(self._shared_menu)
            self.tray_partner.setContextMenu(self._shared_menu)
        else:
            self._menu_backdrop = _MenuBackdrop(self._shared_menu)
            self._shared_menu.aboutToHide.connect(self._menu_backdrop.hide)

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

        register_language_listener(self.retranslate_menu)

    def _create_menu(self) -> QMenu:
        menu = _DarkContextMenu()
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #181825;
                color: #CDD6F4;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 6px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 5px;
            }
            QMenu::item:selected {
                background-color: #313244;
                color: #FFFFFF;
            }
            QMenu::item:disabled {
                color: #6C7086;
                font-weight: bold;
            }
            QMenu::separator {
                height: 1px;
                background: #313244;
                margin: 4px 8px;
            }
            """
        )

        act_app_info = QAction(f"Claude & Antigravity Usage v{__version__}", menu)
        act_app_info.setEnabled(False)
        menu.addAction(act_app_info)

        self._act_claude_summary = QAction(t("tray.init_claude"), menu)
        self._act_claude_summary.setEnabled(False)
        menu.addAction(self._act_claude_summary)

        self._act_ag_summary = QAction(t("tray.init_agy"), menu)
        self._act_ag_summary.setEnabled(False)
        menu.addAction(self._act_ag_summary)

        menu.addSeparator()

        self._act_show = QAction(t("tray.show_widget"), menu)
        self._act_show.triggered.connect(lambda: self.show_flyout())
        menu.addAction(self._act_show)

        self._act_refresh = QAction(t("tray.refresh_now"), menu)
        self._act_refresh.triggered.connect(self.refresh_requested.emit)
        menu.addAction(self._act_refresh)

        menu.addSeparator()

        self._act_settings = QAction(t("tray.settings"), menu)
        self._act_settings.triggered.connect(self._open_settings)
        menu.addAction(self._act_settings)

        self._act_help = QAction(t("tray.help", version=__version__), menu)
        self._act_help.triggered.connect(self._open_help)
        menu.addAction(self._act_help)

        menu.addSeparator()

        self._act_quit = QAction(t("tray.quit"), menu)
        self._act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(self._act_quit)

        return menu

    def retranslate_menu(self, _lang: str = "") -> None:
        """Dynamically retranslates context menu items on language change."""
        if hasattr(self, "_act_show"):
            self._act_show.setText(t("tray.show_widget"))
        if hasattr(self, "_act_refresh"):
            self._act_refresh.setText(t("tray.refresh_now"))
        if hasattr(self, "_act_settings"):
            self._act_settings.setText(t("tray.settings"))
        if hasattr(self, "_act_help"):
            self._act_help.setText(t("tray.help", version=__version__))
        if hasattr(self, "_act_quit"):
            self._act_quit.setText(t("tray.quit"))

    def _show_tray_icon(self, tray: QSystemTrayIcon, wm_class: str) -> None:
        """Shows a tray icon, using X11 QSystemTrayIconSys on Linux/GNOME for direct left/right click."""
        if not self._use_x11_tray:
            if tray is self:
                super().show()
            else:
                tray.show()
            return

        if not _has_x11_system_tray():
            QTimer.singleShot(500, self.show)
            return

        try:
            c_ptr = sip.unwrapinstance(tray)
            d_ptr = ctypes.c_uint64.from_address(c_ptr + 8).value
            sys_ptr = ctypes.c_uint64.from_address(d_ptr + 0xA8).value

            if not sys_ptr:
                # Disable QDBusTrayIcon (qpa_sys at offset 0xB0) so Qt uses QSystemTrayIconSys (XEmbed),
                # which receives direct Button1 (Trigger) and Button3 (Context) events on Ubuntu GNOME.
                ctypes.c_uint64.from_address(d_ptr + 0xB0).value = 0

                # Disable QSystemTrayWatcher (trayWatcher at offset 0xC0) so Qt never recreates
                # QSystemTrayIconSys behind our backs inside C++ with identical WM_CLASS when
                # GNOME Shell's ubuntu-appindicators extension restarts/loads at Ubuntu boot.
                ctypes.c_uint64.from_address(d_ptr + 0xC0).value = 1

                # Clear QXcbIntegration cached m_wmClass & m_instanceName so each icon receives
                # a distinct res_name and res_class at XCreateWindow time (t = 0.000ms)
                _clear_qpa_wm_class(wm_class)

                prev_name = QCoreApplication.applicationName()
                QCoreApplication.setApplicationName(wm_class)
                try:
                    if tray is self:
                        super().show()
                    else:
                        tray.show()
                finally:
                    QCoreApplication.setApplicationName(prev_name or "Claude & Antigravity Usage")

                sys_ptr = ctypes.c_uint64.from_address(d_ptr + 0xA8).value
                if sys_ptr:
                    self._configure_x11_tray_widget(sys_ptr, wm_class, is_new=True, tray=tray)
            else:
                if tray is self:
                    super().show()
                else:
                    tray.show()
                self._configure_x11_tray_widget(sys_ptr, wm_class, is_new=False, tray=tray)
        except Exception as e:
            logger.debug(f"Fallback to standard tray show ({wm_class}): {e}")
            if tray is self:
                super().show()
            else:
                tray.show()

    def _configure_x11_tray_widget(
        self,
        sys_ptr: int,
        wm_class: str,
        is_new: bool = True,
        tray: Optional[QSystemTrayIcon] = None,
    ) -> None:
        """Configures the X11 QSystemTrayIconSys widget to match the XEmbed socket size and unique WM_CLASS on GNOME."""
        try:
            w = sip.wrapinstance(sys_ptr, QWidget)
            w.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
            w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            w.setAutoFillBackground(True)
            pal = w.palette()
            pal.setColor(QPalette.ColorRole.Window, QColor("#131313"))
            w.setPalette(pal)
            wid = int(w.winId())

            # Install custom physical-pixel paint filter so HiDPI (dpr=2.0) never renders a 32x32 icon clipped by a 16x16 XEmbed socket
            if tray is None:
                if wm_class == "ClaudeUsageGemini":
                    tray = self.tray_antigravity
                elif wm_class == "ClaudeUsagePartner":
                    tray = self.tray_partner
                else:
                    tray = self

            if not hasattr(self, "_paint_filters"):
                self._paint_filters: dict[int, QObject] = {}

            if wid not in self._paint_filters:
                tray_ref = tray

                class _X11TrayPaintFilter(QObject):
                    def __init__(self, parent_obj: Optional[QObject] = None) -> None:
                        super().__init__(parent_obj)
                        self.socket_size: int = 16

                    def eventFilter(self, obj: Optional[QObject], event: Optional[QEvent]) -> bool:
                        if event is not None and event.type() == QEvent.Type.Paint and isinstance(obj, QWidget):
                            try:
                                dpr = max(1.0, float(obj.devicePixelRatioF()))
                                side = max(12, min(64, int(self.socket_size)))
                                p = QPainter(obj)
                                # Cancel Qt's automatic HiDPI devicePixelRatio scaling so 1 unit == 1 physical X11 pixel
                                p.scale(1.0 / dpr, 1.0 / dpr)
                                phys_w = max(side, int(round(obj.width() * dpr)))
                                phys_h = max(side, int(round(obj.height() * dpr)))
                                p.fillRect(0, 0, phys_w, phys_h, QColor("#131313"))
                                icon = tray_ref.icon()
                                if not icon.isNull():
                                    pm = icon.pixmap(QSize(side, side), 1.0)
                                    qimg = pm.toImage()
                                    qimg.setDevicePixelRatio(1.0)
                                    p.drawImage(0, 0, qimg)
                                p.end()
                                return True
                            except Exception as ex_paint:
                                logger.debug(f"Custom X11 tray paint filter error: {ex_paint}")
                        return False

                pf = _X11TrayPaintFilter(w)
                w.installEventFilter(pf)
                self._paint_filters[wid] = pf

            paint_filter = self._paint_filters.get(wid)

            class XClassHint(ctypes.Structure):
                _fields_ = [
                    ("res_name", ctypes.c_char_p),
                    ("res_class", ctypes.c_char_p),
                ]

            def _setup_xembed_properties() -> None:
                try:
                    x11 = ctypes.CDLL("libX11.so.6")
                    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
                    x11.XOpenDisplay.restype = ctypes.c_void_p
                    x11.XSetClassHint.argtypes = [
                        ctypes.c_void_p,
                        ctypes.c_ulong,
                        ctypes.POINTER(XClassHint),
                    ]
                    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
                    x11.XInternAtom.restype = ctypes.c_ulong
                    x11.XChangeProperty.argtypes = [
                        ctypes.c_void_p,
                        ctypes.c_ulong,
                        ctypes.c_ulong,
                        ctypes.c_ulong,
                        ctypes.c_int,
                        ctypes.c_int,
                        ctypes.c_char_p,
                        ctypes.c_int,
                    ]
                    x11.XQueryTree.argtypes = [
                        ctypes.c_void_p,
                        ctypes.c_ulong,
                        ctypes.POINTER(ctypes.c_ulong),
                        ctypes.POINTER(ctypes.c_ulong),
                        ctypes.POINTER(ctypes.c_void_p),
                        ctypes.POINTER(ctypes.c_uint),
                    ]
                    x11.XGetGeometry.argtypes = [
                        ctypes.c_void_p,
                        ctypes.c_ulong,
                        ctypes.POINTER(ctypes.c_ulong),
                        ctypes.POINTER(ctypes.c_int),
                        ctypes.POINTER(ctypes.c_int),
                        ctypes.POINTER(ctypes.c_uint),
                        ctypes.POINTER(ctypes.c_uint),
                        ctypes.POINTER(ctypes.c_uint),
                        ctypes.POINTER(ctypes.c_uint),
                    ]
                    x11.XMoveResizeWindow.argtypes = [
                        ctypes.c_void_p,
                        ctypes.c_ulong,
                        ctypes.c_int,
                        ctypes.c_int,
                        ctypes.c_uint,
                        ctypes.c_uint,
                    ]
                    x11.XFree.argtypes = [ctypes.c_void_p]
                    x11.XFlush.argtypes = [ctypes.c_void_p]
                    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

                    dpy = x11.XOpenDisplay(None)
                    if not dpy:
                        return

                    # 1. Enforce unique WM_CLASS per tray icon to prevent GNOME appindicator de-duplication
                    res_name = wm_class.lower().encode("latin1")
                    res_class = wm_class.encode("latin1")
                    hint = XClassHint(res_name=res_name, res_class=res_class)
                    x11.XSetClassHint(dpy, wid, ctypes.byref(hint))

                    # 2. Set _GTK_APPLICATION_ID and _KDE_NET_WM_DESKTOP_FILE
                    for prop_name in (b"_GTK_APPLICATION_ID", b"_KDE_NET_WM_DESKTOP_FILE"):
                        atom = x11.XInternAtom(dpy, prop_name, 0)
                        if atom:
                            x11.XChangeProperty(
                                dpy, wid, atom, 31, 8, 0, res_name, len(res_name)
                            )

                    # 3. Synchronize child window position (0, 0) and size with XEmbed parent socket
                    root = ctypes.c_ulong()
                    parent = ctypes.c_ulong()
                    children = ctypes.c_void_p()
                    nchildren = ctypes.c_uint()
                    ret = x11.XQueryTree(
                        dpy,
                        wid,
                        ctypes.byref(root),
                        ctypes.byref(parent),
                        ctypes.byref(children),
                        ctypes.byref(nchildren),
                    )
                    if children.value:
                        x11.XFree(children)

                    side = 16
                    if ret and parent.value and parent.value != root.value:
                        p_root = ctypes.c_ulong()
                        px = ctypes.c_int()
                        py = ctypes.c_int()
                        pw = ctypes.c_uint()
                        ph = ctypes.c_uint()
                        p_bw = ctypes.c_uint()
                        p_depth = ctypes.c_uint()
                        if x11.XGetGeometry(
                            dpy,
                            parent.value,
                            ctypes.byref(p_root),
                            ctypes.byref(px),
                            ctypes.byref(py),
                            ctypes.byref(pw),
                            ctypes.byref(ph),
                            ctypes.byref(p_bw),
                            ctypes.byref(p_depth),
                        ):
                            if pw.value >= 12 and ph.value >= 12:
                                side = max(12, min(64, min(int(pw.value), int(ph.value))))

                    if paint_filter is not None:
                        paint_filter.socket_size = side

                    # Always anchor wid at (0, 0) inside parent.value using pure X11 XMoveResizeWindow
                    # (never call w.resize() in Qt, which corrupts relative X11 coordinates under dpr=2.0)
                    x11.XMoveResizeWindow(dpy, wid, 0, 0, side, side)
                    x11.XFlush(dpy)
                    x11.XCloseDisplay(dpy)
                    w.update()
                    if self._linux_hover_sensor is not None:
                        self._linux_hover_sensor.update_sensor_geometry()
                except Exception as ex:
                    logger.debug(f"XEmbed property configuration failed: {ex}")

            _setup_xembed_properties()
            if is_new or wid not in self._x11_configured:
                self._x11_configured.add(wid)
                for delay_ms in (50, 250, 800, 1500):
                    QTimer.singleShot(delay_ms, _setup_xembed_properties)
        except Exception as e:
            logger.debug(f"Failed configuring X11 tray widget: {e}")

    def _get_active_tray_centers(self, primary) -> list[tuple[int, QSystemTrayIcon]]:
        """Returns (center_x, tray_icon) on primaryScreen() for all currently visible tray icons."""
        result: list[tuple[int, QSystemTrayIcon]] = []
        for tray in (self, self.tray_antigravity, self.tray_partner):
            if tray.isVisible():
                cx = WindowPositioner._resolve_linux_tray_center_x(tray.geometry(), primary)
                if cx is not None:
                    result.append((cx, tray))
        return result

    def _popup_context_menu(self, tray_geometry: QRect) -> None:
        """Pops up the context menu directly below the clicked tray icon on the primary screen."""
        if self._linux_tooltip is not None:
            self._linux_tooltip.hide()

        pos = WindowPositioner.calculate_menu_position(tray_geometry, self._shared_menu.sizeHint().width() or 240)

        if self._menu_backdrop is not None:
            primary = QGuiApplication.primaryScreen()
            if primary:
                self._menu_backdrop.setGeometry(primary.geometry())
                self._menu_backdrop.show()
                self._menu_backdrop.raise_()

        self._shared_menu.popup(pos)
        self._shared_menu.raise_()

    def on_settings_saved(self, _cfg: object = None) -> None:
        """Triggered immediately when user saves settings from the flyout window."""
        self.show()

    def show(self) -> None:
        """Shows active tray icons based on user configuration."""
        if self._use_x11_tray and not _has_x11_system_tray():
            QTimer.singleShot(500, self.show)
            return

        cfg = getattr(self.flyout, "config", None)
        enable_claude = getattr(cfg, "enable_claude", True)
        enable_antigravity = getattr(cfg, "enable_antigravity", True)
        tray_mode = getattr(cfg, "antigravity_tray_mode", "single_icon")

        if enable_claude:
            self._show_tray_icon(self, "ClaudeUsageClaude")
        else:
            super().hide()

        if enable_antigravity:
            self._show_tray_icon(self.tray_antigravity, "ClaudeUsageGemini")
            if tray_mode == "split_partner_icon":
                self._show_tray_icon(self.tray_partner, "ClaudeUsagePartner")
            else:
                self.tray_partner.hide()
        else:
            self.tray_antigravity.hide()
            self.tray_partner.hide()

        if self._linux_hover_sensor is not None:
            QTimer.singleShot(300, self._linux_hover_sensor.update_sensor_geometry)

        if self._use_x11_tray:
            for delay_ms in (1200, 3000, 6000):
                QTimer.singleShot(delay_ms, self._verify_x11_tray_docking)

    def _on_suspend_watchdog_tick(self) -> None:
        """Periodic health check and suspend/resume detection via time.monotonic clock gap."""
        if not self._use_x11_tray:
            return
        now = time.monotonic()
        elapsed = now - getattr(self, "_last_watchdog_tick", now)
        self._last_watchdog_tick = now

        # A clock gap > 7.0s between 3.0s ticks means the system was asleep/suspended
        if elapsed > 7.0:
            logger.info(
                f"System resume from suspend detected (clock gap {elapsed:.1f}s), re-docking all X11 tray icons..."
            )
            self._redock_attempts.clear()
            for delay in (150, 600, 1500, 3500):
                QTimer.singleShot(delay, self._verify_x11_tray_docking)
            return

        # Periodic health check: verify no tray icon is orphaned on the root desktop
        self._verify_x11_tray_docking()

    def _on_screens_changed(self, *args) -> None:
        """Triggered whenever display configuration changes (e.g. HDMI reconnect, display wake)."""
        if not self._use_x11_tray:
            return
        logger.info("Screen/display topology changed, verifying X11 tray docking and sensor geometry...")
        self._redock_attempts.clear()
        for delay in (200, 800, 2000):
            QTimer.singleShot(delay, self._verify_x11_tray_docking)
        if self._linux_hover_sensor is not None:
            self._linux_hover_sensor.update_sensor_geometry()

    def _redock_x11_window(self, wid: int, wm_class: str) -> bool:
        """Sends X11 SYSTEM_TRAY_REQUEST_DOCK to the active _NET_SYSTEM_TRAY_S0 owner for wid."""
        if not self._use_x11_tray:
            return False
        try:
            x11 = ctypes.CDLL("libX11.so.6")
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            x11.XInternAtom.restype = ctypes.c_ulong
            x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            x11.XGetSelectionOwner.restype = ctypes.c_ulong
            x11.XUnmapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            x11.XSendEvent.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_int,
                ctypes.c_long,
                ctypes.c_void_p,
            ]
            x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

            dpy = x11.XOpenDisplay(None)
            if not dpy:
                return False

            atom_tray = x11.XInternAtom(dpy, b"_NET_SYSTEM_TRAY_S0", 0)
            atom_opcode = x11.XInternAtom(dpy, b"_NET_SYSTEM_TRAY_OPCODE", 0)
            owner = x11.XGetSelectionOwner(dpy, atom_tray)
            if not owner:
                x11.XCloseDisplay(dpy)
                return False

            # Immediately unmap from root so it never flashes or remains at (0, 0)
            x11.XUnmapWindow(dpy, wid)

            class XClientMessageEvent(ctypes.Structure):
                _fields_ = [
                    ("type", ctypes.c_int),
                    ("serial", ctypes.c_ulong),
                    ("send_event", ctypes.c_int),
                    ("display", ctypes.c_void_p),
                    ("window", ctypes.c_ulong),
                    ("message_type", ctypes.c_ulong),
                    ("format", ctypes.c_int),
                    ("data_l", ctypes.c_long * 5),
                ]

            ev = XClientMessageEvent()
            ev.type = 33  # ClientMessage
            ev.window = owner
            ev.message_type = atom_opcode
            ev.format = 32
            ev.data_l[0] = 0  # CurrentTime
            ev.data_l[1] = 0  # SYSTEM_TRAY_REQUEST_DOCK
            ev.data_l[2] = wid  # our tray window ID
            ev.data_l[3] = 0
            ev.data_l[4] = 0

            x11.XSendEvent(dpy, owner, 0, 0, ctypes.byref(ev))
            x11.XSync(dpy, 0)
            x11.XCloseDisplay(dpy)
            logger.info(f"Re-docked X11 tray icon {wm_class} (wid={hex(wid)}) into tray owner {hex(owner)}")
            return True
        except Exception as e:
            logger.debug(f"Failed sending SYSTEM_TRAY_REQUEST_DOCK for {wm_class}: {e}")
            return False

    def _verify_x11_tray_docking(self) -> None:
        """Self-healing watchdog: detects orphaned tray windows on root (0, 0) and re-docks them."""
        if not self._use_x11_tray or not _has_x11_system_tray():
            return

        cfg = getattr(self.flyout, "config", None)
        enable_claude = getattr(cfg, "enable_claude", True)
        enable_antigravity = getattr(cfg, "enable_antigravity", True)
        tray_mode = getattr(cfg, "antigravity_tray_mode", "single_icon")

        expected: list[tuple[QSystemTrayIcon, str]] = []
        if enable_claude:
            expected.append((self, "ClaudeUsageClaude"))
        if enable_antigravity:
            expected.append((self.tray_antigravity, "ClaudeUsageGemini"))
            if tray_mode == "split_partner_icon":
                expected.append((self.tray_partner, "ClaudeUsagePartner"))

        try:
            x11 = ctypes.CDLL("libX11.so.6")
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XQueryTree.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_uint),
            ]
            x11.XGetGeometry.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_uint),
            ]
            x11.XMoveResizeWindow.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.c_uint,
            ]
            x11.XFree.argtypes = [ctypes.c_void_p]
            x11.XFlush.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

            dpy = x11.XOpenDisplay(None)
            if not dpy:
                return
            root_wid = x11.XDefaultRootWindow(dpy)
        except Exception as e:
            logger.debug(f"Cannot initialize X11 display for docking check: {e}")
            return

        try:
            for tray, wm_class in expected:
                try:
                    c_ptr = sip.unwrapinstance(tray)
                    d_ptr = ctypes.c_uint64.from_address(c_ptr + 8).value
                    sys_ptr = ctypes.c_uint64.from_address(d_ptr + 0xA8).value

                    if not sys_ptr:
                        self._show_tray_icon(tray, wm_class)
                        continue

                    w = sip.wrapinstance(sys_ptr, QWidget)
                    wid = int(w.winId())
                    if not wid:
                        continue

                    # Query parent window in X11 tree
                    r = ctypes.c_ulong()
                    p = ctypes.c_ulong()
                    children = ctypes.c_void_p()
                    nchildren = ctypes.c_uint()
                    ret = x11.XQueryTree(
                        dpy,
                        wid,
                        ctypes.byref(r),
                        ctypes.byref(p),
                        ctypes.byref(children),
                        ctypes.byref(nchildren),
                    )
                    if children.value:
                        x11.XFree(children)

                    # An icon is orphaned ONLY if XQueryTree failed or its parent is root_wid (not embedded in tray socket).
                    # Never treat a docked window (p.value != root_wid) as orphaned based on geom.x() == 0,
                    # because unmapping an already-embedded XEmbed plug breaks Mutter's GtkSocket SubstructureRedirectMask!
                    is_orphaned = (
                        not ret
                        or not p.value
                        or p.value == root_wid
                    )

                    if is_orphaned:
                        attempts = self._redock_attempts.get(wm_class, 0)
                        if attempts < 8:
                            self._redock_attempts[wm_class] = attempts + 1
                            logger.info(
                                f"Detected orphaned/undocked X11 tray icon {wm_class} "
                                f"(wid={hex(wid)}, parent={hex(p.value)}, attempt {attempts + 1})"
                            )
                            # Re-dock by sending SYSTEM_TRAY_REQUEST_DOCK
                            self._redock_x11_window(wid, wm_class)
                            self._configure_x11_tray_widget(sys_ptr, wm_class, is_new=True, tray=tray)
                    else:
                        self._redock_attempts[wm_class] = 0
                        # Ensure embedded child window stays anchored at (0, 0) inside parent socket (never call w.resize in Qt!)
                        p_root = ctypes.c_ulong()
                        px = ctypes.c_int()
                        py = ctypes.c_int()
                        pw = ctypes.c_uint()
                        ph = ctypes.c_uint()
                        p_bw = ctypes.c_uint()
                        p_depth = ctypes.c_uint()
                        if x11.XGetGeometry(
                            dpy,
                            p.value,
                            ctypes.byref(p_root),
                            ctypes.byref(px),
                            ctypes.byref(py),
                            ctypes.byref(pw),
                            ctypes.byref(ph),
                            ctypes.byref(p_bw),
                            ctypes.byref(p_depth),
                        ):
                            if pw.value >= 12 and ph.value >= 12:
                                side = max(12, min(64, min(int(pw.value), int(ph.value))))
                                pf = getattr(self, "_paint_filters", {}).get(wid)
                                if pf is not None:
                                    pf.socket_size = side
                                w_root = ctypes.c_ulong()
                                wx = ctypes.c_int()
                                wy = ctypes.c_int()
                                ww = ctypes.c_uint()
                                wh = ctypes.c_uint()
                                w_bw = ctypes.c_uint()
                                w_depth = ctypes.c_uint()
                                if x11.XGetGeometry(
                                    dpy,
                                    wid,
                                    ctypes.byref(w_root),
                                    ctypes.byref(wx),
                                    ctypes.byref(wy),
                                    ctypes.byref(ww),
                                    ctypes.byref(wh),
                                    ctypes.byref(w_bw),
                                    ctypes.byref(w_depth),
                                ):
                                    if wx.value != 0 or wy.value != 0 or ww.value != side or wh.value != side:
                                        x11.XMoveResizeWindow(dpy, wid, 0, 0, side, side)
                                        x11.XFlush(dpy)
                                        w.update()
                except Exception as ex:
                    logger.debug(f"Error inspecting tray {wm_class}: {ex}")
        finally:
            x11.XCloseDisplay(dpy)

        if self._linux_hover_sensor is not None:
            self._linux_hover_sensor.update_sensor_geometry()

    def hide(self) -> None:
        super().hide()
        self.tray_antigravity.hide()
        self.tray_partner.hide()
        if self._linux_tooltip is not None:
            self._linux_tooltip.hide()
        if self._linux_hover_sensor is not None:
            self._linux_hover_sensor.hide()

    def cleanup(self) -> None:
        """Hides and explicitly unregisters all tray icons from the OS panel and D-Bus."""
        try:
            if hasattr(self, "_suspend_watchdog_timer") and self._suspend_watchdog_timer.isActive():
                self._suspend_watchdog_timer.stop()
            self.hide()
            if self._linux_tooltip is not None:
                self._linux_tooltip.close()
            if self._linux_hover_sensor is not None:
                self._linux_hover_sensor.close()
            if self._menu_backdrop is not None:
                self._menu_backdrop.close()
            self.setVisible(False)
            self.tray_antigravity.setVisible(False)
            self.tray_partner.setVisible(False)
            self.setContextMenu(None)
            self.tray_antigravity.setContextMenu(None)
            self.tray_partner.setContextMenu(None)
        except Exception as e:
            logger.debug(f"Error during tray cleanup: {e}")

    def _on_claude_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if self._linux_tooltip is not None:
            self._linux_tooltip.hide()
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        ):
            self.flyout.toggle_at_tray(self.geometry(), target_tab="claude")
        elif reason == QSystemTrayIcon.ActivationReason.Context and self._use_x11_tray:
            self._popup_context_menu(self.geometry())

    def _on_antigravity_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if self._linux_tooltip is not None:
            self._linux_tooltip.hide()
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        ):
            self.flyout.toggle_at_tray(self.tray_antigravity.geometry(), target_tab="antigravity")
        elif reason == QSystemTrayIcon.ActivationReason.Context and self._use_x11_tray:
            self._popup_context_menu(self.tray_antigravity.geometry())

    def _on_partner_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if self._linux_tooltip is not None:
            self._linux_tooltip.hide()
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        ):
            self.flyout.toggle_at_tray(self.tray_partner.geometry(), target_tab="antigravity_partner")
        elif reason == QSystemTrayIcon.ActivationReason.Context and self._use_x11_tray:
            self._popup_context_menu(self.tray_partner.geometry())


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
            icon_claude = IconRenderer.render_tray_icon(
                five_hour_pct=claude_snap.five_hour.utilization_pct,
                seven_day_pct=claude_snap.seven_day.utilization_pct,
                is_offline=claude_snap.is_offline,
                style=style,
                provider_type="claude",
            )
            self.setIcon(icon_claude)
            self._show_tray_icon(self, "ClaudeUsageClaude")

            p5 = int(round(claude_snap.five_hour.utilization_pct))
            p7 = int(round(claude_snap.seven_day.utilization_pct))
            txt = f"5h: {p5}% ({claude_snap.five_hour.time_remaining_str}) | 7g: {p7}% ({claude_snap.seven_day.time_remaining_str})"
            self.setToolTip(truncate_tooltip(claude_snap.workspace_name, txt))
            self._act_claude_summary.setText(f"🟠 Claude: {txt}")
            self._act_claude_summary.setVisible(True)
        else:
            super().hide()
            self._act_claude_summary.setVisible(False)

        # 2. Update Antigravity Icon(s)
        if enable_antigravity and antigravity_snap:
            if tray_mode == "split_partner_icon":
                # Icon 2: Gemini (with dedicated Argon alert badge if active)
                argon_val = (
                    antigravity_snap.gemini_argon_7d.utilization_pct
                    if antigravity_snap.gemini_argon_7d is not None
                    else None
                )
                icon_gemini = IconRenderer.render_tray_icon(
                    five_hour_pct=antigravity_snap.gemini_5h.utilization_pct,
                    seven_day_pct=antigravity_snap.gemini_7d.utilization_pct,
                    is_offline=antigravity_snap.is_offline,
                    style=style,
                    provider_type="antigravity_gemini",
                    argon_pct=argon_val,
                )
                self.tray_antigravity.setIcon(icon_gemini)
                self._show_tray_icon(self.tray_antigravity, "ClaudeUsageGemini")
                g5 = int(round(antigravity_snap.gemini_5h.utilization_pct))
                g7 = int(round(antigravity_snap.gemini_7d.utilization_pct))
                if antigravity_snap.gemini_argon_7d is not None:
                    ar7 = int(round(antigravity_snap.gemini_argon_7d.utilization_pct))
                    gtxt = f"5h: {g5}% ({antigravity_snap.gemini_5h.time_remaining_str}) | 7g: {g7}% | Argon: {ar7}%"
                else:
                    gtxt = f"5h: {g5}% ({antigravity_snap.gemini_5h.time_remaining_str}) | 7g: {g7}% ({antigravity_snap.gemini_7d.time_remaining_str})"
                self.tray_antigravity.setToolTip(truncate_tooltip("Antigravity Gemini", gtxt))
                self._act_ag_summary.setText(f"🔵 Gemini: {gtxt}")
                self._act_ag_summary.setVisible(True)

                # Icon 3: Partner
                icon_partner = IconRenderer.render_tray_icon(
                    five_hour_pct=antigravity_snap.partner_5h.utilization_pct,
                    seven_day_pct=antigravity_snap.partner_7d.utilization_pct,
                    is_offline=antigravity_snap.is_offline,
                    style=style,
                    provider_type="antigravity_partner",
                )
                self.tray_partner.setIcon(icon_partner)
                self._show_tray_icon(self.tray_partner, "ClaudeUsagePartner")
                prt5 = int(round(antigravity_snap.partner_5h.utilization_pct))
                prt7 = int(round(antigravity_snap.partner_7d.utilization_pct))
                ptxt = f"5h: {prt5}% ({antigravity_snap.partner_5h.time_remaining_str}) | 7g: {prt7}% ({antigravity_snap.partner_7d.time_remaining_str})"
                self.tray_partner.setToolTip(truncate_tooltip("Antigravity Partner", ptxt))

            else:
                self.tray_partner.hide()

                # Single Icon: selected pool
                p5_val, p7_val, pool_lbl = antigravity_snap.get_single_pool_utilization(single_pool)
                prov_t = "antigravity_partner" if pool_lbl == "Partner" else "antigravity_gemini"
                argon_single = (
                    antigravity_snap.gemini_argon_7d.utilization_pct
                    if (antigravity_snap.gemini_argon_7d is not None and pool_lbl != "Partner")
                    else None
                )

                icon_single = IconRenderer.render_tray_icon(
                    five_hour_pct=p5_val,
                    seven_day_pct=p7_val,
                    is_offline=antigravity_snap.is_offline,
                    style=style,
                    provider_type=prov_t,
                    argon_pct=argon_single,
                )
                self.tray_antigravity.setIcon(icon_single)
                self._show_tray_icon(self.tray_antigravity, "ClaudeUsageGemini")

                p5_int = int(round(p5_val))
                p7_int = int(round(p7_val))
                time_str = (
                    antigravity_snap.partner_5h.time_remaining_str
                    if pool_lbl == "Partner"
                    else antigravity_snap.gemini_5h.time_remaining_str
                )
                stxt = f"5h: {p5_int}% ({time_str}) | 7g: {p7_int}%"
                self.tray_antigravity.setToolTip(truncate_tooltip(f"Antigravity {pool_lbl}", stxt))
                self._act_ag_summary.setText(f"🔵 Antigravity ({pool_lbl}): {stxt}")
                self._act_ag_summary.setVisible(True)
        else:
            self.tray_antigravity.hide()
            self.tray_partner.hide()
            self._act_ag_summary.setVisible(False)

        if self._linux_hover_sensor is not None:
            self._linux_hover_sensor.update_sensor_geometry()

        if self._use_x11_tray:
            QTimer.singleShot(500, self._verify_x11_tray_docking)


# Alias for architectural clarity
TrayCoordinator = TrayController
