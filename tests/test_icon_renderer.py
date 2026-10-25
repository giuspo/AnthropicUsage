"""Tests for IconRenderer headless image generation."""

import pytest
from PIL import Image

from claude_usage.ui.icon_renderer import IconRenderer
from claude_usage.ui.theme import COLOR_CRITICAL, COLOR_WARNING, get_status_color


def test_status_color_thresholds():
    # Below 75% -> Neutral
    c_low = get_status_color(30.0)
    assert c_low != COLOR_WARNING
    assert c_low != COLOR_CRITICAL

    # 75% - 90% -> Warning
    c_warn = get_status_color(82.0)
    assert c_warn == COLOR_WARNING

    # > 90% -> Critical
    c_crit = get_status_color(94.0)
    assert c_crit == COLOR_CRITICAL


def test_render_pil_image():
    # Test rendering at 64x64
    img = IconRenderer.render_pil_image(utilization_pct=45.0, target_size=64)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"

    # Test rendering at 32x32
    img_32 = IconRenderer.render_pil_image(utilization_pct=85.0, target_size=32)
    assert img_32.size == (32, 32)


def test_app_icon_generation(tmp_path):
    icon_path = tmp_path / "custom_icon.png"
    result = IconRenderer.generate_app_icon(icon_path, size=128)
    assert result.exists()
    assert icon_path.exists()
    ico_path = icon_path.with_suffix(".ico")
    assert ico_path.exists()

    with Image.open(icon_path) as img:
        assert img.size == (128, 128)
        assert img.mode == "RGBA"

