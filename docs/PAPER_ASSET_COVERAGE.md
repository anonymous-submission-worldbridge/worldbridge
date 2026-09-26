# Paper asset implementation coverage

This index connects the asset categories in the paper figure to the anonymous source release. It describes source coverage, not a bundle of generated models or a clean-environment execution benchmark.

## Object-level categories

Paths below are relative to the repository root. `extensions/infinigen/` contains local additions and modifications; it is an overlay, not the entire upstream Infinigen library. Install the pinned upstream revision and apply the overlay as described in the [environment instructions](../README.md#environment-and-resources).

| Paper category | Included implementation or integration | Dependency / scope |
|---|---|---|
| Structural elements | `scripts/generate_urban_v3_all45.py`, `scripts/generate_urban_v3_all45_01.py`, commercial and public-building generators below | Building geometry and scene assembly; native room components also use upstream Infinigen. |
| Furniture and storage | `scripts/commercial_asset_refinement_generator_10.py`, `scripts/commercial_complete_interior_generator_11_object2.py` | Custom commercial fixtures and furnishings are included; native household furniture factories come from upstream Infinigen. |
| Appliances and electronics | Commercial, residential, hospital, and pharmacy scene generators | Placement/integration code is included; native household appliance factories require upstream Infinigen. |
| Fixtures and supplies | `scripts/pharmacy2_asset_factory.py`, `scripts/generate_urban_v3_hospital.py`, `scripts/commercial_complete_interior_generator_11_object2.py` | Custom commercial/service fixtures; upstream components where imported by individual builders. |
| Household items / tableware | `scripts/commercial_complete_interior_generator_11_object2.py`, `extensions/infinigen/infinigen/assets/objects/elements/nature_shelf_trinkets/generate.py` | Custom props and overlay components; remaining native tabletop objects use upstream Infinigen. |
| Decor and household items | Commercial builders and the shelf-trinket overlay above | Scene-specific props plus upstream decor components. |
| Road and boundary components | `scripts/generate_urban_v3_road.py`, `scripts/generate_urban_v3_fence.py`, `scripts/generate_urban_v3_fence2.py` | Procedural road, fence, and boundary builders. |
| Vehicles | `extensions/infinigen/infinigen/assets/objects/vehicles/vehicle.py`, `extensions/infinigen/infinigen/assets/objects/vehicles/openx_vehicle.py` | Vehicle generation/import adapters are included; referenced OpenX meshes are external inputs. |
| Vegetation | `extensions/infinigen/infinigen/assets/objects/trees/urban_tree.py`, `extensions/infinigen/infinigen/assets/objects/grassland/urban_groundcover.py` | Local tree and groundcover factories; additional plants require upstream Infinigen. |
| Street fixtures | `extensions/infinigen/infinigen/assets/objects/street_furniture/street_assets.py`, `scripts/generate_urban_v3_trafficlight.py`, `scripts/generate_urban_v3_busstop.py` | Street furniture, lights, signals, and bus stops. |
| Landscape ornaments | `scripts/generate_urban_v3_sculpture.py`, `extensions/infinigen/infinigen/assets/objects/decor/urban_public_space.py` | Sculptures, pavilions, and public-space elements. |
| Water elements | `extensions/infinigen/infinigen/assets/objects/decor/urban_lake.py`, `extensions/infinigen/infinigen/assets/objects/decor/urban_public_space.py`, `scripts/render_urban_v3_fountain_showcase.py` | Lakes, shorelines, and fountain variants. |
| Public-service equipment | `scripts/generate_urban_v3_delivery.py`, `scripts/generate_urban_v3_sharedbicycle.py`, `scripts/generate_urban_v3_kiosk.py`, `scripts/urban_assets.py` | Parcel facilities, bicycle stations, kiosks, and related equipment. |
| Sports and play equipment | `scripts/generate_urban_v3_fitness.py`, `scripts/generate_urban_v3_all44_02.py`, `scripts/generate_urban_v3_all44_04.py` | Outdoor fitness, sports, and recreation builders. |
| Terrain and rocks | `scripts/generate_urban_v3_lake.py` and outdoor scene assembly | Site/shoreline composition is included; general natural terrain and rock factories are upstream Infinigen dependencies. |

## Building and scene categories

| Paper category | Included entry points |
|---|---|
| Commercial and service facilities | `scripts/commercial_asset_refinement_generator_10.py`, `scripts/commercial_cleanup_generator_13.py`, `scripts/commercial_complete_interior_generator_11_object2.py` and the commercial revisions in the source catalog |
| Public safety and service stations | `scripts/generate_urban_v3_fire.py`, `scripts/generate_urban_v3_police.py`, `scripts/generate_urban_v3_gass.py` |
| Healthcare facilities | `scripts/generate_urban_v3_hospital.py`, `scripts/generate_urban_v3_pharmacy.py`, `scripts/build_pharmacy2.py` |
| Sports facilities | `scripts/generate_urban_v3_fitness.py` and the `generate_urban_v3_all44_*` recreation revisions |
| Cultural facilities | `scripts/generate_urban_v3_library.py` and historical/compositional builders listed in `docs/modeling/catalog.json` |
| Residential buildings | `scripts/generate_urban_v3_all45.py`, `scripts/generate_urban_v3_all45_01.py`, `scripts/generate_urban_v3_all45_02.py` and residential revisions in the source catalog |
| Connected worlds | `scripts/build_urban_v1_full_connect.py`, `scripts/build_urban_v1_full_connect2.py`, `scripts/build_urban_v1_full_connect3.py` and subsequent revisions |

The [modeling source index](modeling/README.md) covers 29 implementation families. The [catalog](modeling/catalog.json) records 702 authored source/configuration paths, including historical revisions. The [current review audit](modeling/review_audit.json) verifies their presence and scans release text and filenames for CJK ideographs.

Generated `.blend` scenes, exported meshes/textures, external vehicle models, and learned weights are not included. Some assembly and render entry points need component scenes generated in earlier stages. The source audit does not claim that every depicted individual asset is independently executable without these prerequisites.
