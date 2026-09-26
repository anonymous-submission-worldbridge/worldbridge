"""Render the existing library scene with low, vertically corrected cameras."""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'urban_v3_library4.blend'
# name, title, position, horizontal target, focal length, framing height, resolution
VIEWS = [
    ('01_pair_front_panorama', 'Both libraries, front panorama', (0, -180, 5), (-3, 2), 43, 18.7, (3200, 870)),
    ('02_pair_west_oblique', 'Both libraries, southwest panorama', (-92, -185, 7), (-3, 1), 46, 19.5, (3200, 900)),
    ('03_pair_east_oblique', 'Both libraries, southeast panorama', (98, -185, 6), (-3, 1), 46, 19.8, (3200, 900)),
    ('04_modern_southwest', 'White library, southwest exterior', (-99, -104, 5), (-38, 3), 49, 17.3, (2800, 1420)),
    ('05_modern_front', 'White library, front facade and cantilevered roof', (-42, -111, 3), (-38, 2), 49, 17, (2800, 1300)),
    ('06_red_southeast', 'Red library, southeast exterior', (95, -99, 4), (39, 3), 52, 17.5, (2800, 1560)),
    ('07_red_front', 'Red library, front facade and layered porch', (39, -105, 3), (39, 2), 57, 17.4, (2600, 1545)),
    ('08_red_southwest', 'Red library, southwest exterior', (1, -90, 4), (39, 3), 49, 17.3, (2800, 1720)),
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--preview', action='store_true')
    p.add_argument('--only', default='')
    p.add_argument('--gpu', type=int, default=7)
    p.add_argument('--samples', type=int, default=128)
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    dest = OUT / '_preview' if a.preview else OUT
    dest.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    devices = [d for d in prefs.devices if d.type == 'OPTIX']
    for d in prefs.devices:
        d.use = d == devices[a.gpu]
    print('GPU', devices[a.gpu].name, devices[a.gpu].id, flush=True)
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 16 if a.preview else a.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.05 if a.preview else 0.012
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 6
    scene.render.use_persistent_data = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = -1.15
    records = []
    selected = a.only.split(',') if a.only else []
    for name, title, position, target, lens, center_z, resolution in VIEWS:
        data = bpy.data.cameras.new('renders2:' + name)
        cam = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(cam)
        cam.location = position
        direction = Vector((target[0], target[1], position[2])) - cam.location
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        data.lens = lens
        data.sensor_width = 36
        data.sensor_fit = 'HORIZONTAL'
        data.shift_y = (center_z - position[2]) * lens / (direction.length * 36)
        data.clip_end = 2000
        data.dof.use_dof = False
        scene.camera = cam
        scene.render.resolution_x, scene.render.resolution_y = ((960, round(960*resolution[1]/resolution[0])) if a.preview else resolution)
        record = dict(file=name+'.png', title=title, position=position, target_xy=target,
                      lens_mm=lens, shift_y=data.shift_y, resolution=resolution)
        records.append(record)
        if selected and name[:2] not in selected:
            continue
        scene.render.filepath = str(dest / record['file'])
        print('RENDER_START', name, flush=True)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        record['seconds'] = round(time.monotonic()-start, 2)
        (dest / (name+'.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print('RENDER_DONE', name, record['seconds'], flush=True)
    manifest = dict(source=str(SOURCE), geometry_unchanged=True, lighting_unchanged=True,
                    exposure=scene.view_settings.exposure, engine='CYCLES', samples=scene.cycles.samples,
                    preview=a.preview, views=records)
    (dest / ('manifest_'+(a.only.replace(',', '_') or 'all')+'.json')).write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
