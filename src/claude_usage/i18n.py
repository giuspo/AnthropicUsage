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
    "es": "Español 🇪🇸",
    "fr": "Français 🇫🇷",
    "de": "Deutsch 🇩🇪",
    "pt": "Português 🇵🇹",
    "ja": "日本語 🇯🇵",
    "zh": "简体中文 🇨🇳",
}

_active_language_setting: str = "auto"
_resolved_language: str = "it"
_listeners: list[Callable[[str], None]] = []


def detect_system_language() -> str:
    """Detects system language code ('it', 'en', 'es', 'fr', 'de', 'pt', 'ja', 'zh')."""
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
        if lower.startswith("es"):
            return "es"
        if lower.startswith("fr"):
            return "fr"
        if lower.startswith("de"):
            return "de"
        if lower.startswith("pt"):
            return "pt"
        if lower.startswith("ja"):
            return "ja"
        if lower.startswith("zh"):
            return "zh"
        if lower.startswith("en"):
            return "en"

    return "en"


def get_current_language() -> str:
    """Returns the effective resolved 2-letter language code."""
    global _resolved_language
    return _resolved_language


def get_language_setting() -> str:
    """Returns the user configured language setting ('auto', 'it', 'en', etc.)."""
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
        # Fallback to English, then Italian
        text = TRANSLATIONS["en"].get(key, TRANSLATIONS["it"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


TRANSLATIONS: dict[str, dict[str, str]] = {
    # =========================================================================
    # ITALIANO (it)
    # =========================================================================
    "it": {
        "nav.metrics": "📊 Metriche",
        "nav.settings": "⚙️ Impostazioni",
        "nav.help": "ℹ️ Guida & Info",
        "flyout.refresh_tooltip": "Aggiorna quote adesso",

        "sub.overview": "⚖️ Panoramica",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Libero)",
        "overview.reset_in": "Reset in {time}",
        "overview.btn_go_claude": "Dettaglio Claude ↗",
        "overview.btn_go_agy": "Dettaglio Google ↗",
        "overview.parallel_title": "💡 Stato di Utilizzo Parallelo",

        "claude.tab_5h": "⏱️ Sessione 5h",
        "claude.tab_7d": "📅 Settimanale (7g)",
        "claude.session_row": "⏱️ Sessione 5h: {pct}%",
        "claude.weekly_row": "📅 Settimanale: {pct}%",
        "claude.rate_hourly": "{rate}% / ora",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Token Totali",
        "claude.burn_rate": "Velocità Consumo",
        "claude.window_active": "Finestra Attiva",

        "agy.tab_gemini": "✨ Pool Gemini",
        "agy.tab_partner": "🤝 Modelli Partner",
        "agy.session_row": "⏱️ Sessione 5h: {pct}%",
        "agy.weekly_row": "📅 Settimanale: {pct}%",
        "agy.partner_sub": "{models} Modelli Partner",
        "agy.credits_info": "💳 AI Credits: {status}  •  Account: {account}",
        "agy.credits_available": "Disponibili",
        "agy.credits_included": "Inclusi",

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

        "tray.show_widget": "📊 Mostra Widget",
        "tray.refresh_now": "↻ Aggiorna Adesso",
        "tray.settings": "⚙️ Impostazioni",
        "tray.help": "ℹ️ Informazioni & Help (v{version} - giuspo)",
        "tray.quit": "❌ Esci",
        "tray.init_claude": "🟠 Claude: Inizializzazione...",
        "tray.init_agy": "🔵 Antigravity: Inizializzazione...",
        "tray.loading": "Caricamento quote in corso...",
        "tray.no_session": "Nessuna sessione attiva",

        "status.connected": "🟢 Connesso",
        "status.connected_claude": "🟢 Connesso via Claude OAuth",
        "status.connected_google": "🟢 Connesso via Google AI Pro",
        "status.disconnected": "🟡 Disconnesso",
        "status.offline": "🔴 Offline",
        "status.demo": "🧪 Modalità Demo (Mock)",

        "notif.crit_title": "🚨 Claude Code: Quota Critica ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Soglia Raggiunta ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Utilizzo al {pct}%",
        "notif.body": "[{workspace}] Hai raggiunto il {pct}% del limite.\nReset previsto tra {time}.",
        "notif.spike_title": "🔥 Claude Code: Consumo Rapido!",
        "notif.spike_body": "[{workspace}] Aumento anomalo del +{delta}% negli ultimi {minutes} min.\nConsumo attuale: {pct}%.",

        "help.creator": "Ideato e sviluppato da <b>giuspo</b> 🚀",
        "help.license": "🛡️ Licenza: GNU GPLv3 (Copyleft Forte)",
        "help.purpose_title": "🎯 Scopo dell'Applicazione Multi-Provider",
        "help.purpose_body": (
            "Monitora in tempo reale dalla barra delle attività le quote d'uso sia di <b>Claude Code (Anthropic)</b> "
            "sia di <b>Google Antigravity (Google AI Pro)</b>, inclusi i modelli Gemini e i modelli Partner (Claude Sonnet/Opus, GPT-OSS). "
            "Puoi visualizzare le icone affiancate o scegliere solo uno dei due servizi."
        ),
    },

    # =========================================================================
    # ENGLISH (en)
    # =========================================================================
    "en": {
        "nav.metrics": "📊 Metrics",
        "nav.settings": "⚙️ Settings",
        "nav.help": "ℹ️ Guide & Info",
        "flyout.refresh_tooltip": "Refresh quotas now",

        "sub.overview": "⚖️ Overview",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Free)",
        "overview.reset_in": "Reset in {time}",
        "overview.btn_go_claude": "Claude Details ↗",
        "overview.btn_go_agy": "Google Details ↗",
        "overview.parallel_title": "💡 Parallel Usage Status",

        "claude.tab_5h": "⏱️ 5h Session",
        "claude.tab_7d": "📅 Weekly (7d)",
        "claude.session_row": "⏱️ 5h Session: {pct}%",
        "claude.weekly_row": "📅 Weekly: {pct}%",
        "claude.rate_hourly": "{rate}% / hr",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Total Tokens",
        "claude.burn_rate": "Burn Rate",
        "claude.window_active": "Active Window",

        "agy.tab_gemini": "✨ Gemini Pool",
        "agy.tab_partner": "🤝 Partner Models",
        "agy.session_row": "⏱️ 5h Session: {pct}%",
        "agy.weekly_row": "📅 Weekly: {pct}%",
        "agy.partner_sub": "{models} Partner Models",
        "agy.credits_info": "💳 AI Credits: {status}  •  Account: {account}",
        "agy.credits_available": "Available",
        "agy.credits_included": "Included",

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

        "tray.show_widget": "📊 Show Widget",
        "tray.refresh_now": "↻ Refresh Now",
        "tray.settings": "⚙️ Settings",
        "tray.help": "ℹ️ About & Help (v{version} - giuspo)",
        "tray.quit": "❌ Quit",
        "tray.init_claude": "🟠 Claude: Initializing...",
        "tray.init_agy": "🔵 Antigravity: Initializing...",
        "tray.loading": "Loading quotas...",
        "tray.no_session": "No active session",

        "status.connected": "🟢 Connected",
        "status.connected_claude": "🟢 Connected via Claude OAuth",
        "status.connected_google": "🟢 Connected via Google AI Pro",
        "status.disconnected": "🟡 Disconnected",
        "status.offline": "🔴 Offline",
        "status.demo": "🧪 Demo Mode (Mock)",

        "notif.crit_title": "🚨 Claude Code: Critical Quota ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Threshold Reached ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Usage at {pct}%",
        "notif.body": "[{workspace}] You reached {pct}% of the limit.\nReset expected in {time}.",
        "notif.spike_title": "🔥 Claude Code: Rapid Consumption!",
        "notif.spike_body": "[{workspace}] Anomaly spike of +{delta}% in the last {minutes} min.\nCurrent usage: {pct}%.",

        "help.creator": "Designed and developed by <b>giuspo</b> 🚀",
        "help.license": "🛡️ License: GNU GPLv3 (Strong Copyleft)",
        "help.purpose_title": "🎯 Multi-Provider Application Purpose",
        "help.purpose_body": (
            "Monitor real-time taskbar usage quotas for both <b>Claude Code (Anthropic)</b> "
            "and <b>Google Antigravity (Google AI Pro)</b>, including Gemini models and Partner models (Claude Sonnet/Opus, GPT-OSS). "
            "You can display side-by-side icons or choose to monitor only one service."
        ),
    },

    # =========================================================================
    # ESPAÑOL (es)
    # =========================================================================
    "es": {
        "nav.metrics": "📊 Métricas",
        "nav.settings": "⚙️ Configuración",
        "nav.help": "ℹ️ Guía e Info",
        "flyout.refresh_tooltip": "Actualizar cuotas ahora",

        "sub.overview": "⚖️ Resumen",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Libre)",
        "overview.reset_in": "Reinicio en {time}",
        "overview.btn_go_claude": "Detalles Claude ↗",
        "overview.btn_go_agy": "Detalles Google ↗",
        "overview.parallel_title": "💡 Estado de Uso Paralelo",

        "claude.tab_5h": "⏱️ Sesión 5h",
        "claude.tab_7d": "📅 Semanal (7d)",
        "claude.session_row": "⏱️ Sesión 5h: {pct}%",
        "claude.weekly_row": "📅 Semanal: {pct}%",
        "claude.rate_hourly": "{rate}% / hora",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Tokens Totales",
        "claude.burn_rate": "Tasa de Consumo",
        "claude.window_active": "Ventana Activa",

        "agy.tab_gemini": "✨ Pool Gemini",
        "agy.tab_partner": "🤝 Modelos Partner",
        "agy.session_row": "⏱️ Sesión 5h: {pct}%",
        "agy.weekly_row": "📅 Semanal: {pct}%",
        "agy.partner_sub": "{models} Modelos Partner",
        "agy.credits_info": "💳 Créditos AI: {status}  •  Cuenta: {account}",
        "agy.credits_available": "Disponibles",
        "agy.credits_included": "Incluidos",

        "settings.title": "🔌 Servicios Activos e Iconos (v{version})",
        "settings.inactive": "Inactivo",
        "settings.enable_claude": "Monitorizar Claude Code",
        "settings.enable_agy": "Monitorizar Google Antigravity",
        "settings.agy_mode_lbl": "Visualización en barra de tareas para Antigravity:",
        "settings.tray_single": "1 Icono (Unificado)",
        "settings.tray_split": "2 Iconos (+ Partner)",
        "settings.which_pool_lbl": "Pool mostrado en icono único:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 Partner",
        "settings.pool_max": "🔥 Consumo Máximo",
        "settings.split_hint": "💡 Se mostrarán 2 iconos separados: Gemini (Azul) y Partner (Esmeralda).",
        "settings.auth_title": "🔐 Cuentas Conectadas",
        "settings.btn_login_claude": "🔑 Iniciar sesión con Claude (1-Click)",
        "settings.btn_login_google": "🔑 Iniciar sesión con Google (1-Click)",
        "settings.btn_logout": "🚪 Cerrar sesión",
        "settings.notif_title": "🔔 Notificaciones y Umbrales de Alerta",
        "settings.chk_notif": "Notificaciones Push",
        "settings.thresholds_lbl": "Umbrales activos (%):",
        "settings.burn_rate_chk": "🔥 Alerta Consumo Rápido (+15% en <10m / Bucle)",
        "settings.style_title": "🎨 Estilo de Iconos en Barra de Tareas",
        "settings.style_concentric": "⭕ Anillos\n(5h / 7d)",
        "settings.style_split": "🌗 Arcos Divididos\n(Izq 5h / Der 7d)",
        "settings.style_bars": "📊 Barras Dobles\n(Columnas 5h / 7d)",
        "settings.lang_title": "🌐 Idioma de la Interfaz",
        "settings.autostart": "🚀 Ejecutar al inicio del sistema",
        "settings.mock": "🧪 Simulación Demo (Mock)",
        "settings.save": "💾 Guardar Configuración",
        "settings.saved_toast": "✅ ¡Configuración guardada!",

        "tray.show_widget": "📊 Mostrar Widget",
        "tray.refresh_now": "↻ Actualizar Ahora",
        "tray.settings": "⚙️ Configuración",
        "tray.help": "ℹ️ Acerca de y Ayuda (v{version} - giuspo)",
        "tray.quit": "❌ Salir",
        "tray.init_claude": "🟠 Claude: Inicializando...",
        "tray.init_agy": "🔵 Antigravity: Inicializando...",
        "tray.loading": "Cargando cuotas...",
        "tray.no_session": "Sin sesión activa",

        "status.connected": "🟢 Conectado",
        "status.connected_claude": "🟢 Conectado vía Claude OAuth",
        "status.connected_google": "🟢 Conectado vía Google AI Pro",
        "status.disconnected": "🟡 Desconectado",
        "status.offline": "🔴 Sin conexión",
        "status.demo": "🧪 Modo Demo (Mock)",

        "notif.crit_title": "🚨 Claude Code: Cuota Crítica ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Umbral Alcanzado ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Uso al {pct}%",
        "notif.body": "[{workspace}] Has alcanzado el {pct}% del límite.\nReinicio previsto en {time}.",
        "notif.spike_title": "🔥 Claude Code: ¡Consumo Rápido!",
        "notif.spike_body": "[{workspace}] Aumento anómalo de +{delta}% en los últimos {minutes} min.\nUso actual: {pct}%.",

        "help.creator": "Diseñado y desarrollado por <b>giuspo</b> 🚀",
        "help.license": "🛡️ Licencia: GNU GPLv3 (Copyleft Fuerte)",
        "help.purpose_title": "🎯 Propósito de la Aplicación Multi-Provider",
        "help.purpose_body": (
            "Monitoriza en tiempo real desde la barra de tareas las cuotas de uso de <b>Claude Code (Anthropic)</b> "
            "y <b>Google Antigravity (Google AI Pro)</b>, incluidos modelos Gemini y modelos Partner (Claude Sonnet/Opus, GPT-OSS). "
            "Puedes mostrar iconos lado a lado o elegir un único servicio."
        ),
    },

    # =========================================================================
    # FRANÇAIS (fr)
    # =========================================================================
    "fr": {
        "nav.metrics": "📊 Métriques",
        "nav.settings": "⚙️ Paramètres",
        "nav.help": "ℹ️ Aide & Info",
        "flyout.refresh_tooltip": "Actualiser les quotas maintenant",

        "sub.overview": "⚖️ Aperçu",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Libre)",
        "overview.reset_in": "Réinitialisation dans {time}",
        "overview.btn_go_claude": "Détails Claude ↗",
        "overview.btn_go_agy": "Détails Google ↗",
        "overview.parallel_title": "💡 État d'Utilisation Parallèle",

        "claude.tab_5h": "⏱️ Session 5h",
        "claude.tab_7d": "📅 Hebdomadaire (7j)",
        "claude.session_row": "⏱️ Session 5h: {pct}%",
        "claude.weekly_row": "📅 Hebdomadaire: {pct}%",
        "claude.rate_hourly": "{rate}% / heure",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Total des Tokens",
        "claude.burn_rate": "Vitesse de Consommation",
        "claude.window_active": "Fenêtre Active",

        "agy.tab_gemini": "✨ Pool Gemini",
        "agy.tab_partner": "🤝 Modèles Partenaires",
        "agy.session_row": "⏱️ Session 5h: {pct}%",
        "agy.weekly_row": "📅 Hebdomadaire: {pct}%",
        "agy.partner_sub": "{models} Modèles Partenaires",
        "agy.credits_info": "💳 Crédits IA: {status}  •  Compte: {account}",
        "agy.credits_available": "Disponibles",
        "agy.credits_included": "Inclus",

        "settings.title": "🔌 Services Actifs & Icônes (v{version})",
        "settings.inactive": "Inactif",
        "settings.enable_claude": "Surveiller Claude Code",
        "settings.enable_agy": "Surveiller Google Antigravity",
        "settings.agy_mode_lbl": "Affichage dans la barre des tâches pour Antigravity :",
        "settings.tray_single": "1 Icône (Unifiée)",
        "settings.tray_split": "2 Icônes (+ Partenaire)",
        "settings.which_pool_lbl": "Pool affiché dans l'icône unique :",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 Partenaire",
        "settings.pool_max": "🔥 Conso Maximale",
        "settings.split_hint": "💡 Deux icônes séparées seront affichées : Gemini (Bleu) et Partenaire (Émeraude).",
        "settings.auth_title": "🔐 Comptes Connectés",
        "settings.btn_login_claude": "🔑 Se connecter avec Claude (1-Clic)",
        "settings.btn_login_google": "🔑 Se connecter avec Google (1-Clic)",
        "settings.btn_logout": "🚪 Déconnexion",
        "settings.notif_title": "🔔 Notifications & Seuils d'Alerte",
        "settings.chk_notif": "Notifications Push",
        "settings.thresholds_lbl": "Seuils actifs (%) :",
        "settings.burn_rate_chk": "🔥 Alerte Conso Rapide (+15% en <10m / Boucle)",
        "settings.style_title": "🎨 Style d'Icônes de la Barre des Tâches",
        "settings.style_concentric": "⭕ Anneaux\n(5h / 7j)",
        "settings.style_split": "🌗 Arcs Divisés\n(G 5h / D 7j)",
        "settings.style_bars": "📊 Doubles Barres\n(Colonnes 5h / 7j)",
        "settings.lang_title": "🌐 Langue de l'Interface",
        "settings.autostart": "🚀 Lancer au démarrage du système",
        "settings.mock": "🧪 Simulation Démo (Mock)",
        "settings.save": "💾 Enregistrer les Paramètres",
        "settings.saved_toast": "✅ Paramètres enregistrés !",

        "tray.show_widget": "📊 Afficher le Widget",
        "tray.refresh_now": "↻ Actualiser Maintenant",
        "tray.settings": "⚙️ Paramètres",
        "tray.help": "ℹ️ À Propos & Aide (v{version} - giuspo)",
        "tray.quit": "❌ Quitter",
        "tray.init_claude": "🟠 Claude: Initialisation...",
        "tray.init_agy": "🔵 Antigravity: Initialisation...",
        "tray.loading": "Chargement des quotas...",
        "tray.no_session": "Aucune session active",

        "status.connected": "🟢 Connecté",
        "status.connected_claude": "🟢 Connecté via Claude OAuth",
        "status.connected_google": "🟢 Connecté via Google AI Pro",
        "status.disconnected": "🟡 Déconnecté",
        "status.offline": "🔴 Hors ligne",
        "status.demo": "🧪 Mode Démo (Mock)",

        "notif.crit_title": "🚨 Claude Code: Quota Critique ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Seuil Atteint ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Utilisation à {pct}%",
        "notif.body": "[{workspace}] Vous avez atteint {pct}% de la limite.\nRéinitialisation prévue dans {time}.",
        "notif.spike_title": "🔥 Claude Code: Consommation Rapide !",
        "notif.spike_body": "[{workspace}] Hausse anormale de +{delta}% au cours des {minutes} dernières min.\nUtilisation actuelle : {pct}%.",

        "help.creator": "Conçu et développé par <b>giuspo</b> 🚀",
        "help.license": "🛡️ Licence : GNU GPLv3 (Copyleft Fort)",
        "help.purpose_title": "🎯 Objectif de l'Application Multi-Fournisseur",
        "help.purpose_body": (
            "Surveille en temps réel depuis la barre des tâches les quotas d'utilisation de <b>Claude Code (Anthropic)</b> "
            "et de <b>Google Antigravity (Google AI Pro)</b>, y compris les modèles Gemini et Partenaires (Claude Sonnet/Opus, GPT-OSS). "
            "Vous pouvez afficher les icônes côte à côte ou ne choisir qu'un seul service."
        ),
    },

    # =========================================================================
    # DEUTSCH (de)
    # =========================================================================
    "de": {
        "nav.metrics": "📊 Metriken",
        "nav.settings": "⚙️ Einstellungen",
        "nav.help": "ℹ️ Hilfe & Info",
        "flyout.refresh_tooltip": "Quoten jetzt aktualisieren",

        "sub.overview": "⚖️ Übersicht",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Frei)",
        "overview.reset_in": "Reset in {time}",
        "overview.btn_go_claude": "Claude Details ↗",
        "overview.btn_go_agy": "Google Details ↗",
        "overview.parallel_title": "💡 Parallele Nutzungsübersicht",

        "claude.tab_5h": "⏱️ 5h-Sitzung",
        "claude.tab_7d": "📅 Wöchentlich (7T)",
        "claude.session_row": "⏱️ 5h-Sitzung: {pct}%",
        "claude.weekly_row": "📅 Wöchentlich: {pct}%",
        "claude.rate_hourly": "{rate}% / Std",
        "claude.tokens_burn": "{tokens} Tok / 10m",
        "claude.tokens_total": "Token Gesamt",
        "claude.burn_rate": "Verbrauchsrate",
        "claude.window_active": "Aktives Fenster",

        "agy.tab_gemini": "✨ Gemini Pool",
        "agy.tab_partner": "🤝 Partner-Modelle",
        "agy.session_row": "⏱️ 5h-Sitzung: {pct}%",
        "agy.weekly_row": "📅 Wöchentlich: {pct}%",
        "agy.partner_sub": "{models} Partner-Modelle",
        "agy.credits_info": "💳 KI-Credits: {status}  •  Konto: {account}",
        "agy.credits_available": "Verfügbar",
        "agy.credits_included": "Inbegriffen",

        "settings.title": "🔌 Aktive Dienste & Icons (v{version})",
        "settings.inactive": "Inaktiv",
        "settings.enable_claude": "Claude Code überwachen",
        "settings.enable_agy": "Google Antigravity überwachen",
        "settings.agy_mode_lbl": "Taskleisten-Anzeige für Antigravity:",
        "settings.tray_single": "1 Icon (Vereint)",
        "settings.tray_split": "2 Icons (+ Partner)",
        "settings.which_pool_lbl": "Im Einzel-Icon angezeigter Pool:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 Partner",
        "settings.pool_max": "🔥 Max. Verbrauch",
        "settings.split_hint": "💡 Es werden 2 separate Icons angezeigt: Gemini (Blau) und Partner (Smaragd).",
        "settings.auth_title": "🔐 Verbundene Konten",
        "settings.btn_login_claude": "🔑 Mit Claude anmelden (1-Klick)",
        "settings.btn_login_google": "🔑 Mit Google anmelden (1-Klick)",
        "settings.btn_logout": "🚪 Abmelden",
        "settings.notif_title": "🔔 Benachrichtigungen & Alarmschwellen",
        "settings.chk_notif": "Push-Benachrichtigungen",
        "settings.thresholds_lbl": "Aktive Schwellen (%):",
        "settings.burn_rate_chk": "🔥 Schnellverbrauchs-Alarm (+15% in <10m / Loop)",
        "settings.style_title": "🎨 Taskleisten-Icon-Stil",
        "settings.style_concentric": "⭕ Ringe\n(5h / 7T)",
        "settings.style_split": "🌗 Geteilte Bögen\n(L 5h / R 7T)",
        "settings.style_bars": "📊 Doppelbalken\n(Säulen 5h / 7T)",
        "settings.lang_title": "🌐 Sprache der Benutzeroberfläche",
        "settings.autostart": "🚀 Beim Systemstart ausführen",
        "settings.mock": "🧪 Demo-Simulation (Mock)",
        "settings.save": "💾 Einstellungen speichern",
        "settings.saved_toast": "✅ Einstellungen gespeichert!",

        "tray.show_widget": "📊 Widget anzeigen",
        "tray.refresh_now": "↻ Jetzt aktualisieren",
        "tray.settings": "⚙️ Einstellungen",
        "tray.help": "ℹ️ Über & Hilfe (v{version} - giuspo)",
        "tray.quit": "❌ Beenden",
        "tray.init_claude": "🟠 Claude: Initialisierung...",
        "tray.init_agy": "🔵 Antigravity: Initialisierung...",
        "tray.loading": "Quoten werden geladen...",
        "tray.no_session": "Keine aktive Sitzung",

        "status.connected": "🟢 Verbunden",
        "status.connected_claude": "🟢 Verbunden über Claude OAuth",
        "status.connected_google": "🟢 Verbunden über Google AI Pro",
        "status.disconnected": "🟡 Getrennt",
        "status.offline": "🔴 Offline",
        "status.demo": "🧪 Demo-Modus (Mock)",

        "notif.crit_title": "🚨 Claude Code: Kritische Quote ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Schwelle erreicht ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Nutzung bei {pct}%",
        "notif.body": "[{workspace}] Sie haben {pct}% des Limits erreicht.\nReset erwartet in {time}.",
        "notif.spike_title": "🔥 Claude Code: Schneller Verbrauch!",
        "notif.spike_body": "[{workspace}] Anomaler Anstieg um +{delta}% in den letzten {minutes} Min.\nAktuelle Nutzung: {pct}%.",

        "help.creator": "Entworfen und entwickelt von <b>giuspo</b> 🚀",
        "help.license": "🛡️ Lizenz: GNU GPLv3 (Starkes Copyleft)",
        "help.purpose_title": "🎯 Zweck der Multi-Provider-Anwendung",
        "help.purpose_body": (
            "Überwachen Sie in Echtzeit aus der Taskleiste die Nutzungskontingente von <b>Claude Code (Anthropic)</b> "
            "und <b>Google Antigravity (Google AI Pro)</b>, einschließlich Gemini- und Partner-Modellen (Claude Sonnet/Opus, GPT-OSS). "
            "Sie können die Icons nebeneinander anzeigen oder nur einen Dienst auswählen."
        ),
    },

    # =========================================================================
    # PORTUGUÊS (pt)
    # =========================================================================
    "pt": {
        "nav.metrics": "📊 Métricas",
        "nav.settings": "⚙️ Configurações",
        "nav.help": "ℹ️ Guia e Ajuda",
        "flyout.refresh_tooltip": "Atualizar cotas agora",

        "sub.overview": "⚖️ Visão Geral",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (Livre)",
        "overview.reset_in": "Redefinição em {time}",
        "overview.btn_go_claude": "Detalhes Claude ↗",
        "overview.btn_go_agy": "Detalhes Google ↗",
        "overview.parallel_title": "💡 Status de Uso Paralelo",

        "claude.tab_5h": "⏱️ Sessão 5h",
        "claude.tab_7d": "📅 Semanal (7d)",
        "claude.session_row": "⏱️ Sessão 5h: {pct}%",
        "claude.weekly_row": "📅 Semanal: {pct}%",
        "claude.rate_hourly": "{rate}% / hora",
        "claude.tokens_burn": "{tokens} tok / 10m",
        "claude.tokens_total": "Total de Tokens",
        "claude.burn_rate": "Taxa de Consumo",
        "claude.window_active": "Janela Ativa",

        "agy.tab_gemini": "✨ Pool Gemini",
        "agy.tab_partner": "🤝 Modelos Parceiros",
        "agy.session_row": "⏱️ Sessão 5h: {pct}%",
        "agy.weekly_row": "📅 Semanal: {pct}%",
        "agy.partner_sub": "{models} Modelos Parceiros",
        "agy.credits_info": "💳 Créditos de IA: {status}  •  Conta: {account}",
        "agy.credits_available": "Disponíveis",
        "agy.credits_included": "Incluídos",

        "settings.title": "🔌 Serviços Ativos e Ícones (v{version})",
        "settings.inactive": "Inativo",
        "settings.enable_claude": "Monitorar Claude Code",
        "settings.enable_agy": "Monitorar Google Antigravity",
        "settings.agy_mode_lbl": "Exibição na barra de tarefas para Antigravity:",
        "settings.tray_single": "1 Ícone (Unificado)",
        "settings.tray_split": "2 Ícones (+ Parceiro)",
        "settings.which_pool_lbl": "Pool exibido no ícone único:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 Parceiro",
        "settings.pool_max": "🔥 Consumo Máximo",
        "settings.split_hint": "💡 Serão exibidos 2 ícones separados: Gemini (Azul) e Parceiro (Esmeralda).",
        "settings.auth_title": "🔐 Contas Conectadas",
        "settings.btn_login_claude": "🔑 Entrar com Claude (1-Clique)",
        "settings.btn_login_google": "🔑 Entrar com Google (1-Clique)",
        "settings.btn_logout": "🚪 Desconectar",
        "settings.notif_title": "🔔 Notificações e Limiares de Alerta",
        "settings.chk_notif": "Notificações Push",
        "settings.thresholds_lbl": "Limiares ativos (%):",
        "settings.burn_rate_chk": "🔥 Alerta de Consumo Rápido (+15% em <10m / Loop)",
        "settings.style_title": "🎨 Estilo de Ícones da Barra de Tarefas",
        "settings.style_concentric": "⭕ Anéis\n(5h / 7d)",
        "settings.style_split": "🌗 Arcos Divididos\n(Esq 5h / Dir 7d)",
        "settings.style_bars": "📊 Barras Duplas\n(Colunas 5h / 7d)",
        "settings.lang_title": "🌐 Idioma da Interface",
        "settings.autostart": "🚀 Executar na inicialização do sistema",
        "settings.mock": "🧪 Simulação Demo (Mock)",
        "settings.save": "💾 Salvar Configurações",
        "settings.saved_toast": "✅ Configurações salvas!",

        "tray.show_widget": "📊 Mostrar Widget",
        "tray.refresh_now": "↻ Atualizar Agora",
        "tray.settings": "⚙️ Configurações",
        "tray.help": "ℹ️ Sobre e Ajuda (v{version} - giuspo)",
        "tray.quit": "❌ Sair",
        "tray.init_claude": "🟠 Claude: Inicializando...",
        "tray.init_agy": "🔵 Antigravity: Inicializando...",
        "tray.loading": "Carregando cotas...",
        "tray.no_session": "Nenhuma sessão ativa",

        "status.connected": "🟢 Conectado",
        "status.connected_claude": "🟢 Conectado via Claude OAuth",
        "status.connected_google": "🟢 Conectado via Google AI Pro",
        "status.disconnected": "🟡 Desconectado",
        "status.offline": "🔴 Desconectado",
        "status.demo": "🧪 Modo Demo (Mock)",

        "notif.crit_title": "🚨 Claude Code: Cota Crítica ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: Limite Atingido ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: Uso em {pct}%",
        "notif.body": "[{workspace}] Você atingiu {pct}% do limite.\nRedefinição esperada em {time}.",
        "notif.spike_title": "🔥 Claude Code: Consumo Rápido!",
        "notif.spike_body": "[{workspace}] Aumento anômalo de +{delta}% nos últimos {minutes} min.\nUso atual: {pct}%.",

        "help.creator": "Criado e desenvolvido por <b>giuspo</b> 🚀",
        "help.license": "🛡️ Licença: GNU GPLv3 (Copyleft Forte)",
        "help.purpose_title": "🎯 Propósito do Aplicativo Multi-Provedor",
        "help.purpose_body": (
            "Monitore em tempo real na barra de tarefas as cotas de uso do <b>Claude Code (Anthropic)</b> "
            "e do <b>Google Antigravity (Google AI Pro)</b>, incluindo modelos Gemini e modelos Parceiros (Claude Sonnet/Opus, GPT-OSS). "
            "É possível exibir ícones lado a lado ou monitorar apenas um serviço."
        ),
    },

    # =========================================================================
    # 日本語 (ja)
    # =========================================================================
    "ja": {
        "nav.metrics": "📊 メトリクス",
        "nav.settings": "⚙️ 設定",
        "nav.help": "ℹ️ ガイド＆情報",
        "flyout.refresh_tooltip": "クォータを今すぐ更新",

        "sub.overview": "⚖️ 概要",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (空き)",
        "overview.reset_in": "リセットまで {time}",
        "overview.btn_go_claude": "Claude 詳細 ↗",
        "overview.btn_go_agy": "Google 詳細 ↗",
        "overview.parallel_title": "💡 並行利用状況",

        "claude.tab_5h": "⏱️ 5時間セッション",
        "claude.tab_7d": "📅 週間 (7日間)",
        "claude.session_row": "⏱️ 5時間セッション: {pct}%",
        "claude.weekly_row": "📅 週間: {pct}%",
        "claude.rate_hourly": "{rate}% / 時間",
        "claude.tokens_burn": "{tokens} トークン / 10分",
        "claude.tokens_total": "合計トークン",
        "claude.burn_rate": "消費速度",
        "claude.window_active": "アクティブウィンドウ",

        "agy.tab_gemini": "✨ Gemini プール",
        "agy.tab_partner": "🤝 パートナーモデル",
        "agy.session_row": "⏱️ 5時間セッション: {pct}%",
        "agy.weekly_row": "📅 週間: {pct}%",
        "agy.partner_sub": "{models} パートナーモデル",
        "agy.credits_info": "💳 AIクレジット: {status}  •  アカウント: {account}",
        "agy.credits_available": "利用可能",
        "agy.credits_included": "含まれる",

        "settings.title": "🔌 有効なサービス＆アイコン (v{version})",
        "settings.inactive": "無効",
        "settings.enable_claude": "Claude Code を監視",
        "settings.enable_agy": "Google Antigravity を監視",
        "settings.agy_mode_lbl": "Antigravity のタスクバー表示:",
        "settings.tray_single": "1 アイコン (統合)",
        "settings.tray_split": "2 アイコン (+ パートナー)",
        "settings.which_pool_lbl": "単一アイコンで表示するプール:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 パートナー",
        "settings.pool_max": "🔥 最大消費",
        "settings.split_hint": "💡 Gemini（青）とパートナー（エメラルド）の2つのアイコンが個別に表示されます。",
        "settings.auth_title": "🔐 接続済みアカウント",
        "settings.btn_login_claude": "🔑 Claude でログイン (1-Click)",
        "settings.btn_login_google": "🔑 Google でログイン (1-Click)",
        "settings.btn_logout": "🚪 ログアウト",
        "settings.notif_title": "🔔 通知とアラートしきい値",
        "settings.chk_notif": "プッシュ通知",
        "settings.thresholds_lbl": "有効なしきい値 (%):",
        "settings.burn_rate_chk": "🔥 急速消費アラート (<10分で+15% / ループ)",
        "settings.style_title": "🎨 タスクバーアイコンのスタイル",
        "settings.style_concentric": "⭕ リング\n(5h / 7d)",
        "settings.style_split": "🌗 分割アーク\n(左 5h / 右 7d)",
        "settings.style_bars": "📊 デュアルバー\n(列 5h / 7d)",
        "settings.lang_title": "🌐 インターフェース言語",
        "settings.autostart": "🚀 システム起動時に自動実行",
        "settings.mock": "🧪 デモシミュレーション (Mock)",
        "settings.save": "💾 設定を保存",
        "settings.saved_toast": "✅ 設定を保存しました！",

        "tray.show_widget": "📊 ウィジェットを表示",
        "tray.refresh_now": "↻ 今すぐ更新",
        "tray.settings": "⚙️ 設定",
        "tray.help": "ℹ️ 情報＆ヘルプ (v{version} - giuspo)",
        "tray.quit": "❌ 終了",
        "tray.init_claude": "🟠 Claude: 初期化中...",
        "tray.init_agy": "🔵 Antigravity: 初期化中...",
        "tray.loading": "クォータを読み込み中...",
        "tray.no_session": "アクティブなセッションはありません",

        "status.connected": "🟢 接続済み",
        "status.connected_claude": "🟢 Claude OAuth で接続中",
        "status.connected_google": "🟢 Google AI Pro で接続中",
        "status.disconnected": "🟡 未接続",
        "status.offline": "🔴 オフライン",
        "status.demo": "🧪 デモモード (Mock)",

        "notif.crit_title": "🚨 Claude Code: クォータ危機 ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: しきい値到達 ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: 使用率 {pct}%",
        "notif.body": "[{workspace}] 上限の {pct}% に達しました。\nリセット予定: {time} 後。",
        "notif.spike_title": "🔥 Claude Code: 急速消費を検知！",
        "notif.spike_body": "[{workspace}] 過去 {minutes} 分間で +{delta}% の急増。\n現在の使用率: {pct}%。",

        "help.creator": "設計・開発: <b>giuspo</b> 🚀",
        "help.license": "🛡️ ライセンス: GNU GPLv3 (強力なコピーレフト)",
        "help.purpose_title": "🎯 マルチプロバイダー アプリケーションの目的",
        "help.purpose_body": (
            "<b>Claude Code (Anthropic)</b> および <b>Google Antigravity (Google AI Pro)</b>"
            "（Gemini およびパートナーモデル含む）の利用クォータをタスクバーからリアルタイムで監視します。"
            "並べて表示することも、片方のサービスのみを選択することも可能です。"
        ),
    },

    # =========================================================================
    # 简体中文 (zh)
    # =========================================================================
    "zh": {
        "nav.metrics": "📊 用量指标",
        "nav.settings": "⚙️ 偏好设置",
        "nav.help": "ℹ️ 帮助与说明",
        "flyout.refresh_tooltip": "立即刷新配额",

        "sub.overview": "⚖️ 总览",
        "sub.claude": "✴️ Claude Code",
        "sub.antigravity": "✨ Antigravity",

        "overview.claude_head": "✴️ Claude Code",
        "overview.agy_head": "✨ Antigravity",
        "overview.pct_free": "{pct}% (可用)",
        "overview.reset_in": "{time} 后重置",
        "overview.btn_go_claude": "Claude 详情 ↗",
        "overview.btn_go_agy": "Google 详情 ↗",
        "overview.parallel_title": "💡 并行使用状态",

        "claude.tab_5h": "⏱️ 5小时会话",
        "claude.tab_7d": "📅 每周配额 (7天)",
        "claude.session_row": "⏱️ 5小时会话: {pct}%",
        "claude.weekly_row": "📅 每周配额: {pct}%",
        "claude.rate_hourly": "{rate}% / 小时",
        "claude.tokens_burn": "{tokens} Token / 10分",
        "claude.tokens_total": "总 Token 数",
        "claude.burn_rate": "消耗速率",
        "claude.window_active": "活跃窗口",

        "agy.tab_gemini": "✨ Gemini 资源池",
        "agy.tab_partner": "🤝 合作伙伴模型",
        "agy.session_row": "⏱️ 5小时会话: {pct}%",
        "agy.weekly_row": "📅 每周配额: {pct}%",
        "agy.partner_sub": "{models} 个合作伙伴模型",
        "agy.credits_info": "💳 AI 点数: {status}  •  账户: {account}",
        "agy.credits_available": "可用",
        "agy.credits_included": "已包含",

        "settings.title": "🔌 启用的服务与图标 (v{version})",
        "settings.inactive": "未启用",
        "settings.enable_claude": "监控 Claude Code",
        "settings.enable_agy": "监控 Google Antigravity",
        "settings.agy_mode_lbl": "Antigravity 任务栏图标显示:",
        "settings.tray_single": "单图标 (合并)",
        "settings.tray_split": "双图标 (+ 合作伙伴)",
        "settings.which_pool_lbl": "单图标中显示的资源池:",
        "settings.pool_gemini": "✨ Gemini",
        "settings.pool_partner": "🤝 合作伙伴",
        "settings.pool_max": "🔥 最大消耗",
        "settings.split_hint": "💡 将分别显示两个独立图标：Gemini (蓝色) 与 合作伙伴 (翡翠绿)。",
        "settings.auth_title": "🔐 关联账户",
        "settings.btn_login_claude": "🔑 登录 Claude (一键连接)",
        "settings.btn_login_google": "🔑 登录 Google (一键连接)",
        "settings.btn_logout": "🚪 退出登录",
        "settings.notif_title": "🔔 通知与告警阈值",
        "settings.chk_notif": "桌面推送通知",
        "settings.thresholds_lbl": "生效告警阈值 (%):",
        "settings.burn_rate_chk": "🔥 快速消耗告警 (<10分钟内增长超过 +15%)",
        "settings.style_title": "🎨 任务栏图标样式",
        "settings.style_concentric": "⭕ 同心圆环\n(5h / 7天)",
        "settings.style_split": "🌗 分割圆弧\n(左 5h / 右 7天)",
        "settings.style_bars": "📊 双柱图\n(柱状 5h / 7天)",
        "settings.lang_title": "🌐 界面语言 (Language)",
        "settings.autostart": "🚀 开机自启动",
        "settings.mock": "🧪 演示模拟模式 (Mock)",
        "settings.save": "💾 保存设置",
        "settings.saved_toast": "✅ 设置已保存！",

        "tray.show_widget": "📊 显示微件",
        "tray.refresh_now": "↻ 立即刷新",
        "tray.settings": "⚙️ 设置",
        "tray.help": "ℹ️ 关于与帮助 (v{version} - giuspo)",
        "tray.quit": "❌ 退出",
        "tray.init_claude": "🟠 Claude: 正在初始化...",
        "tray.init_agy": "🔵 Antigravity: 正在初始化...",
        "tray.loading": "正在加载配额...",
        "tray.no_session": "无活跃会话",

        "status.connected": "🟢 已连接",
        "status.connected_claude": "🟢 已通过 Claude OAuth 连接",
        "status.connected_google": "🟢 已通过 Google AI Pro 连接",
        "status.disconnected": "🟡 未连接",
        "status.offline": "🔴 离线",
        "status.demo": "🧪 演示模式 (Mock)",

        "notif.crit_title": "🚨 Claude Code: 配额严重预警 ({pct}%)",
        "notif.warn_title": "⚠️ Claude Code: 达到用量阈值 ({pct}%)",
        "notif.info_title": "ℹ️ Claude Code: 当前用量 {pct}%",
        "notif.body": "[{workspace}] 您已消耗配额的 {pct}%。\n预计在 {time} 后重置。",
        "notif.spike_title": "🔥 Claude Code: 快速消耗预警！",
        "notif.spike_body": "[{workspace}] 过去 {minutes} 分钟内异常激增 +{delta}%。\n当前用量: {pct}%。",

        "help.creator": "设计与开发: <b>giuspo</b> 🚀",
        "help.license": "🛡️ 许可证: GNU GPLv3 (强互惠开源)",
        "help.purpose_title": "🎯 多服务提供商应用目标",
        "help.purpose_body": (
            "在系统任务栏中实时监控 <b>Claude Code (Anthropic)</b> 与 <b>Google Antigravity (Google AI Pro)</b>"
            "（包括 Gemini 模型及 Claude Sonnet/Opus、GPT-OSS 等合作伙伴模型）的用量配额。支持并排显示多图标或仅选择监控单一服务。"
        ),
    },
}
