"""Export a Blender scene into Unity-friendly FBX components.

Run inside Blender:
    blender -b scene.blend --python infinigen/tools/unity/export_blend_to_unity.py -- \
        --output outputs/urban_block_10/unity_export
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import bpy


logger = logging.getLogger(__name__)


URBAN_SURFACE_TOKENS = {
    "road",
    "sidewalk",
    "sidewalk_joint",
    "lawn",
    "curb",
    "curb_ramp",
    "crosswalk",
    "lane_marking",
    "stop_line",
    "asphalt_patch",
    "road_stain",
    "road_crack",
    "manhole",
    "tactile_paving",
    "bollard",
    "storm_drain",
    "surface",
}

URBAN_BUILDING_TOKENS = {
    "building",
    "window",
    "window_frame",
    "window_ac",
    "window_ac_vent",
    "window_stain",
    "door",
    "door_frame",
    "entrance_step",
    "storefront_sign",
    "storefront_sign_glyph",
    "awning",
    "facade_ledge",
    "facade_vertical_trim",
    "facade_cable",
    "facade_stain",
    "downspout",
    "graffiti",
    "rooftop_vent",
    "rooftop_vent_cap",
    "rooftop_hvac",
    "rooftop_hvac_grille",
}

URBAN_VEGETATION_TOKENS = {
    "tree",
    "nature_tree",
    "nature_bush",
    "nature_grass_tuft",
    "nature_flowerplant",
    "grass_blades",
    "grass_seed_stems",
    "grass_seed_head",
    "grass_litter_leaf",
    "shrub",
    "fallback_flowerplant",
}

URBAN_STREET_TOKENS = {
    "street_lamp",
    "bus_stop",
    "bike_rack",
    "fire_hydrant",
    "bench",
    "trash_bin",
    "planter",
    "traffic_sign",
    "traffic_light",
    "fountain",
    "sculpture",
}

URBAN_DYNAMIC_TOKENS = {
    "vehicle",
    "pedestrian",
}

FACTORY_PROTOTYPE_MARKERS = (
    "GenericTreeFactory",
    "TreeFactory",
    "BushFactory",
    "LeafFactory",
    "TreeFlowerFactory",
    "BranchFactory",
)


@dataclass
class ExportUnit:
    name: str
    objects: list
    category: str


def parse_blender_args(parser):
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def safe_name(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return value.strip("._") or "component"


def relpath(path, parent):
    try:
        return str(path.relative_to(parent))
    except ValueError:
        return str(path)


def urban_token(obj_name):
    if not obj_name.startswith("urban:"):
        return None
    parts = obj_name.split(":")
    return parts[1] if len(parts) > 1 else None


def should_export_object(obj, include_factory_prototypes=False, include_hidden=False):
    if obj.library is not None:
        return False
    if obj.type not in {"MESH", "CURVE", "EMPTY"}:
        return False
    if not include_hidden and (obj.hide_viewport or obj.hide_render):
        return False
    if not include_factory_prototypes and any(marker in obj.name for marker in FACTORY_PROTOTYPE_MARKERS):
        return False
    return obj.name.startswith("urban:")


def object_category(obj):
    token = urban_token(obj.name)
    if token in URBAN_SURFACE_TOKENS:
        return "surfaces"
    if token in URBAN_BUILDING_TOKENS:
        return "buildings"
    if token in URBAN_VEGETATION_TOKENS:
        return "vegetation"
    if token in URBAN_STREET_TOKENS:
        return "street_assets"
    if token in URBAN_DYNAMIC_TOKENS:
        return token + "s" if not token.endswith("s") else token
    if obj.name.startswith("urban_detail:"):
        return "urban_details"
    return "urban_misc"


def group_objects(objects, vegetation_mode, max_objects_per_file):
    groups = {}
    for obj in objects:
        category = object_category(obj)
        if category == "vegetation" and vegetation_mode == "object":
            key = f"vegetation/{safe_name(obj.name)}"
        else:
            key = category
        groups.setdefault(key, []).append(obj)

    units = []
    for key, group in sorted(groups.items()):
        if len(group) <= max_objects_per_file:
            units.append(ExportUnit(safe_name(key), group, key.split("/", 1)[0]))
            continue
        for idx in range(0, len(group), max_objects_per_file):
            chunk = group[idx : idx + max_objects_per_file]
            units.append(ExportUnit(f"{safe_name(key)}_{idx // max_objects_per_file:03d}", chunk, key.split("/", 1)[0]))
    return units


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0] if objects else None


_TREE_TRUNK_PATTERN = re.compile(r"^urban:nature_tree:\d+$")
_FACTORY_PROTO_PATTERN = re.compile(r"^GenericTreeFactory\(")


def _collect_tree_factory_unit(scene_objects, collection):
    """Return (ExportUnit | None, temp_objects) for the merged factory-tree unit.

    Finds every GenericTreeFactory prototype in the scene and creates one
    linked duplicate (shared mesh data) per trunk position.  All copies are
    bundled into a single ExportUnit so the FBX exporter writes one shared
    Geometry node (≈200 MB) instead of N×200 MB separate files.
    """
    factory_proto = next(
        (
            obj
            for obj in scene_objects
            if _FACTORY_PROTO_PATTERN.match(obj.name) and obj.type == "MESH"
        ),
        None,
    )
    if factory_proto is None:
        return None, []

    trunk_matrices = [
        obj.matrix_world.copy()
        for obj in scene_objects
        if _TREE_TRUNK_PATTERN.match(obj.name)
    ]
    if not trunk_matrices:
        return None, []

    temp_objects = []
    for i, mat in enumerate(trunk_matrices):
        linked = bpy.data.objects.new(f"tree_factory_inst_{i}", factory_proto.data)
        linked.matrix_world = mat
        collection.objects.link(linked)
        temp_objects.append(linked)

    unit = ExportUnit("vegetation_tree_factory", temp_objects, "vegetation_tree_factory")
    logger.info(
        "Factory-tree unit: %d instances of %s at trunk positions",
        len(temp_objects),
        factory_proto.name,
    )
    return unit, temp_objects


def _is_tree_unit(unit):
    """Return True for trunk/branch units that are superseded by the factory unit."""
    return (
        "nature_tree" in unit.name
        and "tree_pit_stone" not in unit.name
        and unit.category == "vegetation"
    )


def _realize_nodes_modifiers(objects):
    """Convert Geometry Nodes instance outputs into real mesh data.

    Blender's FBX exporter does not capture GN instances (e.g. leaf cards
    scattered along branch geometry) because they live only in the depsgraph,
    not in the object's mesh data block.  We first insert a Realize Instances
    node at the end of each NODES modifier so that instances become actual
    geometry (with their own material slots), then call convert() to bake them.
    """
    needs_convert = [
        obj for obj in objects
        if obj.type == "MESH" and any(m.type == "NODES" for m in obj.modifiers)
    ]
    if not needs_convert:
        return

    bpy.ops.object.select_all(action="DESELECT")
    for obj in needs_convert:
        was_hidden = obj.hide_viewport
        obj.hide_viewport = False
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.convert(target="MESH")
        except Exception as exc:
            logger.warning("GN realize failed for %s: %s", obj.name, exc)
        finally:
            obj.hide_viewport = was_hidden

    bpy.ops.object.select_all(action="DESELECT")


def export_unit(unit, model_dir):
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"{unit.name}.fbx"
    _realize_nodes_modifiers(unit.objects)
    select_only(unit.objects)
    bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        object_types={"MESH", "EMPTY", "OTHER"},
        path_mode="COPY",
        embed_textures=True,
        use_mesh_modifiers=True,
        bake_space_transform=False,
        apply_unit_scale=True,
        use_triangles=True,
        add_leaf_bones=False,
    )
    return path


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


UNITY_EDITOR_SCRIPT = r'''using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace InfinigenUnity
{
    [Serializable] public class ComponentEntry
    {
        public string name;
        public string category;
        public string assetPath;
        public int objectCount;
    }

    [Serializable] public class SceneManifest
    {
        public string sourceBlend;
        public string generatedAt;
        public List<ComponentEntry> components;
    }

	    public static class InfinigenUrbanSceneBuilder
	    {
	        const string ManifestPath = "Assets/InfinigenUrban/manifest.json";
	        const string ScenePath = "Assets/InfinigenUrban/Scenes/UrbanBlock.unity";
	        const string MaterialDir = "Assets/InfinigenUrban/Materials";

        [MenuItem("Infinigen/Build Urban Scene")]
        public static void BuildSceneFromManifest()
        {
            AssetDatabase.Refresh();
            var manifest = JsonUtility.FromJson<SceneManifest>(File.ReadAllText(ManifestPath));
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var root = new GameObject("InfinigenUrbanRoot");
            foreach (var entry in manifest.components)
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(entry.assetPath);
                if (prefab == null)
                {
                    Debug.LogWarning("Missing imported FBX: " + entry.assetPath);
                    continue;
                }
	                var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
	                instance.name = entry.name;
	                instance.transform.SetParent(root.transform, false);
	                ApplyUrbanMaterialOverrides(instance, entry);
	            }

	            var light = new GameObject("Sun").AddComponent<Light>();
	            light.type = LightType.Directional;
	            light.intensity = 1.35f;
	            light.transform.rotation = Quaternion.Euler(50, -35, 0);
	            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
	            RenderSettings.ambientLight = new Color(0.50f, 0.55f, 0.60f);
	            RenderSettings.fog = false;

	            var cameraGo = new GameObject("RenderCamera");
	            var camera = cameraGo.AddComponent<Camera>();
	            camera.clearFlags = CameraClearFlags.SolidColor;
	            camera.backgroundColor = new Color(0.70f, 0.77f, 0.84f);
            camera.fieldOfView = 34f;
            camera.nearClipPlane = 0.05f;
            camera.farClipPlane = 500f;
            PlaceOrbitCamera(camera, 0f, 95f, 26f, new Vector3(0, 5.8f, 0));

            Directory.CreateDirectory("Assets/InfinigenUrban/Scenes");
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
            Debug.Log("Built scene: " + ScenePath);
        }

        [MenuItem("Infinigen/Render Orbit Frames")]
        public static void RenderOrbitFrames()
        {
            if (!File.Exists(ScenePath)) BuildSceneFromManifest();
            EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var camera = GameObject.Find("RenderCamera").GetComponent<Camera>();
            var outDir = Path.GetFullPath("Renders/InfinigenUrban/orbit_frames");
            Directory.CreateDirectory(outDir);

            int width = GetIntEnv("UNITY_RENDER_WIDTH", 1920);
            int height = GetIntEnv("UNITY_RENDER_HEIGHT", 1080);
            int frames = GetIntEnv("UNITY_RENDER_FRAMES", 120);
	            float radius = GetFloatEnv("UNITY_ORBIT_RADIUS", 95f);
	            float z = GetFloatEnv("UNITY_ORBIT_HEIGHT", 26f);
	            var target = new Vector3(
	                GetFloatEnv("UNITY_ORBIT_TARGET_X", 0f),
	                GetFloatEnv("UNITY_ORBIT_TARGET_Y", 5.8f),
	                GetFloatEnv("UNITY_ORBIT_TARGET_Z", 0f));
	            bool fixedCamera = HasEnv("UNITY_CAMERA_X") && HasEnv("UNITY_CAMERA_Y") && HasEnv("UNITY_CAMERA_Z");
	            var fixedPosition = new Vector3(
	                GetFloatEnv("UNITY_CAMERA_X", 0f),
	                GetFloatEnv("UNITY_CAMERA_Y", 0f),
	                GetFloatEnv("UNITY_CAMERA_Z", 0f));

	            var rt = new RenderTexture(width, height, 24);
	            var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
	            camera.targetTexture = rt;
	            for (int i = 0; i < frames; i++)
	            {
	                if (fixedCamera) PlaceFixedCamera(camera, fixedPosition, target);
	                else PlaceOrbitCamera(camera, (float)i / Math.Max(1, frames), radius, z, target);
	                camera.Render();
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();
                File.WriteAllBytes(Path.Combine(outDir, $"frame_{i:D04}.png"), tex.EncodeToPNG());
            }
            camera.targetTexture = null;
            RenderTexture.active = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
	            Debug.Log("Wrote orbit frames to " + outDir);
	        }

	        static void ApplyUrbanMaterialOverrides(GameObject instance, ComponentEntry entry)
	        {
	            if (entry.category != "vegetation" && entry.category != "surfaces") return;
	            string entryName = entry.name.ToLowerInvariant();
	            foreach (var renderer in instance.GetComponentsInChildren<Renderer>(true))
	            {
	                var source = renderer.sharedMaterials;
	                var updated = new Material[source.Length];
	                for (int i = 0; i < source.Length; i++)
	                {
	                    string materialName = source[i] != null ? source[i].name.ToLowerInvariant() : "";
	                    string probe = entryName + " " + renderer.name.ToLowerInvariant() + " " + materialName;
	                    updated[i] = ResolveUrbanMaterial(probe, entry.category, i);
	                }
	                renderer.sharedMaterials = updated;
	            }
	        }

	        static Material ResolveUrbanMaterial(string probe, string category, int slot)
	        {
	            if (probe.Contains("tree_pit_stone")) return GetMaterial("urban_unity_tree_pit_stone", new Color(0.45f, 0.43f, 0.38f), 0.95f, 0.0f);
	            if (probe.Contains("grass_tuft") || probe.Contains("grass_blades") || probe.Contains("grass_seed")) return GetMaterial("urban_unity_grass", new Color(0.15f, 0.38f, 0.12f), 0.92f, 0.0f);
	            if (probe.Contains("flowerplant") || probe.Contains("bush") || probe.Contains("shrub")) return GetMaterial("urban_unity_shrub_leaf", new Color(0.06f, 0.28f, 0.10f), 0.93f, 0.0f);
	            if (probe.Contains("_tree.") || probe.Contains("_tree_004") || probe.Contains("_tree_012") || probe.Contains("_tree_020") || probe.Contains("leaf") || probe.Contains("birch") || probe.Contains("twig")) return GetMaterial("urban_unity_tree_leaf", new Color(0.025f, 0.24f, 0.075f), 0.98f, 0.0f);
	            // vegetation_tree_factory: full GenericTreeFactory mesh with 5 material slots.
	            // Slot 0 = shader_random_bark_mat (bark) → brown; slots 1-4 = shader_material.* (leaf LODs) → green.
	            if (category == "vegetation_tree_factory") {
	                if (probe.Contains("bark"))
	                    return GetMaterial("urban_unity_tree_bark", new Color(0.18f, 0.105f, 0.045f), 0.90f, 0.0f);
	                return GetMaterial("urban_unity_tree_leaf", new Color(0.025f, 0.24f, 0.075f), 0.98f, 0.0f);
	            }
	            // nature_tree trunk mesh: apply green foliage colour (fallback for scenes without factory export).
	            if (probe.Contains("nature_tree")) return GetMaterial("urban_unity_tree_foliage", new Color(0.08f, 0.28f, 0.06f), 0.95f, 0.0f);
	            if (probe.Contains("bark") || probe.Contains("trunk") || probe.Contains("branch")) return GetMaterial("urban_unity_tree_bark", new Color(0.18f, 0.105f, 0.045f), 0.90f, 0.0f);
	            if (category == "surfaces" && probe.Contains("lawn")) return GetMaterial("urban_unity_lawn", new Color(0.34f, 0.62f, 0.36f), 0.88f, 0.0f);
	            if (category == "surfaces" && (probe.Contains("road") || probe.Contains("asphalt"))) return GetMaterial("urban_unity_asphalt", new Color(0.22f, 0.22f, 0.21f), 0.95f, 0.0f);
	            if (category == "surfaces" && (probe.Contains("sidewalk") || probe.Contains("curb"))) return GetMaterial("urban_unity_concrete", new Color(0.56f, 0.56f, 0.52f), 0.92f, 0.0f);
	            return GetMaterial("urban_unity_default_" + slot, new Color(0.62f, 0.62f, 0.58f), 0.90f, 0.0f);
	        }

	        static Material GetMaterial(string name, Color color, float roughness, float metallic)
	        {
	            Directory.CreateDirectory(MaterialDir);
	            string path = MaterialDir + "/" + name + ".mat";
	            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
	            if (material == null)
	            {
	                var shader = Shader.Find("Universal Render Pipeline/Lit");
	                if (shader == null) shader = Shader.Find("Standard");
	                material = new Material(shader);
	                AssetDatabase.CreateAsset(material, path);
	            }
	            SetMaterialColor(material, color);
	            SetMaterialFloat(material, "_Smoothness", Mathf.Clamp01(1f - roughness));
	            SetMaterialFloat(material, "_Metallic", metallic);
	            material.doubleSidedGI = true;
	            return material;
	        }

	        static void SetMaterialColor(Material material, Color color)
	        {
	            if (material.HasProperty("_BaseColor")) material.SetColor("_BaseColor", color);
	            if (material.HasProperty("_Color")) material.SetColor("_Color", color);
	        }

	        static void SetMaterialFloat(Material material, string property, float value)
	        {
	            if (material.HasProperty(property)) material.SetFloat(property, value);
	        }

	        static void PlaceOrbitCamera(Camera camera, float t, float radius, float z, Vector3 target)
	        {
	            float angle = t * Mathf.PI * 2f + Mathf.PI * 0.18f;
	            var pos = new Vector3(Mathf.Cos(angle) * radius, z, Mathf.Sin(angle) * radius);
	            camera.transform.position = pos;
	            camera.transform.LookAt(target, Vector3.up);
	        }

	        static void PlaceFixedCamera(Camera camera, Vector3 position, Vector3 target)
	        {
	            camera.transform.position = position;
	            camera.transform.LookAt(target, Vector3.up);
	        }

        static int GetIntEnv(string name, int fallback)
        {
            int value;
            return int.TryParse(Environment.GetEnvironmentVariable(name), out value) ? value : fallback;
        }

	        static float GetFloatEnv(string name, float fallback)
	        {
	            float value;
	            return float.TryParse(Environment.GetEnvironmentVariable(name), out value) ? value : fallback;
	        }

	        static bool HasEnv(string name)
	        {
	            return !string.IsNullOrEmpty(Environment.GetEnvironmentVariable(name));
	        }
    }
}
'''


def write_unity_project(output_dir, manifest, project_name):
    project_dir = output_dir / project_name
    assets_dir = project_dir / "Assets" / "InfinigenUrban"
    models_dir = assets_dir / "Models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "Scenes").mkdir(parents=True, exist_ok=True)
    (project_dir / "Assets" / "Editor").mkdir(parents=True, exist_ok=True)
    (project_dir / "ProjectSettings").mkdir(parents=True, exist_ok=True)

    write_text(project_dir / "Assets" / "Editor" / "InfinigenUrbanSceneBuilder.cs", UNITY_EDITOR_SCRIPT)
    write_text(
        project_dir / "ProjectSettings" / "ProjectVersion.txt",
        "m_EditorVersion: 2022.3.0f1\nm_EditorVersionWithRevision: 2022.3.0f1\n",
    )
    write_text(assets_dir / "manifest.json", json.dumps(manifest, indent=2))
    return project_dir, models_dir


def copy_models_to_unity(models, unity_models_dir, export_root):
    entries = []
    for item in models:
        src = item["file_abs"]
        dst = unity_models_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        entries.append(
            {
                "name": item["name"],
                "category": item["category"],
                "assetPath": f"Assets/InfinigenUrban/Models/{dst.name}",
                "objectCount": item["object_count"],
            }
        )
    return entries


def main(args):
    output_dir = Path(args.output_dir).resolve()
    export_root = output_dir / "fbx_components"
    export_root.mkdir(parents=True, exist_ok=True)

    if args.input_blend:
        logger.info("Opening %s", args.input_blend)
        bpy.ops.wm.open_mainfile(filepath=str(Path(args.input_blend).resolve()))

    objects = [
        obj
        for obj in bpy.context.scene.objects
        if should_export_object(
            obj,
            include_factory_prototypes=args.include_factory_prototypes,
            include_hidden=args.include_hidden,
        )
    ]
    units = group_objects(objects, args.vegetation_mode, args.max_objects_per_file)

    # Replace per-tree trunk units with a single factory unit that contains
    # the full GenericTreeFactory mesh (bark + leaf material slots) instanced
    # at every trunk position.  All instances share one mesh data block so the
    # FBX exporter writes a single shared Geometry node.
    factory_unit, temp_tree_objects = _collect_tree_factory_unit(
        bpy.context.scene.objects, bpy.context.collection
    )
    if factory_unit is not None:
        units = [u for u in units if not _is_tree_unit(u)] + [factory_unit]

    logger.info("Exporting %d objects as %d FBX components", len(objects), len(units))

    models = []
    for idx, unit in enumerate(units, start=1):
        logger.info("[%d/%d] Exporting %s (%d objects)", idx, len(units), unit.name, len(unit.objects))
        path = export_unit(unit, export_root)
        models.append(
            {
                "name": unit.name,
                "category": unit.category,
                "file": relpath(path, output_dir),
                "file_abs": path,
                "object_count": len(unit.objects),
            }
        )

    # Remove temporary factory instance objects before writing the scene state.
    for obj in temp_tree_objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    manifest = {
        "sourceBlend": str(Path(args.input_blend).resolve()) if args.input_blend else bpy.data.filepath,
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "components": [],
    }
    project_dir, unity_models_dir = write_unity_project(output_dir, manifest, args.project_name)
    manifest["components"] = copy_models_to_unity(models, unity_models_dir, output_dir)
    write_text(project_dir / "Assets" / "InfinigenUrban" / "manifest.json", json.dumps(manifest, indent=2))

    standalone_manifest = dict(manifest)
    standalone_manifest["components"] = [
        {k: v for k, v in item.items() if k != "assetPath"} | {"file": relpath(models[idx]["file_abs"], output_dir)}
        for idx, item in enumerate(manifest["components"])
    ]
    write_text(output_dir / "unity_export_manifest.json", json.dumps(standalone_manifest, indent=2))
    write_text(
        output_dir / "README_Unity.md",
        f"""# Unity export

