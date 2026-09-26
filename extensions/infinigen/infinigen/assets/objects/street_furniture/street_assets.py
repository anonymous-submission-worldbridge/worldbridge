import math

from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    cone_obj,
    curve_obj,
    cube_obj,
    cylinder_between,
    cylinder_obj,
    ellipsoid_obj,
    sphere_obj,
    torus_obj,
)


class StreetFurnitureFactory:
    def __init__(self, mats):
        self.mats = mats

    def create_street_lamp(self, request: UrbanAssetRequest):
        lid = request.params.get("id", "0")
        x, y, _ = request.location
        head_sign = request.params.get("head_sign", 1)
        arm_y = y - head_sign * 0.72
        objs = [
            cylinder_obj(f"urban:street_lamp:base:{lid}", (x, y, 0.08), 0.28, 0.16, self.mats["metal"], "street-lamp", vertices=32),
            cylinder_obj(f"urban:street_lamp:pole:{lid}", (x, y, 1.78), 0.055, 3.45, self.mats["metal"], "street-lamp", vertices=24),
            curve_obj(
                f"urban:street_lamp:curved_arm:{lid}",
                [(x, y, 3.18), (x, y - head_sign * 0.25, 3.48), (x, arm_y, 3.42)],
                0.035,
                self.mats["metal"],
                "street-lamp",
            ),
            cone_obj(f"urban:street_lamp:shade:{lid}", (x, arm_y, 3.30), 0.27, 0.12, 0.22, self.mats["metal"], "street-lamp", vertices=32),
            ellipsoid_obj(f"urban:street_lamp:bulb:{lid}", (x, arm_y, 3.19), (0.13, 0.13, 0.07), self.mats["lamp"], "street-lamp", segments=24),
        ]
        return objs, {"id": f"lamp_{lid}", "type": "street-lamp", "center": [x, y, 0]}

    def create_bus_stop(self, request: UrbanAssetRequest):
        x, y, _ = request.location
        sid = request.params.get("id", "0")
        parts = [
            ("glass_back", (x, y, 1.15), (4.2, 0.055, 1.9), self.mats["bus_stop_glass"], "bus-stop"),
            ("glass_left", (x - 2.12, y - 0.48, 1.1), (0.055, 0.96, 1.75), self.mats["bus_stop_glass"], "bus-stop"),
            ("glass_right", (x + 2.12, y - 0.48, 1.1), (0.055, 0.96, 1.75), self.mats["bus_stop_glass"], "bus-stop"),
            ("roof", (x, y - 0.45, 2.25), (4.75, 1.35, 0.13), self.mats["metal"], "bus-stop"),
            ("roof_lip_front", (x, y - 1.13, 2.16), (4.85, 0.08, 0.20), self.mats["metal"], "bus-stop"),
            ("schedule_panel", (x - 1.55, y - 0.065, 1.35), (0.65, 0.045, 0.95), self.mats["bus_stop_sign"], "bus-stop-sign"),
            ("route_header", (x - 1.55, y - 0.10, 1.88), (0.70, 0.05, 0.10), self.mats["lamp"], "bus-stop-sign"),
            ("sign", (x - 2.55, y + 0.05, 2.65), (0.55, 0.08, 0.55), self.mats["bus_stop_sign"], "bus-stop-sign"),
        ]
        objs = [cube_obj(f"urban:bus_stop:{sid}:{pid}", loc, dims, mat, sem, bevel=0.025) for pid, loc, dims, mat, sem in parts]
        for i, fx in enumerate([-2.25, -0.75, 0.75, 2.25]):
            objs.append(cylinder_obj(f"urban:bus_stop:post:{sid}:{i}", (x + fx, y - 0.02, 1.12), 0.035, 2.1, self.mats["metal"], "bus-stop", vertices=16))
        for i, px in enumerate([-0.7, 0.0, 0.7]):
            objs.append(cube_obj(f"urban:bus_stop:bench_plank:{sid}:{i}", (x + px, y - 0.78, 0.58), (0.58, 0.24, 0.12), self.mats["bench"], "bench", bevel=0.04))
            objs.append(cylinder_obj(f"urban:bus_stop:bench_leg:{sid}:{i}:l", (x + px - 0.20, y - 0.78, 0.34), 0.025, 0.48, self.mats["metal"], "bench", vertices=12))
            objs.append(cylinder_obj(f"urban:bus_stop:bench_leg:{sid}:{i}:r", (x + px + 0.20, y - 0.78, 0.34), 0.025, 0.48, self.mats["metal"], "bench", vertices=12))
        for i, z in enumerate([1.55, 1.38, 1.21, 1.04]):
            objs.append(cube_obj(f"urban:bus_stop:schedule_line:{sid}:{i}", (x - 1.55, y - 0.095, z), (0.46, 0.02, 0.025), self.mats["license_plate"], "bus-stop-sign", bevel=0.002))
        for i, px in enumerate([-0.18, 0.0, 0.18]):
            objs.append(cube_obj(f"urban:bus_stop:route_digit:{sid}:{i}", (x - 2.55 + px, y + 0.005, 2.66), (0.055, 0.02, 0.26), self.mats["license_plate"], "bus-stop-sign", bevel=0.003))
        return objs, {"id": f"bus_stop_{sid}", "type": "bus-stop", "center": [x, y, 0]}

    def create_bike_rack(self, request: UrbanAssetRequest):
        rid = request.params.get("id", "0")
        x, y, _ = request.location
        objs = [
            torus_obj(f"urban:bike_rack:loop:{rid}", (x, y, 0.56), 0.38, 0.035, self.mats["metal"], "bike-rack", rotation=(math.radians(90), 0, 0)),
            cylinder_obj(f"urban:bike_rack:foot_l:{rid}", (x - 0.28, y, 0.12), 0.035, 0.24, self.mats["metal"], "bike-rack", vertices=12),
            cylinder_obj(f"urban:bike_rack:foot_r:{rid}", (x + 0.28, y, 0.12), 0.035, 0.24, self.mats["metal"], "bike-rack", vertices=12),
        ]
        return objs, {"id": f"bike_rack_{rid}", "type": "bike-rack", "center": [x, y, 0]}

    def create_fire_hydrant(self, request: UrbanAssetRequest):
        x, y, _ = request.location
        hid = request.params.get("id", "0")
        specs = [
            ("body", (x, y, 0.45), 0.16, 0.72),
            ("cap", (x, y, 0.88), 0.13, 0.18),
            ("side_l", (x - 0.22, y, 0.55), 0.07, 0.24),
            ("side_r", (x + 0.22, y, 0.55), 0.07, 0.24),
        ]
        objs = []
        for part, loc, radius, depth in specs:
            obj = cylinder_obj(f"urban:fire_hydrant:{hid}:{part}", loc, radius, depth, self.mats["hydrant"], "fire-hydrant", vertices=16)
            if part.startswith("side"):
                obj.rotation_euler[1] = math.radians(90)
            objs.append(obj)
        objs.extend(
            [
                torus_obj(f"urban:fire_hydrant:ring:{hid}", (x, y, 0.76), 0.16, 0.018, self.mats["metal"], "fire-hydrant"),
                cone_obj(f"urban:fire_hydrant:top:{hid}", (x, y, 1.02), 0.16, 0.04, 0.22, self.mats["hydrant"], "fire-hydrant", vertices=20),
                cube_obj(f"urban:fire_hydrant:chain:{hid}", (x, y - 0.20, 0.57), (0.045, 0.28, 0.035), self.mats["metal"], "fire-hydrant", bevel=0.012),
            ]
        )
        return objs, {"id": f"fire_hydrant_{hid}", "type": "fire-hydrant", "center": [x, y, 0]}

    def create_bench(self, request: UrbanAssetRequest):
        bid = request.params.get("id", "0")
        x, y, _ = request.location
        objs = []
        for i, z in enumerate([0.48, 0.62, 0.76]):
            objs.append(cube_obj(f"urban:bench:seat_plank:{bid}:{i}", (x, y, z), (1.85, 0.13, 0.07), self.mats["bench"], "bench", bevel=0.025))
        for i, z in enumerate([0.88, 1.02]):
            objs.append(cube_obj(f"urban:bench:back_plank:{bid}:{i}", (x, y + 0.28, z), (1.85, 0.10, 0.07), self.mats["bench"], "bench", bevel=0.025))
        for i, sx in enumerate([-0.72, 0.72]):
            objs.append(cylinder_between(f"urban:bench:side_frame:{bid}:{i}:front", (x + sx, y - 0.24, 0.18), (x + sx, y - 0.16, 0.72), 0.025, self.mats["metal"], "bench", vertices=12))
            objs.append(cylinder_between(f"urban:bench:side_frame:{bid}:{i}:back", (x + sx, y + 0.28, 0.18), (x + sx, y + 0.30, 1.08), 0.025, self.mats["metal"], "bench", vertices=12))
        return objs, {"id": f"bench_{bid}", "type": "bench", "center": [x, y, 0]}

    def create_trash_bin(self, request: UrbanAssetRequest):
        tid = request.params.get("id", "0")
        x, y, _ = request.location
        objs = [
            cylinder_obj(f"urban:trash_bin:body:{tid}", (x, y, 0.45), 0.28, 0.82, self.mats["trash"], "trash-bin", vertices=28),
            cylinder_obj(f"urban:trash_bin:rim:{tid}", (x, y, 0.88), 0.30, 0.08, self.mats["metal"], "trash-bin", vertices=28),
            cube_obj(f"urban:trash_bin:slot:{tid}", (x, y - 0.285, 0.72), (0.34, 0.035, 0.10), self.mats["tire"], "trash-bin", bevel=0.01),
        ]
        return objs, {"id": f"trash_bin_{tid}", "type": "trash-bin", "center": [x, y, 0]}

    def create_planter(self, request: UrbanAssetRequest):
        pid = request.params.get("id", "0")
        x, y, _ = request.location
        objs = [
            cube_obj(f"urban:planter:box:{pid}", (x, y, 0.35), (2.2, 0.8, 0.7), self.mats["planter"], "planter", bevel=0.055),
            cube_obj(f"urban:planter:rim_front:{pid}", (x, y - 0.43, 0.74), (2.32, 0.08, 0.10), self.mats["stone"], "planter", bevel=0.025),
            cube_obj(f"urban:planter:rim_back:{pid}", (x, y + 0.43, 0.74), (2.32, 0.08, 0.10), self.mats["stone"], "planter", bevel=0.025),
            cube_obj(f"urban:planter:soil:{pid}", (x, y, 0.77), (1.90, 0.52, 0.06), self.mats.get("soil", self.mats["trunk"]), "soil", bevel=0.018),
        ]
        for i, px in enumerate([-0.70, -0.35, 0.0, 0.35, 0.70]):
            objs.append(ellipsoid_obj(f"urban:planter:leaf_mound:{pid}:{i}", (x + px, y, 1.00 + 0.04 * (i % 2)), (0.35, 0.23, 0.25), self.mats["leaf"] if i % 2 else self.mats["shrub"], "planter", segments=16, ring_count=8))
            if i % 2 == 0:
                objs.append(ellipsoid_obj(f"urban:planter:flower:{pid}:{i}", (x + px + 0.08, y - 0.04, 1.25), (0.055, 0.055, 0.035), self.mats.get("flower_purple", self.mats["lamp"]), "flower", segments=10, ring_count=6))
        return objs, {"id": f"planter_{pid}", "type": "planter", "center": [x, y, 0]}

    def create_traffic_sign(self, request: UrbanAssetRequest):
        sid = request.params.get("id", "0")
        x, y, _ = request.location
        objs = [
            cylinder_obj(f"urban:traffic_sign:post:{sid}", (x, y, 1.25), 0.035, 2.5, self.mats["metal"], "traffic-sign", vertices=16),
            cube_obj(f"urban:traffic_sign:face:{sid}", (x, y - 0.07, 2.25), (0.9, 0.06, 0.9), self.mats["sign"], "traffic-sign", bevel=0.035),
            cube_obj(f"urban:traffic_sign:border_top:{sid}", (x, y - 0.105, 2.66), (0.78, 0.018, 0.05), self.mats["license_plate"], "traffic-sign", bevel=0.004),
            cube_obj(f"urban:traffic_sign:border_bottom:{sid}", (x, y - 0.105, 1.84), (0.78, 0.018, 0.05), self.mats["license_plate"], "traffic-sign", bevel=0.004),
            cube_obj(f"urban:traffic_sign:person_body:{sid}", (x, y - 0.112, 2.22), (0.10, 0.014, 0.28), self.mats["license_plate"], "traffic-sign", bevel=0.006),
            sphere_obj(f"urban:traffic_sign:person_head:{sid}", (x, y - 0.112, 2.42), 0.07, self.mats["license_plate"], "traffic-sign"),
            cylinder_between(f"urban:traffic_sign:person_leg_l:{sid}", (x, y - 0.112, 2.08), (x - 0.16, y - 0.112, 1.92), 0.018, self.mats["license_plate"], "traffic-sign", vertices=8),
            cylinder_between(f"urban:traffic_sign:person_leg_r:{sid}", (x, y - 0.112, 2.08), (x + 0.15, y - 0.112, 1.92), 0.018, self.mats["license_plate"], "traffic-sign", vertices=8),
        ]
        return objs, {"id": f"sign_{sid}", "type": "traffic-sign", "center": [x, y, 0]}
