"""Surroundings from OSM: ground, roads, neighbouring blocks, parking, cars, trees."""
import math
import random

import bpy
from mathutils import Vector

from .config import B1_WAY
from .geom import area2, dist_to_poly, point_in_poly, right_normal
from .meshkit import MB, V3, cylinder, prism, quad_along


def build_ground(coll, size=260):
    ground = MB('Ctx_Ground')
    S = size
    ground.face([(-S, -S, 0), (S, -S, 0), (S, S, 0), (-S, S, 0)], 'Ctx_Paving', (0, 0, 1))
    ground.build(coll)


def build_context(osm, proj, coll, b1_outline):
    nodes, ways = osm
    rnd = random.Random(5)

    def poly_of(w):
        if not all(r in nodes for r in w['refs']):
            return None
        refs = w['refs'][:-1] if w['refs'][0] == w['refs'][-1] else w['refs']
        pts = [proj(r) for r in refs]
        return pts[::-1] if area2(pts) < 0 else pts

    blocked = [b1_outline]
    bld = MB('Ctx_Buildings')
    flat = MB('Ctx_Surfaces')
    shed = MB('Ctx_MotorbikeShed')
    for wid, w in ways.items():
        t = w['tags']
        closed = w['refs'][0] == w['refs'][-1]
        if wid == B1_WAY or not closed:
            continue
        if 'building' in t:
            pts = poly_of(w)
            if not pts:
                continue
            default = {'retail': 1, 'yes': 3}.get(t['building'], 4)
            lv = int(float(t.get('building:levels', default)))
            h = lv * 3.4
            prism(bld, pts, 0.0, h, 'Ctx_Wall', bottom=False)
            bld.fmat[-1] = bld._mi('Ctx_Roof')  # prism's last face is the roof
            for i in range(len(pts)):
                a, b = pts[i], pts[(i + 1) % len(pts)]
                L = (b - a).length
                if L < 4:
                    continue
                u, n = (b - a) / L, right_normal(b - a)
                for f in range(lv):
                    quad_along(bld, a, u, n, 0.8, L - 0.8, f * 3.4 + 0.9, f * 3.4 + 2.5, 0.03, 'B1_Glass')
            blocked.append(pts)
        elif t.get('amenity') == 'parking':
            pts = poly_of(w)
            if pts:
                flat.face([V3(p, 0.03) for p in pts], 'Ctx_Asphalt', (0, 0, 1))
                build_cars(coll, pts, b1_outline, rnd)
        elif t.get('amenity') == 'motorcycle_parking':
            pts = poly_of(w)
            if pts:
                shed.face([V3(p, 3.2) for p in pts], 'Ctx_Rust', (0, 0, 1))
                shed.face([V3(p, 3.12) for p in pts], 'Ctx_Rust', (0, 0, -1))
                for i in range(len(pts)):
                    a, b = pts[i], pts[(i + 1) % len(pts)]
                    for k in range(max(1, int((b - a).length // 4))):
                        q = a.lerp(b, k / max(1, int((b - a).length // 4)))
                        if dist_to_poly(q, b1_outline) > 0.5:
                            cylinder(shed, q, 0.06, 0.0, 3.12, 'B1_Metal', 8)
                blocked.append(pts)

    widths = {'tertiary': 9.0, 'residential': 6.0, 'service': 4.0, 'footway': 2.2,
              'path': 1.8, 'steps': 2.0, 'pedestrian': 4.0}
    tree_pts = []
    for wid, w in ways.items():
        hw = w['tags'].get('highway')
        if hw not in widths or not all(r in nodes for r in w['refs']):
            continue
        width = widths[hw]
        foot = hw in ('footway', 'path', 'steps', 'pedestrian')
        mat = 'Ctx_Footway' if foot else 'Ctx_Asphalt'
        z = 0.06 if foot else {'tertiary': 0.05, 'residential': 0.045}.get(hw, 0.04)
        pts = [proj(r) for r in w['refs']]
        if all(p.length > 260 for p in pts):
            continue
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if (b - a).length < 1e-3:
                continue
            n = right_normal(b - a) * (width / 2)
            flat.face([V3(a - n, z), V3(b - n, z), V3(b + n, z), V3(a + n, z)], mat, (0, 0, 1))
            if i:
                flat.face([V3(a + Vector((math.cos(k * math.pi / 4), math.sin(k * math.pi / 4))) * width / 2, z)
                           for k in range(8)], mat, (0, 0, 1))
            if not foot:
                L = (b - a).length
                for k in range(int(L // 11)):
                    q = a.lerp(b, (k + 0.5) * 11 / L)
                    for side in (-1, 1):
                        tree_pts.append(q + right_normal(b - a) * side * (width / 2 + 2.0))
    flat.build(coll)
    bld.build(coll)
    shed.build(coll)

    kept = []
    for q in tree_pts:
        if q.length > 140 or rnd.random() < 0.35:
            continue
        if any(point_in_poly(q, poly) or dist_to_poly(q, poly) < 3.5 for poly in blocked):
            continue
        if any((q - k).length < 6 for k in kept):
            continue
        kept.append(q)
    build_trees(coll, kept, rnd)


def build_cars(coll, lot, b1_outline, rnd):
    placed = []
    edges = sorted(((lot[(i + 1) % len(lot)] - lot[i]) for i in range(len(lot))), key=lambda e: -e.length)
    axis = edges[0].normalized()
    xs = [p.x for p in lot]
    ys = [p.y for p in lot]
    tries = 0
    while len(placed) < 14 and tries < 4000:
        tries += 1
        q = Vector((rnd.uniform(min(xs), max(xs)), rnd.uniform(min(ys), max(ys))))
        if not point_in_poly(q, lot) or dist_to_poly(q, lot) < 2.5 or dist_to_poly(q, b1_outline) < 6:
            continue
        if any((q - p).length < 5.5 for p in placed):
            continue
        placed.append(q)
    for k, q in enumerate(placed):
        u = axis if rnd.random() < 0.7 else Vector((-axis.y, axis.x))
        v = Vector((-u.y, u.x))
        paint = rnd.choice(['Car_White', 'Car_White', 'Car_Silver', 'Car_Black', 'Car_Red', 'Car_Grey'])
        mb = MB(f'Ctx_Car.{k:02d}')
        rect = lambda c, l, w: [c - u * l - v * w, c + u * l - v * w, c + u * l + v * w, c - u * l + v * w]
        prism(mb, rect(q, 2.2, 0.88), 0.3, 1.05, paint)
        prism(mb, rect(q - u * 0.2, 1.25, 0.8), 1.05, 1.5, 'B1_Glass')
        prism(mb, rect(q - u * 0.2, 1.1, 0.72), 1.5, 1.55, paint)
        for su in (-1.4, 1.4):
            for sv in (-0.8, 0.8):
                c = q + u * su + v * sv
                prism(mb, rect(c, 0.33, 0.12), 0.0, 0.62, 'Ctx_Tyre')
        mb.build(coll)


def build_trees(coll, pts, rnd):
    variants = []
    for k in range(3):
        mb = MB(f'Ctx_TreeMesh.{k}')
        cylinder(mb, Vector((0, 0)), 0.18, 0.0, 3.4, 'Ctx_Trunk', 10)
        r2 = random.Random(100 + k)
        for blob in range(4):
            c = Vector((r2.uniform(-1.2, 1.2), r2.uniform(-1.2, 1.2)))
            r = r2.uniform(1.6, 2.4)
            zc = r2.uniform(4.6, 6.2)
            # low-poly lumpy sphere
            rings, seg = 5, 8
            rows = []
            for i in range(rings + 1):
                phi = math.pi * i / rings
                row = []
                for j in range(seg):
                    th = 2 * math.pi * j / seg
                    jitter = 1 + r2.uniform(-0.15, 0.15) if 0 < i < rings else 1
                    row.append((c.x + r * jitter * math.sin(phi) * math.cos(th),
                                c.y + r * jitter * math.sin(phi) * math.sin(th),
                                zc + r * 0.85 * math.cos(phi)))
                rows.append(row)
            for i in range(rings):
                for j in range(seg):
                    q = [rows[i][j], rows[i][(j + 1) % seg], rows[i + 1][(j + 1) % seg], rows[i + 1][j]]
                    cen = ((q[0][0] + q[2][0]) / 2 - c.x, (q[0][1] + q[2][1]) / 2 - c.y, (q[0][2] + q[2][2]) / 2 - zc)
                    mb.face(q, 'Ctx_Leaf', cen, smooth=True)
        ob = mb.build(coll)
        variants.append(ob.data)
        bpy.data.objects.remove(ob)
    for k, q in enumerate(pts):
        ob = bpy.data.objects.new(f'Ctx_Tree.{k:03d}', variants[k % 3])
        s = rnd.uniform(0.85, 1.35)
        ob.scale = (s, s, s * rnd.uniform(0.9, 1.2))
        ob.rotation_euler = (0, 0, rnd.uniform(0, math.tau))
        ob.location = (q.x, q.y, 0)
        coll.objects.link(ob)
