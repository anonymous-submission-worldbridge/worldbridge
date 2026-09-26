#!/usr/bin/env python3
"""
generate_bev_all6.py
====================
Generate annotated Bird's Eye View (BEV) layout diagram for urban_v3_all6.
Uses only PIL (no matplotlib / Blender required).

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all6/bev_layout.png
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


from PIL import Image, ImageDraw, ImageFont
import math
from pathlib import Path

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all6")
OUT.mkdir(parents=True, exist_ok=True)

# ─── LAYOUT CONSTANTS (meters) ────────────────────────────────────────────────
R = 4.5  # road half-width  (9m total = 4 lanes)
SW = 3.5  # sidewalk width
FW = 2.5  # curb flower-bed width
S1 = R + SW  # 8.0   inner flower-bed / outer sidewalk edge
G1 = S1 + FW  # 10.5  outer flower-bed / zone start
ARM = 50.0  # arm length from intersection edge to end

# ─── PIXEL / SCALE ────────────────────────────────────────────────────────────
SCALE = 11.0  # pixels per meter
IMG_W = 1600
IMG_H = 1600
CX, CY = IMG_W // 2, IMG_H // 2  # world origin in pixel space


def W2P(wx, wy):
    """World coords → pixel coords (Y-up to Y-down flip)."""
    px = int(CX + wx * SCALE)
    py = int(CY - wy * SCALE)
    return (px, py)


def rect_pix(x0, y0, x1, y1):
    """Return PIL bounding box for world rectangle."""
    p0 = W2P(min(x0, x1), max(y0, y1))
    p1 = W2P(max(x0, x1), min(y0, y1))
    return [p0[0], p0[1], p1[0], p1[1]]


# ─── COLOURS ──────────────────────────────────────────────────────────────────
C_GROUND = (210, 197, 168)
C_ROAD = (45, 45, 45)
C_SIDEWALK = (185, 180, 170)
C_FLOWER = (80, 130, 55)
C_XWALK = (220, 215, 200)
C_STRIPE_Y = (240, 195, 20)
C_STRIPE_W = (240, 240, 230)
C_LAWN = (90, 160, 65)
C_RESID = (180, 150, 110)  # residential zone tint
C_PARK = (80, 145, 65)  # park zone tint
C_COMM = (210, 140, 80)  # commercial zone tint
C_WEST = (130, 165, 175)  # west arm zone tint
C_BUS = (30, 100, 210)
C_BIKE = (40, 160, 60)
C_HOUSE = (140, 100, 70)
C_SHOP = (200, 110, 50)
C_PARK_F = (50, 110, 50)  # park features
C_TL = (200, 50, 50)
C_LAMP = (240, 200, 10)
C_BENCH = (120, 80, 50)
C_TREE = (30, 100, 30)
C_PAVILION = (200, 140, 20)
C_WHITE = (255, 255, 255)
C_BLACK = (0, 0, 0)
C_LABEL_BG = (255, 255, 255, 200)

# ─── CREATE IMAGE ─────────────────────────────────────────────────────────────
img = Image.new("RGB", (IMG_W, IMG_H), C_GROUND)
draw = ImageDraw.Draw(img, "RGBA")

# Try to load a font; fall back to default
try:
    font_sm = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 14
    )
    font_md = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 18
    )
    font_lg = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 26
    )
    font_xl = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 34
    )
    font_ttl = ImageFont.truetype(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 42
    )
except Exception:
    font_sm = font_md = font_lg = font_xl = font_ttl = ImageFont.load_default()

EXTENT = G1 + ARM  # 60.5m

# ─── ZONE BACKGROUNDS ─────────────────────────────────────────────────────────
# North residential (both sides of N arm beyond G1)
draw.rectangle(rect_pix(-EXTENT, G1, EXTENT, EXTENT), fill=(*C_RESID, 140))
# East park (east of G1, both north and south)
draw.rectangle(rect_pix(G1, -EXTENT, EXTENT, EXTENT), fill=(*C_PARK, 130))
# South commercial (both sides of S arm below -G1)
draw.rectangle(rect_pix(-EXTENT, -EXTENT, EXTENT, -G1), fill=(*C_COMM, 130))
# West green (west of -G1)
draw.rectangle(rect_pix(-EXTENT, -EXTENT, -G1, EXTENT), fill=(*C_WEST, 110))

# ─── ROAD SURFACES ────────────────────────────────────────────────────────────
# Intersection box
draw.rectangle(rect_pix(-R, -R, R, R), fill=C_ROAD)

# N/S arm road + sidewalks + flower beds
for sgn in (+1, -1):
    y0 = sgn * R
    y1 = sgn * (R + ARM)
    draw.rectangle(rect_pix(-R, min(y0, y1), R, max(y0, y1)), fill=C_ROAD)
    # E sidewalk
    draw.rectangle(rect_pix(R, min(y0, y1), S1, max(y0, y1)), fill=C_SIDEWALK)
    # W sidewalk
    draw.rectangle(rect_pix(-S1, min(y0, y1), -R, max(y0, y1)), fill=C_SIDEWALK)
    # E flower bed
    draw.rectangle(rect_pix(S1, min(y0, y1), G1, max(y0, y1)), fill=C_FLOWER)
    # W flower bed
    draw.rectangle(rect_pix(-G1, min(y0, y1), -S1, max(y0, y1)), fill=C_FLOWER)

# E/W arm road + sidewalks + flower beds
for sgn in (+1, -1):
    x0 = sgn * R
    x1 = sgn * (R + ARM)
    draw.rectangle(rect_pix(min(x0, x1), -R, max(x0, x1), R), fill=C_ROAD)
    # N sidewalk
    draw.rectangle(rect_pix(min(x0, x1), R, max(x0, x1), S1), fill=C_SIDEWALK)
    # S sidewalk
    draw.rectangle(rect_pix(min(x0, x1), -S1, max(x0, x1), -R), fill=C_SIDEWALK)
    # N flower bed
    draw.rectangle(rect_pix(min(x0, x1), S1, max(x0, x1), G1), fill=C_FLOWER)
    # S flower bed
    draw.rectangle(rect_pix(min(x0, x1), -G1, max(x0, x1), -S1), fill=C_FLOWER)

# Corner sidewalk patches
for xs, ys in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
    x0 = xs * R
    x1 = xs * S1
    y0 = ys * R
    y1 = ys * S1
    draw.rectangle(
        rect_pix(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), fill=C_SIDEWALK
    )

# ─── CROSSWALKS ───────────────────────────────────────────────────────────────
CW_W, CW_G = 0.45, 0.25
for k in range(6):
    off = (R + 0.5) + k * (CW_W + CW_G)
    # N crosswalk (stripes run E-W across road)
    draw.rectangle(rect_pix(-R + 0.3, off, R - 0.3, off + CW_W), fill=C_XWALK)
    # S crosswalk
    draw.rectangle(rect_pix(-R + 0.3, -(off + CW_W), R - 0.3, -off), fill=C_XWALK)
    # E crosswalk (stripes run N-S)
    draw.rectangle(rect_pix(off, -R + 0.3, off + CW_W, R - 0.3), fill=C_XWALK)
    # W crosswalk
    draw.rectangle(rect_pix(-(off + CW_W), -R + 0.3, -off, R - 0.3), fill=C_XWALK)


# ─── LANE MARKINGS ────────────────────────────────────────────────────────────
def h_line(x0, x1, y, color, thick=2):
    p0 = W2P(x0, y)
    p1 = W2P(x1, y)
    draw.rectangle([p0[0], p0[1] - thick // 2, p1[0], p1[1] + thick // 2], fill=color)


def v_line(x, y0, y1, color, thick=2):
    p0 = W2P(x, y0)
    p1 = W2P(x, y1)
    draw.rectangle(
        [p0[0] - thick // 2, min(p0[1], p1[1]), p0[0] + thick // 2, max(p0[1], p1[1])],
        fill=color,
    )


# Yellow double centre lines (N-S and E-W)
v_line(-0.10, -(R + ARM), R + ARM, C_STRIPE_Y, thick=2)
v_line(0.10, -(R + ARM), R + ARM, C_STRIPE_Y, thick=2)
h_line(-(R + ARM), R + ARM, -0.10, C_STRIPE_Y, thick=2)
h_line(-(R + ARM), R + ARM, 0.10, C_STRIPE_Y, thick=2)

# White dashed lane lines (N-S arms)
DASH_L, DASH_G = 2.0, 2.0
for lane_x in [R / 2, -R / 2]:  # centre of each half-road
    for sgn in [+1, -1]:
        y = sgn * (R + 1.0)
        while abs(y) < R + ARM - 1.0:
            draw.rectangle(
                rect_pix(lane_x - 0.06, y, lane_x + 0.06, y + sgn * DASH_L),
                fill=C_STRIPE_W,
            )
            y += sgn * (DASH_L + DASH_G)

# White dashed lane lines (E-W arms)
for lane_y in [R / 2, -R / 2]:
    for sgn in [+1, -1]:
        x = sgn * (R + 1.0)
        while abs(x) < R + ARM - 1.0:
            draw.rectangle(
                rect_pix(x, lane_y - 0.06, x + sgn * DASH_L, lane_y + 0.06),
                fill=C_STRIPE_W,
            )
            x += sgn * (DASH_L + DASH_G)

# Stop lines at intersection edges
SL_OFS = 0.4
for y in [R + SL_OFS, -(R + SL_OFS)]:
    draw.rectangle(rect_pix(-R, y - 0.15, R, y + 0.15), fill=C_STRIPE_W)
for x in [R + SL_OFS, -(R + SL_OFS)]:
    draw.rectangle(rect_pix(x - 0.15, -R, x + 0.15, R), fill=C_STRIPE_W)


# ─── FLOWER BED GAPS (access openings shown as sidewalk-colour breaks) ─────────
def fb_gap_ns(x_inner, side, y0, y1):
    """Draw flower bed gap (revert to sidewalk colour) in N-S arm."""
    cx = x_inner + (FW / 2 if side == "e" else -FW / 2)
    draw.rectangle(rect_pix(cx - FW / 2, y0, cx + FW / 2, y1), fill=C_SIDEWALK)


def fb_gap_ew(y_inner, side, x0, x1):
    """Draw flower bed gap in E-W arm."""
    cy = y_inner + (FW / 2 if side == "n" else -FW / 2)
    draw.rectangle(rect_pix(x0, cy - FW / 2, x1, cy + FW / 2), fill=C_SIDEWALK)


# N arm E flower bed gaps: bus stop, bike station, house A gate, house B gate
fb_gap_ns(S1, "e", 12.0, 16.5)  # bus stop access
fb_gap_ns(S1, "e", 22.5, 27.5)  # bike station access
fb_gap_ns(S1, "e", 31.0, 35.5)  # house A gate
fb_gap_ns(S1, "e", 45.5, 49.5)  # house B gate

# N arm W flower bed gap: house C gate
fb_gap_ns(-S1, "w", 36.0, 40.0)  # house C gate

# S arm E flower bed gaps: 3 shop entrances
fb_gap_ns(S1, "e", -18.5, -13.5)  # shop A
fb_gap_ns(S1, "e", -30.5, -25.5)  # shop B
fb_gap_ns(S1, "e", -42.5, -37.5)  # shop C

# S arm W flower bed gaps: 2 shop entrances
fb_gap_ns(-S1, "w", -18.5, -13.5)
fb_gap_ns(-S1, "w", -30.5, -25.5)

# E arm N flower bed gap: park entrance
fb_gap_ew(S1, "n", 13.0, 19.0)  # park entrance

# ─── PARK LAWN ────────────────────────────────────────────────────────────────
draw.rectangle(rect_pix(G1, G1, EXTENT, 45.0), fill=(*C_LAWN, 200))

# ─── ACCESS PATHS (driveways / park path) ─────────────────────────────────────
PATH_C = (170, 165, 155)
# House A driveway (crosses E flower bed gap)
draw.rectangle(rect_pix(S1, 31.8, G1 + 1.5, 35.2), fill=PATH_C)
# House B driveway
draw.rectangle(rect_pix(S1, 45.8, G1 + 1.5, 49.2), fill=PATH_C)
# House C driveway (crosses W flower bed)
draw.rectangle(rect_pix(-G1 - 1.5, 36.8, -S1, 40.2), fill=PATH_C)

# Park main paths
draw.rectangle(rect_pix(13.5, G1, 18.5, 45.0), fill=PATH_C)  # N-S path
draw.rectangle(rect_pix(G1, 25.5, EXTENT - 3, 28.5), fill=PATH_C)  # E-W path

# Park entry path (in flower bed gap)
draw.rectangle(rect_pix(13.0, S1, 19.0, G1), fill=PATH_C)

# ─── ASSET SYMBOLS ────────────────────────────────────────────────────────────


def dot(wx, wy, color, r=6):
    p = W2P(wx, wy)
    draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color, outline=C_WHITE)


def square(wx, wy, color, hw=5, hh=5):
    p = W2P(wx, wy)
    draw.rectangle(
        [p[0] - hw, p[1] - hh, p[0] + hw, p[1] + hh], fill=color, outline=C_WHITE
    )


def asset_rect(x0, y0, x1, y1, color, label="", font=None):
    draw.rectangle(rect_pix(x0, y0, x1, y1), fill=color, outline=C_WHITE)
    if label:
        p = W2P((x0 + x1) / 2, (y0 + y1) / 2)
        fnt = font or font_sm
        draw.text(p, label, fill=C_WHITE, font=fnt, anchor="mm")


def label_at(wx, wy, text, color=C_BLACK, font=None, anchor="mm"):
    p = W2P(wx, wy)
    fnt = font or font_sm
    # White background halo
    bbox = fnt.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.rectangle(
        [
            p[0] - tw // 2 - 3,
            p[1] - th // 2 - 2,
            p[0] + tw // 2 + 3,
            p[1] + th // 2 + 2,
        ],
        fill=(255, 255, 255, 180),
    )
    draw.text(p, text, fill=color, font=fnt, anchor=anchor)


# ─── TRAFFIC LIGHTS ───────────────────────────────────────────────────────────
for tx, ty in [(0, R + 2.5), (0, -(R + 2.5)), (R + 2.5, 0), (-(R + 2.5), 0)]:
    square(tx, ty, C_TL, hw=7, hh=7)

# ─── BUS STOP (N arm E sidewalk) ──────────────────────────────────────────────
asset_rect(R + 0.2, 12.0, S1 - 0.2, 16.5, C_BUS, "BUS", font=font_sm)

# ─── BIKE STATION (N arm E beyond flower bed) ────────────────────────────────
asset_rect(G1 + 0.3, 22.5, G1 + 6.5, 27.5, C_BIKE, "BIKES", font=font_sm)

# ─── HOUSES (N arm) ──────────────────────────────────────────────────────────
# House A (east side, centered at (22, 33))
asset_rect(G1 + 1, 26.0, G1 + 23, 40.0, C_HOUSE, "HOUSE A", font=font_sm)
# House B
asset_rect(G1 + 1, 41.0, G1 + 23, 54.0, C_HOUSE, "HOUSE B", font=font_sm)
# House C (west side, centered at (-22, 38))
asset_rect(-G1 - 24, 31.0, -G1 - 1, 45.0, C_HOUSE, "HOUSE C", font=font_sm)

# ─── PARK FEATURES (E arm, NE quadrant) ──────────────────────────────────────
# Pavilion
dot(34.0, 30.0, C_PAVILION, r=9)
label_at(34.0, 30.0 - 3.5, "Pavilion", C_BLACK, font_sm)

# Sculptures
dot(20.0, 22.0, (150, 60, 180), r=7)
label_at(20.0, 22.0 - 2.5, "Sculpture", C_BLACK, font_sm)
dot(22.0, 40.0, (150, 60, 180), r=7)
label_at(22.0, 40.0 - 2.5, "Sculpture", C_BLACK, font_sm)

# Water feature
dot(26.0, 28.0, (50, 120, 220), r=6)
label_at(26.0, 28.0 + 3.0, "Pool", C_BLACK, font_sm)

# Park benches
for bx, by in [(18.0, 25.0), (26.0, 40.0), (42.0, 25.0), (42.0, 40.0)]:
    dot(bx, by, C_BENCH, r=5)

# Park trees (infinigen, large circles)
for tx, ty in [(17, 16), (24, 43), (38, 14), (46, 40), (30, 44), (15, 38), (44, 22)]:
    dot(tx, ty, C_TREE, r=9)

# ─── COMMERCIAL SHOPS (S arm) ─────────────────────────────────────────────────
for cy_s in [-16.0, -28.0, -40.0]:
    asset_rect(G1 + 0.3, cy_s - 5.5, G1 + 17, cy_s + 5.5, C_SHOP, "SHOP", font=font_sm)
for cy_s in [-16.0, -28.0]:
    asset_rect(
        -G1 - 17, cy_s - 5.5, -G1 - 0.3, cy_s + 5.5, C_SHOP, "SHOP", font=font_sm
    )

# ─── KIOSK (S arm E sidewalk) ─────────────────────────────────────────────────
dot(6.25, -22.0, (200, 120, 20), r=7)
label_at(6.25, -22.0 - 3.0, "Kiosk", C_BLACK, font_sm)

# ─── PHONE BOOTHS ─────────────────────────────────────────────────────────────
dot(-6.25, 18.0, (200, 30, 30), r=5)
label_at(-6.25, 18.0 + 3.0, "PhBooth", C_BLACK, font_sm)
dot(6.25, -38.0, (200, 30, 30), r=5)
label_at(6.25, -38.0 + 3.0, "PhBooth", C_BLACK, font_sm)

# ─── STREET TREES (in flower beds) ───────────────────────────────────────────
# N arm flower beds
for ty in [7.5, 18.0, 28.0, 40.0, 50.5]:
    dot(9.25, ty, C_TREE, r=7)
    dot(-9.25, ty, C_TREE, r=7)
# S arm flower beds
for ty in [-7.5, -18.0, -28.0, -40.0, -50.5]:
    dot(9.25, ty, C_TREE, r=7)
    dot(-9.25, ty, C_TREE, r=7)
# E arm flower beds
for tx in [7.5, 18.0, 28.0, 38.0, 48.0]:
    dot(tx, 9.25, C_TREE, r=7)
    dot(tx, -9.25, C_TREE, r=7)
# W arm flower beds
for tx in [-7.5, -18.0, -28.0, -38.0, -48.0]:
    dot(tx, 9.25, C_TREE, r=7)
    dot(tx, -9.25, C_TREE, r=7)

# ─── STREET LAMPS ─────────────────────────────────────────────────────────────
for ys in [8, 16, 24, 32, 40, 48]:
    square(5.5, ys, C_LAMP, hw=3, hh=3)
    square(-5.5, ys, C_LAMP, hw=3, hh=3)
    square(5.5, -ys, C_LAMP, hw=3, hh=3)
    square(-5.5, -ys, C_LAMP, hw=3, hh=3)
for xs in [8, 16, 24, 32, 40, 48]:
    square(xs, 5.5, C_LAMP, hw=3, hh=3)
    square(xs, -5.5, C_LAMP, hw=3, hh=3)
    square(-xs, 5.5, C_LAMP, hw=3, hh=3)
    square(-xs, -5.5, C_LAMP, hw=3, hh=3)

# ─── VEHICLES ─────────────────────────────────────────────────────────────────
# N arm northbound lane (X=2.25)
for vy in [20.0, 36.0]:
    draw.rectangle(
        rect_pix(0.4, vy - 2.0, R - 0.4, vy + 2.0), fill=(30, 80, 160), outline=C_WHITE
    )
# N arm southbound (-X side)
for vy in [28.0, 44.0]:
    draw.rectangle(
        rect_pix(-R + 0.4, vy - 2.0, -0.4, vy + 2.0),
        fill=(160, 30, 30),
        outline=C_WHITE,
    )
# S arm southbound (X=2.25, going south)
for vy in [-20.0, -38.0]:
    draw.rectangle(
        rect_pix(0.4, vy - 2.0, R - 0.4, vy + 2.0), fill=(30, 80, 160), outline=C_WHITE
    )
# E arm eastbound (Y=-2.25)
for vx in [20.0, 36.0]:
    draw.rectangle(
        rect_pix(vx - 2.0, -R + 0.4, vx + 2.0, -0.4),
        fill=(30, 80, 160),
        outline=C_WHITE,
    )
# W arm westbound (Y=2.25)
for vx in [-20.0, -36.0]:
    draw.rectangle(
        rect_pix(vx - 2.0, 0.4, vx + 2.0, R - 0.4), fill=(160, 30, 30), outline=C_WHITE
    )

# ─── ZONE TITLE LABELS ────────────────────────────────────────────────────────
label_at(0.0, 50.0, "NORTH ARM — RESIDENTIAL", (100, 60, 20), font_lg)
label_at(35.0, 0.0, "EAST ARM — PARK", (20, 90, 20), font_lg)
label_at(0.0, -50.0, "SOUTH ARM — COMMERCIAL", (180, 70, 10), font_lg)
label_at(-35.0, 0.0, "WEST ARM — GREEN", (20, 80, 120), font_lg)

# ─── LEGEND ───────────────────────────────────────────────────────────────────
LX, LY = IMG_W - 220, 30  # legend top-right in pixel space
items = [
    (C_ROAD, "Road (asphalt)"),
    (C_SIDEWALK, "Sidewalk (stone)"),
    (C_FLOWER, "Curb flower bed"),
    (C_LAWN, "Park lawn"),
    (C_HOUSE, "House + fence"),
    (C_SHOP, "Shop facade"),
    (C_BUS, "Bus stop"),
    (C_BIKE, "Bike station"),
    (C_TREE, "Tree (infinigen)"),
    (C_TL, "Traffic light"),
    (C_LAMP, "Street lamp"),
    (C_BENCH, "Bench / bin"),
]
draw.rectangle(
    [LX - 8, LY - 8, IMG_W - 8, LY + len(items) * 22 + 8], fill=(255, 255, 255, 200)
)
for i, (color, text) in enumerate(items):
    by = LY + i * 22
    draw.rectangle([LX, by + 2, LX + 18, by + 18], fill=color, outline=C_BLACK)
    draw.text((LX + 24, by + 10), text, fill=C_BLACK, font=font_sm, anchor="lm")

# ─── SCALE BAR ────────────────────────────────────────────────────────────────
sb_wx0, sb_wx1, sb_wy = -55.0, -35.0, -65.0
p0 = W2P(sb_wx0, sb_wy)
p1 = W2P(sb_wx1, sb_wy)
draw.rectangle([p0[0], p0[1] - 2, p1[0], p1[1] + 2], fill=C_BLACK)
draw.text(
    ((p0[0] + p1[0]) // 2, p0[1] - 12), "20 m", fill=C_BLACK, font=font_sm, anchor="mm"
)

# ─── NORTH ARROW ──────────────────────────────────────────────────────────────
na_x, na_y0, na_y1 = IMG_W - 60, 580, 520
draw.polygon(
    [(na_x, na_y0), (na_x - 8, na_y0 + 30), (na_x + 8, na_y0 + 30)], fill=C_BLACK
)
draw.line([(na_x, na_y0 + 30), (na_x, na_y1 + 55)], fill=C_BLACK, width=2)
draw.text((na_x, na_y1 + 55), "N", fill=C_BLACK, font=font_xl, anchor="mm")

# ─── TITLE ────────────────────────────────────────────────────────────────────
draw.text(
    (IMG_W // 2, 30),
    "urban_v3_all6 — BEV Layout Plan",
    fill=C_BLACK,
    font=font_ttl,
    anchor="mm",
)
draw.text(
    (IMG_W // 2, 70),
    "4-Zone Crossroads: Residential / Park / Commercial / Green  |  Scale ~11 px/m",
    fill=(80, 80, 80),
    font=font_md,
    anchor="mm",
)

# ─── COORDINATE GRID LABELS ────────────────────────────────────────────────────
for v in [-40, -20, 0, 20, 40]:
    p = W2P(v, -G1 - ARM - 1.5)
    draw.text((p[0], p[1]), f"{v}m", fill=(100, 100, 100), font=font_sm, anchor="mm")
    p2 = W2P(-G1 - ARM - 1.5, v)
    draw.text((p2[0], p2[1]), f"{v}m", fill=(100, 100, 100), font=font_sm, anchor="mm")

# ─── SAVE ─────────────────────────────────────────────────────────────────────
out_path = OUT / "bev_layout.png"
img.save(str(out_path), dpi=(150, 150))
print(f"[BEV] Saved: {out_path}")
print(
    f"[BEV] Scene: ±{EXTENT:.1f}m  |  Road: {2*R:.1f}m  |  Sidewalk: {SW:.1f}m  |  FlowerBed: {FW:.1f}m"
)
print(f"[BEV] G1={G1}m (zone start from center)")
