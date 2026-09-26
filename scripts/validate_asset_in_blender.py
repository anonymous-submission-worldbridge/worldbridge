"""Run with Blender --background --factory-startup --disable-autoexec FILE --python SCRIPT.

Pass -- REPORT.json after Blender arguments. This only inspects the loaded file;
it never saves the scene or executes any embedded scene script.
"""
from pathlib import Path
import json
import sys
import bpy


def main():
    output = Path(sys.argv[sys.argv.index("--") + 1])
    missing = []
    external = []
    root = Path(__file__).resolve().parents[1]
    for category in ("libraries", "images", "fonts", "sounds", "movieclips", "volumes"):
        for item in getattr(bpy.data, category):
            value = getattr(item, "filepath", "")
            if not value or value == "<builtin>":
                continue
            if getattr(item, "packed_file", None) or getattr(
                item, "packed_files", None
            ):
                continue
            if category == "images" and item.source in ("GENERATED", "VIEWER"):
                continue
            path = Path(bpy.path.abspath(value, library=getattr(item, "library", None)))
            if not path.resolve().is_relative_to(root):
                from urllib.parse import quote

                external.append(
                    {"kind": category, "path_uri": quote(str(path), safe="/+_.-")}
                )
            if not path.is_file():
                from urllib.parse import quote

                missing.append(
                    {"kind": category, "path_uri": quote(str(path), safe="/+_.-")}
                )
    result = {
        "file": bpy.data.filepath,
        "blender_version": bpy.app.version_string,
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "libraries": len(bpy.data.libraries),
        "missing_dependencies": missing,
        "references_outside_worldbridge": external,
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    if not result["objects"] or not result["meshes"]:
        raise RuntimeError("Expected an authored scene with mesh geometry")


if __name__ == "__main__":
    main()
