"""Script to render UX design options for dual quota visualization on the system tray."""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CANVAS = 256

def draw_claude_spark(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple):
    num_spikes = 12
    points = []
    inner_r = r * 0.32
    for i in range(num_spikes * 2):
        angle = (i * math.pi) / num_spikes - math.pi / 2.0
        cur_r = r if (i % 2 == 0) else inner_r
        px = cx + cur_r * math.cos(angle)
        py = cy + cur_r * math.sin(angle)
        points.append((px, py))
    draw.polygon(points, fill=color)

def get_color(pct: float):
    if pct >= 90.0:
        return (239, 68, 68, 255)   # Coral Red #EF4444
    elif pct >= 75.0:
        return (245, 158, 11, 255)  # Amber Orange #F59E0B
    else:
        return (248, 250, 252, 255) # Clean White #F8FAFC

def draw_arc_with_caps(draw, cx, cy, radius, width, start_deg, sweep_deg, color, track_color=None, full_track_sweep=360):
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    cap_r = width / 2.0
    
    # Track
    if track_color:
        draw.arc(bbox, start=start_deg, end=start_deg + full_track_sweep, fill=track_color, width=int(width))
    
    if sweep_deg > 0.5:
        end_deg = start_deg + sweep_deg
        draw.arc(bbox, start=start_deg, end=end_deg, fill=color, width=int(width))
        
        # Start cap
        s_rad = math.radians(start_deg)
        sx = cx + radius * math.cos(s_rad)
        sy = cy + radius * math.sin(s_rad)
        draw.ellipse((sx - cap_r, sy - cap_r, sx + cap_r, sy + cap_r), fill=color)
        
        # End cap
        e_rad = math.radians(end_deg)
        ex = cx + radius * math.cos(e_rad)
        ey = cy + radius * math.sin(e_rad)
        draw.ellipse((ex - cap_r, ey - cap_r, ex + cap_r, ey + cap_r), fill=color)

# Option A: Dual Concentric Rings (Outer = 5h Session, Inner = 7d Weekly)
def render_option_a(pct_5h: float, pct_7d: float) -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = CANVAS / 2.0, CANVAS / 2.0
    
    c_5h = get_color(pct_5h)
    c_7d = get_color(pct_7d)
    
    # Outer Ring (5h): radius 112, width 22
    r_outer = 112
    w_outer = 22
    t_5h = (c_5h[0], c_5h[1], c_5h[2], 50)
    sweep_5h = (min(pct_5h, 100.0) / 100.0) * 360.0
    draw_arc_with_caps(draw, cx, cy, r_outer, w_outer, 270, sweep_5h, c_5h, t_5h, 360)
    
    # Inner Ring (7d): radius 78, width 18
    r_inner = 78
    w_inner = 18
    t_7d = (c_7d[0], c_7d[1], c_7d[2], 50)
    sweep_7d = (min(pct_7d, 100.0) / 100.0) * 360.0
    draw_arc_with_caps(draw, cx, cy, r_inner, w_inner, 270, sweep_7d, c_7d, t_7d, 360)
    
    # Central Spark: radius 36
    draw_claude_spark(draw, cx, cy, r=36, color=(218, 119, 86, 255))
    return img

