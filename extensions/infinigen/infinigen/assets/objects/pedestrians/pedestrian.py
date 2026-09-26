import math

from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    cube_obj,
    cylinder_between,
    cylinder_obj,
    ellipsoid_obj,
    sphere_obj,
)


class PedestrianFactory:
    def __init__(self, mats):
        self.mats = mats

    def create(self, request: UrbanAssetRequest):
        pid = request.params.get("id", "0")
        shirt_key = request.params.get("shirt", "person_shirt_blue")
        facing = request.params.get("facing", request.yaw)
        x, y, _ = request.location

        stride = 0.08 if int(pid) % 2 == 0 else -0.08
        left_hip = (x - 0.08, y, 0.74)
        right_hip = (x + 0.08, y, 0.74)
        left_ankle = (x - 0.10, y + stride, 0.16)
        right_ankle = (x + 0.10, y - stride, 0.16)
        left_leg = cylinder_between(f"urban:pedestrian:leg_l:{pid}", left_hip, left_ankle, 0.048, self.mats["person_pants"], "pedestrian", vertices=12)
        right_leg = cylinder_between(f"urban:pedestrian:leg_r:{pid}", right_hip, right_ankle, 0.048, self.mats["person_pants"], "pedestrian", vertices=12)
        torso = ellipsoid_obj(f"urban:pedestrian:torso:{pid}", (x, y, 0.98), (0.18, 0.12, 0.34), self.mats[shirt_key], "pedestrian", segments=18, ring_count=10)
        neck = cylinder_obj(f"urban:pedestrian:neck:{pid}", (x, y, 1.28), 0.055, 0.12, self.mats["person_skin"], "pedestrian", vertices=12)
        head = ellipsoid_obj(f"urban:pedestrian:head:{pid}", (x, y, 1.45), (0.13, 0.115, 0.16), self.mats["person_skin"], "pedestrian", segments=18, ring_count=10)
        hair = ellipsoid_obj(f"urban:pedestrian:hair:{pid}", (x, y - 0.015, 1.55), (0.132, 0.115, 0.07), self.mats["person_hair"], "pedestrian", segments=18, ring_count=8)
        left_arm = cylinder_between(f"urban:pedestrian:arm_l:{pid}", (x - 0.18, y, 1.12), (x - 0.25, y - 0.08, 0.82), 0.035, self.mats["person_skin"], "pedestrian", vertices=10)
        right_arm = cylinder_between(f"urban:pedestrian:arm_r:{pid}", (x + 0.18, y, 1.12), (x + 0.25, y + 0.08, 0.82), 0.035, self.mats["person_skin"], "pedestrian", vertices=10)
        left_hand = sphere_obj(f"urban:pedestrian:hand_l:{pid}", (x - 0.25, y - 0.08, 0.80), 0.045, self.mats["person_skin"], "pedestrian")
        right_hand = sphere_obj(f"urban:pedestrian:hand_r:{pid}", (x + 0.25, y + 0.08, 0.80), 0.045, self.mats["person_skin"], "pedestrian")
        left_foot = cube_obj(f"urban:pedestrian:foot_l:{pid}", (left_ankle[0], left_ankle[1] - 0.04, 0.055), (0.13, 0.24, 0.07), self.mats["person_shoe"], "pedestrian", bevel=0.025)
        right_foot = cube_obj(f"urban:pedestrian:foot_r:{pid}", (right_ankle[0], right_ankle[1] + 0.04, 0.055), (0.13, 0.24, 0.07), self.mats["person_shoe"], "pedestrian", bevel=0.025)
        bag = cube_obj(f"urban:pedestrian:bag:{pid}", (x + 0.30, y + 0.02, 0.82), (0.16, 0.08, 0.24), self.mats["person_pants"], "pedestrian", bevel=0.035)

        objs = [left_leg, right_leg, torso, neck, head, hair, left_arm, right_arm, left_hand, right_hand, left_foot, right_foot, bag]
        for obj in objs:
            obj.rotation_euler[2] = facing
        return objs, {"id": f"pedestrian_{pid}", "type": "pedestrian", "center": [x, y, 0]}
