import bpy, json, time, sys, os
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.render.threads_mode='FIXED'
scene.render.threads=24
scene.cycles.device='GPU'
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='OPTIX'
prefs.get_devices()
for d in prefs.devices:
    d.use=d.type=='OPTIX' and ('57:00' in d.id or os.environ.get('CUDA_VISIBLE_DEVICES')=='3')
print('DEVICES',[(d.name,d.id,d.use) for d in prefs.devices],flush=True)
scene.render.use_persistent_data=True
scene.cycles.use_denoising=True
scene.cycles.use_adaptive_sampling=True
scene.cycles.adaptive_threshold=.04
scene.cycles.max_bounces=8
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
scene.render.film_transparent=False
scene.view_settings.exposure=0.0
cam=scene.camera
cam.animation_data_clear()
cam.data.dof.use_dof=False
cam.data.sensor_width=36
cam.data.clip_end=1000
cam.data.clip_start=.05
print('LOADED',len(bpy.data.meshes),sum(len(m.polygons) for m in bpy.data.meshes),flush=True)
config=Path(sys.argv[sys.argv.index('--')+1])
while True:
    if config.exists():
        task=json.loads(config.read_text())
        if task.get('stop'): break
        records=[]
        for v in task['views']:
            cam.location=v['camera']
            cam.rotation_euler=(Vector(v['target'])-cam.location).to_track_quat('-Z','Y').to_euler()
            cam.data.lens=v['lens']
            cam.data.shift_y=v.get('shift_y',0)
            scene.render.resolution_x=task.get('width',960)
            scene.render.resolution_y=task.get('height',640)
            scene.render.resolution_percentage=100
            scene.cycles.samples=task.get('samples',24)
            path=OUT/task.get('folder','_work')/(v['name']+'.png')
            path.parent.mkdir(exist_ok=True,parents=True)
            scene.render.filepath=str(path)
            bpy.context.view_layer.update()
            print('RENDER_START',v['name'],flush=True)
            started=time.time()
            bpy.ops.render.render(write_still=True)
            records.append(dict(v,filename=str(path.relative_to(OUT)),seconds=round(time.time()-started,2)))
            (OUT/'_work'/('manifest_'+task['id']+'.json')).write_text(json.dumps(records,indent=2))
        (OUT/'_work'/('done_'+task['id'])).write_text('complete')
        if task.get('exit') or '--once' in sys.argv: break
        config.unlink()
    time.sleep(2)
