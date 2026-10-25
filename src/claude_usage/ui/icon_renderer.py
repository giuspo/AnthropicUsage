"""Dynamic System Tray Icon Renderer with Supersampled 4x Anti-Aliasing."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw
from PyQt6.QtGui import QIcon, QImage, QPixmap

from claude_usage.ui.theme import get_status_color


class IconRenderer:
    """Renders crisp circular progress rings with the Claude spark logo at runtime."""

    CANVAS_SIZE = 256  # 4x Supersampling base
    TARGET_SIZE = 64  # Downsampled target size for HiDPI tray

    @classmethod
    def render_tray_icon(
        cls,
        utilization_pct: float,
        is_offline: bool = False,
        size: int = TARGET_SIZE,
    ) -> QIcon:
        """Generates a QIcon representing current quota utilization."""
        img = cls.render_pil_image(utilization_pct, is_offline, size)
        byte_arr = io.BytesIO()
        img.save(byte_arr, format="PNG")
        qimg = QImage.fromData(byte_arr.getvalue())
        pixmap = QPixmap.fromImage(qimg)
        return QIcon(pixmap)

    @classmethod
    def render_pil_image(
        cls,
        utilization_pct: float,
        is_offline: bool = False,
        target_size: int = TARGET_SIZE,
    ) -> Image.Image:
        """Draws the 256x256 vector supersampled icon and downsamples to target_size."""
        dim = cls.CANVAS_SIZE
        img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        rgb = get_status_color(utilization_pct, is_offline)
        main_color = (rgb[0], rgb[1], rgb[2], 255)
        track_color = (rgb[0], rgb[1], rgb[2], 55)  # ~22% opacity for background track

        # Geometry parameters
        margin = 16
        ring_width = 22
        bbox = (margin, margin, dim - margin, dim - margin)

        # 1. Background Track Ring (full 360 circle)
        draw.ellipse(bbox, outline=track_color, width=ring_width)

        # 2. Progress Ring Arc
        # -90 degrees is top (12 o'clock). PIL arc is clockwise in degrees from 3 o'clock (0).
        # In PIL: 0 is 3 o'clock, 90 is 6 o'clock, 180 is 9 o'clock, 270 is 12 o'clock.
        clamped_pct = max(0.0, min(100.0, utilization_pct))
        if clamped_pct > 0.5:
            start_angle = 270.0
            sweep = (clamped_pct / 100.0) * 360.0
            end_angle = start_angle + sweep
            draw.arc(bbox, start=start_angle, end=end_angle, fill=main_color, width=ring_width)

            # Draw rounded caps at the start and end of the arc
            radius = (dim - 2 * margin) / 2.0
            center = dim / 2.0

            # Start cap (at 12 o'clock)
            start_x = center + radius * math.cos(math.radians(start_angle))
            start_y = center + radius * math.sin(math.radians(start_angle))
            cap_r = ring_width / 2.0
            draw.ellipse(
                (start_x - cap_r, start_y - cap_r, start_x + cap_r, start_y + cap_r),
                fill=main_color,
            )

            # End cap
            end_x = center + radius * math.cos(math.radians(end_angle))
            end_y = center + radius * math.sin(math.radians(end_angle))
            draw.ellipse(
                (end_x - cap_r, end_y - cap_r, end_x + cap_r, end_y + cap_r),
                fill=main_color,
            )

        # 3. Central Claude Spark / Starburst Vector Logo
        center = dim / 2.0
        cls._draw_claude_spark(draw, center, center, spark_radius=54, color=main_color)

        # 4. Anti-Aliased Lanczos Downsampling
        return img.resize((target_size, target_size), Image.Resampling.LANCZOS)

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
        # 12 rays radiating outward: alternating long and medium rays
        num_rays = 12
        ray_width = 8
        for i in range(num_rays):
            angle = i * (360.0 / num_rays)
            rad = math.radians(angle)
            # Long rays on cardinals/semi-cardinals, slightly shorter in between
            r_len = spark_radius if (i % 2 == 0) else (spark_radius * 0.72)
            inner_gap = 10.0

            x1 = cx + inner_gap * math.cos(rad)
            y1 = cy + inner_gap * math.sin(rad)
            x2 = cx + r_len * math.cos(rad)
            y2 = cy + r_len * math.sin(rad)

            draw.line([(x1, y1), (x2, y2)], fill=color, width=ray_width)
            # Round line tips
            cap_r = ray_width / 2.0
            draw.ellipse((x2 - cap_r, y2 - cap_r, x2 + cap_r, y2 + cap_r), fill=color)

        # Small central core dot
        core_r = 7.0
        draw.ellipse(
            (cx - core_r, cy - core_r, cx + core_r, cy + core_r),
            fill=color,
        )

    @classmethod
    def get_app_icon_path(cls) -> Path:
        """Returns the path to the official app icon, creating it if absent."""
        res_dir = Path(__file__).resolve().parent.parent / "resources"
        res_dir.mkdir(parents=True, exist_ok=True)
        png_path = res_dir / "app_icon.png"
        if not png_path.exists():
            cls.generate_app_icon(png_path)
        return png_path

    @classmethod
    def generate_app_icon(cls, output_path: Path, size: int = 256) -> Path:
        """Generates a crisp Fluent-style app icon with dark squircle, glowing track, and Claude spark."""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Dark squircle / rounded card background
        corner_r = int(size * 0.22)
        bg_color = (20, 20, 24, 255)
        border_color = (46, 46, 56, 255)
        draw.rounded_rectangle(
            (6, 6, size - 6, size - 6),
            radius=corner_r,
            fill=bg_color,
            outline=border_color,
            width=2,
        )

        # 2. Outer Progress Track & Accent Arc
        margin = int(size * 0.11)
        ring_w = int(size * 0.065)
        bbox = (margin, margin, size - margin, size - margin)
        claude_coral = (224, 105, 77, 255)
        track_color = (224, 105, 77, 45)
        draw.ellipse(bbox, outline=track_color, width=ring_w)

        # Arc (~75% sweep)
        start_angle = 270.0
        sweep = 270.0
        draw.arc(bbox, start=start_angle, end=start_angle + sweep, fill=claude_coral, width=ring_w)

        # 3. Central Claude starburst spark
        cx, cy = size / 2.0, size / 2.0
        spark_r = size * 0.18
        cls._draw_claude_spark(draw, cx, cy, spark_radius=spark_r, color=claude_coral)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, format="PNG")
        ico_path = output_path.with_suffix(".ico")
        try:
            img.save(
                ico_path,
                format="ICO",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
            )
        except Exception:
            pass

        return output_path

