"""
OpenXVehicleFactory — load vehicles from OpenX .blend asset packs and wrap
them in the standard Infinigen UrbanAssetFactory interface.

Usage:
    export OPENX_ASSETS_ROOT=/path/to/openx_assets
    factory = OpenXVehicleFactory(mats)
    objects, meta = factory.create(request)

Falls back to the procedural VehicleFactory when no OpenX assets are found.
"""

import json
import math
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import bpy
from mathutils import Vector

from infinigen.assets.objects.vehicles.vehicle import VehicleFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest


# ─── Asset entry ──────────────────────────────────────────────────────────────

@dataclass
class OpenXVehicleEntry:
    vehicle_id: str
    name: str
    blend_path: Path
    xoma_path: Optional[Path] = None
    length: float = 4.50     # metres  (x-axis forward)
    width: float  = 1.88     # metres  (y-axis lateral)
    height: float = 1.45     # metres  (z-axis up)
    category: str = "car"    # car | truck | bus | motorcycle
    mass: float   = 1500.0   # kg


# ─── Manifest scanner ─────────────────────────────────────────────────────────

class OpenXManifest:
    """
    Scan ``OPENX_ASSETS_ROOT/src/vehicles/main/<id>/`` for .xoma + .blend
    pairs.  Also accepts a plain directory of .blend files without .xoma.
    """

    def __init__(self, assets_root: Optional[str] = None):
        root_env = assets_root or os.environ.get("OPENX_ASSETS_ROOT", "")
        self.root = Path(root_env) if root_env else None
        self.entries: list[OpenXVehicleEntry] = []
        if self.root and self.root.exists():
            self._scan()

    # ------------------------------------------------------------------
    def _scan(self):
        search_dir = self.root / "src" / "vehicles" / "main"
        if not search_dir.exists():
            search_dir = self.root

        seen_blends: set[Path] = set()

        for xoma in sorted(search_dir.rglob("*.xoma")):
            blend = xoma.with_suffix(".blend")
            if not blend.exists():
                candidates = sorted(xoma.parent.glob("*.blend"))
                if not candidates:
                    continue
                blend = candidates[0]
            entry = self._parse_xoma(xoma, blend)
            self.entries.append(entry)
            seen_blends.add(blend)

        # pick up .blend files that have no .xoma companion
        for blend in sorted(search_dir.rglob("*.blend")):
            if blend not in seen_blends:
                vid = blend.stem
                self.entries.append(OpenXVehicleEntry(
                    vehicle_id=vid, name=vid,
                    blend_path=blend, xoma_path=None,
                ))

    # ------------------------------------------------------------------
    def _parse_xoma(self, xoma: Path, blend: Path) -> OpenXVehicleEntry:
        """Parse .xoma (OpenMATERIAL-3D JSON or legacy XML/JSON) metadata."""
        text = xoma.read_text(errors="replace")
        vid  = xoma.stem
        name, length, width, height, category, mass = vid, 4.50, 1.88, 1.45, "car", 1500.0

        # ── OpenMATERIAL-3D JSON (primary format) ──────────────────────────
        # Structure: { "metadata": { "name", "vehicleClassData": { "vehicleCategory" },
        #              "boundingBox": { "x":[min,max], "y":[min,max], "z":[min,max] },
        #              "mass": float } }
        try:
            data = json.loads(text)
            meta = data.get("metadata", data)   # tolerate both wrapped and flat
            name     = meta.get("name", vid) or vid
            mass_raw = meta.get("mass")
            if mass_raw is not None:
                mass = float(mass_raw)
            vcd      = meta.get("vehicleClassData", {})
            category = vcd.get("vehicleCategory", category).lower()
            bb       = meta.get("boundingBox", {})
            if "x" in bb and isinstance(bb["x"], list) and len(bb["x"]) == 2:
                # OpenMATERIAL-3D range format: {"x":[min,max], "y":[min,max], "z":[min,max]}
                length = float(bb["x"][1]) - float(bb["x"][0])
                width  = float(bb["y"][1]) - float(bb["y"][0])
                height = float(bb["z"][1]) - float(bb["z"][0])
            else:
                # flat length/width/height format
                length = float(bb.get("length", length))
                width  = float(bb.get("width",  width))
                height = float(bb.get("height", height))
            return OpenXVehicleEntry(
                vehicle_id=vid, name=name, blend_path=blend, xoma_path=xoma,
                length=length, width=width, height=height, category=category, mass=mass,
            )
        except Exception:
            pass

        # ── Legacy XML fallback ─────────────────────────────────────────────
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(text)

            def _f(tag, default):
                el = root.find(f".//{tag}")
                return float(el.text) if (el is not None and el.text) else default

            def _s(tag, default):
                el = root.find(f".//{tag}")
                return el.text.strip() if (el is not None and el.text) else default

            name     = _s("name", vid) or _s("id", vid)
            length   = _f("length", length)
            width    = _f("width",  width)
            height   = _f("height", height)
            mass     = _f("mass",   mass)
            category = _s("vehicleCategory", category).lower()
        except Exception:
            pass

        return OpenXVehicleEntry(
            vehicle_id=vid, name=name, blend_path=blend, xoma_path=xoma,
            length=length, width=width, height=height, category=category, mass=mass,
        )

    # ------------------------------------------------------------------
    def pick(self, category: Optional[str] = None,
             seed: Optional[int] = None) -> Optional[OpenXVehicleEntry]:
        pool = [e for e in self.entries if not category or e.category == category]
        if not pool:
            pool = self.entries
        if not pool:
            return None
        return random.Random(seed).choice(pool)

    def __len__(self):
        return len(self.entries)


