"""Export reusable FBX meshes, exact per-wall UCX hulls, hinged doors and scene placement.

Mesh coordinates are explicitly reflected Y; FBX import MUST disable scene conversion.
A deliberately asymmetric calibration mesh is checked before the city is assembled.
"""
import hashlib, json, math, re, sys, time, os
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT
from astra_city.geometry import Batch, collection

DEST = OUT / "ue5"
S = Matrix.Diagonal((1, -1, 1, 1))


def safe(s):
    return re.sub("[^A-Za-z0-9_]", "_", s)


def dims(mesh):
    import numpy as np

    c = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", c)
    c = c.reshape(-1, 3)
    return c.min(axis=0).tolist(), c.max(axis=0).tolist()


def run():
    DEST.mkdir(exist_ok=True)
    (DEST / "Meshes").mkdir(exist_ok=True)
    geom = json.loads((OUT / "geometry_manifest.json").read_text())
    plan = json.loads((OUT / "world_manifest.json").read_text())
    originals = [o for o in bpy.context.scene.objects if o.type in ("MESH", "FONT")]
    bpy.ops.object.select_all(action="DESELECT")
    stage = collection("ASTRA_EXPORT_TEMP")
    manifests = []
    instances = []
    exported = {}
    materials = {}
    deps = bpy.context.evaluated_depsgraph_get()
    cache = {}
    cached_materials = {}
    if (
        os.environ.get("ASTRA_REUSE_STATIC_EXPORTS") == "1"
        and (DEST / "scene_manifest.json").exists()
    ):
        old = json.loads((DEST / "scene_manifest.json").read_text())
        if old["plan_sha256"] != plan["plan_sha256"]:
            raise RuntimeError("Cannot reuse exports across plan revisions")
        cache = {m["id"]: m for m in old["meshes"]}
        cached_materials = {m["id"]: m for m in old["materials"]}
    # Test asymmetric bounds [0,-300,0] .. [200,0,100] centimetres at the importer.
    calibration = Batch("SM_AstraCalibration")
    calibration.box("axes", (1, 1.5, 0.5), (2, 3, 1), next(iter(bpy.data.materials)))
    calibration.box(
        "offset", (1.75, 0.25, 0.75), (0.5, 0.5, 0.5), next(iter(bpy.data.materials))
    )
    co = calibration.finish(stage, role="calibration")
    originals.insert(0, co)
    doors = {r["object"]: r for r in geom["doors"]}
    for n, source in enumerate(originals):
        role = source.get("astra_role", "detail")
        bid = source.get("building_id", "")
        key = source.data.name if source.type == "MESH" else source.name
        door = doors.get(source.name)
        if door:
            key = f'door_{door["width_m"]}_{door["height_m"]}'
        cached = cache.get("SM_" + safe(key))
        if (
            key not in exported
            and cached
            and not key.startswith("astra_native_")
            and role not in ("calibration", "structure", "detail")
        ):
            path = DEST / cached["file"]
            if path.is_file() and path.stat().st_size == cached["bytes"]:
                exported[key] = cached["id"]
                manifests.append(cached)
                for mid in cached["materials"]:
                    materials[mid] = cached_materials[mid]
        if key not in exported:
            name = "SM_" + safe(key)
            path = DEST / "Meshes" / (name + ".fbx")
            if source.type == "FONT":
                mesh = bpy.data.meshes.new_from_object(source.evaluated_get(deps))
                mesh.transform(source.matrix_world.to_3x3().to_4x4())
            else:
                mesh = source.data.copy()
            low, high = dims(mesh)
            mesh.transform(S)
            mesh.flip_normals()
            obj = bpy.data.objects.new(name, mesh)
            stage.objects.link(obj)
            collisions = []
            if role == "structure":
                collisions = [
                    c
                    for c in geom["colliders"][bid]
                    if not c.get("dynamic")
                    and not c.get("furniture")
                    and c["name"] != "glass"
                ]
            elif role == "glass":
                collisions = [c for c in geom["colliders"][bid] if c["name"] == "glass"]
            elif role == "street_detail":
                collisions = geom["outdoor_colliders"]
            elif role in ("furniture", "door"):
                collisions = [
                    {
                        "center": [(low[i] + high[i]) / 2 for i in range(3)],
                        "dimensions": [high[i] - low[i] for i in range(3)],
                        "yaw": 0,
                        "name": "bounds",
                    }
                ]
            hulls = []
            for i, c in enumerate(collisions):
                batch = Batch(f"UCX_{name}_{i:04d}")
                batch.box(
                    c["name"],
                    c["center"],
                    c["dimensions"],
                    mesh.materials[0],
                    c.get("yaw", 0),
                )
                hull = batch.finish(stage)
                hull.data.transform(S)
                hull.data.flip_normals()
                hulls.append(hull)
            obj.select_set(True)
            for hull in hulls:
                hull.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.export_scene.fbx(
                filepath=str(path),
                use_selection=True,
                object_types={"MESH"},
                apply_unit_scale=False,
                apply_scale_options="FBX_SCALE_NONE",
                global_scale=1,
                axis_forward="Y",
                axis_up="Z",
                use_space_transform=False,
                bake_space_transform=True,
                use_mesh_modifiers=False,
                mesh_smooth_type="FACE",
                use_triangles=True,
                add_leaf_bones=False,
                bake_anim=False,
                path_mode="STRIP",
                use_custom_props=False,
            )
            slots = []
            for mat in mesh.materials:
                if mat is None:
                    continue
                mid = "M_" + safe(mat.name)
                slots.append(mid)
                if mid not in materials:
                    p = (
                        next(
                            (
                                x
                                for x in mat.node_tree.nodes
                                if x.type == "BSDF_PRINCIPLED"
                            ),
                            None,
                        )
                        if mat.use_nodes
                        else None
                    )
                    color = (
                        list(p.inputs["Base Color"].default_value)
                        if p
                        else list(mat.diffuse_color)
                    )
                    rough = float(p.inputs["Roughness"].default_value) if p else 0.6
                    metal = float(p.inputs["Metallic"].default_value) if p else 0
                    alpha = float(p.inputs["Alpha"].default_value) if p else 1
                    materials[mid] = {
                        "id": mid,
                        "blender_material": mat.name,
                        "base_color_linear": color,
                        "roughness": rough,
                        "metallic": metal,
                        "opacity": alpha,
                        "two_sided": role == "vegetation",
                        "base_color_texture": f"Textures/{mid}_BaseColor.png",
                    }
            rec = {
                "id": name,
                "file": f"Meshes/{name}.fbx",
                "role": role,
                "materials": slots,
                "collision_hulls": len(hulls),
                "collision_mode": "complex_as_simple"
                if role in ("road", "sidewalk", "context_outside_city_boundary")
                else ("simple" if hulls else "none"),
                "nanite_candidate": role not in ("glass", "door")
                and len(mesh.polygons) > 10000,
                "vertices": len(mesh.vertices),
                "faces_before_triangulation": len(mesh.polygons),
                "expected_bounds_cm": [
                    [100 * low[0], -100 * high[1], 100 * low[2]],
                    [100 * high[0], -100 * low[1], 100 * high[2]],
                ],
                "bytes": path.stat().st_size,
            }
            manifests.append(rec)
            exported[key] = name
            for x in [obj, *hulls]:
                me = x.data
                bpy.data.objects.remove(x, do_unlink=True)
                bpy.data.meshes.remove(me)
            print("FBX_EXPORTED", len(manifests), name, rec["bytes"], flush=True)
        location, rotation, scale = source.matrix_world.decompose()
        yaw = rotation.to_euler().z
        if role != "calibration":
            record = {
                "id": safe(source.name),
                "asset": exported[key],
                "role": role,
                "building_id": bid,
                "position_cm": [100 * location.x, -100 * location.y, 100 * location.z],
                "yaw_deg": -math.degrees(yaw) if source.type == "MESH" else 0,
                "scale": list(scale) if source.type == "MESH" else [1, 1, 1],
            }
            if door:
                record["door"] = {
                    "open_angle_deg": -door["open_angle_deg"],
                    "default_open": True,
                    "portal_id": door["id"],
                }
            instances.append(record)
        if n % 30 == 0:
            (DEST / "export_progress.json").write_text(
                json.dumps({"objects_processed": n, "meshes": len(manifests)})
            )
    lights = []
    for o in bpy.context.scene.objects:
        if o.get("astra_role") != "interior_light":
            continue
        p = o.matrix_world.translation
        lights.append(
            {
                "id": safe(o.name),
                "position_cm": [p.x * 100, -p.y * 100, p.z * 100],
                "color": list(o.data.color),
                "intensity_lumens": 450,
                "attenuation_radius_cm": 550,
            }
        )
    b = plan["buildings"][0]
    a = math.radians(b["yaw_deg"])
    x = b["origin"][0] + math.sin(a) * 1.5
    y = b["origin"][1] - math.cos(a) * 1.5
    result = {
        "schema": "astra.ue5.package.v1",
        "status": "EXPORTED_NOT_ENGINE_TESTED",
        "coordinate_contract": {
            "units": "centimetres",
            "blender_to_ue": "(x,-y,z)*100",
            "fbx_convert_scene": False,
            "fbx_convert_scene_unit": False,
            "mandatory_calibration_asset": "SM_SM_AstraCalibration_mesh",
        },
        "meshes": manifests,
        "instances": instances,
        "materials": list(materials.values()),
        "lights": lights,
        "player_start_cm": [x * 100, -y * 100, 108],
        "player_yaw": -90 - b["yaw_deg"],
        "plan_sha256": plan["plan_sha256"],
        "engine_import_status": "NOT_RUN",
        "runtime_walk_status": "NOT_RUN",
    }
    (DEST / "scene_manifest.json").write_text(json.dumps(result, indent=2))
    print("UE_EXPORT_COMPLETE", len(manifests), len(instances), flush=True)


if __name__ == "__main__":
    run()