Generated from:

`{manifest['sourceBlend']}`

Open this Unity project:

`{project_dir}`

Editor menu:

- `Infinigen > Build Urban Scene`
- `Infinigen > Render Orbit Frames`

Batch example:

```bash
Unity -batchmode -quit -projectPath "{project_dir}" -executeMethod InfinigenUnity.InfinigenUrbanSceneBuilder.BuildSceneFromManifest
UNITY_RENDER_WIDTH=1920 UNITY_RENDER_HEIGHT=1080 UNITY_RENDER_FRAMES=120 \\
Unity -batchmode -quit -projectPath "{project_dir}" -executeMethod InfinigenUnity.InfinigenUrbanSceneBuilder.RenderOrbitFrames
ffmpeg -y -framerate 24 -i "{project_dir}/Renders/InfinigenUrban/orbit_frames/frame_%04d.png" -c:v libx264 -pix_fmt yuv420p "{output_dir}/orbit_preview.mp4"
```
""",
    )
    logger.info("Wrote Unity project: %s", project_dir)
    logger.info("Wrote manifest: %s", output_dir / "unity_export_manifest.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-blend", type=Path, default=None)
    parser.add_argument("--output", dest="output_dir", type=Path, default=None)
    parser.add_argument("--project-name", default="UnityUrbanProject")
    parser.add_argument("--vegetation-mode", choices=["object", "group"], default="object")
    parser.add_argument("--max-objects-per-file", type=int, default=250)
    parser.add_argument("--include-factory-prototypes", action="store_true")
    parser.add_argument("--include-hidden", action="store_true")
    args = parse_blender_args(parser)
    if args.output_dir is None:
        parser.error("--output is required")
    logging.basicConfig(
        format="[%(asctime)s.%(msecs)03d] [%(module)s] [%(levelname)s] | %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )
    main(args)
