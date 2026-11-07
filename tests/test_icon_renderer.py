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

    # Test rendering Gemini icon with Argon alert badge (bars, concentric, split)
    img_argon_bars = IconRenderer.render_pil_image(
        five_hour_pct=37.0,
        seven_day_pct=30.0,
        style="bars",
        provider_type="antigravity_gemini",
        target_size=64,
        argon_pct=94.0,
    )
    assert img_argon_bars.size == (64, 64)
    assert img_argon_bars.mode == "RGBA"

    img_argon_rings = IconRenderer.render_pil_image(
        five_hour_pct=37.0,
        seven_day_pct=30.0,
        style="concentric",
        provider_type="antigravity_gemini",
        target_size=64,
        argon_pct=80.0,
    )
    assert img_argon_rings.size == (64, 64)
    assert img_argon_rings.mode == "RGBA"


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


def test_low_utilization_baseline_visibility():
    """Validates that at 0% or low usage (5%, 16%), bars and gauges render an active illuminated baseline."""
    # 1. Bars at 0% usage (e.g. Partner icon with 0% 5h and 0% 7d)
    img_bars_zero = IconRenderer.render_pil_image(
        five_hour_pct=0.0,
        seven_day_pct=0.0,
        style="bars",
        provider_type="antigravity_partner",
        target_size=24,
    )
    alphas = [img_bars_zero.getpixel((x, y))[3] for y in range(24) for x in range(24)]
    solid_count = sum(1 for a in alphas if a >= 200)
    assert solid_count > 0, "0% usage must display illuminated baseline floor cap, never ghost into black"
    assert max(alphas) == 255

    # 2. Bars at 16% and 5% (Gemini in user screenshot)
    img_bars_low = IconRenderer.render_pil_image(
        five_hour_pct=16.0,
        seven_day_pct=5.0,
        style="bars",
        provider_type="antigravity_gemini",
        target_size=24,
    )
    alphas_low = [img_bars_low.getpixel((x, y))[3] for y in range(24) for x in range(24)]
    solid_low = sum(1 for a in alphas_low if a >= 200)
    assert solid_low >= solid_count, "16% + 5% fill must have at least as many solid pixels as baseline"

    # 3. Concentric and Split at 0%
    img_concentric_zero = IconRenderer.render_pil_image(
        five_hour_pct=0.0,
        seven_day_pct=0.0,
        style="concentric",
        provider_type="claude",
        target_size=32,
    )
    assert max(img_concentric_zero.getpixel((x, y))[3] for y in range(32) for x in range(32)) == 255

    img_split_zero = IconRenderer.render_pil_image(
        five_hour_pct=0.0,
        seven_day_pct=0.0,
        style="split",
        provider_type="antigravity_gemini",
        target_size=32,
    )
    assert max(img_split_zero.getpixel((x, y))[3] for y in range(32) for x in range(32)) == 255


def test_high_contrast_slot_and_fill_distinction():
    """Validates that empty track slots remain dark neutral charcoal while active fill is bright neon,

    guaranteeing a > 4:1 contrast ratio that eliminates hollow or uniformly colored icons on dark taskbars.
    """
    img_gemini_22 = IconRenderer.render_pil_image(
        five_hour_pct=22.0,
        seven_day_pct=6.0,
        style="bars",
        provider_type="antigravity_gemini",
        target_size=24,
    )

    # Empty upper slot region in left pill (column x=7, rows y=4..13)
    empty_brightnesses = [
        int(0.299 * img_gemini_22.getpixel((7, y))[0] + 0.587 * img_gemini_22.getpixel((7, y))[1] + 0.114 * img_gemini_22.getpixel((7, y))[2])
        for y in range(4, 14)
    ]
    avg_empty = sum(empty_brightnesses) / len(empty_brightnesses)
    assert avg_empty < 50.0, f"Empty track slot must be dark neutral charcoal, got brightness {avg_empty}"

    # Filled lower level region in left pill (column x=7, rows y=17..20)
    fill_brightnesses = [
        int(0.299 * img_gemini_22.getpixel((7, y))[0] + 0.587 * img_gemini_22.getpixel((7, y))[1] + 0.114 * img_gemini_22.getpixel((7, y))[2])
        for y in range(17, 21)
    ]
    avg_fill = sum(fill_brightnesses) / len(fill_brightnesses)
    assert avg_fill > 130.0, f"Filled level region must be vibrant neon, got brightness {avg_fill}"

    contrast_ratio = avg_fill / avg_empty
    assert contrast_ratio >= 4.0, f"Contrast ratio between fill and slot must be >= 4.0, got {contrast_ratio:.2f}"


