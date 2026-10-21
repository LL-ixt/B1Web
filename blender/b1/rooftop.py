"""Roof plant on the 10-storey block and the blue "B1" lettering."""
import math
import os

import bpy
from mathutils import Vector

from .config import BAND_D, PENTHOUSE_EDGES
from .materials import MAT
from .meshkit import MB, collection, cylinder, prism, quad_along


def rect(c, u, n, a, b):
    return [c - u * a - n * b, c + u * a - n * b, c + u * a + n * b, c - u * a + n * b]


def build_rooftop(info, parent):
    coll = collection(parent, 'B1_Rooftop')
    main = max(info.values(), key=lambda p: p['h'])
    H = main['h']
    tops = []
    ac = MB('Roof_ACUnits')
    for k, (key, inward, w_along, w_in, h) in enumerate(PENTHOUSE_EDGES):
        if key not in main.get('edges', {}):
            continue
        a, b, n = main['edges'][key]
        u = (b - a).normalized()
        c = (a + b) / 2 - n * inward
        ph = MB(f'Roof_Penthouse_{chr(65 + k)}')
        prism(ph, rect(c, u, n, w_along / 2, w_in / 2), H, H + h, 'B1_Wall', bottom=False)
        prism(ph, rect(c, u, n, w_along / 2 + 0.3, w_in / 2 + 0.3), H + h, H + h + 0.35, 'B1_Wall')
        # door + louvre on the face looking along the wing
        quad_along(ph, c + n * (w_in / 2) - u * 1.0, u, n, 0, 1.0, H, H + 2.2, 0.02, 'B1_FrameDark')
        quad_along(ph, c + n * (w_in / 2) + u * 1.0, u, n, 0, 1.6, H + 1.4, H + 2.4, 0.02, 'B1_Glass')
        ph.build(coll)
        tops.append((c, u, n, H + h + 0.35, w_along, w_in))
        for j in range(3):
            p = c - n * (w_in / 2 + 1.2) + u * (-w_along / 2 + 1.2 + j * 1.5)
            prism(ac, rect(p, u, n, 0.45, 0.3), H, H + 0.8, 'B1_Frame')

    if tops:
        # telecom mast with panel antennas on the higher penthouse
        c, u, n, zt, _, _ = tops[0]
        ms = MB('Roof_Mast')
        cylinder(ms, c, 0.12, zt, zt + 8.5, 'B1_Metal', 12)
        for k in range(3):
            ang = 2 * math.pi * k / 3
            d = Vector((math.cos(ang), math.sin(ang)))
            t = Vector((-d.y, d.x))
            p = c + d * 0.45
            prism(ms, [p - t * 0.15 - d * 0.05, p + t * 0.15 - d * 0.05, p + t * 0.15 + d * 0.05, p - t * 0.15 + d * 0.05],
                  zt + 6.3, zt + 8.0, 'B1_Frame')
            for leg_z in (zt, zt + 3.0):
                q = c + d * 1.0
                prism(ms, [q - t * 0.04, q + t * 0.04, c + t * 0.04, c - t * 0.04], leg_z, leg_z + 0.08, 'B1_Metal')
        ms.build(coll)
        # stainless water tanks on the main roof
        wt = MB('Roof_WaterTanks')
        for k in range(2):
            p = c - n * 6.0 + u * (-1.6 + k * 3.2)
            cylinder(wt, p, 0.75, H + 0.4, H + 2.2, 'B1_Steel', 20)
            prism(wt, rect(p, u, n, 0.8, 0.8), H, H + 0.4, 'B1_Metal')
        wt.build(coll)
    if len(tops) > 1:
        c, u, n, zt, wa, wi = tops[1]
        for k in range(4):
            p = c + u * (-wa / 2 + 1.5 + k * 2.2)
            prism(ac, rect(p, u, n, 0.5, 0.35), zt, zt + 0.9, 'B1_Frame')
        cylinder(ac, c + n * (wi / 2 - 1), 0.06, zt, zt + 3.5, 'B1_Metal', 8)
    ac.build(coll)

    # "B1" lettering on the upper gable of the 10-storey block
    if 'sign' in main:
        a, b, n = main['sign']
        u = (b - a).normalized()
        cu = bpy.data.curves.new('B1_Sign', 'FONT')
        cu.body = 'B1'
        cu.size = 2.4
        cu.extrude = 0.1
        cu.align_x = 'CENTER'
        for fp in ('C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/arial.ttf'):
            if os.path.exists(fp):
                cu.font = bpy.data.fonts.load(fp, check_existing=True)
                break
        ob = bpy.data.objects.new('B1_Sign', cu)
        ob.data.materials.append(MAT['B1_SignBlue'])
        pos = a + u * ((b - a).length * 0.23) + n * (BAND_D + 0.11)
        ob.location = (pos.x, pos.y, H - 0.25)
        ob.rotation_euler = (math.radians(90), 0, math.atan2(n.x, -n.y))
        coll.objects.link(ob)
