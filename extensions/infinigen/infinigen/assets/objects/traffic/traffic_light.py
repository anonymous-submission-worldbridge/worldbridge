import numpy as np

from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    cube_obj,
    cylinder_between,
    cylinder_obj,
    sphere_obj,
)


class TrafficLightFactory:
    def __init__(self, mats):
        self.mats = mats

    def create(self, request: UrbanAssetRequest):
        x, y, _ = request.location
        tid = request.params.get("id", "0")
        facing_axis = request.params.get("facing_axis", "x")

        objects = [
            cylinder_obj(
                f"urban:traffic_light:pole:{tid}",
                (x, y, 1.55),
                0.07,
                3.1,
                self.mats["metal"],
                "traffic-light",
                vertices=20,
            )
        ]
        objects.append(
            cylinder_obj(
                f"urban:traffic_light:base:{tid}",
                (x, y, 0.12),
                0.22,
                0.24,
                self.mats["metal"],
                "traffic-light",
                vertices=28,
            )
        )

        if facing_axis == "x":
            mast_loc = (x + np.sign(x) * 0.55, y, 3.0)
            mast_dims = (1.1, 0.08, 0.08)
            box_loc = (x + np.sign(x) * 1.15, y, 2.7)
            box_dims = (0.32, 0.22, 0.82)
            button_loc = (x, y + np.sign(y or 1) * 0.09, 1.15)
            light_locs = [
                (box_loc[0], y - 0.12, 2.95),
                (box_loc[0], y - 0.12, 2.7),
                (box_loc[0], y - 0.12, 2.45),
            ]
            hood_dims = (0.34, 0.20, 0.055)
        else:
            mast_loc = (x, y + np.sign(y) * 0.55, 3.0)
            mast_dims = (0.08, 1.1, 0.08)
            box_loc = (x, y + np.sign(y) * 1.15, 2.7)
            box_dims = (0.22, 0.32, 0.82)
            button_loc = (x + np.sign(x or 1) * 0.09, y, 1.15)
            light_locs = [
                (x + 0.12, box_loc[1], 2.95),
                (x + 0.12, box_loc[1], 2.7),
                (x + 0.12, box_loc[1], 2.45),
            ]
            hood_dims = (0.20, 0.34, 0.055)

        objects.append(cube_obj(f"urban:traffic_light:mast:{tid}", mast_loc, mast_dims, self.mats["metal"], "traffic-light", bevel=0.035))
        objects.append(
            cylinder_between(
                f"urban:traffic_light:diagonal_brace:{tid}",
                (x, y, 2.15),
                mast_loc,
                0.035,
                self.mats["metal"],
                "traffic-light",
                vertices=14,
            )
        )
        objects.append(cube_obj(f"urban:traffic_light:box:{tid}", box_loc, box_dims, self.mats["signal_box"], "traffic-light", bevel=0.045))
        for color, loc in zip(["red_signal", "yellow_signal", "green_signal"], light_locs):
            objects.append(sphere_obj(f"urban:traffic_light:{color}:{tid}", loc, 0.095, self.mats[color], "traffic-light"))
            hood_loc = (loc[0], loc[1] - 0.075, loc[2] + 0.045) if facing_axis == "x" else (loc[0] + 0.075, loc[1], loc[2] + 0.045)
            objects.append(
                cube_obj(
                    f"urban:traffic_light:visor:{color}:{tid}",
                    hood_loc,
                    hood_dims,
                    self.mats["signal_box"],
                    "traffic-light",
                    bevel=0.018,
                )
            )
        objects.extend(
            [
                cube_obj(
                    f"urban:traffic_light:ped_button_box:{tid}",
                    button_loc,
                    (0.13, 0.06, 0.22) if facing_axis == "x" else (0.06, 0.13, 0.22),
                    self.mats["signal_box"],
                    "traffic-light",
                    bevel=0.02,
                ),
                sphere_obj(
                    f"urban:traffic_light:ped_button:{tid}",
                    (button_loc[0], button_loc[1], button_loc[2] + 0.02),
                    0.035,
                    self.mats["yellow_signal"],
                    "traffic-light",
                ),
            ]
        )

        return objects, {
            "id": f"traffic_light_{tid}",
            "type": "traffic-light",
            "center": [x, y, 0],
        }
