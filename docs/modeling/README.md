# Modeling source index

This collection preserves the code that constructs the assets. Saved models and model export files are not packaged.

Main generators remain in `scripts/`; local Infinigen factories and configurations remain in `extensions/infinigen/`. Historical project versions are under `scripts/modeling_history/`. Floor plans and camera routes recovered from output directories are under `configs/modeling/`.

## Find a modeling implementation

The table links the implementation files. `catalog.json` lists every audited source and all matching family files, with checksums and source provenance.

| Family | Implementation | Role |
|---|---|---|
| Shared bicycles and docking stations | [generate_urban_v3_sharedbicycle.py](../../scripts/generate_urban_v3_sharedbicycle.py), [generate_urban_v3_sharedbicycle2.py](../../scripts/generate_urban_v3_sharedbicycle2.py), [generate_urban_v3_sharedbicycle3.py](../../scripts/generate_urban_v3_sharedbicycle3.py) (plus 1 versions in the catalog) | Procedural bicycles, docks, and stations. |
| Food lockers, parcel lockers, and delivery stations | [generate_urban_v3_delivery.py](../../scripts/generate_urban_v3_delivery.py), [urban_assets.py](../../scripts/urban_assets.py) | Live procedural builders, including articulated doors. |
| Factory buildings | [factory_building.py](../../extensions/infinigen/infinigen/assets/objects/urban/factory_building.py) | FactoryBuildingFactory creates industrial geometry. |
| Schools and campuses | [generate_urban_v3_school.py](../../scripts/generate_urban_v3_school.py) | Campus buildings, interiors, sports grounds, and site geometry. |
| Police stations | [generate_urban_v3_police.py](../../scripts/generate_urban_v3_police.py) | Three reference-driven station variants and their sites. |
| Parks and public spaces | [urban_public_space.py](../../extensions/infinigen/infinigen/assets/objects/decor/urban_public_space.py), [build_community_reading_park2.py](../../scripts/build_community_reading_park2.py), [build_urban_v1_full_connect3.py](../../scripts/build_urban_v1_full_connect3.py) (plus 10 versions in the catalog) | Public-space factories and scene assembly; assembly requires generated inputs. |
| Benches and trash bins | [generate_urban_v3_bench_trashbin.py](../../scripts/generate_urban_v3_bench_trashbin.py), [generate_urban_v3_bench_trashbin2.py](../../scripts/generate_urban_v3_bench_trashbin2.py), [street_assets.py](../../extensions/infinigen/infinigen/assets/objects/street_furniture/street_assets.py) | Street furniture geometry and shared factories. |
| Streetlights | [streetlight_render.py](../../extensions/infinigen/infinigen_examples/streetlight_render.py), [street_assets.py](../../extensions/infinigen/infinigen/assets/objects/street_furniture/street_assets.py) | Streetlight construction and preview entry point. |
| Traffic signals | [generate_urban_v3_trafficlight.py](../../scripts/generate_urban_v3_trafficlight.py), [generate_urban_v3_trafficlight2.py](../../scripts/generate_urban_v3_trafficlight2.py), [generate_urban_v3_trafficlight3.py](../../scripts/generate_urban_v3_trafficlight3.py) (plus 1 versions in the catalog) | Traffic signal geometry and variants. |
| Phone booths | [phonebooth2_render.py](../../extensions/infinigen/infinigen_examples/phonebooth2_render.py), [phonebooth3_render.py](../../extensions/infinigen/infinigen_examples/phonebooth3_render.py), [phonebooth4_render.py](../../extensions/infinigen/infinigen_examples/phonebooth4_render.py) (plus 2 versions in the catalog) | Phone booth geometry and versioned preview scripts. |
| Bus stops | [generate_urban_v3_busstop.py](../../scripts/generate_urban_v3_busstop.py) | Bus shelter and stop geometry. |
| Kiosks and ATMs | [generate_urban_v3_kiosk.py](../../scripts/generate_urban_v3_kiosk.py), [generate_urban_v3_kiosk2.py](../../scripts/generate_urban_v3_kiosk2.py), [generate_urban_v3_kiosk3.py](../../scripts/generate_urban_v3_kiosk3.py) (plus 6 versions in the catalog) | Kiosk revisions and ATM facilities. |
| Trees and groundcover | [urban_tree.py](../../extensions/infinigen/infinigen/assets/objects/trees/urban_tree.py), [urban_groundcover.py](../../extensions/infinigen/infinigen/assets/objects/grassland/urban_groundcover.py), [grass_asset_render.py](../../extensions/infinigen/infinigen_examples/grass_asset_render.py) (plus 1 versions in the catalog) | Procedural tree and groundcover factories. |
| Sculptures and pavilions | [generate_urban_v3_sculpture.py](../../scripts/generate_urban_v3_sculpture.py) | Sculpture and pavilion geometry. |
| Fountains | [urban_public_space.py](../../extensions/infinigen/infinigen/assets/objects/decor/urban_public_space.py), [render_urban_v3_fountain_showcase.py](../../scripts/render_urban_v3_fountain_showcase.py) | Fountain construction and variants. |
| Outdoor fitness facilities | [generate_urban_v3_fitness.py](../../scripts/generate_urban_v3_fitness.py) | Exercise equipment and outdoor fitness sites. |
| Libraries | [generate_urban_v3_library.py](../../scripts/generate_urban_v3_library.py) | Library buildings and interiors. |
| Fire stations | [generate_urban_v3_fire.py](../../scripts/generate_urban_v3_fire.py) | Station architecture; imported vehicle meshes remain external inputs. |
| Hospitals | [generate_urban_v3_hospital.py](../../scripts/generate_urban_v3_hospital.py) | Hospital architecture and clinical spaces. |
| Gas stations | [generate_urban_v3_gass.py](../../scripts/generate_urban_v3_gass.py) | Station canopy, pumps, shop, and site. |
| Pharmacies | [generate_urban_v3_pharmacy.py](../../scripts/generate_urban_v3_pharmacy.py), [build_pharmacy2.py](../../scripts/build_pharmacy2.py), [pharmacy2_asset_factory.py](../../scripts/pharmacy2_asset_factory.py) | Pharmacy geometry, fixtures, and later scene variants. |
| Commercial buildings and shops | [commercial_asset_refinement_generator_10.py](../../scripts/commercial_asset_refinement_generator_10.py), [commercial_cleanup_generator_13.py](../../scripts/commercial_cleanup_generator_13.py), [commercial_complete_interior_generator_11_object2.py](../../scripts/commercial_complete_interior_generator_11_object2.py) (plus 21 versions in the catalog) | Shop and commercial-block builders and refinements. |
| Playgrounds and sports areas | [generate_urban_v3_all44_02.py](../../scripts/generate_urban_v3_all44_02.py), [generate_urban_v3_all44_03.py](../../scripts/generate_urban_v3_all44_03.py), [generate_urban_v3_all44_04.py](../../scripts/generate_urban_v3_all44_04.py) (plus 12 versions in the catalog) | Recreation and sports scene variants. |
| Residential buildings | [generate_urban_v3_all45.py](../../scripts/generate_urban_v3_all45.py), [generate_urban_v3_all45_01.py](../../scripts/generate_urban_v3_all45_01.py), [generate_urban_v3_all45_02.py](../../scripts/generate_urban_v3_all45_02.py) (plus 3 versions in the catalog) | Residential layouts, interiors, and assembly stages. |
| Lakes and waterfronts | [generate_urban_v3_lake.py](../../scripts/generate_urban_v3_lake.py), [urban_lake.py](../../extensions/infinigen/infinigen/assets/objects/decor/urban_lake.py) | Lake geometry, shoreline, and environment construction. |
| Roads, fences, and green belts | [generate_urban_v3_road.py](../../scripts/generate_urban_v3_road.py), [generate_urban_v3_fence.py](../../scripts/generate_urban_v3_fence.py), [generate_urban_v3_fence2.py](../../scripts/generate_urban_v3_fence2.py) (plus 5 versions in the catalog) | Road and boundary geometry. |
| Vehicles | [__init__.py](../../extensions/infinigen/infinigen/assets/objects/vehicles/__init__.py), [openx_vehicle.py](../../extensions/infinigen/infinigen/assets/objects/vehicles/openx_vehicle.py), [vehicle.py](../../extensions/infinigen/infinigen/assets/objects/vehicles/vehicle.py) (plus 11 versions in the catalog) | Vehicle factories and external OpenX import adapters. |
| Robots and articulated task animation | [robot1_model.py](../../scripts/robot1_model.py), [build_render_robot1.py](../../scripts/build_render_robot1.py), [robot1_tasks.py](../../scripts/robot1_tasks.py) (plus 12 versions in the catalog) | Robot geometry, joints, poses, task plans, and media helpers. |
| Connected neighborhood scenes | [build_urban_v1_full_connect.py](../../scripts/build_urban_v1_full_connect.py), [build_urban_v1_full_connect2.py](../../scripts/build_urban_v1_full_connect2.py), [build_urban_v1_full_connect3.py](../../scripts/build_urban_v1_full_connect3.py) (plus 6 versions in the catalog) | Layout and composition code; generate referenced component assets first. |

