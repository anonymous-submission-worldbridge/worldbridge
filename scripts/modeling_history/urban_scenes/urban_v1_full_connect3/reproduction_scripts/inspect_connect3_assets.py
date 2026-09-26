import bpy, json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
P = R / "infinigen/outputs/outdoor_part_demo"
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
files = [
    "urban_v3_school5",
    "urban_v3_police3",
    "urban_v3_fire7",
    "urban_v3_factory3",
    "urban_v3_delivery6",
    "urban_v3_atm4",
    "urban_v3_gass4",
    "urban_v3_lake3",
    "urban_v3_fitness5",
    "urban_v3_all43_25",
    "urban_v3_all41_house_small_a",
    "urban_v3_all41_house_large",
]
r = {}
for key in files:
    paths = list((P / key).glob("*.blend"))
    if not paths:
        continue
    with bpy.data.libraries.load(str(paths[0]), link=True) as (a, b):
        r[key] = {"path": str(paths[0]), "collections": list(a.collections)}
    print(key, r[key]["collections"], flush=True)
(O / "asset_catalogue.json").write_text(json.dumps(r, indent=2))