# Option B: Split Semicircles (Left = 5h Session, Right = 7d Weekly)
def render_option_b(pct_5h: float, pct_7d: float) -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = CANVAS / 2.0, CANVAS / 2.0
    
    c_5h = get_color(pct_5h)
    c_7d = get_color(pct_7d)
    
    r = 110
    w = 26
    
    # Left Semicircle (5h): starts from 265 deg (top-left) sweeping CCW to 95 deg (bottom-left) -> 170 deg arc
    # Or in PIL angles: 95 to 265 is the left half!
    # Let's start at 265 and sweep towards 95 (counter-clockwise, or start at 95 and sweep to 265).
    # To start at top (265) and go down left: PIL arc goes clockwise.
    # So left half goes from 95 to 265 clockwise (bottom to top? 90 is bottom, 180 is left, 270 is top).
    # So from 270 to 90 going down-right is clockwise.
    # Left half: from 90 to 270 is bottom -> left -> top.
    # To start from top and go down: start at 270 - sweep.
    # Let's do top (266) to bottom (94) for RIGHT half (7d): sweep up to 172 deg.
    t_7d = (c_7d[0], c_7d[1], c_7d[2], 50)
    sweep_7d = (min(pct_7d, 100.0) / 100.0) * 172.0
    draw_arc_with_caps(draw, cx, cy, r, w, 274, sweep_7d, c_7d, t_7d, 172)
    
    # Left half (5h): starts at top (266) and sweeps counter-clockwise to 94, OR starts at 94 and sweeps to 266.
    # In PIL clockwise: from 94 to 266 is the left arc!
    # If we want progress from top downwards: start at 266 - sweep_5h, end at 266.
    t_5h = (c_5h[0], c_5h[1], c_5h[2], 50)
    sweep_5h = (min(pct_5h, 100.0) / 100.0) * 172.0
    start_5h = 266 - sweep_5h
    draw_arc_with_caps(draw, cx, cy, r, w, start_5h, sweep_5h, c_5h, t_5h, 172)
    
    # Central Spark: radius 52 (full size)
    draw_claude_spark(draw, cx, cy, r=52, color=(218, 119, 86, 255))
    return img

# Option C: Concentric Rings Inverted (Outer = 7d Weekly Container, Inner = 5h Current Turn)
def render_option_c(pct_5h: float, pct_7d: float) -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = CANVAS / 2.0, CANVAS / 2.0
    
    c_5h = get_color(pct_5h)
    c_7d = get_color(pct_7d)
    
    # Outer Ring (7d Weekly): radius 112, width 22
    r_outer = 112
    w_outer = 22
    t_7d = (c_7d[0], c_7d[1], c_7d[2], 50)
    sweep_7d = (min(pct_7d, 100.0) / 100.0) * 360.0
    draw_arc_with_caps(draw, cx, cy, r_outer, w_outer, 270, sweep_7d, c_7d, t_7d, 360)
    
    # Inner Ring (5h Session): radius 78, width 18
    r_inner = 78
    w_inner = 18
    t_5h = (c_5h[0], c_5h[1], c_5h[2], 50)
    sweep_5h = (min(pct_5h, 100.0) / 100.0) * 360.0
    draw_arc_with_caps(draw, cx, cy, r_inner, w_inner, 270, sweep_5h, c_5h, t_5h, 360)
    
    # Central Spark: radius 36
    draw_claude_spark(draw, cx, cy, r=36, color=(218, 119, 86, 255))
    return img

# Option D: Primary Ring (5h) + Satellite Pill/Dot (7d)
def render_option_d(pct_5h: float, pct_7d: float) -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = CANVAS / 2.0, CANVAS / 2.0
    
    c_5h = get_color(pct_5h)
    c_7d = get_color(pct_7d)
    
    # Main Ring (5h): radius 110, width 24
    r_outer = 110
    w_outer = 24
    t_5h = (c_5h[0], c_5h[1], c_5h[2], 50)
    sweep_5h = (min(pct_5h, 100.0) / 100.0) * 360.0
    draw_arc_with_caps(draw, cx, cy, r_outer, w_outer, 270, sweep_5h, c_5h, t_5h, 360)
    
    # Center: Spark radius 44
    draw_claude_spark(draw, cx, cy, r=44, color=(218, 119, 86, 255))
    
    # Badge in bottom-right corner for 7d quota
    bx, by = 196, 196
    br = 46
    # Badge background
    draw.ellipse((bx - br, by - br, bx + br, by + br), fill=(24, 24, 27, 255), outline=(63, 63, 70, 255), width=4)
    # Badge mini-arc
    b_track = (c_7d[0], c_7d[1], c_7d[2], 60)
    b_sweep = (min(pct_7d, 100.0) / 100.0) * 360.0
    draw_arc_with_caps(draw, bx, by, radius=br - 10, width=12, start_deg=270, sweep_deg=b_sweep, color=c_7d, track_color=b_track, full_track_sweep=360)
    return img

print('Render functions defined.')