## Running the code

Install Blender and the documented Infinigen environment, then apply the overlay with `python scripts/setup_extensions.py --apply`. A saved model is a generated output, not a repository deliverable.

Individual procedural builders construct geometry in Blender. Scene assembly, repair, and rendering scripts can require previously generated component scenes or third-party resources. This source audit does not assert that all scripts can regenerate a complete city from an empty directory. Configure external resources and generate prerequisites before running those stages.

Historical snapshots retain their original algorithms and revision-specific assumptions. Use the current entry points above for active development; the history directory is for reference and reproduction of earlier versions.

## Audit

- 702 authored source/configuration paths checked; 0 missing.
- 25 previously omitted scripts recovered, plus four floor-plan/camera-route configurations.
- 59 historical project scripts relocated out of the former model directory.
- Three later source revisions retained separately without overwriting refactored entry points.
- The earlier count of 185 historical scripts included 126 third-party Shapely files. Those files are excluded from the authored-code inventory and removed from the project copy.
- Model and support-file removals are recorded in `removal_summary.json` and `removed_files.jsonl`.
- The source projects are read-only inputs to this correction.

See [verification.json](verification.json) for the final source, syntax, language, and model-removal checks. Older binary-copy reports under `docs/assets/` are historical records superseded by this source-only inventory.
