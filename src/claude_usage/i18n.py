"""Internationalization (i18n) and localization support for Claude & Antigravity Usage Widget."""

from __future__ import annotations

import locale
import logging
import os
import sys
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "auto": "Auto (Sistema / System)",
    "it": "Italiano 🇮🇹",
    "en": "English 🇬🇧",
}

_active_language_setting: str = "auto"
_resolved_language: str = "it"
_listeners: list[Callable[[str], None]] = []


def detect_system_language() -> str:
    """Detects system language code ('it' or 'en')."""
    candidates: list[str] = []
    try:
        loc = locale.getlocale()[0]
        if loc:
            candidates.append(loc)
    except Exception:
        pass

    for env_var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(env_var)
        if val:
            candidates.append(val)

    for cand in candidates:
        lower = cand.lower()
        if lower.startswith("it"):
            return "it"
        if lower.startswith("en"):
            return "en"

    return "en"


def get_current_language() -> str:
    """Returns the effective resolved 2-letter language code ('it' or 'en')."""
    global _resolved_language
    return _resolved_language


def get_language_setting() -> str:
    """Returns the user configured language setting ('auto', 'it', or 'en')."""
    global _active_language_setting
    return _active_language_setting


def set_language(lang_code: str) -> None:
    """Sets active language and notifies registered listeners."""
    global _active_language_setting, _resolved_language
    clean = lang_code.strip().lower()
    if clean not in SUPPORTED_LANGUAGES:
        clean = "auto"

    _active_language_setting = clean
    if clean == "auto":
        _resolved_language = detect_system_language()
    else:
        _resolved_language = clean

    logger.debug(f"Language set to: setting={_active_language_setting}, resolved={_resolved_language}")
    for listener in _listeners:
        try:
            listener(_resolved_language)
        except Exception as e:
            logger.debug(f"Error notifying i18n listener: {e}")


def register_language_listener(callback: Callable[[str], None]) -> None:
    """Registers a callback function to be called when the language changes."""
    if callback not in _listeners:
        _listeners.append(callback)


def t(key: str, **kwargs) -> str:
    """Translates a key into the currently active language, applying optional format kwargs."""
    lang = get_current_language()
    table = TRANSLATIONS.get(lang) or TRANSLATIONS["it"]
    text = table.get(key)
    if text is None:
        # Fallback to Italian, then English
        text = TRANSLATIONS["it"].get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


