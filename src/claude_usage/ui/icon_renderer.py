"""Dynamic System Tray Icon Renderer with Configurable Activity Rings."""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw
from PyQt6.QtGui import QIcon, QImage, QPixmap

from claude_usage.ui.theme import get_channel_color, get_status_color


class IconRenderer:
    """Renders crisp progress indicators with the Claude spark logo at runtime.

    Supports three customizable tray icon styles:
    - "concentric": Dual Concentric Rings 2.0 (Outer Cyan 5h, Inner Violet 7d)
    - "split": Split Bottom-Up Twin Gauges 2.0 (Left Cyan 5h, Right Violet 7d)
    - "bars": Dual Vertical Pill Columns (Left Cyan 5h, Right Violet 7d)
    """

    CANVAS_SIZE = 256  # 4x Supersampling base
    TARGET_SIZE = 64  # Downsampled target size for HiDPI tray

    @classmethod
    def render_tray_icon(
        cls,
        five_hour_pct: float,
        seven_day_pct: Optional[float] = None,
        is_offline: bool = False,
        style: str = "concentric",
        size: int = TARGET_SIZE,
    ) -> QIcon:
        """Generates a QIcon representing current quota utilization with dual indicators."""
        img = cls.render_pil_image(
            five_hour_pct=five_hour_pct,
            seven_day_pct=seven_day_pct,
            is_offline=is_offline,
            style=style,
            target_size=size,
        )
        byte_arr = io.BytesIO()
        img.save(byte_arr, format="PNG")
        qimg = QImage.fromData(byte_arr.getvalue())
        pixmap = QPixmap.fromImage(qimg)
        return QIcon(pixmap)

    @classmethod
    def render_pil_image(
        cls,
        five_hour_pct: float,
        seven_day_pct: Optional[float] = None,
        is_offline: bool = False,
        style: str = "concentric",
        target_size: int = TARGET_SIZE,
    ) -> Image.Image:
        """Draws the 256x256 vector supersampled icon and downsamples to target_size."""
        dim = cls.CANVAS_SIZE
        img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx = dim / 2.0
        cy = dim / 2.0

        p_5h = max(0.0, min(100.0, float(five_hour_pct)))
        p_7d = max(0.0, min(100.0, float(seven_day_pct))) if seven_day_pct is not None else p_5h

        rgb_5h = get_channel_color(p_5h, is_weekly=False, is_offline=is_offline)
        rgb_7d = get_channel_color(p_7d, is_weekly=True, is_offline=is_offline)

        color_5h = (rgb_5h[0], rgb_5h[1], rgb_5h[2], 255)
        track_5h = (rgb_5h[0], rgb_5h[1], rgb_5h[2], 65)

        color_7d = (rgb_7d[0], rgb_7d[1], rgb_7d[2], 255)
        track_7d = (rgb_7d[0], rgb_7d[1], rgb_7d[2], 65)

        # Central Spark color
        if max(p_5h, p_7d) >= 90.0:
            spark_color = (239, 68, 68, 255)  # Critical Alert Red
        elif max(p_5h, p_7d) >= 75.0:
            spark_color = (251, 191, 36, 255)  # Warning Amber
        else:
            spark_color = (218, 119, 86, 255)  # Iconic Claude Terracotta #DA7756

        if style == "bars":
            # -------------------------------------------------------------
            # STYLE C: DUAL VERTICAL PILL COLUMNS (Sinistra 5h, Destra 7g)
            # -------------------------------------------------------------
            cls._draw_vertical_pill_bar(
                draw=draw,
                x0=38,
                y0=22,
                x1=114,
                y1=234,
                pct=p_5h,
                color=color_5h,
                track_color=track_5h,
            )
            cls._draw_vertical_pill_bar(
                draw=draw,
                x0=142,
                y0=22,
                x1=218,
                y1=234,
                pct=p_7d,
                color=color_7d,
                track_color=track_7d,
            )
        elif style == "split":
            # -------------------------------------------------------------
            # STYLE B: SPLIT BOTTOM-UP TWIN GAUGES (Sinistra 5h, Destra 7g)
            # -------------------------------------------------------------
            # Both arcs start at 6 o'clock (bottom) and climb upward to 12 o'clock
            # with a clean 36-degree separation gap at bottom and top.
            r = 114.0
            w = 28.0

            # Left Gauge (5h Cyan): bottom-left (108 deg) climbing clockwise to top-left (252 deg, 144 deg span)
            cls._draw_split_arc_bottom_up(
                draw=draw,
                cx=cx,
                cy=cy,
                radius=r,
                width=w,
                pct=p_5h,
                color=color_5h,
                track_color=track_5h,
                is_left_side=True,
            )

            # Right Gauge (7d Violet): bottom-right (72 deg) climbing counter-clockwise to top-right (288 deg, 144 deg span)
            cls._draw_split_arc_bottom_up(
                draw=draw,
                cx=cx,
                cy=cy,
                radius=r,
                width=w,
                pct=p_7d,
                color=color_7d,
                track_color=track_7d,
                is_left_side=False,
            )

            # Central Claude Spark (generous 48px)
            cls._draw_claude_spark(draw, cx, cy, spark_radius=48.0, color=spark_color)
        else:
            # -------------------------------------------------------------
            # STYLE A: DUAL CONCENTRIC RINGS 2.0 (Esterno 5h Ciano, Interno 7g Viola)
            # -------------------------------------------------------------
            # Outer Ring (5h): outer radius 116, width 24 -> spans [92..116]
            r_outer = 116.0
            w_outer = 24.0
            cls._draw_arc_with_caps(
                draw=draw,
                cx=cx,
                cy=cy,
                radius=r_outer,
                width=w_outer,
                start_deg=270.0,
                sweep_deg=(p_5h / 100.0) * 360.0,
                color=color_5h,
                track_color=track_5h,
            )

            # Inner Ring (7d): outer radius 80, width 20 -> spans [60..80] (12px radial gap!)
            r_inner = 80.0
            w_inner = 20.0
            cls._draw_arc_with_caps(
                draw=draw,
                cx=cx,
                cy=cy,
                radius=r_inner,
                width=w_inner,
                start_deg=270.0,
                sweep_deg=(p_7d / 100.0) * 360.0,
                color=color_7d,
                track_color=track_7d,
            )

            # Central Claude Spark (compact 36px)
            cls._draw_claude_spark(draw, cx, cy, spark_radius=36.0, color=spark_color)

        return img.resize((target_size, target_size), Image.Resampling.LANCZOS)

    @classmethod
    def _draw_arc_with_caps(
        cls,
        draw: ImageDraw.ImageDraw,
        cx: float,
        cy: float,
        radius: float,
        width: float,
        start_deg: float,
        sweep_deg: float,
        color: tuple,
        track_color: tuple,
    ) -> None:
        """Draws a 360-degree track and a progress arc with rounded end caps centered on r_mid."""
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        cap_r = width / 2.0
        # PIL draw.arc draws stroke inward from `radius` to `radius - width`, so centerline is `r_mid`
        r_mid = radius - cap_r

        # Draw full background track
        draw.arc(bbox, start=start_deg, end=start_deg + 360.0, fill=track_color, width=int(width))

        # Draw active progress arc
        if sweep_deg > 0.5:
            end_deg = start_deg + min(360.0, sweep_deg)
            draw.arc(bbox, start=start_deg, end=end_deg, fill=color, width=int(width))

            # Start cap (at 12 o'clock)
            s_rad = math.radians(start_deg)
            sx = cx + r_mid * math.cos(s_rad)
            sy = cy + r_mid * math.sin(s_rad)
            draw.ellipse((sx - cap_r, sy - cap_r, sx + cap_r, sy + cap_r), fill=color)

            # End cap
            e_rad = math.radians(end_deg)
            ex = cx + r_mid * math.cos(e_rad)
            ey = cy + r_mid * math.sin(e_rad)
            draw.ellipse((ex - cap_r, ey - cap_r, ex + cap_r, ey + cap_r), fill=color)

    @classmethod
    def _draw_split_arc_bottom_up(
        cls,
        draw: ImageDraw.ImageDraw,
        cx: float,
        cy: float,
        radius: float,
        width: float,
        pct: float,
        color: tuple,
        track_color: tuple,
        is_left_side: bool = True,
    ) -> None:
        """Draws a 144-degree bottom-up gauge arc (6 o'clock to 12 o'clock) with a 36-deg gap."""
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        cap_r = width / 2.0
        r_mid = radius - cap_r
        span = 144.0

        if is_left_side:
            # Left gauge (5h): starts at bottom-left (108 deg) and climbs clockwise to top-left (252 deg)
            t_start, t_end = 108.0, 252.0
            draw.arc(bbox, start=t_start, end=t_end, fill=track_color, width=int(width))
            for deg in (t_start, t_end):
                rad = math.radians(deg)
                draw.ellipse(
                    (
                        cx + r_mid * math.cos(rad) - cap_r,
                        cy + r_mid * math.sin(rad) - cap_r,
                        cx + r_mid * math.cos(rad) + cap_r,
                        cy + r_mid * math.sin(rad) + cap_r,
                    ),
                    fill=track_color,
                )

            if pct > 0.5:
                sweep = max(4.0, (pct / 100.0) * span)
                a_end = min(t_end, t_start + sweep)
                draw.arc(bbox, start=t_start, end=a_end, fill=color, width=int(width))
                for deg in (t_start, a_end):
                    rad = math.radians(deg)
                    draw.ellipse(
                        (
                            cx + r_mid * math.cos(rad) - cap_r,
                            cy + r_mid * math.sin(rad) - cap_r,
                            cx + r_mid * math.cos(rad) + cap_r,
                            cy + r_mid * math.sin(rad) + cap_r,
                        ),
                        fill=color,
                    )
        else:
            # Right gauge (7d): starts at bottom-right (72 deg) and climbs counter-clockwise to top-right (-72 / 288 deg)
            # In PIL clockwise angles: from -72.0 to 72.0
            draw.arc(bbox, start=-72.0, end=72.0, fill=track_color, width=int(width))
            for deg in (-72.0, 72.0):
                rad = math.radians(deg)
                draw.ellipse(
                    (
                        cx + r_mid * math.cos(rad) - cap_r,
                        cy + r_mid * math.sin(rad) - cap_r,
                        cx + r_mid * math.cos(rad) + cap_r,
                        cy + r_mid * math.sin(rad) + cap_r,
                    ),
                    fill=track_color,
                )

            if pct > 0.5:
                sweep = max(4.0, (pct / 100.0) * span)
                a_start = max(-72.0, 72.0 - sweep)
                draw.arc(bbox, start=a_start, end=72.0, fill=color, width=int(width))
                for deg in (a_start, 72.0):
                    rad = math.radians(deg)
                    draw.ellipse(
                        (
                            cx + r_mid * math.cos(rad) - cap_r,
                            cy + r_mid * math.sin(rad) - cap_r,
                            cx + r_mid * math.cos(rad) + cap_r,
                            cy + r_mid * math.sin(rad) + cap_r,
                        ),
                        fill=color,
                    )

    @classmethod
    def _draw_vertical_pill_bar(
        cls,
        draw: ImageDraw.ImageDraw,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        pct: float,
        color: tuple,
        track_color: tuple,
    ) -> None:
        """Draws a vertical pill-shaped level column filling from bottom to top."""
        bar_w = x1 - x0
        bar_h = y1 - y0
        pill_r = bar_w // 2
        outline_color = (color[0], color[1], color[2], 110)

        # Background pill track
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=pill_r,
            fill=track_color,
            outline=outline_color,
            width=4,
        )

        # Active bottom-up fill
        if pct > 0.5:
            fill_h = max(int(bar_w * 0.65), int((pct / 100.0) * bar_h))
            draw.rounded_rectangle(
                (x0, y1 - fill_h, x1, y1),
                radius=min(pill_r, fill_h // 2),
                fill=color,
            )

    @classmethod
    def _draw_claude_spark(
        cls,
        draw: ImageDraw.ImageDraw,
        cx: float,
        cy: float,
        spark_radius: float,
        color: tuple,
    ) -> None:
        """Draws Claude's iconic starburst rays in the center."""
        num_rays = 12
        ray_width = 6
        for i in range(num_rays):
            angle = i * (360.0 / num_rays)
            rad = math.radians(angle)
            r_len = spark_radius if (i % 2 == 0) else (spark_radius * 0.70)
            inner_gap = 7.0

            x1 = cx + inner_gap * math.cos(rad)
            y1 = cy + inner_gap * math.sin(rad)
            x2 = cx + r_len * math.cos(rad)
            y2 = cy + r_len * math.sin(rad)

            draw.line([(x1, y1), (x2, y2)], fill=color, width=ray_width)
            cap_r = ray_width / 2.0
            draw.ellipse((x2 - cap_r, y2 - cap_r, x2 + cap_r, y2 + cap_r), fill=color)

        core_r = 5.0
        draw.ellipse(
            (cx - core_r, cy - core_r, cx + core_r, cy + core_r),
            fill=color,
        )

    @classmethod
    def get_app_icon_path(cls) -> Path:
        """Returns the path to the official app icon, creating it if absent."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            bundle_dir = Path(sys._MEIPASS)
            icon_png = bundle_dir / "claude_usage" / "resources" / "app_icon.png"
            if icon_png.exists():
                return icon_png

        pkg_res = Path(__file__).parent.parent / "resources"
        icon_png = pkg_res / "app_icon.png"
        icon_ico = pkg_res / "app_icon.ico"

        if not icon_png.exists() or not icon_ico.exists():
            pkg_res.mkdir(parents=True, exist_ok=True)
            cls.generate_app_icon(icon_png, size=256)

        return icon_png

    @classmethod
    def generate_app_icon(cls, target_path: Path, size: int = 256) -> Path:
        """Generates the official Fluent Dark application icon with dual rings and Claude spark."""
        canvas_dim = 512
        img = Image.new("RGBA", (canvas_dim, canvas_dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Dark squircle plate
        margin = 24
        plate_bbox = (margin, margin, canvas_dim - margin, canvas_dim - margin)
        draw.rounded_rectangle(plate_bbox, radius=108, fill=(18, 18, 20, 255), outline=(42, 42, 48, 255), width=4)

        # 2. Dual Concentric Progress Rings
        cx, cy = canvas_dim / 2.0, canvas_dim / 2.0

        # Outer Ring: 5h Session ring (Cyan #38BDF8, e.g. 68%)
        color_outer = (56, 189, 248, 255)
        track_outer = (56, 189, 248, 55)
        cls._draw_arc_with_caps(
            draw=draw,
            cx=cx,
            cy=cy,
            radius=190.0,
            width=32.0,
            start_deg=270.0,
            sweep_deg=0.68 * 360.0,
            color=color_outer,
            track_color=track_outer,
        )

        # Inner Ring: 7d Weekly ring (Violet #C084FC, e.g. 48%)
        color_inner = (192, 132, 252, 255)
        track_inner = (192, 132, 252, 55)
        cls._draw_arc_with_caps(
            draw=draw,
            cx=cx,
            cy=cy,
            radius=142.0,
            width=26.0,
            start_deg=270.0,
            sweep_deg=0.48 * 360.0,
            color=color_inner,
            track_color=track_inner,
        )

        # 3. Terracotta Spark Logo in the Center
        terracotta = (218, 119, 86, 255)
        cls._draw_claude_spark(draw, cx, cy, spark_radius=72.0, color=terracotta)

        # Save resized PNG
        final_img = img.resize((size, size), Image.Resampling.LANCZOS)
        final_img.save(target_path, format="PNG")

        # Save multi-size ICO
        ico_path = target_path.with_suffix(".ico")
        icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        ico_images = [img.resize(s, Image.Resampling.LANCZOS) for s in icon_sizes]
        ico_images[0].save(
            ico_path,
            format="ICO",
            sizes=icon_sizes,
            append_images=ico_images[1:],
        )

        return target_path
