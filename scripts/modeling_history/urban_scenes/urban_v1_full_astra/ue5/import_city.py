"""UE5 editor Python: run only inside the supplied, compiled AstraCity project.

Uses legacy FbxFactory explicitly; checks scale/axes and collision before assembly.
The importer refuses to overwrite an existing city map. Delete/rename that map
manually only if you intend to replace it, then rerun.
"""
import json,math,traceback
from pathlib import Path
import unreal as u

ROOT=Path(__file__).resolve().parent
PACKAGE='/Game/AstraCity'
REPORT={'status':'STARTED','engine_version':u.SystemLibrary.get_engine_version(),'checks':[]}
TOOLS=u.AssetToolsHelpers.get_asset_tools()
ASSETS=u.EditorAssetLibrary
ACTORS=u.get_editor_subsystem(u.EditorActorSubsystem)
LEVELS=u.get_editor_subsystem(u.LevelEditorSubsystem)
MESHES=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)

def import_mesh(rec):
    target=f'{PACKAGE}/Meshes/{rec["id"]}'
    if not ASSETS.does_asset_exist(target):
        options=u.FbxImportUI()
        options.set_editor_property('automated_import_should_detect_type',False)
        options.set_editor_property('import_mesh',True)
        options.set_editor_property('import_as_skeletal',False)
        options.set_editor_property('mesh_type_to_import',u.FBXImportType.FBXIT_STATIC_MESH)
        options.set_editor_property('import_materials',False)
        options.set_editor_property('import_textures',False)
        data=options.static_mesh_import_data
        for key,value in {'combine_meshes':True,'auto_generate_collision':False,'one_convex_hull_per_ucx':True,
                           'convert_scene':False,'convert_scene_unit':False,'force_front_x_axis':False,
                           'transform_vertex_to_absolute':True,'generate_lightmap_u_vs':False,
                           'reorder_material_to_fbx_order':True}.items():
            data.set_editor_property(key,value)
        task=u.AssetImportTask();task.filename=str(ROOT/rec['file']);task.destination_path=PACKAGE+'/Meshes'
        task.destination_name=rec['id'];task.automated=True;task.save=True;task.replace_existing=False
        task.factory=u.FbxFactory();task.options=options
        TOOLS.import_asset_tasks([task])
    mesh=u.load_asset(target)
    if not isinstance(mesh,u.StaticMesh):raise RuntimeError('Static mesh import failed: '+target)
    if MESHES.get_number_materials(mesh)!=len(rec['materials']):raise RuntimeError('FBX material-slot count mismatch: '+rec['id'])
    # Refuse scene assembly with a wrong coordinate/scale contract.
    bounds=mesh.get_bounding_box();expected=rec['expected_bounds_cm']
    actual=[[bounds.min.x,bounds.min.y,bounds.min.z],[bounds.max.x,bounds.max.y,bounds.max.z]]
    deviation=max(abs(actual[i][j]-expected[i][j]) for i in range(2) for j in range(3))
    if deviation>max(.5,max(abs(v) for p in expected for v in p)*.0001):
        raise RuntimeError(f'FBX axis/scale mismatch {rec["id"]}: actual={actual}, expected={expected}')
    if rec['collision_hulls']:
        count=MESHES.get_convex_collision_count(mesh)
        if count!=rec['collision_hulls']:raise RuntimeError(f'UCX mismatch {rec["id"]}: {count} != {rec["collision_hulls"]}')
    if rec['collision_mode']=='complex_as_simple':
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    if rec['nanite_candidate']:
        settings=mesh.get_editor_property('nanite_settings');settings.set_editor_property('enabled',True)
        MESHES.set_nanite_settings(mesh,settings,True)
    ASSETS.save_loaded_asset(mesh)
    REPORT['checks'].append({'asset':rec['id'],'bounds_max_error_cm':deviation,'expected_collision_hulls':rec['collision_hulls']})
    return mesh

def scalar(mat,value,prop):
    node=u.MaterialEditingLibrary.create_material_expression(mat,u.MaterialExpressionConstant)
    node.set_editor_property('r',float(value));u.MaterialEditingLibrary.connect_material_property(node,'',prop)

def texture(path,name,linear=False):
    target=f'{PACKAGE}/Textures/{name}'
    if not ASSETS.does_asset_exist(target):
        task=u.AssetImportTask();task.filename=str(path);task.destination_path=PACKAGE+'/Textures';task.destination_name=name
        task.automated=True;task.save=True;TOOLS.import_asset_tasks([task])
    tex=u.load_asset(target)
    if not tex:raise RuntimeError('Texture import failed: '+str(path))
    tex.set_editor_property('srgb',not linear);ASSETS.save_loaded_asset(tex);return tex

def material(rec):
    path=f'{PACKAGE}/Materials/{rec["id"]}'
    if ASSETS.does_asset_exist(path):return u.load_asset(path)
    mat=TOOLS.create_asset(rec['id'],PACKAGE+'/Materials',u.Material,u.MaterialFactoryNew())
    mat.set_editor_property('two_sided',rec.get('two_sided',False))
    for suffix,prop,linear in [('BaseColor',u.MaterialProperty.MP_BASE_COLOR,False),('Roughness',u.MaterialProperty.MP_ROUGHNESS,True)]:
        file=ROOT/'Textures'/f'{rec["id"]}_{suffix}.png'
        if not file.exists():raise RuntimeError('Required baked texture missing: '+str(file))
        node=u.MaterialEditingLibrary.create_material_expression(mat,u.MaterialExpressionTextureSample)
        node.set_editor_property('texture',texture(file,rec['id']+'_'+suffix,linear))
        node.set_editor_property('sampler_type',u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR if linear else u.MaterialSamplerType.SAMPLERTYPE_COLOR)
        u.MaterialEditingLibrary.connect_material_property(node,'RGB' if not linear else 'R',prop)
    scalar(mat,rec['metallic'],u.MaterialProperty.MP_METALLIC)
    if rec['opacity']<.99:
        mat.set_editor_property('blend_mode',u.BlendMode.BLEND_TRANSLUCENT)
        scalar(mat,rec['opacity'],u.MaterialProperty.MP_OPACITY)
    u.MaterialEditingLibrary.recompile_material(mat);ASSETS.save_loaded_asset(mat);return mat

