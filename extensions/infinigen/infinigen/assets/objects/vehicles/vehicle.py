import math

from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    cube_obj,
    cylinder_between,
    cylinder_obj,
    ellipsoid_obj,
    mesh_obj,
    multi_curve_obj,
    torus_obj,
)


class VehicleFactory:
    def __init__(self, mats):
        self.mats = mats

    def _m(self, key, fallback="metal"):
        return self.mats.get(key, self.mats.get(fallback))

    def create(self, request: UrbanAssetRequest):
        vid = request.params.get("id", "0")
        axis = request.params.get("axis", "x")
        vehicle_type = request.params.get("vehicle_type", "car")
        variant = request.params.get("variant", "sedan")
        color_key = request.params.get("color", "car_blue")
        x, y, _ = request.location

        if vehicle_type == "bus":
            return self._create_bus(vid, x, y, axis, color_key)
        elif variant == "suv":
            return self._create_suv(vid, x, y, axis, color_key)
        elif variant == "pickup":
            return self._create_pickup(vid, x, y, axis, color_key)
        elif variant == "hatchback":
            return self._create_hatchback(vid, x, y, axis, color_key)
        return self._create_sedan(vid, x, y, axis, color_key)

    # -------------------------------------------------------------------------
    # Coordinate helpers
    # -------------------------------------------------------------------------

    def _dims(self, length, width, height, axis):
        return (length, width, height) if axis == "x" else (width, length, height)

    def _loc(self, x, y, forward, lateral, z, axis):
        return (x + forward, y + lateral, z) if axis == "x" else (x + lateral, y + forward, z)

    def _oriented_box_dims(self, forward_size, lateral_size, z_size, axis):
        return self._dims(forward_size, lateral_size, z_size, axis)

    def _mesh_vertex(self, x, y, forward, lateral, z, axis):
        return self._loc(x, y, forward, lateral, z, axis)

    # -------------------------------------------------------------------------
    # Shell geometry  (cross-section loft)
    # -------------------------------------------------------------------------

    def _car_shell_from_stations(self, name, stations, x, y, axis, width, color_key):
        """Loft a closed cross-section mesh through a list of (forward, hw_pct, ztop) stations."""
        verts = []
        for forward, half_width_pct, ztop in stations:
            hw = width * half_width_pct
            # 4 verts per station: bottom-left, bottom-right, top-right, top-left
            verts.extend([
                self._mesh_vertex(x, y, forward, -hw,       0.28, axis),
                self._mesh_vertex(x, y, forward,  hw,       0.28, axis),
                self._mesh_vertex(x, y, forward,  hw * 0.9, ztop, axis),
                self._mesh_vertex(x, y, forward, -hw * 0.9, ztop, axis),
            ])
        faces = []
        for i in range(len(stations) - 1):
            a, b = i * 4, (i + 1) * 4
            faces.extend([
                (a,     b,     b + 3, a + 3),   # left side
                (a + 1, a + 2, b + 2, b + 1),   # right side
                (a + 3, b + 3, b + 2, a + 2),   # top
                (a,     a + 1, b + 1, b),        # bottom
            ])
        n = (len(stations) - 1) * 4
        faces.extend([(0, 3, 2, 1), (n, n + 1, n + 2, n + 3)])  # front/rear caps
        return mesh_obj(name, verts, faces, self.mats[color_key], "vehicle", smooth=True)

    # -------------------------------------------------------------------------
    # Enhanced wheel assembly (5-spoke alloy, brake disc, lug nuts)
    # -------------------------------------------------------------------------

    def _wheel_set(self, vid, wi, x, y, forward, lateral, axis, radius, ground_z=0.34,
                   width_scale=1.0):
        loc = self._loc(x, y, forward, lateral, ground_z, axis)
        # Rotation: wheel lies in a vertical plane perpendicular to travel direction
        rot_x = math.radians(90) if axis == "y" else 0
        rot_y = math.radians(90) if axis == "x" else 0

        tire_minor = radius * 0.255 * width_scale
        tire = torus_obj(
            f"urban:vehicle:tire:{vid}:{wi}",
            loc, radius, tire_minor,
            self._m("tire"),
            "vehicle-wheel",
            rotation=(rot_x, rot_y, 0),
        )

        # Rim face disk
        rim_depth = tire_minor * 1.85
        rim = cylinder_obj(
            f"urban:vehicle:rim_face:{vid}:{wi}",
            loc, radius * 0.56, rim_depth,
            self._m("rim_metal", "metal"),
            "vehicle-wheel",
            vertices=36,
        )
        rim.rotation_euler = (rot_x, rot_y, 0)

        # Brake disc (set slightly back behind rim face)
        disc_offset = rim_depth * 0.55
        if axis == "x":
            disc_loc = (loc[0], loc[1] + disc_offset * math.copysign(1, lateral), loc[2])
        else:
            disc_loc = (loc[0] + disc_offset * math.copysign(1, lateral), loc[1], loc[2])
        brake = cylinder_obj(
            f"urban:vehicle:brake_disc:{vid}:{wi}",
            disc_loc, radius * 0.50, rim_depth * 0.4,
            self._m("brake_disc", "metal"),
            "vehicle-wheel",
            vertices=24,
        )
        brake.rotation_euler = (rot_x, rot_y, 0)

        # 5 alloy spokes as thin flat rectangles
        spoke_objs = []
        for si in range(5):
            angle = si * math.tau / 5
            spoke_forward = math.cos(angle) * radius * 0.58
            spoke_lateral = math.sin(angle) * radius * 0.58
            if axis == "x":
                sp_loc = (loc[0] + spoke_forward, loc[1], loc[2] + spoke_lateral)
                sp_dims = (radius * 0.38, rim_depth * 0.9, radius * 0.12)
                sp_rot = (math.radians(90), 0, angle)
            else:
                sp_loc = (loc[0], loc[1] + spoke_forward, loc[2] + spoke_lateral)
                sp_dims = (rim_depth * 0.9, radius * 0.38, radius * 0.12)
                sp_rot = (0, math.radians(90), angle)
            sp = cube_obj(
                f"urban:vehicle:spoke:{vid}:{wi}:{si}",
                sp_loc, sp_dims,
                self._m("rim_metal", "metal"),
                "vehicle-wheel",
                bevel=0.01,
            )
            sp.rotation_euler = sp_rot
            spoke_objs.append(sp)

        # Center hub cap
        hub = cylinder_obj(
            f"urban:vehicle:hub:{vid}:{wi}",
            loc, radius * 0.14, rim_depth * 0.95,
            self._m("rim_metal", "metal"),
            "vehicle-wheel",
            vertices=16,
        )
        hub.rotation_euler = (rot_x, rot_y, 0)

        # 5 lug nuts
        lug_objs = []
        for li in range(5):
            angle = li * math.tau / 5
            lug_r = radius * 0.27
            lug_fwd = math.cos(angle) * lug_r
            lug_lat = math.sin(angle) * lug_r
            if axis == "x":
                ll = (loc[0] + lug_fwd, loc[1], loc[2] + lug_lat)
            else:
                ll = (loc[0], loc[1] + lug_fwd, loc[2] + lug_lat)
            lg = cylinder_obj(
                f"urban:vehicle:lug:{vid}:{wi}:{li}",
                ll, radius * 0.038, rim_depth * 0.55,
                self._m("rim_metal", "metal"),
                "vehicle-wheel",
                vertices=6,
            )
            lg.rotation_euler = (rot_x, rot_y, 0)
            lug_objs.append(lg)

        return [tire, rim, brake, *spoke_objs, hub, *lug_objs]

    # -------------------------------------------------------------------------
    # Shared detail helpers
    # -------------------------------------------------------------------------

    def _headlight_assembly(self, vid, name, x, y, forward, lateral, zloc, axis, scale=1.0):
        """Three-part headlight: housing, LED DRL strip, lens cover."""
        objs = []
        # Main housing (dark reflector)
        h_dims = self._dims(0.05, 0.32 * scale, 0.14 * scale, axis)
        objs.append(cube_obj(
            f"urban:vehicle:hl_housing:{vid}:{name}",
            self._loc(x, y, forward, lateral, zloc, axis),
            h_dims, self._m("signal_box"), "vehicle-headlight", bevel=0.008,
        ))
        # LED DRL strip (thin bright bar across headlight width)
        led_dims = self._dims(0.035, 0.28 * scale, 0.028 * scale, axis)
        objs.append(cube_obj(
            f"urban:vehicle:hl_led:{vid}:{name}",
            self._loc(x, y, forward + 0.012, lateral, zloc - 0.035 * scale, axis),
            led_dims, self._m("headlight_led", "headlight"), "vehicle-headlight", bevel=0.002,
        ))
        # Main beam projector (ellipsoid)
        proj_scale = (0.022, 0.10 * scale, 0.08 * scale)
        objs.append(ellipsoid_obj(
            f"urban:vehicle:hl_proj:{vid}:{name}",
            self._loc(x, y, forward + 0.01, lateral, zloc + 0.022 * scale, axis),
            proj_scale, self._m("headlight"), "vehicle-headlight", segments=16,
        ))
        return objs

    def _taillight_assembly(self, vid, name, x, y, forward, lateral, zloc, axis, scale=1.0):
        """Three-section tail light: brake, indicator, reverse."""
        objs = []
        for idx, (offset, h, mat_k) in enumerate([
            (-0.10 * scale, 0.11, "tail_light"),
            (0.02 * scale,  0.09, "tail_indicator"),
            (0.11 * scale,  0.07, "tail_reverse"),
        ]):
            sec_dims = self._dims(0.04, 0.10 * scale, h, axis)
            objs.append(cube_obj(
                f"urban:vehicle:tl_{mat_k}:{vid}:{name}",
                self._loc(x, y, forward, lateral + offset, zloc, axis),
                sec_dims, self._m(mat_k, "tail_light"), "vehicle-taillight", bevel=0.006,
            ))
        return objs

    def _door_handles(self, vid, x, y, axis, forward_positions, lateral, z, color_key):
        objs = []
        for i, fwd in enumerate(forward_positions):
            objs.append(cube_obj(
                f"urban:vehicle:door_handle:{vid}:{i}",
                self._loc(x, y, fwd, lateral * 1.022, z, axis),
                self._dims(0.09, 0.018, 0.032, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.006,
            ))
        return objs

    def _body_crease(self, vid, x, y, axis, length, lateral, z, color_key):
        """Horizontal character line / body crease along the door area."""
        return cube_obj(
            f"urban:vehicle:body_crease:{vid}",
            self._loc(x, y, 0, lateral * 1.008, z, axis),
            self._oriented_box_dims(length * 0.62, 0.018, 0.022, axis),
            self._m("signal_box"), "vehicle", bevel=0.003,
        )

    def _windshield_visor(self, vid, x, y, axis, forward, width, z, depth=0.055):
        """Dark tinted strip at top of windshield."""
        return cube_obj(
            f"urban:vehicle:windshield_visor:{vid}",
            self._loc(x, y, forward, 0, z, axis),
            self._dims(depth, width * 0.78, 0.028, axis),
            self._m("signal_box"), "vehicle", bevel=0.002,
        )

    def _antenna(self, vid, x, y, axis, forward, lateral, z_base, height=0.38):
        return cylinder_between(
            f"urban:vehicle:antenna:{vid}",
            self._loc(x, y, forward, lateral, z_base, axis),
            self._loc(x, y, forward, lateral, z_base + height, axis),
            0.006, self._m("signal_box"), "vehicle", vertices=6,
        )

    # -------------------------------------------------------------------------
    # Sedan
    # -------------------------------------------------------------------------

    def _create_sedan(self, vid, x, y, axis, color_key):
        length, width = 4.22, 1.78
        ground_z = 0.34
        stations = [
            (-length / 2,      0.36, 0.56),   # front fascia
            (-length * 0.30,   0.74, 0.82),   # windshield base / A-pillar
            (0.12,             0.82, 0.97),   # roofline peak
            (length * 0.38,    0.64, 0.78),   # C-pillar / rear window
            (length / 2,       0.38, 0.55),   # trunk
        ]
        objects = [self._car_shell_from_stations(
            f"urban:vehicle:shell:{vid}", stations, x, y, axis, width, color_key)]

        # Hood / bonnet
        objects.append(cube_obj(
            f"urban:vehicle:hood:{vid}",
            self._loc(x, y, -0.55, 0, 0.85, axis),
            self._dims(1.42, width * 0.86, 0.06, axis),
            self.mats[color_key], "vehicle", bevel=0.04,
        ))
        # Cabin interior (dark, visible through glass)
        objects.append(cube_obj(
            f"urban:vehicle:interior:{vid}",
            self._loc(x, y, -0.28, 0, 1.05, axis),
            self._dims(1.52, width * 0.70, 0.62, axis),
            self._m("car_interior", "signal_box"), "vehicle", bevel=0.04,
        ))
        # Windshield
        objects.append(cube_obj(
            f"urban:vehicle:windshield:{vid}",
            self._loc(x, y, -length * 0.24, 0, 1.10, axis),
            self._dims(0.06, width * 0.82, 0.58, axis),
            self._m("car_glass"), "vehicle", bevel=0.015,
        ))
        objects.append(self._windshield_visor(vid, x, y, axis, -length * 0.24, width, 1.36))
        # Rear windshield
        objects.append(cube_obj(
            f"urban:vehicle:rear_windshield:{vid}",
            self._loc(x, y, length * 0.32, 0, 1.08, axis),
            self._dims(0.06, width * 0.72, 0.48, axis),
            self._m("car_glass"), "vehicle", bevel=0.015,
        ))
        # Roof panel
        objects.append(cube_obj(
            f"urban:vehicle:roof:{vid}",
            self._loc(x, y, -0.15, 0, 1.48, axis),
            self._dims(1.28, width * 0.88, 0.06, axis),
            self.mats[color_key], "vehicle", bevel=0.04,
        ))
        # Trunk lid
        objects.append(cube_obj(
            f"urban:vehicle:trunk_lid:{vid}",
            self._loc(x, y, length * 0.38, 0, 0.92, axis),
            self._dims(0.92, width * 0.82, 0.055, axis),
            self.mats[color_key], "vehicle", bevel=0.03,
        ))
        # Rear spoiler
        objects.append(cube_obj(
            f"urban:vehicle:spoiler:{vid}",
            self._loc(x, y, length * 0.44, 0, 1.05, axis),
            self._dims(0.06, width * 0.56, 0.055, axis),
            self.mats[color_key], "vehicle", bevel=0.012,
        ))
        # Front bumper
        objects.append(cube_obj(
            f"urban:vehicle:front_bumper:{vid}",
            self._loc(x, y, -length / 2 - 0.06, 0, 0.44, axis),
            self._oriented_box_dims(0.12, width * 0.84, 0.22, axis),
            self._m("signal_box"), "vehicle", bevel=0.04,
        ))
        # Front grille background
        objects.append(cube_obj(
            f"urban:vehicle:grille_bg:{vid}",
            self._loc(x, y, -length / 2 - 0.07, 0, 0.60, axis),
            self._oriented_box_dims(0.04, width * 0.50, 0.22, axis),
            self._m("signal_box"), "vehicle", bevel=0.008,
        ))
        # Grille horizontal bars (4 bars)
        for gi, gz in enumerate([0.54, 0.60, 0.66, 0.72]):
            objects.append(cube_obj(
                f"urban:vehicle:grille_bar:{vid}:{gi}",
                self._loc(x, y, -length / 2 - 0.065, 0, gz, axis),
                self._oriented_box_dims(0.022, width * 0.48, 0.018, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.003,
            ))
        # Rear bumper
        objects.append(cube_obj(
            f"urban:vehicle:rear_bumper:{vid}",
            self._loc(x, y, length / 2 + 0.06, 0, 0.44, axis),
            self._oriented_box_dims(0.12, width * 0.84, 0.22, axis),
            self._m("signal_box"), "vehicle", bevel=0.04,
        ))
        # Exhaust pipe
        objects.append(cylinder_obj(
            f"urban:vehicle:exhaust:{vid}",
            self._loc(x, y, length / 2 + 0.06, -width * 0.24, 0.32, axis),
            0.045, 0.08, self._m("signal_box"), "vehicle", vertices=12,
        ))

        # Side windows, door seams, sills, mirrors, body crease, door handles
        for side, lat_sign in [("l", -1), ("r", 1)]:
            lat = lat_sign * width * 0.525
            objects.extend([
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:front",
                    self._loc(x, y, -0.08, lat, 1.12, axis),
                    self._dims(0.58, 0.04, 0.40, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:rear",
                    self._loc(x, y, -0.78, lat, 1.10, axis),
                    self._dims(0.50, 0.04, 0.36, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                # A-pillar
                cube_obj(
                    f"urban:vehicle:a_pillar:{vid}:{side}",
                    self._loc(x, y, -length * 0.28 + 0.08, lat * 0.92, 1.10, axis),
                    self._dims(0.065, 0.065, 0.62, axis),
                    self.mats[color_key], "vehicle", bevel=0.010,
                ),
                # C-pillar
                cube_obj(
                    f"urban:vehicle:c_pillar:{vid}:{side}",
                    self._loc(x, y, length * 0.30, lat * 0.90, 1.04, axis),
                    self._dims(0.062, 0.062, 0.55, axis),
                    self.mats[color_key], "vehicle", bevel=0.010,
                ),
                # Door seam
                cube_obj(
                    f"urban:vehicle:door_seam:{vid}:{side}",
                    self._loc(x, y, -0.42, lat * 1.005, 0.72, axis),
                    self._dims(0.022, 0.022, 0.56, axis),
                    self._m("signal_box"), "vehicle", bevel=0.002,
                ),
                # Side sill
                cube_obj(
                    f"urban:vehicle:sill:{vid}:{side}",
                    self._loc(x, y, 0.08, lat * 1.012, 0.36, axis),
                    self._oriented_box_dims(2.65, 0.038, 0.072, axis),
                    self._m("signal_box"), "vehicle", bevel=0.008,
                ),
                # Side mirror
                cube_obj(
                    f"urban:vehicle:mirror:{vid}:{side}",
                    self._loc(x, y, -length * 0.24 + 0.28, lat * 1.12, 1.08, axis),
                    self._dims(0.18, 0.10, 0.12, axis),
                    self.mats[color_key], "vehicle", bevel=0.022,
                ),
                # Mirror glass
                cube_obj(
                    f"urban:vehicle:mirror_glass:{vid}:{side}",
                    self._loc(x, y, -length * 0.24 + 0.28, lat * 1.12 + lat_sign * 0.058, 1.08, axis),
                    self._dims(0.15, 0.015, 0.098, axis),
                    self._m("car_glass"), "vehicle", bevel=0.005,
                ),
                self._body_crease(vid, x, y, axis, length, lat, 0.72, color_key),
            ])
            # Wheel arches
            for fi, fwd in enumerate([-1.15, 1.10]):
                objects.append(cube_obj(
                    f"urban:vehicle:wheel_arch:{vid}:{side}:{fi}",
                    self._loc(x, y, fwd, lat, 0.65, axis),
                    self._oriented_box_dims(0.78, 0.048, 0.22, axis),
                    self.mats[color_key], "vehicle", bevel=0.07,
                ))
            # Door handles
            objects.extend(self._door_handles(
                vid, x, y, axis, [-0.16, -0.76], lat, 1.02, color_key))

        # Headlights (3-part assembly)
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.extend(self._headlight_assembly(
                vid, side, x, y, -length / 2 - 0.012,
                lat_sign * width * 0.30, 0.72, axis))

        # Tail lights (3-section)
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.extend(self._taillight_assembly(
                vid, side, x, y, length / 2 + 0.012,
                lat_sign * width * 0.30, 0.70, axis))

        # Wipers
        for lat_sign, wlat in [(-1, -0.26), (1, 0.28)]:
            objects.append(cylinder_between(
                f"urban:vehicle:wiper:{vid}:{wlat}",
                self._loc(x, y, -length * 0.22, wlat, 1.20, axis),
                self._loc(x, y, -length * 0.30, wlat * 0.38, 1.32, axis),
                0.011, self._m("signal_box"), "vehicle", vertices=6,
            ))

        # License plates (front and rear)
        for fwd_sign, fwd_offset in [(-1, -length / 2 - 0.022), (1, length / 2 + 0.022)]:
            objects.append(cube_obj(
                f"urban:vehicle:plate:{vid}:{fwd_sign}",
                self._loc(x, y, fwd_offset, 0, 0.44, axis),
                self._oriented_box_dims(0.035, 0.52, 0.12, axis),
                self._m("license_plate"), "vehicle-license-plate", bevel=0.004,
            ))

        # Antenna
        objects.append(self._antenna(vid, x, y, axis, 0.18, -width * 0.16, 1.50))

        # Fog lights (small)
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.append(ellipsoid_obj(
                f"urban:vehicle:fog_light:{vid}:{side}",
                self._loc(x, y, -length / 2 - 0.032, lat_sign * width * 0.42, 0.44, axis),
                (0.018, 0.06, 0.04),
                self._m("headlight"), "vehicle-headlight", segments=12,
            ))

        # Wheels (4 corners)
        for wi, (fwd, lat) in enumerate([(-1.15, -0.80), (1.10, -0.80),
                                          (-1.15,  0.80), (1.10,  0.80)]):
            objects.extend(self._wheel_set(vid, wi, x, y, fwd, lat, axis, 0.30, ground_z))

        return objects, {"id": f"vehicle_{vid}", "type": "sedan",
                         "center": [x, y, 0], "axis": axis}

    # -------------------------------------------------------------------------
    # SUV
    # -------------------------------------------------------------------------

    def _create_suv(self, vid, x, y, axis, color_key):
        length, width = 4.70, 1.95
        ground_z = 0.44   # higher clearance
        wheel_r  = 0.36
        stations = [
            (-length / 2,      0.36, 0.58),
            (-length * 0.28,   0.74, 0.88),
            (0.08,             0.84, 1.06),   # taller roofline
            (length * 0.36,    0.78, 0.98),   # more upright rear
            (length / 2,       0.38, 0.60),
        ]
        objects = [self._car_shell_from_stations(
            f"urban:vehicle:shell:{vid}", stations, x, y, axis, width, color_key)]

        # Hood
        objects.append(cube_obj(
            f"urban:vehicle:hood:{vid}",
            self._loc(x, y, -0.62, 0, 0.92, axis),
            self._dims(1.55, width * 0.84, 0.065, axis),
            self.mats[color_key], "vehicle", bevel=0.045,
        ))
        # Interior
        objects.append(cube_obj(
            f"urban:vehicle:interior:{vid}",
            self._loc(x, y, -0.20, 0, 1.08, axis),
            self._dims(2.10, width * 0.68, 0.72, axis),
            self._m("car_interior", "signal_box"), "vehicle", bevel=0.04,
        ))
        # Windshield (less steeply raked)
        objects.append(cube_obj(
            f"urban:vehicle:windshield:{vid}",
            self._loc(x, y, -length * 0.22, 0, 1.16, axis),
            self._dims(0.075, width * 0.80, 0.64, axis),
            self._m("car_glass"), "vehicle", bevel=0.015,
        ))
        objects.append(self._windshield_visor(vid, x, y, axis, -length * 0.22, width, 1.44))
        # Rear hatch glass (nearly vertical)
        objects.append(cube_obj(
            f"urban:vehicle:rear_glass:{vid}",
            self._loc(x, y, length * 0.40, 0, 1.12, axis),
            self._dims(0.06, width * 0.72, 0.58, axis),
            self._m("car_glass"), "vehicle", bevel=0.015,
        ))
        # Roof
        objects.append(cube_obj(
            f"urban:vehicle:roof:{vid}",
            self._loc(x, y, -0.08, 0, 1.60, axis),
            self._dims(2.20, width * 0.86, 0.065, axis),
            self.mats[color_key], "vehicle", bevel=0.04,
        ))
        # Roof rack rails
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.append(cube_obj(
                f"urban:vehicle:roof_rack:{vid}:{side}",
                self._loc(x, y, -0.06, lat_sign * width * 0.36, 1.64, axis),
                self._dims(2.0, 0.055, 0.048, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.012,
            ))
        # Roof rack cross bars
        for ci, fwd in enumerate([-0.6, 0.35]):
            objects.append(cube_obj(
                f"urban:vehicle:rack_bar:{vid}:{ci}",
                self._loc(x, y, fwd, 0, 1.67, axis),
                self._oriented_box_dims(0.04, width * 0.72, 0.042, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.010,
            ))
        # Front bumper / skid plate
        objects.append(cube_obj(
            f"urban:vehicle:front_bumper:{vid}",
            self._loc(x, y, -length / 2 - 0.07, 0, 0.46, axis),
            self._oriented_box_dims(0.14, width * 0.82, 0.24, axis),
            self._m("signal_box"), "vehicle", bevel=0.04,
        ))
        # Skid plate (bottom, dark)
        objects.append(cube_obj(
            f"urban:vehicle:skid_plate:{vid}",
            self._loc(x, y, -length / 2 - 0.075, 0, 0.32, axis),
            self._oriented_box_dims(0.10, width * 0.78, 0.065, axis),
            self._m("chrome", "metal"), "vehicle", bevel=0.015,
        ))
        # Grille
        objects.append(cube_obj(
            f"urban:vehicle:grille:{vid}",
            self._loc(x, y, -length / 2 - 0.078, 0, 0.68, axis),
            self._oriented_box_dims(0.045, width * 0.52, 0.30, axis),
            self._m("signal_box"), "vehicle", bevel=0.010,
        ))
        for gi, gz in enumerate([0.56, 0.63, 0.70, 0.77, 0.84]):
            objects.append(cube_obj(
                f"urban:vehicle:grille_bar:{vid}:{gi}",
                self._loc(x, y, -length / 2 - 0.068, 0, gz, axis),
                self._oriented_box_dims(0.025, width * 0.50, 0.020, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.004,
            ))
        # Rear bumper
        objects.append(cube_obj(
            f"urban:vehicle:rear_bumper:{vid}",
            self._loc(x, y, length / 2 + 0.07, 0, 0.46, axis),
            self._oriented_box_dims(0.14, width * 0.82, 0.24, axis),
            self._m("signal_box"), "vehicle", bevel=0.04,
        ))
        # Fender flares (4 corners)
        for fi, (fwd, lat_sign) in enumerate([(-1.22, -1), (-1.22, 1), (1.18, -1), (1.18, 1)]):
            objects.append(cube_obj(
                f"urban:vehicle:fender_flare:{vid}:{fi}",
                self._loc(x, y, fwd, lat_sign * width * 0.535, 0.62, axis),
                self._oriented_box_dims(0.82, 0.055, 0.26, axis),
                self.mats[color_key], "vehicle", bevel=0.04,
            ))
        # Running boards
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.append(cube_obj(
                f"urban:vehicle:running_board:{vid}:{side}",
                self._loc(x, y, -0.05, lat_sign * width * 0.56, 0.38, axis),
                self._oriented_box_dims(2.20, 0.22, 0.060, axis),
                self._m("signal_box"), "vehicle", bevel=0.015,
            ))

        # Side windows
        for side, lat_sign in [("l", -1), ("r", 1)]:
            lat = lat_sign * width * 0.535
            objects.extend([
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:front",
                    self._loc(x, y, -0.04, lat, 1.18, axis),
                    self._dims(0.72, 0.045, 0.48, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:rear",
                    self._loc(x, y, -0.88, lat, 1.16, axis),
                    self._dims(0.68, 0.045, 0.44, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:quarter",
                    self._loc(x, y, -1.72, lat, 1.14, axis),
                    self._dims(0.42, 0.045, 0.38, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:door_seam:{vid}:{side}",
                    self._loc(x, y, -0.48, lat * 1.005, 0.78, axis),
                    self._dims(0.022, 0.022, 0.60, axis),
                    self._m("signal_box"), "vehicle", bevel=0.002,
                ),
                cube_obj(
                    f"urban:vehicle:sill:{vid}:{side}",
                    self._loc(x, y, 0.02, lat * 1.010, 0.38, axis),
                    self._oriented_box_dims(2.85, 0.042, 0.075, axis),
                    self._m("signal_box"), "vehicle", bevel=0.008,
                ),
                cube_obj(
                    f"urban:vehicle:mirror:{vid}:{side}",
                    self._loc(x, y, -length * 0.22 + 0.30, lat_sign * width * 0.60, 1.14, axis),
                    self._dims(0.20, 0.12, 0.13, axis),
                    self.mats[color_key], "vehicle", bevel=0.022,
                ),
                self._body_crease(vid, x, y, axis, length, lat, 0.78, color_key),
            ])
            # Wheel arches (taller, for larger wheels)
            for fi, fwd in enumerate([-1.22, 1.18]):
                objects.append(cube_obj(
                    f"urban:vehicle:wheel_arch:{vid}:{side}:{fi}",
                    self._loc(x, y, fwd, lat, 0.70, axis),
                    self._oriented_box_dims(0.88, 0.055, 0.26, axis),
                    self.mats[color_key], "vehicle", bevel=0.08,
                ))
            objects.extend(self._door_handles(
                vid, x, y, axis, [-0.18, -0.92], lat, 1.12, color_key))

        # Headlights
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.extend(self._headlight_assembly(
                vid, side, x, y, -length / 2 - 0.012,
                lat_sign * width * 0.28, 0.78, axis, scale=1.15))

        # Tail lights
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.extend(self._taillight_assembly(
                vid, side, x, y, length / 2 + 0.012,
                lat_sign * width * 0.28, 0.76, axis, scale=1.15))

        # Wheels (larger, higher ground clearance)
        for wi, (fwd, lat) in enumerate([(-1.22, -0.88), (1.18, -0.88),
                                          (-1.22,  0.88), (1.18,  0.88)]):
            objects.extend(self._wheel_set(vid, wi, x, y, fwd, lat, axis,
                                           wheel_r, ground_z, width_scale=1.12))

        # License plates
        for fwd_sign, fwd_offset in [(-1, -length / 2 - 0.022), (1, length / 2 + 0.022)]:
            objects.append(cube_obj(
                f"urban:vehicle:plate:{vid}:{fwd_sign}",
                self._loc(x, y, fwd_offset, 0, 0.46, axis),
                self._oriented_box_dims(0.035, 0.52, 0.12, axis),
                self._m("license_plate"), "vehicle-license-plate", bevel=0.004,
            ))

        # Wipers
        for wlat in [-0.28, 0.30]:
            objects.append(cylinder_between(
                f"urban:vehicle:wiper:{vid}:{wlat}",
                self._loc(x, y, -length * 0.20, wlat, 1.26, axis),
                self._loc(x, y, -length * 0.28, wlat * 0.40, 1.40, axis),
                0.012, self._m("signal_box"), "vehicle", vertices=6,
            ))

        objects.append(self._antenna(vid, x, y, axis, 0.22, -width * 0.14, 1.64))

        return objects, {"id": f"vehicle_{vid}", "type": "suv",
                         "center": [x, y, 0], "axis": axis}

    # -------------------------------------------------------------------------
    # Hatchback
    # -------------------------------------------------------------------------

    def _create_hatchback(self, vid, x, y, axis, color_key):
        length, width = 3.80, 1.72
        ground_z = 0.32
        stations = [
            (-length / 2,      0.36, 0.54),
            (-length * 0.28,   0.74, 0.80),
            (0.06,             0.82, 0.96),
            (length * 0.30,    0.74, 0.90),   # more upright rear than sedan
            (length / 2,       0.40, 0.58),
        ]
        objects = [self._car_shell_from_stations(
            f"urban:vehicle:shell:{vid}", stations, x, y, axis, width, color_key)]

        # Hood
        objects.append(cube_obj(
            f"urban:vehicle:hood:{vid}",
            self._loc(x, y, -0.48, 0, 0.82, axis),
            self._dims(1.30, width * 0.84, 0.058, axis),
            self.mats[color_key], "vehicle", bevel=0.04,
        ))
        # Interior
        objects.append(cube_obj(
            f"urban:vehicle:interior:{vid}",
            self._loc(x, y, -0.22, 0, 1.02, axis),
            self._dims(1.60, width * 0.70, 0.58, axis),
            self._m("car_interior", "signal_box"), "vehicle", bevel=0.04,
        ))
        # Windshield (sportier rake)
        objects.append(cube_obj(
            f"urban:vehicle:windshield:{vid}",
            self._loc(x, y, -length * 0.22, 0, 1.08, axis),
            self._dims(0.07, width * 0.80, 0.58, axis),
            self._m("car_glass"), "vehicle", bevel=0.014,
        ))
        objects.append(self._windshield_visor(vid, x, y, axis, -length * 0.22, width, 1.34))
        # Rear hatch glass (upright)
        objects.append(cube_obj(
            f"urban:vehicle:rear_glass:{vid}",
            self._loc(x, y, length * 0.36, 0, 1.06, axis),
            self._dims(0.065, width * 0.70, 0.52, axis),
            self._m("car_glass"), "vehicle", bevel=0.014,
        ))
        # Roof
        objects.append(cube_obj(
            f"urban:vehicle:roof:{vid}",
            self._loc(x, y, -0.10, 0, 1.44, axis),
            self._dims(1.35, width * 0.86, 0.058, axis),
            self.mats[color_key], "vehicle", bevel=0.038,
        ))
        # Bumpers
        objects.append(cube_obj(
            f"urban:vehicle:front_bumper:{vid}",
            self._loc(x, y, -length / 2 - 0.055, 0, 0.42, axis),
            self._oriented_box_dims(0.11, width * 0.82, 0.20, axis),
            self._m("signal_box"), "vehicle", bevel=0.038,
        ))
        objects.append(cube_obj(
            f"urban:vehicle:rear_bumper:{vid}",
            self._loc(x, y, length / 2 + 0.055, 0, 0.42, axis),
            self._oriented_box_dims(0.11, width * 0.82, 0.20, axis),
            self._m("signal_box"), "vehicle", bevel=0.038,
        ))
        # Grille
        objects.append(cube_obj(
            f"urban:vehicle:grille:{vid}",
            self._loc(x, y, -length / 2 - 0.068, 0, 0.60, axis),
            self._oriented_box_dims(0.038, width * 0.46, 0.22, axis),
            self._m("signal_box"), "vehicle", bevel=0.008,
        ))
        for gi, gz in enumerate([0.54, 0.60, 0.66, 0.72]):
            objects.append(cube_obj(
                f"urban:vehicle:grille_bar:{vid}:{gi}",
                self._loc(x, y, -length / 2 - 0.060, 0, gz, axis),
                self._oriented_box_dims(0.020, width * 0.44, 0.016, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.003,
            ))

        # Side panels
        for side, lat_sign in [("l", -1), ("r", 1)]:
            lat = lat_sign * width * 0.525
            objects.extend([
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:front",
                    self._loc(x, y, -0.04, lat, 1.10, axis),
                    self._dims(0.56, 0.038, 0.38, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:rear",
                    self._loc(x, y, -0.70, lat, 1.08, axis),
                    self._dims(0.46, 0.038, 0.34, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:door_seam:{vid}:{side}",
                    self._loc(x, y, -0.38, lat * 1.005, 0.70, axis),
                    self._dims(0.020, 0.020, 0.52, axis),
                    self._m("signal_box"), "vehicle", bevel=0.002,
                ),
                cube_obj(
                    f"urban:vehicle:sill:{vid}:{side}",
                    self._loc(x, y, 0.04, lat * 1.010, 0.34, axis),
                    self._oriented_box_dims(2.30, 0.036, 0.068, axis),
                    self._m("signal_box"), "vehicle", bevel=0.008,
                ),
                cube_obj(
                    f"urban:vehicle:mirror:{vid}:{side}",
                    self._loc(x, y, -length * 0.22 + 0.26, lat_sign * width * 0.56, 1.04, axis),
                    self._dims(0.16, 0.092, 0.108, axis),
                    self.mats[color_key], "vehicle", bevel=0.020,
                ),
                self._body_crease(vid, x, y, axis, length, lat, 0.70, color_key),
            ])
            for fi, fwd in enumerate([-1.08, 1.02]):
                objects.append(cube_obj(
                    f"urban:vehicle:wheel_arch:{vid}:{side}:{fi}",
                    self._loc(x, y, fwd, lat, 0.62, axis),
                    self._oriented_box_dims(0.72, 0.044, 0.20, axis),
                    self.mats[color_key], "vehicle", bevel=0.065,
                ))
            objects.extend(self._door_handles(
                vid, x, y, axis, [-0.14, -0.70], lat, 0.98, color_key))

        # Headlights / tail lights
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.extend(self._headlight_assembly(
                vid, side, x, y, -length / 2 - 0.010,
                lat_sign * width * 0.28, 0.68, axis, scale=0.92))
            objects.extend(self._taillight_assembly(
                vid, side, x, y, length / 2 + 0.010,
                lat_sign * width * 0.28, 0.66, axis, scale=0.92))

        # Rear roof spoiler (hatchback style)
        objects.append(cube_obj(
            f"urban:vehicle:spoiler:{vid}",
            self._loc(x, y, length * 0.36, 0, 1.30, axis),
            self._dims(0.055, width * 0.62, 0.065, axis),
            self.mats[color_key], "vehicle", bevel=0.014,
        ))

        # Wheels
        for wi, (fwd, lat) in enumerate([(-1.08, -0.76), (1.02, -0.76),
                                          (-1.08,  0.76), (1.02,  0.76)]):
            objects.extend(self._wheel_set(vid, wi, x, y, fwd, lat, axis, 0.28, ground_z))

        # License plates
        for fwd_sign, fwd_offset in [(-1, -length / 2 - 0.020), (1, length / 2 + 0.020)]:
            objects.append(cube_obj(
                f"urban:vehicle:plate:{vid}:{fwd_sign}",
                self._loc(x, y, fwd_offset, 0, 0.42, axis),
                self._oriented_box_dims(0.032, 0.48, 0.11, axis),
                self._m("license_plate"), "vehicle-license-plate", bevel=0.004,
            ))

        # Wipers
        for wlat in [-0.24, 0.26]:
            objects.append(cylinder_between(
                f"urban:vehicle:wiper:{vid}:{wlat}",
                self._loc(x, y, -length * 0.20, wlat, 1.16, axis),
                self._loc(x, y, -length * 0.28, wlat * 0.38, 1.28, axis),
                0.010, self._m("signal_box"), "vehicle", vertices=6,
            ))

        return objects, {"id": f"vehicle_{vid}", "type": "hatchback",
                         "center": [x, y, 0], "axis": axis}

    # -------------------------------------------------------------------------
    # Pickup truck
    # -------------------------------------------------------------------------

    def _create_pickup(self, vid, x, y, axis, color_key):
        cab_len  = 2.80    # front cab section
        bed_len  = 2.75    # rear bed section
        total_len = cab_len + bed_len
        width    = 2.05
        ground_z = 0.52    # high clearance
        wheel_r  = 0.40

        # Cab shell (front half of truck)
        cab_fwd_origin = -(bed_len / 2)   # cab center is shifted forward relative to truck center
        cab_stations = [
            (cab_fwd_origin - cab_len / 2,        0.36, 0.58),
            (cab_fwd_origin - cab_len * 0.28,     0.76, 0.90),
            (cab_fwd_origin,                       0.82, 1.04),
            (cab_fwd_origin + cab_len * 0.40,     0.80, 0.98),
            (cab_fwd_origin + cab_len / 2,        0.44, 0.65),
        ]
        objects = [self._car_shell_from_stations(
            f"urban:vehicle:shell:{vid}", cab_stations, x, y, axis, width, color_key)]

        # Truck bed walls (rear section)
        bed_fwd_origin = cab_len / 2   # relative to truck center
        bed_floor_z = ground_z - wheel_r + 0.20
        # Bed floor
        objects.append(cube_obj(
            f"urban:vehicle:bed_floor:{vid}",
            self._loc(x, y, bed_fwd_origin, 0, bed_floor_z, axis),
            self._dims(bed_len, width * 0.88, 0.045, axis),
            self._m("signal_box"), "vehicle", bevel=0.015,
        ))
        # Bed side walls
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.append(cube_obj(
                f"urban:vehicle:bed_wall:{vid}:{side}",
                self._loc(x, y, bed_fwd_origin, lat_sign * width * 0.48, bed_floor_z + 0.28, axis),
                self._dims(bed_len, 0.065, 0.55, axis),
                self.mats[color_key], "vehicle", bevel=0.022,
            ))
        # Bed front wall (cab-side)
        objects.append(cube_obj(
            f"urban:vehicle:bed_front_wall:{vid}",
            self._loc(x, y, bed_fwd_origin - bed_len / 2 + 0.04, 0, bed_floor_z + 0.28, axis),
            self._oriented_box_dims(0.08, width * 0.88, 0.55, axis),
            self.mats[color_key], "vehicle", bevel=0.022,
        ))
        # Tailgate (rear)
        objects.append(cube_obj(
            f"urban:vehicle:tailgate:{vid}",
            self._loc(x, y, bed_fwd_origin + bed_len / 2 - 0.04, 0, bed_floor_z + 0.28, axis),
            self._oriented_box_dims(0.08, width * 0.88, 0.52, axis),
            self.mats[color_key], "vehicle", bevel=0.022,
        ))
        # Bed rail caps
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.append(cube_obj(
                f"urban:vehicle:bed_rail:{vid}:{side}",
                self._loc(x, y, bed_fwd_origin, lat_sign * width * 0.48, bed_floor_z + 0.58, axis),
                self._dims(bed_len, 0.095, 0.042, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.016,
            ))

        # Cab hood
        objects.append(cube_obj(
            f"urban:vehicle:hood:{vid}",
            self._loc(x, y, cab_fwd_origin - 0.50, 0, 0.98, axis),
            self._dims(1.55, width * 0.82, 0.072, axis),
            self.mats[color_key], "vehicle", bevel=0.045,
        ))
        # Interior
        objects.append(cube_obj(
            f"urban:vehicle:interior:{vid}",
            self._loc(x, y, cab_fwd_origin + 0.05, 0, 1.12, axis),
            self._dims(1.45, width * 0.66, 0.70, axis),
            self._m("car_interior", "signal_box"), "vehicle", bevel=0.04,
        ))
        # Windshield
        objects.append(cube_obj(
            f"urban:vehicle:windshield:{vid}",
            self._loc(x, y, cab_fwd_origin - cab_len * 0.20, 0, 1.22, axis),
            self._dims(0.082, width * 0.78, 0.64, axis),
            self._m("car_glass"), "vehicle", bevel=0.015,
        ))
        objects.append(self._windshield_visor(vid, x, y, axis,
            cab_fwd_origin - cab_len * 0.20, width, 1.52))
        # Cab rear window
        objects.append(cube_obj(
            f"urban:vehicle:rear_cab_window:{vid}",
            self._loc(x, y, cab_fwd_origin + cab_len * 0.38, 0, 1.20, axis),
            self._dims(0.065, width * 0.68, 0.54, axis),
            self._m("car_glass"), "vehicle", bevel=0.014,
        ))
        # Cab roof
        objects.append(cube_obj(
            f"urban:vehicle:roof:{vid}",
            self._loc(x, y, cab_fwd_origin + 0.08, 0, 1.68, axis),
            self._dims(1.58, width * 0.84, 0.075, axis),
            self.mats[color_key], "vehicle", bevel=0.04,
        ))
        # Front bumper (chunky)
        objects.append(cube_obj(
            f"urban:vehicle:front_bumper:{vid}",
            self._loc(x, y, cab_fwd_origin - cab_len / 2 - 0.08, 0, 0.50, axis),
            self._oriented_box_dims(0.16, width * 0.88, 0.28, axis),
            self._m("chrome", "metal"), "vehicle", bevel=0.045,
        ))
        # Brush guard / bull bar
        objects.append(cube_obj(
            f"urban:vehicle:bull_bar:{vid}",
            self._loc(x, y, cab_fwd_origin - cab_len / 2 - 0.10, 0, 0.72, axis),
            self._oriented_box_dims(0.055, width * 0.40, 0.32, axis),
            self._m("chrome", "metal"), "vehicle", bevel=0.020,
        ))
        # Grille (large)
        objects.append(cube_obj(
            f"urban:vehicle:grille:{vid}",
            self._loc(x, y, cab_fwd_origin - cab_len / 2 - 0.085, 0, 0.80, axis),
            self._oriented_box_dims(0.05, width * 0.55, 0.38, axis),
            self._m("signal_box"), "vehicle", bevel=0.012,
        ))
        for gi, gz in enumerate([0.64, 0.72, 0.80, 0.88, 0.96]):
            objects.append(cube_obj(
                f"urban:vehicle:grille_bar:{vid}:{gi}",
                self._loc(x, y, cab_fwd_origin - cab_len / 2 - 0.072, 0, gz, axis),
                self._oriented_box_dims(0.028, width * 0.53, 0.024, axis),
                self._m("chrome", "metal"), "vehicle", bevel=0.005,
            ))
        # Rear bumper
        objects.append(cube_obj(
            f"urban:vehicle:rear_bumper:{vid}",
            self._loc(x, y, bed_fwd_origin + bed_len / 2 + 0.07, 0, 0.50, axis),
            self._oriented_box_dims(0.14, width * 0.82, 0.26, axis),
            self._m("chrome", "metal"), "vehicle", bevel=0.04,
        ))
        # Towing hitch
        objects.append(cube_obj(
            f"urban:vehicle:hitch:{vid}",
            self._loc(x, y, bed_fwd_origin + bed_len / 2 + 0.15, 0, 0.36, axis),
            self._oriented_box_dims(0.14, 0.065, 0.065, axis),
            self._m("chrome", "metal"), "vehicle", bevel=0.012,
        ))

        # Side panels
        for side, lat_sign in [("l", -1), ("r", 1)]:
            lat = lat_sign * width * 0.535
            fwd_c = cab_fwd_origin + 0.05
            objects.extend([
                cube_obj(
                    f"urban:vehicle:side_window:{vid}:{side}:front",
                    self._loc(x, y, fwd_c, lat, 1.24, axis),
                    self._dims(0.72, 0.048, 0.50, axis),
                    self._m("car_glass"), "vehicle", bevel=0.012,
                ),
                cube_obj(
                    f"urban:vehicle:door_seam:{vid}:{side}",
                    self._loc(x, y, fwd_c - 0.05, lat * 1.005, 0.90, axis),
                    self._dims(0.022, 0.022, 0.62, axis),
                    self._m("signal_box"), "vehicle", bevel=0.002,
                ),
                cube_obj(
                    f"urban:vehicle:sill:{vid}:{side}",
                    self._loc(x, y, fwd_c, lat * 1.010, 0.44, axis),
                    self._oriented_box_dims(3.20, 0.048, 0.082, axis),
                    self._m("signal_box"), "vehicle", bevel=0.010,
                ),
                cube_obj(
                    f"urban:vehicle:mirror:{vid}:{side}",
                    self._loc(x, y, cab_fwd_origin - cab_len * 0.18 + 0.32,
                              lat_sign * width * 0.62, 1.22, axis),
                    self._dims(0.22, 0.14, 0.16, axis),
                    self.mats[color_key], "vehicle", bevel=0.024,
                ),
                self._body_crease(vid, x, y, axis, total_len, lat, 0.85, color_key),
            ])
            # Wheel arches (large, flared)
            for fi, fwd in enumerate([cab_fwd_origin - 1.18, cab_fwd_origin + 1.10]):
                objects.append(cube_obj(
                    f"urban:vehicle:wheel_arch:{vid}:{side}:{fi}",
                    self._loc(x, y, fwd, lat, 0.78, axis),
                    self._oriented_box_dims(0.96, 0.060, 0.32, axis),
                    self.mats[color_key], "vehicle", bevel=0.09,
                ))
            objects.extend(self._door_handles(
                vid, x, y, axis, [fwd_c - 0.06], lat, 1.18, color_key))

        # Headlights / tail lights
        for side, lat_sign in [("l", -1), ("r", 1)]:
            objects.extend(self._headlight_assembly(
                vid, side, x, y,
                cab_fwd_origin - cab_len / 2 - 0.012,
                lat_sign * width * 0.30, 0.86, axis, scale=1.20))
            objects.extend(self._taillight_assembly(
                vid, side, x, y,
                bed_fwd_origin + bed_len / 2 + 0.012,
                lat_sign * width * 0.30, 0.78, axis, scale=1.20))

        # Wheels (4, with large radius)
        for wi, (fwd, lat) in enumerate([
            (cab_fwd_origin - 1.18, -0.92),
            (cab_fwd_origin + 1.10, -0.92),
            (cab_fwd_origin - 1.18,  0.92),
            (cab_fwd_origin + 1.10,  0.92),
        ]):
            objects.extend(self._wheel_set(vid, wi, x, y, fwd, lat, axis,
                                           wheel_r, ground_z, width_scale=1.18))

        # License plates
        for fwd_sign, fwd_offset in [
            (-1, cab_fwd_origin - cab_len / 2 - 0.022),
            (1, bed_fwd_origin + bed_len / 2 + 0.022),
        ]:
            objects.append(cube_obj(
                f"urban:vehicle:plate:{vid}:{fwd_sign}",
                self._loc(x, y, fwd_offset, 0, 0.50, axis),
                self._oriented_box_dims(0.038, 0.56, 0.13, axis),
                self._m("license_plate"), "vehicle-license-plate", bevel=0.004,
            ))

        # Wipers
        for wlat in [-0.30, 0.32]:
            objects.append(cylinder_between(
                f"urban:vehicle:wiper:{vid}:{wlat}",
                self._loc(x, y, cab_fwd_origin - cab_len * 0.17, wlat, 1.34, axis),
                self._loc(x, y, cab_fwd_origin - cab_len * 0.26, wlat * 0.42, 1.50, axis),
                0.013, self._m("signal_box"), "vehicle", vertices=6,
            ))

        objects.append(self._antenna(vid, x, y, axis, cab_fwd_origin + 0.20,
                                     -width * 0.14, 1.72))

        return objects, {"id": f"vehicle_{vid}", "type": "pickup",
                         "center": [x, y, 0], "axis": axis}

    # -------------------------------------------------------------------------
    # Bus
    # -------------------------------------------------------------------------

    def _create_bus(self, vid, x, y, axis, color_key):
        length, width = 5.6, 1.86
        objects = [
            cube_obj(
                f"urban:vehicle:bus_body:{vid}",
                (x, y, 0.82),
                self._dims(length, width, 1.48, axis),
                self.mats[color_key],
                "vehicle",
                bevel=0.12,
            ),
            cube_obj(
                f"urban:vehicle:bus_roof:{vid}",
                (x, y, 1.60),
                self._dims(length * 0.94, width * 0.92, 0.16, axis),
                self._m("car_white", color_key),
                "vehicle",
                bevel=0.05,
            ),
            cube_obj(
                f"urban:vehicle:bus_front_windshield:{vid}",
                self._loc(x, y, length / 2 + 0.035, 0, 1.22, axis),
                self._oriented_box_dims(0.035, width * 0.70, 0.55, axis),
                self._m("car_glass"),
                "vehicle",
                bevel=0.02,
            ),
            cube_obj(
                f"urban:vehicle:bus_route_display:{vid}",
                self._loc(x, y, length / 2 + 0.045, 0, 1.66, axis),
                self._oriented_box_dims(0.028, width * 0.55, 0.16, axis),
                self._m("signal_box"),
                "vehicle",
                bevel=0.006,
            ),
            cube_obj(
                f"urban:vehicle:bus_floor_trim:{vid}",
                (x, y, 0.36),
                self._oriented_box_dims(length * 0.96, width * 1.02, 0.08, axis),
                self._m("tire"),
                "vehicle",
                bevel=0.025,
            ),
        ]

        for i, forward in enumerate([-1.8, -0.8, 0.2, 1.2]):
            for side, lateral in [("l", -width * 0.52), ("r", width * 0.52)]:
                objects.append(
                    cube_obj(
                        f"urban:vehicle:bus_window:{vid}:{side}:{i}",
                        self._loc(x, y, forward, lateral, 1.15, axis),
                        self._dims(0.70, 0.035, 0.42, axis),
                        self._m("car_glass"),
                        "vehicle",
                        bevel=0.018,
                    )
                )

        objects.append(
            cube_obj(
                f"urban:vehicle:bus_door:{vid}",
                self._loc(x, y, 2.05, -width * 0.53, 0.78, axis),
                self._dims(0.62, 0.04, 0.90, axis),
                self._m("car_glass"),
                "vehicle",
                bevel=0.015,
            )
        )
        for i, line_z in enumerate([0.98, 1.36]):
            objects.append(
                cube_obj(
                    f"urban:vehicle:bus_side_pinstripe:{vid}:{i}",
                    self._loc(x, y, 0, -width * 0.535, line_z, axis),
                    self._oriented_box_dims(length * 0.88, 0.025, 0.035, axis),
                    self._m("license_plate"),
                    "vehicle",
                    bevel=0.003,
                )
            )
        for wi, (forward, lateral) in enumerate([(-1.95, -0.9), (1.8, -0.9), (-1.95, 0.9), (1.8, 0.9)]):
            objects.extend(self._wheel_set(vid, wi, x, y, forward, lateral, axis, 0.34, 0.40))

        for name, forward, mat_key in [("front", length / 2 + 0.02, "headlight"),
                                        ("rear", -length / 2 - 0.02, "tail_light")]:
            for lateral in [-0.45, 0.45]:
                objects.append(
                    cube_obj(
                        f"urban:vehicle:bus_{name}_light:{vid}:{lateral}",
                        self._loc(x, y, forward, lateral, 0.70, axis),
                        self._dims(0.045, 0.25, 0.14, axis),
                        self._m(mat_key),
                        "vehicle",
                        bevel=0.008,
                    )
                )
        return objects, {"id": f"vehicle_{vid}", "type": "bus", "center": [x, y, 0], "axis": axis}
