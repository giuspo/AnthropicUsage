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
    assert "auto" in SUPPORTED_LANGUAGES
    assert "it" in SUPPORTED_LANGUAGES
    assert "en" in SUPPORTED_LANGUAGES


def test_i18n_language_switching_and_translations():
    # Set Italian
    set_language("it")
    assert get_language_setting() == "it"
    assert get_current_language() == "it"
    assert "Esegui all'avvio" in t("settings.autostart")
    assert "Metriche" in t("nav.metrics")
    assert "Disconnetti" in t("settings.btn_logout")

    # Set English
    set_language("en")
    assert get_language_setting() == "en"
    assert get_current_language() == "en"
    assert "Launch at system startup" in t("settings.autostart")
    assert "Metrics" in t("nav.metrics")
    assert "Logout" in t("settings.btn_logout")

    # String formatting
    assert t("overview.reset_in", time="2h 15m") == "Reset in 2h 15m"


def test_i18n_listener_notification():
    received = []

    def callback(lang: str):
        received.append(lang)

    register_language_listener(callback)

    set_language("it")
    assert received[-1] == "it"

    set_language("en")
    assert received[-1] == "en"


def test_i18n_auto_resolution():
    set_language("auto")
    assert get_language_setting() == "auto"
    assert get_current_language() in ("it", "en")
