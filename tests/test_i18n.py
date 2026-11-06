"""Unit tests for internationalization (i18n) module."""

import pytest
from claude_usage.i18n import (
    SUPPORTED_LANGUAGES,
    detect_system_language,
    get_current_language,
    get_language_setting,
    register_language_listener,
    set_language,
    t,
)


def test_i18n_supported_languages():
    for lang in ("auto", "it", "en", "es", "fr", "de", "pt", "ja", "zh"):
        assert lang in SUPPORTED_LANGUAGES


def test_i18n_language_switching_and_translations():
    # Italian
    set_language("it")
    assert get_language_setting() == "it"
    assert get_current_language() == "it"
    assert "Esegui all'avvio" in t("settings.autostart")
    assert "Metriche" in t("nav.metrics")
    assert "Disconnetti" in t("settings.btn_logout")

    # English
    set_language("en")
    assert get_language_setting() == "en"
    assert get_current_language() == "en"
    assert "Launch at system startup" in t("settings.autostart")
    assert "Metrics" in t("nav.metrics")
    assert "Logout" in t("settings.btn_logout")

    # Spanish
    set_language("es")
    assert get_current_language() == "es"
    assert "inicio del sistema" in t("settings.autostart")
    assert "Métricas" in t("nav.metrics")

    # French
    set_language("fr")
    assert get_current_language() == "fr"
    assert "démarrage du système" in t("settings.autostart")
    assert "Métriques" in t("nav.metrics")

    # German
    set_language("de")
    assert get_current_language() == "de"
    assert "Systemstart" in t("settings.autostart")
    assert "Metriken" in t("nav.metrics")

    # Portuguese
    set_language("pt")
    assert get_current_language() == "pt"
    assert "inicialização do sistema" in t("settings.autostart")
    assert "Métricas" in t("nav.metrics")

    # Japanese
    set_language("ja")
    assert get_current_language() == "ja"
    assert "システム起動時" in t("settings.autostart")
    assert "メトリクス" in t("nav.metrics")

    # Chinese
    set_language("zh")
    assert get_current_language() == "zh"
    assert "开机自启动" in t("settings.autostart")
    assert "用量指标" in t("nav.metrics")

    # String formatting
    assert t("overview.reset_in", time="2h 15m") == "2h 15m 后重置"


def test_i18n_listener_notification():
    received = []

    def callback(lang: str):
        received.append(lang)

    register_language_listener(callback)

    set_language("it")
    assert received[-1] == "it"

    set_language("en")
    assert received[-1] == "en"

    set_language("de")
    assert received[-1] == "de"


def test_i18n_auto_resolution():
    set_language("auto")
    assert get_language_setting() == "auto"
    assert get_current_language() in ("it", "en", "es", "fr", "de", "pt", "ja", "zh")
