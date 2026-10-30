"""Dynamic System Tray Icon Renderer with Dual Concentric Activity Rings."""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw
from PyQt6.QtGui import QIcon, QImage, QPixmap

from claude_usage.ui.theme import get_status_color


class IconRenderer:
    """Renders crisp circular progress rings with the Claude spark logo at runtime.
    
    Supports dual concentric activity rings:
    - Outer Ring: 5-Hour session quota (immediate working velocity)
    - Inner Ring: 7-Day weekly quota (long-term safety ceiling)
    """

    CANVAS_SIZE = 256  # 4x Supersampling base
    TARGET_SIZE = 64  # Downsampled target size for HiDPI tray

    @classmethod
    def render_tray_icon(
        cls,
        five_hour_pct: float,
        seven_day_pct: Optional[float] = None,
        is_offline: bool = False,
        size: int = TARGET_SIZE,
    ) -> QIcon:
        """Generates a QIcon representing current quota utilization with dual rings."""
        img = cls.render_pil_image(
            five_hour_pct=five_hour_pct,
            seven_day_pct=seven_day_pct,
            is_offline=is_offline,
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
        target_size: int = TARGET_SIZE,
    ) -> Image.Image:
        """Draws the 256x256 vector supersampled icon and downsamples to target_size."""
        dim = cls.CANVAS_SIZE
        img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx = dim / 2.0
        cy = dim / 2.0

        # If seven_day_pct is None, fallback to single ring or mirror five_hour_pct
        p_5h = max(0.0, min(100.0, float(five_hour_pct)))
        p_7d = max(0.0, min(100.0, float(seven_day_pct))) if seven_day_pct is not None else p_5h

        rgb_5h = get_status_color(p_5h, is_offline)
        rgb_7d = get_status_color(p_7d, is_offline)

        color_5h = (rgb_5h[0], rgb_5h[1], rgb_5h[2], 255)
        track_5h = (rgb_5h[0], rgb_5h[1], rgb_5h[2], 55)

        color_7d = (rgb_7d[0], rgb_7d[1], rgb_7d[2], 255)
        track_7d = (rgb_7d[0], rgb_7d[1], rgb_7d[2], 55)

        # -------------------------------------------------------------
        # 1. OUTER RING: 5-Hour Session Quota (Active Turn)
        # -------------------------------------------------------------
        r_outer = 112.0
        w_outer = 22.0
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

        # -------------------------------------------------------------
        # 2. INNER RING: 7-Day Weekly Quota (Global Ceiling)
        # -------------------------------------------------------------
        r_inner = 78.0
        w_inner = 18.0
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

        # -------------------------------------------------------------
        # 3. CENTRAL CLAUDE SPARK / STARBURST VECTOR LOGO
        # -------------------------------------------------------------
        # Use primary bottleneck color or warm Claude terracotta
        if max(p_5h, p_7d) >= 90.0:
            spark_color = (239, 68, 68, 255)  # Critical Alert Red
        elif max(p_5h, p_7d) >= 75.0:
            spark_color = (245, 158, 11, 255)  # Warning Amber
        else:
            spark_color = (218, 119, 86, 255)  # Iconic Claude Terracotta #DA7756

        cls._draw_claude_spark(draw, cx, cy, spark_radius=38.0, color=spark_color)

        # -------------------------------------------------------------
        # 4. Anti-Aliased Lanczos Downsampling
        # -------------------------------------------------------------
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
        """Draws a 360-degree track and a progress arc with rounded end caps."""
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        cap_r = width / 2.0

        # Draw full background track
        draw.arc(bbox, start=start_deg, end=start_deg + 360.0, fill=track_color, width=int(width))

        # Draw active progress arc
        if sweep_deg > 0.5:
            end_deg = start_deg + min(360.0, sweep_deg)
            draw.arc(bbox, start=start_deg, end=end_deg, fill=color, width=int(width))

            # Start cap (at 12 o'clock)
            s_rad = math.radians(start_deg)
            sx = cx + radius * math.cos(s_rad)
            sy = cy + radius * math.sin(s_rad)
            draw.ellipse((sx - cap_r, sy - cap_r, sx + cap_r, sy + cap_r), fill=color)

            # End cap
            e_rad = math.radians(end_deg)
            ex = cx + radius * math.cos(e_rad)
            ey = cy + radius * math.sin(e_rad)
            draw.ellipse((ex - cap_r, ey - cap_r, ex + cap_r, ey + cap_r), fill=color)

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

        # Outer Ring: 5h Session ring (e.g. 68%)
        color_outer = (248, 250, 252, 255)
        track_outer = (248, 250, 252, 40)
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

        # Inner Ring: 7d Weekly ring (e.g. 82% Warning Amber)
        color_inner = (245, 158, 11, 255)
        track_inner = (245, 158, 11, 40)
        cls._draw_arc_with_caps(
            draw=draw,
            cx=cx,
            cy=cy,
            radius=140.0,
            width=26.0,
            start_deg=270.0,
            sweep_deg=0.82 * 360.0,
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