def main():
    scene=json.loads((ROOT/'scene_manifest.json').read_text())
    if ASSETS.does_asset_exist(PACKAGE+'/Maps/AstraCity'):
        raise RuntimeError('City map already exists; refusing to overwrite user work.')
    door_class=u.load_class(None,'/Script/AstraCity.AstraDoor')
    game_class=u.load_class(None,'/Script/AstraCity.AstraGameMode')
    if not door_class or not game_class:raise RuntimeError('Compile the supplied AstraCity C++ module before running this importer.')
    first=scene['meshes'][0]
    if first['role']!='calibration':raise RuntimeError('Calibration must precede all city assets')
    import_mesh(first)
    mats={r['id']:material(r) for r in scene['materials']}
    meshes={}
    for rec in scene['meshes']:
        mesh=import_mesh(rec)
        for i,mid in enumerate(rec['materials']):mesh.set_material(i,mats[mid])
        ASSETS.save_loaded_asset(mesh);meshes[rec['id']]=mesh
    LEVELS.new_level(PACKAGE+'/Maps/AstraCity')
    roles={r['id']:r for r in scene['meshes']}
    for i,rec in enumerate(scene['instances']):
        pos=u.Vector(*rec['position_cm']);yaw=rec['yaw_deg']
        if rec.get('door'):
            d=rec['door'];actor=ACTORS.spawn_actor_from_class(door_class,pos,u.Rotator(0,yaw-d['open_angle_deg'],0))
            actor.set_editor_property('open_angle',d['open_angle_deg']);actor.set_editor_property('b_open',True)
            comp=actor.get_editor_property('door_mesh');comp.set_static_mesh(meshes[rec['asset']])
            comp.set_relative_rotation(u.Rotator(0,d['open_angle_deg'],0),False,False)
        else:
            actor=ACTORS.spawn_actor_from_class(u.StaticMeshActor,pos,u.Rotator(0,yaw,0))
            comp=actor.static_mesh_component;comp.set_static_mesh(meshes[rec['asset']])
            comp.set_mobility(u.ComponentMobility.STATIC)
        comp.set_collision_profile_name('NoCollision' if roles[rec['asset']]['collision_mode']=='none' else 'BlockAll')
        actor.set_actor_scale3d(u.Vector(*rec['scale']));actor.set_actor_label(rec['id'])
        actor.set_folder_path('AstraCity/'+(rec['building_id'] or rec['role']))
        actor.tags=[u.Name('AstraCity'),u.Name(rec['role'])]
        if i%100==0:u.log(f'Astra scene: {i}/{len(scene["instances"])} actors')
    for rec in scene['lights']:
        actor=ACTORS.spawn_actor_from_class(u.PointLight,u.Vector(*rec['position_cm']))
        c=actor.point_light_component;c.set_mobility(u.ComponentMobility.MOVABLE)
        c.set_editor_property('intensity_units',u.LightUnits.LUMENS);c.set_intensity(rec['intensity_lumens'])
        c.set_light_color(u.LinearColor(*rec['color'],1));c.set_attenuation_radius(rec['attenuation_radius_cm'])
        c.set_editor_property('max_draw_distance',1800);c.set_editor_property('max_distance_fade_range',400)
        actor.set_folder_path('AstraCity/InteriorLights')
    sun=ACTORS.spawn_actor_from_class(u.DirectionalLight,u.Vector(0,0,20000),u.Rotator(-38,-35,0))
    sun.light_component.set_mobility(u.ComponentMobility.MOVABLE);sun.light_component.set_intensity(3.0)
    sky=ACTORS.spawn_actor_from_class(u.SkyLight,u.Vector(0,0,0));sky.light_component.set_mobility(u.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property('real_time_capture',True)
    ACTORS.spawn_actor_from_class(u.SkyAtmosphere,u.Vector(0,0,0))
    ACTORS.spawn_actor_from_class(u.PlayerStart,u.Vector(*scene['player_start_cm']),u.Rotator(0,scene['player_yaw'],0))
    # Walking uses CharacterMovement/physical collision and does not require AI navigation.
    # Avoid claiming a Recast build: the engine's version-specific navigation builder must run separately if AI agents are needed.
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode',game_class)
    LEVELS.save_current_level();ASSETS.save_directory(PACKAGE,only_if_is_dirty=True,recursive=True)
    REPORT.update(status='EDITOR_IMPORT_PASS_RUNTIME_NOT_RUN',actor_instances=len(scene['instances']),
                  plan_sha256=scene['plan_sha256'],runtime_walk_status='NOT_RUN',navmesh_status='NOT_BUILT_NOT_REQUIRED_FOR_MANUAL_WALK')

try:
    main()
except Exception:
    REPORT['status']='FAIL';REPORT['error']=traceback.format_exc();u.log_error(REPORT['error'])
    raise
finally:
    (ROOT/'engine_import_audit.json').write_text(json.dumps(REPORT,indent=2))