# ─── Material helpers ─────────────────────────────────────────────────────────

_PAINT_PALETTE = [
    ("pearl_white",    (0.86, 0.87, 0.85), 0.60, 0.18),
    ("midnight_black", (0.030, 0.030, 0.032), 0.85, 0.14),
    ("racing_red",     (0.55, 0.030, 0.020), 0.80, 0.16),
    ("ocean_blue",     (0.030, 0.095, 0.50), 0.80, 0.16),
    ("slate_grey",     (0.24, 0.25, 0.27), 0.82, 0.18),
    ("forest_green",   (0.040, 0.24, 0.090), 0.78, 0.20),
    ("champagne",      (0.62, 0.52, 0.36), 0.72, 0.22),
    ("copper_orange",  (0.55, 0.22, 0.060), 0.76, 0.20),
]


def _make_paint(name: str, rgb: tuple, metallic: float = 0.82,
                roughness: float = 0.16) -> bpy.types.Material:
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if not bsdf:
        return mat
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value   = metallic
    bsdf.inputs["Roughness"].default_value  = roughness
    for k in ("Coat Weight", "Clearcoat"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = 0.90
            break
    for k in ("Coat Roughness", "Clearcoat Roughness"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = 0.030
            break
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = 1.52
    return mat


def _make_glass(name: str = "openx_glass") -> bpy.types.Material:
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.040, 0.070, 0.10, 1.0)
        bsdf.inputs["Roughness"].default_value  = 0.018
        for k in ("Transmission Weight", "Transmission"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = 0.95
                break
    return mat


def _pick_paint(seed: int):
    rng = random.Random(seed)
    label, rgb, metallic, roughness = rng.choice(_PAINT_PALETTE)
    rgb = tuple(max(0.0, min(1.0, c + rng.uniform(-0.04, 0.04))) for c in rgb)
    return label, rgb, metallic, roughness


# ─── Dirt / scratch overlay ───────────────────────────────────────────────────

def _add_dirt_overlay(body_objects: list, seed: int = 0,
                      max_intensity: float = 0.15):
    """Inject a noise-driven dirt shader into body paint materials."""
    rng = random.Random(seed)
    dirt_level = rng.uniform(0.0, max_intensity)
    if dirt_level < 0.02:
        return

    for obj in body_objects:
        if not (hasattr(obj, "data") and hasattr(obj.data, "materials")):
            continue
        for mat in obj.data.materials:
            if mat is None or not mat.name.startswith("openx_paint"):
                continue
            nt = mat.node_tree
            if any(n.name == "_openx_dirt" for n in nt.nodes):
                continue  # already patched

            out_node  = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
            bsdf_node = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not out_node or not bsdf_node:
                continue

            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.name = "_openx_dirt"
            noise.inputs["Scale"].default_value    = 18.0
            noise.inputs["Detail"].default_value   = 8.0
            noise.inputs["Roughness"].default_value = 0.65

            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = 0.55
            ramp.color_ramp.elements[0].color    = (0.0, 0.0, 0.0, 1.0)
            ramp.color_ramp.elements[1].position = 1.0
            ramp.color_ramp.elements[1].color    = (1.0, 1.0, 1.0, 1.0)

            dirt_bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
            dirt_bsdf.inputs["Color"].default_value = (0.060, 0.040, 0.020, 1.0)

            mix = nt.nodes.new("ShaderNodeMixShader")
            mix.inputs[0].default_value = dirt_level

            for lk in list(nt.links):
                if lk.to_node == out_node:
                    nt.links.remove(lk)

            nt.links.new(bsdf_node.outputs[0], mix.inputs[1])
            nt.links.new(dirt_bsdf.outputs[0], mix.inputs[2])
            nt.links.new(ramp.outputs["Color"], mix.inputs[0])
            nt.links.new(noise.outputs["Fac"],  ramp.inputs["Fac"])
            nt.links.new(mix.outputs[0], out_node.inputs["Surface"])


# ─── BBox helper ──────────────────────────────────────────────────────────────

def _add_bbox_empty(name: str, length: float, width: float, height: float,
                    loc: tuple) -> bpy.types.Object:
    bpy.ops.object.empty_add(type="CUBE", location=loc)
    em = bpy.context.active_object
    em.name = name
    em.scale = (length / 2, width / 2, height / 2)
    em.hide_render = True
    em["bbox_length"] = length
    em["bbox_width"]  = width
    em["bbox_height"] = height
    return em


# ─── OpenXVehicleFactory ──────────────────────────────────────────────────────

class OpenXVehicleFactory:
    """
    Wrap an OpenX .blend vehicle asset in the Infinigen UrbanAssetFactory
    interface.  Falls back to the procedural VehicleFactory when no OpenX
    assets are available.

    Parameters
    ----------
    mats        : dict of material name → bpy.types.Material
    assets_root : path to OpenX asset root; overrides OPENX_ASSETS_ROOT env var
    fallback    : if True, use VehicleFactory when no OpenX assets exist
    """

    def __init__(self, mats: dict,
                 assets_root: Optional[str] = None,
                 fallback: bool = True):
        self.mats     = mats
        self.manifest = OpenXManifest(assets_root)
        self._fallback_factory = VehicleFactory(mats) if fallback else None

        if len(self.manifest) == 0:
            if fallback:
                print("[OpenXVehicleFactory] No OpenX assets found — will use "
                      "procedural VehicleFactory fallback.")
            else:
                raise RuntimeError(
                    "No OpenX assets found.  Set OPENX_ASSETS_ROOT or pass "
                    "assets_root=<path> to OpenXVehicleFactory."
                )

    # ------------------------------------------------------------------
    def create(self, request: UrbanAssetRequest):
        """
        Returns (objects_list, metadata_dict) — same contract as VehicleFactory.
        """
        seed = hash((request.asset_type, request.location,
                     request.semantic, request.yaw)) & 0xFFFFFFFF
        rng  = random.Random(seed)

        category = request.params.get("vehicle_category", None)
        entry    = self.manifest.pick(category=category, seed=seed)

        if entry is None:
            objs, meta = self._fallback_factory.create(request)
            meta["source"] = "procedural"
            return objs, meta

        return self._load_and_prepare(entry, request, rng)

    # ------------------------------------------------------------------
    def _load_and_prepare(self, entry: OpenXVehicleEntry,
                          request: UrbanAssetRequest,
                          rng: random.Random):
        x, y, _z = request.location

        loaded = self._append_blend(entry)
        if not loaded:
            print(f"[OpenXVehicleFactory] Could not load {entry.blend_path}, "
                  "falling back to procedural.")
            objs, meta = self._fallback_factory.create(request)
            meta["source"] = "procedural"
            return objs, meta

        self._normalize_scale(loaded, entry)

        jitter_yaw = rng.uniform(-0.035, 0.035)
        self._place(loaded, x, y, request.yaw + jitter_yaw)

        paint_seed = rng.randint(0, 0xFFFF)
        body_objs  = self._randomize_materials(loaded, paint_seed)
        _add_dirt_overlay(body_objs, seed=paint_seed, max_intensity=0.15)

        plate_objs = self._add_license_plate(entry, x, y)
        loaded.extend(plate_objs)

        bbox_em = _add_bbox_empty(
            f"openx:vehicle:bbox:{entry.vehicle_id}",
            entry.length, entry.width, entry.height,
            loc=(x, y, entry.height / 2),
        )
        loaded.append(bbox_em)

        self._tag_objects(loaded, request.semantic or "vehicle")

        meta = {
            "id":       entry.vehicle_id,
            "name":     entry.name,
            "type":     entry.category,
            "center":   [x, y, 0.0],
            "yaw":      request.yaw,
            "length":   entry.length,
            "width":    entry.width,
            "height":   entry.height,
            "mass":     entry.mass,
            "source":   "openx",
            "blend":    str(entry.blend_path),
        }
        return loaded, meta

    # ------------------------------------------------------------------
    def _append_blend(self, entry: OpenXVehicleEntry) -> list:
        """Append all objects from entry.blend_path into the active scene."""
        before = set(bpy.data.objects.keys())
        try:
            with bpy.data.libraries.load(str(entry.blend_path), link=False) as (src, dst):
                dst.objects = list(src.objects)
        except Exception as exc:
            print(f"[OpenXVehicleFactory] bpy.data.libraries.load failed: {exc}")
            return []

        result = []
        for name in set(bpy.data.objects.keys()) - before:
            obj = bpy.data.objects[name]
            if obj.name not in bpy.context.collection.objects:
                bpy.context.collection.objects.link(obj)
            result.append(obj)

        # refresh depsgraph so matrix_world is correct for all loaded objects
        bpy.context.view_layer.update()
        return result

    # ------------------------------------------------------------------
    def _roots(self, objs: list) -> list:
        """Return objects whose parent is None or not in the loaded set."""
        names = {o.name for o in objs}
        return [o for o in objs
                if o.parent is None or o.parent.name not in names]

    # ------------------------------------------------------------------
    def _normalize_scale(self, objs: list, entry: OpenXVehicleEntry):
        """
        Scale and translate only ROOT objects.
        Computes the world bounding box from all mesh objects, then applies a
        uniform scale + translation to each root so the vehicle is
        entry.length long, centred at the world origin, and bottom at z = 0.
        Children follow automatically via the parent hierarchy.
        """
        xs, ys, zs = [], [], []
        for obj in objs:
            if obj.type != "MESH":
                continue
            mw = obj.matrix_world
            for corner in obj.bound_box:
                w = mw @ Vector(corner)
                xs.append(w.x); ys.append(w.y); zs.append(w.z)
        if not xs:
            return

        cur_len = max(xs) - min(xs)
        if cur_len < 0.001:
            return

        sf    = entry.length / cur_len
        cx    = (max(xs) + min(xs)) / 2
        cy    = (max(ys) + min(ys)) / 2
        z_bot = min(zs)

        # Only transform ROOT objects — children follow automatically
        for obj in self._roots(objs):
            obj.scale    = (obj.scale.x * sf, obj.scale.y * sf, obj.scale.z * sf)
            obj.location = (
                (obj.location.x - cx)    * sf,
                (obj.location.y - cy)    * sf,
                (obj.location.z - z_bot) * sf,
            )
        bpy.context.view_layer.update()

    # ------------------------------------------------------------------
    def _place(self, objs: list, x: float, y: float, yaw: float):
        """Translate and rotate ROOT objects only; children follow the hierarchy."""
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        for obj in self._roots(objs):
            lx, ly = obj.location.x, obj.location.y
            obj.location.x = x + lx * cos_y - ly * sin_y
            obj.location.y = y + lx * sin_y + ly * cos_y
            obj.rotation_euler.z += yaw

    # ------------------------------------------------------------------
    # Material keywords that indicate NON-BODY parts — leave these alone
    _SKIP_MAT_KEYWORDS = (
        "light", "lamp", "light_low", "light_high", "light_tail",
        "light_brake", "light_turn", "light_reverse", "light_fog",
        "wheel", "tire", "tyre", "rim", "brake",
        "interior", "seat", "dashboard", "cockpit",
        "license", "plate", "number",
        "glass", "window", "windshield", "windscreen", "visor",
    )
    _GLASS_KEYWORDS = ("glass", "window", "windshield", "windscreen", "visor")
    # Object-name patterns that are definitely NOT body panels
    _SKIP_OBJ_KEYWORDS = (
        "light_", "wheel_", "tire_", "license_plate", "interior_",
    )

    def _randomize_materials(self, objs: list, seed: int) -> list:
        """
        Replace only the main body-paint materials; leave lights, tyres,
        glass and interior materials untouched.
        Returns a list of body objects for the dirt overlay.
        """
        label, rgb, metallic, roughness = _pick_paint(seed)
        paint_name = f"openx_paint_{label}_{seed & 0xFFF:03x}"
        paint_mat  = _make_paint(paint_name, rgb, metallic, roughness)
        glass_mat  = _make_glass()

        body_objs = []
        for obj in objs:
            if obj.type != "MESH":
                continue

            obj_name_lower = obj.name.lower()
            # skip objects that are clearly not body panels
            if any(k in obj_name_lower for k in self._SKIP_OBJ_KEYWORDS):
                continue

            is_body = False
            for si in range(len(obj.data.materials)):
                mat = obj.data.materials[si]
                if mat is None:
                    continue
                mn = mat.name.lower()
                # replace glass/window materials
                if any(k in mn for k in self._GLASS_KEYWORDS):
                    obj.data.materials[si] = glass_mat
                    continue
                # skip non-body material slots
                if any(k in mn for k in self._SKIP_MAT_KEYWORDS):
                    continue
                # slot 0 that survives the above checks → body paint
                if si == 0:
                    obj.data.materials[si] = paint_mat
                    is_body = True

            if is_body:
                body_objs.append(obj)
        return body_objs

    # ------------------------------------------------------------------
    def _add_license_plate(self, entry: OpenXVehicleEntry,
                           x: float, y: float) -> list:
        plate_mat = self.mats.get("license_plate")
        if plate_mat is None:
            return []
        objs   = []
        half_l = entry.length / 2
        for sign, label in [(-1, "front"), (1, "rear")]:
            loc = (x + sign * (half_l + 0.022), y, 0.44)
            bpy.ops.object.select_all(action="DESELECT")
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
            pl = bpy.context.active_object
            pl.name       = f"openx:vehicle:plate:{entry.vehicle_id}:{label}"
            pl.dimensions = (0.035, 0.520, 0.120)
            bpy.ops.object.transform_apply(scale=True)
            pl.data.materials.append(plate_mat)
            pl["semantic"] = "vehicle-license-plate"
            objs.append(pl)
        return objs

    # ------------------------------------------------------------------
    @staticmethod
    def _tag_objects(objs: list, semantic: str):
        try:
            import infinigen.core.tagging as tagging
            for obj in objs:
                if obj.type == "MESH":
                    tagging.tag_object(obj, semantic)
        except Exception:
            for obj in objs:
                if obj.type == "MESH":
                    obj["semantic"] = semantic
