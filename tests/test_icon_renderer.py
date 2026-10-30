"""Tests for IconRenderer headless image generation."""

import pytest
from PIL import Image

from claude_usage.ui.icon_renderer import IconRenderer
from claude_usage.ui.theme import COLOR_CRITICAL, COLOR_WARNING, get_channel_color, get_status_color


def test_status_color_thresholds():
    # Below 75% -> Neutral
    c_low = get_status_color(30.0)
    assert c_low != COLOR_WARNING
    assert c_low != COLOR_CRITICAL

    # Below 75% -> Distinct dual channel colors (5h Cyan != 7d Violet)
    c_5h = get_channel_color(30.0, is_weekly=False)
    c_7d = get_channel_color(30.0, is_weekly=True)
    assert c_5h != c_7d

    # 75% - 90% -> Warning
    c_warn = get_status_color(82.0)
    assert c_warn == COLOR_WARNING
    assert get_channel_color(82.0, is_weekly=False) == COLOR_WARNING
    assert get_channel_color(82.0, is_weekly=True) == COLOR_WARNING

    # > 90% -> Critical
    c_crit = get_status_color(94.0)
    assert c_crit == COLOR_CRITICAL
    assert get_channel_color(94.0, is_weekly=False) == COLOR_CRITICAL
    assert get_channel_color(94.0, is_weekly=True) == COLOR_CRITICAL


def test_render_pil_image():
    # Test rendering at 64x64 with concentric rings (default)
    img = IconRenderer.render_pil_image(five_hour_pct=45.0, seven_day_pct=80.0, style="concentric", target_size=64)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"

    # Test rendering at 32x32 with split bottom-up gauges
    img_split = IconRenderer.render_pil_image(five_hour_pct=85.0, seven_day_pct=30.0, style="split", target_size=32)
    assert img_split.size == (32, 32)
    assert img_split.mode == "RGBA"

    # Test rendering at 32x32 with dual vertical pill bars
    img_bars = IconRenderer.render_pil_image(five_hour_pct=25.0, seven_day_pct=65.0, style="bars", target_size=32)
    assert img_bars.size == (32, 32)
    assert img_bars.mode == "RGBA"

    # Test rendering Antigravity Gemini icon
    img_gemini = IconRenderer.render_pil_image(
        five_hour_pct=35.0, seven_day_pct=20.0, style="concentric", provider_type="antigravity_gemini", target_size=32
    )
    assert img_gemini.size == (32, 32)
    assert img_gemini.mode == "RGBA"

    # Test rendering Antigravity Partner icon
    img_partner = IconRenderer.render_pil_image(
        five_hour_pct=50.0, seven_day_pct=40.0, style="split", provider_type="antigravity_partner", target_size=32
    )
    assert img_partner.size == (32, 32)
    assert img_partner.mode == "RGBA"


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