TRANSLATIONS: dict[str, dict[str, str]] = {
    "it": {
        # Nav bar
        "nav.metrics": "📊 Metriche",
        "nav.settings": "⚙️ Impostazioni",
        "nav.help": "ℹ️ Guida & Info",
        "flyout.refresh_tooltip": "Aggiorna quote adesso",

        # Sub bar
        "sub.overview": "⚖️ Panoramica",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        # Overview cards
        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Libero)",
        "overview.reset_in": "Reset in {time}",
        "overview.btn_go_claude": "Dettaglio Claude ↗",
        "overview.btn_go_agy": "Dettaglio Google ↗",
        "overview.parallel_title": "💡 Stato di Utilizzo Parallelo",

        # Claude details
        "claude.tab_5h": "⏱️ Sessione 5h",
        "claude.tab_7d": "📅 Settimanale (7g)",
        "claude.session_row": "⏱️ Sessione 5h: {pct}%",
        "claude.weekly_row": "📅 Settimanale: {pct}%",
        "claude.rate_hourly": "{rate}% / ora",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Token Totali",
        "claude.burn_rate": "Velocità Consumo",
        "claude.window_active": "Finestra Attiva",

        # Antigravity details
        "agy.tab_gemini": "✨ Pool Gemini",
        "agy.tab_partner": "🤝 Modelli Partner",
        "agy.session_row": "⏱️ Sessione 5h: {pct}%",
        "agy.weekly_row": "📅 Settimanale: {pct}%",
        "agy.partner_sub": "{models} Modelli Partner",
        "agy.credits_info": "💳 AI Credits: {status}  •  Account: {account}",
        "agy.credits_available": "Disponibili",
        "agy.credits_included": "Inclusi",

        # Settings
        "settings.title": "🔌 Servizi Attivi & Icone Taskbar (v{version})",
        "settings.inactive": "Inattivo",
        "settings.enable_claude": "Monitora Claude Code",
        "settings.enable_agy": "Monitora Google Antigravity",
        "settings.agy_mode_lbl": "Visualizzazione Taskbar per Antigravity:",
        "settings.tray_single": "1 Icona (Unificata)",
        "settings.tray_split": "2 Icone (+ Partner)",
        "settings.which_pool_lbl": "Pool visualizzato nell'icona singola:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 Partner",
        "settings.pool_max": "🔥 Max Consumo",
        "settings.split_hint": "💡 Verranno mostrate 2 icone separate: Gemini (Azzurro) e Partner (Smeraldo).",
        "settings.auth_title": "🔐 Account Connessi",
        "settings.btn_login_claude": "🔑 Accedi con Claude (1-Click)",
        "settings.btn_login_google": "🔑 Accedi con Google (1-Click)",
        "settings.btn_logout": "🚪 Disconnetti",
        "settings.notif_title": "🔔 Notifiche & Soglie Alert",
        "settings.chk_notif": "Notifiche Push",
        "settings.thresholds_lbl": "Soglie attive (%):",
        "settings.burn_rate_chk": "🔥 Alert Consumo Rapido (+15% in <10m / Loop)",
        "settings.style_title": "🎨 Stile Icone Taskbar & Sistema",
        "settings.style_concentric": "⭕ Anelli\n(5h / 7g)",
        "settings.style_split": "🌗 Archi Split\n(Sx 5h / Dx 7g)",
        "settings.style_bars": "📊 Doppie Barre\n(Colonne 5h / 7g)",
        "settings.lang_title": "🌐 Lingua dell'Interfaccia",
        "settings.autostart": "🚀 Esegui all'avvio del sistema",
        "settings.mock": "🧪 Simulazione Demo (Mock)",
        "settings.save": "💾 Salva Impostazioni",
        "settings.saved_toast": "✅ Impostazioni salvate!",

        # Tray & Menu
        "tray.show_widget": "📊 Mostra Widget",
        "tray.refresh_now": "↻ Aggiorna Adesso",
        "tray.settings": "⚙️ Impostazioni",
        "tray.help": "ℹ️ Informazioni & Help (v{version} - giuspo)",
        "tray.quit": "❌ Esci",
        "tray.init_claude": "🟠 Claude: Inizializzazione...",
        "tray.init_agy": "🔵 Antigravity: Inizializzazione...",
        "tray.loading": "Caricamento quote in corso...",
        "tray.no_session": "Nessuna sessione attiva",

        # Status
        "status.connected": "🟢 Connesso",
        "status.connected_claude": "🟢 Connesso via Claude OAuth",
        "status.connected_google": "🟢 Connesso via Google AI Pro",
        "status.disconnected": "🟡 Disconnesso",
        "status.offline": "🔴 Offline",
        "status.demo": "🧪 Modalità Demo (Mock)",

        # Notifier
        "notif.crit_title": "🚨 Claude Code: Quota Critica ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Soglia Raggiunta ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Utilizzo al {pct}%",
        "notif.body": "[{workspace}] Hai raggiunto il {pct}% del limite.\nReset previsto tra {time}.",
        "notif.spike_title": "🔥 Claude Code: Consumo Rapido!",
        "notif.spike_body": "[{workspace}] Aumento anomalo del +{delta}% negli ultimi {minutes} min.\nConsumo attuale: {pct}%.",

        # Help
        "help.creator": "Ideato e sviluppato da <b>giuspo</b> 🚀",
        "help.license": "🛡️ Licenza: GNU GPLv3 (Copyleft Forte)",
        "help.purpose_title": "🎯 Scopo dell'Applicazione Multi-Provider",
        "help.purpose_body": (
            "Monitora in tempo reale dalla barra delle attività le quote d'uso sia di <b>Claude Code (Anthropic)</b> "
            "sia di <b>Google Antigravity (Google AI Pro)</b>, inclusi i modelli Gemini e i modelli Partner (Claude Sonnet/Opus, GPT-OSS). "
            "Puoi visualizzare le icone affiancate o scegliere solo uno dei due servizi."
        ),
    },
    "en": {
        # Nav bar
        "nav.metrics": "📊 Metrics",
        "nav.settings": "⚙️ Settings",
        "nav.help": "ℹ️ Guide & Info",
        "flyout.refresh_tooltip": "Refresh quotas now",

        # Sub bar
        "sub.overview": "⚖️ Overview",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        # Overview cards
        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Free)",
        "overview.reset_in": "Reset in {time}",
        "overview.btn_go_claude": "Claude Details ↗",
        "overview.btn_go_agy": "Google Details ↗",
        "overview.parallel_title": "💡 Parallel Usage Status",

        # Claude details
        "claude.tab_5h": "⏱️ 5h Session",
        "claude.tab_7d": "📅 Weekly (7d)",
        "claude.session_row": "⏱️ 5h Session: {pct}%",
        "claude.weekly_row": "📅 Weekly: {pct}%",
        "claude.rate_hourly": "{rate}% / hr",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Total Tokens",
        "claude.burn_rate": "Burn Rate",
        "claude.window_active": "Active Window",

        # Antigravity details
        "agy.tab_gemini": "✨ Gemini Pool",
        "agy.tab_partner": "🤝 Partner Models",
        "agy.session_row": "⏱️ 5h Session: {pct}%",
        "agy.weekly_row": "📅 Weekly: {pct}%",
        "agy.partner_sub": "{models} Partner Models",
        "agy.credits_info": "💳 AI Credits: {status}  •  Account: {account}",
        "agy.credits_available": "Available",
        "agy.credits_included": "Included",

        # Settings
        "settings.title": "🔌 Active Services & Taskbar Icons (v{version})",
        "settings.inactive": "Inactive",
        "settings.enable_claude": "Monitor Claude Code",
        "settings.enable_agy": "Monitor Google Antigravity",
        "settings.agy_mode_lbl": "Taskbar Display for Antigravity:",
        "settings.tray_single": "1 Icon (Unified)",
        "settings.tray_split": "2 Icons (+ Partner)",
        "settings.which_pool_lbl": "Pool displayed in single icon:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 Partner",
        "settings.pool_max": "🔥 Max Usage",
        "settings.split_hint": "💡 2 separate icons will be displayed: Gemini (Blue) and Partner (Emerald).",
        "settings.auth_title": "🔐 Connected Accounts",
        "settings.btn_login_claude": "🔑 Login with Claude (1-Click)",
        "settings.btn_login_google": "🔑 Login with Google (1-Click)",
        "settings.btn_logout": "🚪 Logout",
        "settings.notif_title": "🔔 Notifications & Alert Thresholds",
        "settings.chk_notif": "Push Notifications",
        "settings.thresholds_lbl": "Active thresholds (%):",
        "settings.burn_rate_chk": "🔥 Rapid Consumption Alert (+15% in <10m / Loop)",
        "settings.style_title": "🎨 Taskbar & System Icon Style",
        "settings.style_concentric": "⭕ Rings\n(5h / 7d)",
        "settings.style_split": "🌗 Split Arcs\n(L 5h / R 7d)",
        "settings.style_bars": "📊 Dual Bars\n(Bars 5h / 7d)",
        "settings.lang_title": "🌐 Interface Language",
        "settings.autostart": "🚀 Launch at system startup",
        "settings.mock": "🧪 Demo Simulation (Mock)",
        "settings.save": "💾 Save Settings",
        "settings.saved_toast": "✅ Settings saved!",

        # Tray & Menu
        "tray.show_widget": "📊 Show Widget",
        "tray.refresh_now": "↻ Refresh Now",
        "tray.settings": "⚙️ Settings",
        "tray.help": "ℹ️ About & Help (v{version} - giuspo)",
        "tray.quit": "❌ Quit",
        "tray.init_claude": "🟠 Claude: Initializing...",
        "tray.init_agy": "🔵 Antigravity: Initializing...",
        "tray.loading": "Loading quotas...",
        "tray.no_session": "No active session",

        # Status
        "status.connected": "🟢 Connected",
        "status.connected_claude": "🟢 Connected via Claude OAuth",
        "status.connected_google": "🟢 Connected via Google AI Pro",
        "status.disconnected": "🟡 Disconnected",
        "status.offline": "🔴 Offline",
        "status.demo": "🧪 Demo Mode (Mock)",

        # Notifier
        "notif.crit_title": "🚨 Claude Code: Critical Quota ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Threshold Reached ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Usage at {pct}%",
        "notif.body": "[{workspace}] You reached {pct}% of the limit.\nReset expected in {time}.",
        "notif.spike_title": "🔥 Claude Code: Rapid Consumption!",
        "notif.spike_body": "[{workspace}] Anomaly spike of +{delta}% in the last {minutes} min.\nCurrent usage: {pct}%.",

        # Help
        "help.creator": "Designed and developed by <b>giuspo</b> 🚀",
        "help.license": "🛡️ License: GNU GPLv3 (Strong Copyleft)",
        "help.purpose_title": "🎯 Multi-Provider Application Purpose",
        "help.purpose_body": (
            "Monitor real-time taskbar usage quotas for both <b>Claude Code (Anthropic)</b> "
            "and <b>Google Antigravity (Google AI Pro)</b>, including Gemini models and Partner models (Claude Sonnet/Opus, GPT-OSS). "
            "You can display side-by-side icons or choose to monitor only one service."
        ),
    },
}
