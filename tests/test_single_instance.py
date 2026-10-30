"""Tests for single instance enforcement and autostart duplicate cleanup."""

import sys
from PyQt6.QtWidgets import QApplication

from claude_usage.core.single_instance import SingleInstanceManager
from claude_usage.autostart import cleanup_duplicate_autostart, is_autostart_enabled


# Ensure QApplication exists for Qt tests
_app = QApplication.instance() or QApplication(sys.argv)


def test_single_instance_acquisition():
    """Validates that only one instance can acquire the single-instance lock."""
    inst1 = SingleInstanceManager(app_name="TestApp_Unique_1")
    inst2 = SingleInstanceManager(app_name="TestApp_Unique_1")

    try:
        # First instance must succeed
        assert inst1.acquire() is True

        # Second instance must fail (another instance is already primary)
        assert inst2.acquire() is False
    finally:
        inst1.release()
        inst2.release()


def test_single_instance_release_and_reacquire():
    """Validates that releasing the primary instance allows another to acquire."""
    inst1 = SingleInstanceManager(app_name="TestApp_Unique_2")
    inst2 = SingleInstanceManager(app_name="TestApp_Unique_2")

    try:
        assert inst1.acquire() is True
        inst1.release()

        # After inst1 is released, inst2 can acquire
        assert inst2.acquire() is True
    finally:
        inst1.release()
        inst2.release()


def test_cleanup_duplicate_autostart_safety():
    """Ensures duplicate autostart cleanup runs safely without throwing."""
    # Should run cleanly and not raise any exceptions
    cleanup_duplicate_autostart()


def test_is_autostart_enabled_query():
    """Ensures querying autostart status returns a boolean cleanly."""
    status = is_autostart_enabled()
    assert isinstance(status, bool)

