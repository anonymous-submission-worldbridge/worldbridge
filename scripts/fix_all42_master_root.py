import bpy

root = bpy.data.collections.get("C2W_MASTERS") or bpy.data.collections.new(
    "C2W_MASTERS"
)
root["c2w_role"] = "master_root"
root.use_fake_user = True
prototypes = sorted(
    [
        c
        for c in bpy.data.collections
        if c.name.startswith("All39Fast5_TreePrototype_")
        or c.name.startswith("All39Fast5_ShrubPrototype_")
    ],
    key=lambda c: c.name,
)
for collection in prototypes:
    if collection.name not in root.children:
        root.children.link(collection)
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
print(
    f"ALL42_MASTER_ROOT_FIXED prototypes={len(prototypes)} fake_user={root.use_fake_user}"
)
