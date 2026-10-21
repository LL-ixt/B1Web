"""Round glazed stair tower rising above the lobby in the inner corner of the V."""
import math
import random

from mathutils import Vector

from .config import PARAPET, level_top
from .materials import GLASS_POOL
from .meshkit import MB, N3, V3, annulus, collection, cylinder, prism

R = 4.2
SEG = 48


def build_tower(arc, info, parent):
    coll = collection(parent, 'B1_StairTower')
    P, apex, HE = arc['P'], arc['apex'], arc['HE']
    H10 = max(p['h'] for p in info.values())
    bis = ((P[0] + P[-1]) / 2 + P[len(P) // 2]) / 2 - apex
    bis.normalize()
    c = apex + bis * 2.0
    rnd = random.Random(3)

    gl = MB('Tower_Glazing')
    bd = MB('Tower_Bands')
    for lv in range(5, 11):
        fb, ft = level_top(lv - 1), level_top(lv)
        oz0, oz1 = fb + 0.95, ft - 0.35
        for i in range(SEG):
            a0 = 2 * math.pi * i / SEG
            a1 = 2 * math.pi * (i + 1) / SEG
            pa, pb = c + Vector((math.cos(a0), math.sin(a0))) * R, c + Vector((math.cos(a1), math.sin(a1))) * R
            gl.face([V3(pa, oz0), V3(pb, oz0), V3(pb, oz1), V3(pa, oz1)], rnd.choice(GLASS_POOL[:14]),
                    N3((pa + pb) / 2 - c))
            if i % 3 == 0:
                dvec = Vector((math.cos(a0), math.sin(a0)))
                tvec = Vector((-dvec.y, dvec.x))
                prism(gl, [c + dvec * (R - 0.02) - tvec * 0.035, c + dvec * (R - 0.02) + tvec * 0.035,
                           c + dvec * (R + 0.08) + tvec * 0.035, c + dvec * (R + 0.08) - tvec * 0.035],
                      oz0, oz1, 'B1_Frame', top=False, bottom=False)
        annulus(bd, c, R - 0.4, R + 0.35, max(HE, fb - 0.35), fb + 0.95, 'B1_Wall')
    annulus(bd, c, R - 0.3, R + 0.35, H10 - 0.35, H10 + PARAPET, 'B1_Wall')
    gl.build(coll)
    bd.build(coll)

    rf = MB('Tower_Roof')
    cylinder(rf, c, R - 0.3, H10 - 0.4, H10, 'B1_Roof', 48)
    rf.build(coll)
