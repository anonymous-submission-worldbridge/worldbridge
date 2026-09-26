"""Validate reference-camera coverage and update the complete image gallery."""
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"
SOURCE = BASE / "corner_kitchen"
OUT = BASE / "corner_kitchen2"
manifest = json.loads((OUT / "images/render_manifest.json").read_text())
rendered = {r["name"]: r for r in manifest["renders"]}
original = json.loads((SOURCE / "scene_manifest.json").read_text())["shots"]
expanded = json.loads((SOURCE / "images2/render_manifest.json").read_text())["renders"]
references = {n: dict(s, source_image=f"images/{n}.png") for n, s in original.items()}
references.update(
    {
        r["name"]: dict(
            position=r["position"],
            target=r["target"],
            lens=r["lens_mm"],
            source_image=f"images2/{r['name']}.png",
        )
        for r in expanded
    }
)
actual_source = {
    f.stem for folder in ("images", "images2") for f in (SOURCE / folder).glob("*.png")
}
assert set(references) == actual_source
assert set(references) <= set(rendered), sorted(set(references) - set(rendered))
assert manifest["resolution"] == [1920, 1080]
coverage = []
for name, ref in references.items():
    result = rendered[name]
    assert result["position"] == ref["position"], name
    assert result["target"] == ref["target"], name
    assert result["lens_mm"] == ref["lens"], name
    coverage.append(
        dict(
            name=name,
            source_image=str(SOURCE / ref["source_image"]),
            rendered_image=result["file"],
            camera_matches=True,
        )
    )
for name, result in rendered.items():
    path = OUT / "images" / f"{name}.png"
    assert path.resolve() == Path(result["file"]).resolve()
    with Image.open(path) as im:
        assert im.size == (1920, 1080), (name, im.size)
        im.load()
assert {p.stem for p in (OUT / "images").glob("*.png")} == set(rendered)
report = dict(
    reference_view_count=len(references),
    covered_view_count=len(coverage),
    total_images=len(rendered),
    resolution=manifest["resolution"],
    samples=manifest["samples"],
    missing_views=[],
    camera_checks=coverage,
    extra_views=sorted(set(rendered) - set(references)),
)
(OUT / "view_coverage.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)

groups = [
    ("6 initial perspectives", list(original)),
    ("Add 20 perspectives.", sorted(r["name"] for r in expanded)),
    ("Close-up of Original Assets", report["extra_views"]),
]
ordered = [name for _, names in groups for name in names]
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
sheet = Image.new("RGB", (1920, 298 * ((len(ordered) + 3) // 4)), "#25282b")
draw = ImageDraw.Draw(sheet)
for i, name in enumerate(ordered):
    with Image.open(OUT / "images" / f"{name}.png") as im:
        im = im.convert("RGB")
        im.thumbnail((480, 270), Image.Resampling.LANCZOS)
        x, y = i % 4 * 480, i // 4 * 298
        sheet.paste(im, (x, y))
        draw.text((x + 7, y + 275), name, fill="white", font=font)
sheet.save(OUT / "contact_sheet.jpg", quality=94)

parts = [
    """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corner Kitchen 2 · All views</title>
<style>body{max-width:1500px;margin:32px auto;padding:0 20px;background:#181a1c;color:#eee;font:16px system-ui}
h1{font-size:26px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:24px}
figure{margin:0;background:#25282b;border-radius:8px;overflow:hidden}img{width:100%;display:block}
figcaption{padding:12px}small{color:#aaa;display:block;margin-top:6px}a{color:inherit;text-decoration:none}
.compare{position:relative;width:100%;aspect-ratio:16/9}.compare img{position:absolute;inset:0}
.compare .before{clip-path:inset(0 50% 0 0)}input{width:100%;margin:12px 0 28px}h2{margin-top:36px}</style>
<h1>Corner Kitchen 2 · All Perspectives</h1>""",
    f"<p>{len(rendered)} Zhang 1920×1080 image, covering the entire original scene {len(references)} image perspectives, plus 2 native asset close-ups. Click the image to view the original.</p>",
    """<h2>Specified View Comparison</h2><p>Drag the slider to compare: the left side is the original image, and the right side is the image after replacing the native asset.</p>
<div class=\"compare\"><img src=\"images/08_courtyard_eye_level.png\" alt=\"After replacing native assets\">
<img class=\"before\" id=\"before\" src=\"../corner_kitchen/images2/08_courtyard_eye_level.png\" alt=\"Original image\"></div>
<input type=\"range\" min=\"0\" max=\"100\" value=\"50\" aria-label=\"Adjust the comparison position between the original and new images\"
oninput="document.getElementById('before').style.clipPath='inset(0 '+(100-this.value)+'% 0 0)'">""",
]
for label, names in groups:
    parts.append(f"<h2>{label}</h2><main>")
    for name in names:
        desc = html.escape(rendered[name]["description"])
        parts.append(
            f'<figure><a href="images/{name}.png"><img loading="lazy" src="images/{name}.png" alt="{desc}"><figcaption>{desc}<small>{name}</small></figcaption></a></figure>'
        )
    parts.append("</main>")
parts.append("</html>")
(OUT / "index.html").write_text("\n".join(parts))
readme = (OUT / "README.md").read_text()
readme = readme.replace("There are 9 PNG images with dimensions 1920x1080.", "There are 28 PNG images with dimensions 1920x1080.")
readme = readme.replace("Nine Perspective Overview", "Overview from 28 perspectives")
marker = "\n Full-angle Coverage \n"
readme = readme.split(marker)[0].rstrip()
readme += (
    marker + "\n covers 6 perspectives of `corner_kitchen/images` and 20 perspectives of `corner_kitchen/images2`."
)
readme += "Use all camera positions, target points, and focal lengths from the usage records, and retain 2 native asset close-ups, totaling 28 images."
readme += "\n\n results are concentrated in `images/`, with filenames corresponding to the source images; coverage verification details are in `view_coverage.json`. \n"
(OUT / "README.md").write_text(readme)
print(
    json.dumps(
        {k: v for k, v in report.items() if k != "camera_checks"},
        ensure_ascii=False,
        indent=2,
    )
)
