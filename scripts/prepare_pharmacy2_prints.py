"""Procedural print artwork for actual modeled packages and equipment screens."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json, random

R = Path(__file__).resolve().parents[1]
D = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/pharmacy2/assets"
D.mkdir(parents=True, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = FONT.replace(".ttf", "-Bold.ttf")


def font(s, b=False):
    return ImageFont.truetype(BOLD if b else FONT, s)


colors = [
    "#17655d",
    "#234f80",
    "#785277",
    "#b46835",
    "#477344",
    "#397788",
    "#a24c55",
    "#536287",
]
specs = [
    ("bottle", "VITAMIN\nC", "60 TABLETS"),
    ("bottle", "VITAMIN\nD3", "90 SOFTGELS"),
    ("bottle", "VITAMIN\nB12", "60 TABLETS"),
    ("bottle", "MAGNESIUM", "60 CAPSULES"),
    ("bottle", "ZINC", "30 TABLETS"),
    ("bottle", "OMEGA\n3", "60 SOFTGELS"),
    ("carton", "ALLERGY\nCARE", "30 TABLETS"),
    ("carton", "DAILY\nSUPPORT", "30 CAPSULES"),
    ("carton", "ORAL\nREHYDRATION", "12 SACHETS"),
    ("carton", "STERILE\nDRESSINGS", "20 DRESSINGS"),
    ("carton", "ANTISEPTIC\nWIPES", "24 WIPES"),
    ("carton", "EYE\nCARE", "10 mL"),
    ("carton", "PAIN\nRELIEF", "20 TABLETS"),
    ("carton", "NASAL\nCARE", "20 mL"),
    ("tube", "HAND\nCREAM", "50 g"),
    ("tube", "BARRIER\nCREAM", "50 g"),
    ("tube", "SKINCARE\nCREAM", "75 g"),
    ("tube", "ALOE\nGEL", "50 g"),
    ("tube", "SOOTHING\nBALM", "40 g"),
    ("tube", "MOISTURISING\nCREAM", "50 g"),
]
catalog = []


def barcode(draw, box, seed):
    x, y, w, h = box
    r = random.Random(seed)
    a = x
    while a < x + w:
        k = r.choice([2, 2, 3, 4, 6])
        draw.rectangle((a, y, min(a + k, x + w), y + h), fill="#182a2d")
        a += k + r.choice([2, 3, 4])


for i, (kind, name, amount) in enumerate(specs):
    col = colors[i % len(colors)]
    prefix = f"sku_{i:02d}"
    catalog.append(
        {
            "id": i,
            "kind": kind,
            "name": name.replace("\n", " "),
            "amount": amount,
            "color": col,
            "prefix": prefix,
        }
    )
    im = Image.new("RGB", (768, 1152), "#f4f3eb")
    dr = ImageDraw.Draw(im)
    dr.rectangle((0, 0, 768, 155), fill=col)
    dr.text((48, 43), "WELL / PHARMACY", font=font(47, True), fill="white")
    dr.text((48, 186), "COMMUNITY HEALTH RANGE", font=font(23, True), fill=col)
    for j, line in enumerate(name.split("\n")):
        size = min(89, int(665 / max(1, len(line)) / 0.65))
        dr.text((46, 295 + j * 105), line, font=font(size, True), fill="#243b41")
    dr.rounded_rectangle((48, 568, 720, 670), radius=10, fill=col)
    dr.text((72, 593), amount, font=font(44, True), fill="white")
    dr.text((48, 720), "Quality care. Clearly labelled.", font=font(28), fill="#374b4e")
    dr.text((48, 773), "Sealed for your protection", font=font(26), fill="#374b4e")
    dr.line((48, 837, 720, 837), fill="#b6c5bf", width=2)
    dr.text(
        (48, 866),
        "Read the enclosed information leaflet.",
        font=font(24),
        fill="#334448",
    )
    dr.text((48, 910), "Keep the original packaging.", font=font(24), fill="#334448")
    dr.rectangle((0, 1020, 768, 1152), fill=col)
    dr.text(
        (48, 1061), "PHARMACY  •  " + f"{i+1:02d}", font=font(28, True), fill="white"
    )
    im.save(D / (prefix + "_front.png"), optimize=True)
    back = Image.new("RGB", (768, 1152), "#f4f3eb")
    dr = ImageDraw.Draw(back)
    dr.rectangle((0, 0, 768, 118), fill=col)
    dr.text((42, 33), "PRODUCT INFORMATION", font=font(38, True), fill="white")
    dr.text((42, 168), name.replace("\n", " "), font=font(32, True), fill="#233a40")
    lines = [
        "CONTENTS",
        amount,
        "PACKAGE INFORMATION",
        "Manufactured for community pharmacy retail.",
        "The pack contains a sealed inner product.",
        "Check the seal before opening.",
        "Retain the information leaflet.",
        "",
        "STORAGE",
        "Store in the original container.",
        "Keep away from moisture and direct sunlight.",
        "",
        "TRACEABILITY",
        f"LOT  WC26-{i+1:03d}-042",
        "EXP  2028 / 09",
        "PACKED  2026 / 09",
    ]
    for j, line in enumerate(lines):
        dr.text((42, 245 + j * 37), line, font=font(23, line.isupper()), fill="#354a4d")
    barcode(dr, (60, 891, 580, 110), 431 + i)
    dr.text(
        (68, 1019), "5 012340 " + f"{18000+i:05d}" + " 8", font=font(29), fill="#233a40"
    )
    dr.text((43, 1100), "BATCH VERIFIED   /   QUALITY CONTROL", font=font(20), fill=col)
    back.save(D / (prefix + "_back.png"), optimize=True)
    wrap = Image.new("RGB", (2048, 768), "#f4f3eb")
    wrap.paste(im.resize((700, 768)), (674, 0))
    wrap.paste(back.resize((580, 768)), (50, 0))
    wrap.paste(back.resize((580, 768)), (1420, 0))
    wrap.save(D / (prefix + "_wrap.png"), optimize=True)
(D / "catalog.json").write_text(json.dumps(catalog, indent=2))

# Screen pixels are mapped onto the real LCD surface, never onto the output image.
im = Image.new("RGB", (1280, 800), "#e7eef0")
d = ImageDraw.Draw(im)
d.rectangle((0, 0, 1280, 92), fill="#154f58")
d.text((34, 24), "WELL  /  DISPENSING DESK", font=font(35, True), fill="white")
d.text((1020, 34), "09:42   ONLINE", font=font(20), fill="#c5ede6")
d.rectangle((0, 92, 215, 800), fill="#233c47")
for i, t in enumerate(
    ["Overview", "Dispensing", "Collection", "Stock search", "Stock orders", "Reports"]
):
    y = 148 + i * 84
    if i == 1:
        d.rounded_rectangle((12, y - 13, 200, y + 45), radius=8, fill="#317a7d")
    d.text((30, y), t, font=font(22), fill="#e7f1f0")
d.text((250, 126), "Prescription collection queue", font=font(32, True), fill="#213d48")
d.rounded_rectangle(
    (250, 195, 1240, 251), radius=7, fill="white", outline="#bbced3", width=2
)
d.text((271, 208), "Search order number or product name", font=font(23), fill="#758d94")
d.rectangle((252, 295, 1238, 345), fill="#d2e1e4")
for x, t in [(270, "ORDER"), (430, "PRODUCT"), (840, "QTY"), (960, "STATUS")]:
    d.text((x, 308), t, font=font(21, True), fill="#395560")
for i, (product, status) in enumerate(
    [
        ("Vitamin C • sealed pack", "Ready"),
        ("Sterile dressings", "Ready"),
        ("Oral rehydration", "Checking"),
        ("Eye care • unit pack", "Ready"),
        ("Daily support", "Collection"),
    ]
):
    y = 365 + i * 61
    d.rectangle((252, y - 7, 1238, y + 47), fill="white" if i % 2 == 0 else "#eff4f5")
    d.text((270, y), f"A-{241+i}", font=font(23), fill="#264952")
    d.text((430, y), product, font=font(22), fill="#264952")
    d.text((860, y), "1", font=font(23), fill="#264952")
    d.rounded_rectangle((950, y - 2, 1199, y + 35), radius=12, fill="#d6e9e0")
    d.text((977, y + 2), status, font=font(20, True), fill="#226551")
d.rounded_rectangle((927, 706, 1238, 772), radius=9, fill="#17645f")
d.text((974, 723), "Confirm collection", font=font(23, True), fill="white")
d.text((262, 725), "STATION 02   •   Printer ready", font=font(20), fill="#4c6972")
im.save(D / "dispensing_lcd.png", optimize=True)
im = Image.new("RGB", (1280, 800), "#eef3f2")
d = ImageDraw.Draw(im)
d.rectangle((0, 0, 1280, 115), fill="#185e60")
d.text((55, 34), "WELL / PRESCRIPTION COLLECTION", font=font(43, True), fill="white")
d.text((68, 172), "Welcome", font=font(67, True), fill="#24454f")
d.text((70, 269), "Collect your prepared order", font=font(36), fill="#476c75")
for i, (a, b) in enumerate(
    [
        ("1", "Scan collection code"),
        ("2", "Confirm your order"),
        ("3", "Collect from the drawer"),
    ]
):
    y = 372 + i * 100
    d.ellipse((73, y, 132, y + 59), fill="#267c79")
    d.text((92, y + 6), a, font=font(35, True), fill="white")
    d.text((170, y + 7), b, font=font(32), fill="#294f59")
d.rounded_rectangle(
    (842, 258, 1198, 650), radius=18, fill="white", outline="#c6d8d8", width=3
)
r = random.Random(991)
for y in range(21):
    for x in range(21):
        if r.random() > 0.5:
            d.rectangle(
                (880 + x * 13, 303 + y * 13, 892 + x * 13, 315 + y * 13), fill="#173f4a"
            )
d.text((887, 603), "SCAN YOUR CODE", font=font(21, True), fill="#31515c")
im.save(D / "collection_lcd.png", optimize=True)
im = Image.new("RGB", (1024, 160), "#faf9ef")
d = ImageDraw.Draw(im)
d.text((24, 17), "WELL  /  PHARMACY RANGE", font=font(23, True), fill="#285b5c")
d.text((24, 63), "Sealed pack   •   Stock checked", font=font(20), fill="#253e42")
barcode(d, (28, 103, 374, 30), 129)
d.text((676, 39), "£ 6.45", font=font(63, True), fill="#253e42")
im.save(D / "shelf_ticket.png", optimize=True)
im = Image.new("RGB", (600, 360), "#f6f5ed")
d = ImageDraw.Draw(im)
d.text((24, 18), "WELL / DISPENSING", font=font(35, True), fill="#223f45")
d.text((24, 82), "ORDER A-0241  •  1 PACK", font=font(25), fill="#223f45")
d.text((24, 131), "BATCH WC26-042   /   CHECKED", font=font(23), fill="#223f45")
barcode(d, (26, 209, 500, 82), 996)
d.text((28, 310), "001241  260924  STATION 02", font=font(22), fill="#223f45")
im.save(D / "dispensing_label.png", optimize=True)
im = Image.new("RGB", (800, 220), "#162b32")
d = ImageDraw.Draw(im)
d.text((28, 19), "NET WEIGHT", font=font(27), fill="#96b8b4")
d.text((90, 77), "0.000 g", font=font(102, True), fill="#b8e2cb")
im.save(D / "scale_lcd.png", optimize=True)
print("PROCEDURAL_PRINTS_READY", len(catalog), flush=True)
