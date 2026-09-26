# Unity Urban Export Workflow

This workflow avoids opening or rendering very large urban `.blend` files directly in Blender.
It exports visible urban components to Unity-native FBX files, writes a manifest, and creates a
minimal Unity project with editor scripts for scene assembly and orbit-frame rendering.

## Export an Existing Blend

```bash
cd ./infinigen

blender --background \
  outputs/urban_block_10/scene.blend \
  --python infinigen/tools/unity/export_blend_to_unity.py -- \
  --output outputs/urban_block_10/unity_export \
  --project-name UnityUrbanBlock10 \
  --vegetation-mode object \
  --max-objects-per-file 250
```

The exporter skips hidden objects, cameras, lights, and generated factory prototypes by default.
Visible urban objects are grouped into FBX components. Vegetation is exported object-by-object so
trees, shrubs, and small plants remain independently manageable inside Unity.

## Open and Build in Unity

Open this generated project in Unity:

```text
outputs/urban_block_10/unity_export/UnityUrbanBlock10
```

Then run:

```text
Infinigen > Build Urban Scene
```

This imports the FBX components listed in:

```text
Assets/InfinigenUrban/manifest.json
```

and saves:

```text
Assets/InfinigenUrban/Scenes/UrbanBlock.unity
```

## Render Orbit Frames in Unity

From the Unity editor menu:

```text
Infinigen > Render Orbit Frames
```

Or in batch mode, if `Unity` points to a Unity Editor executable:

```bash
Unity -batchmode -quit \
  -projectPath ./infinigen/outputs/urban_block_10/unity_export/UnityUrbanBlock10 \
  -executeMethod InfinigenUnity.InfinigenUrbanSceneBuilder.BuildSceneFromManifest

UNITY_RENDER_WIDTH=1920 UNITY_RENDER_HEIGHT=1080 UNITY_RENDER_FRAMES=120 \
Unity -batchmode -quit \
  -projectPath ./infinigen/outputs/urban_block_10/unity_export/UnityUrbanBlock10 \
  -executeMethod InfinigenUnity.InfinigenUrbanSceneBuilder.RenderOrbitFrames
```

Convert frames to video:

```bash
ffmpeg -y -framerate 24 \
  -i ./infinigen/outputs/urban_block_10/unity_export/UnityUrbanBlock10/Renders/InfinigenUrban/orbit_frames/frame_%04d.png \
  -c:v libx264 -pix_fmt yuv420p \
  ./infinigen/outputs/urban_block_10/unity_export/orbit_preview.mp4
```

## Generate Output Modes

`generate_urban_detailed.py` supports three export formats. Use one root `--output` directory.
Unity files are written to `<output>/unity_export`.

### 1. Blend Only

```bash
cd ./infinigen

blender --background \
  --python infinigen_examples/generate_urban_detailed.py -- \
  --output outputs/urban_v2_0 \
  --export-format blend \
  --seed 2026
```

This writes:

```text
outputs/urban_v2_0/scene.blend
```

### 2. Unity Files Only

```bash
cd ./infinigen

blender --background \
  --python infinigen_examples/generate_urban_detailed.py -- \
  --output outputs/urban_v2_0 \
  --export-format unity \
  --unity-project-name UnityUrbanV2 \
  --seed 2026
```

This generates the scene in Blender memory and exports Unity-ready FBX components without saving
`scene.blend`.

### 3. Blend Then Unity

```bash
cd ./infinigen

blender --background \
  --python infinigen_examples/generate_urban_detailed.py -- \
  --output outputs/urban_v2_0 \
  --export-format blend+unity \
  --seed 2026 \
  --unity-project-name UnityUrbanV2
```

This saves `scene.blend`, then reopens/converts that saved blend into Unity-ready files.

Use Unity export only after the Blender-side asset generation is producing the desired geometry.
Unity can render and preview the exported scene more comfortably than Blender, but it cannot
magically fix extremely dense source geometry; the exporter keeps components split so Unity can cull,
disable, or replace parts more easily.
