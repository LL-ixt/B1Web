"""Build the exterior of HUST building B1 in Blender from an OpenStreetMap export.

Footprint and per-part heights come from OSM (way 184021007 + its building:part ways);
facade articulation (window strips, pilasters, round stair tower, curved entrance with
canopy, rooftop plant, "B1" sign) follows the reference photo ref.jpg.

Run inside a live Blender (e.g. via the BlenderMCP socket) or headless:
    blender -b -P build_b1.py -- "path/to/map.osm"
Re-running rebuilds only the "B1_OSM" collection.
"""
import math
import os
import random
import sys
import xml.etree.ElementTree as ET

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(globals().get('__file__', 'D:/Project III/B1Web/blender/build_b1.py')))
OSM_PATH = globals().get('OSM_PATH') or os.path.join(HERE, '..', 'map (3).osm')
if '--' in sys.argv and len(sys.argv) > sys.argv.index('--') + 1:
    OSM_PATH = sys.argv[sys.argv.index('--') + 1]

B1_WAY = '184021007'
ENTRANCE_PART = '1207082389'

GROUND_H = 4.5      # ground floor storey height (m)
FLOOR_H = 3.6       # typical storey height (m)
PARAPET = 1.0
BAND_D = 0.35       # projection of the horizontal spandrel bands
PIL_D = 0.45        # projection of the vertical pilasters
PIL_W = 0.5
BAY_W = 6.6         # target structural bay width

# Gable walls (perpendicular to a wing) get a solid wall with one column of small windows.
END_EDGES = {frozenset(e) for e in [
    ('1944623862', '1944623858'), ('1944623880', '1944623872'),
    ('8158144803', '8158144804'), ('8158144801', '8158144802'),
    ('8158144799', '8158144800'), ('8158144797', '8158144798'),
]}
SIGN_EDGE = frozenset(('8158144801', '8158144802'))  # west wing gable, seen in ref.jpg
PENTHOUSE_EDGES = [  # (gable edge of the 10-storey part, distance inward, size along edge, size inward, height)
    (frozenset(('8158144801', '8158144802')), 9.0, 8.0, 7.0, 4.2),
    (frozenset(('8158144803', '8158144804')), 15.0, 10.0, 12.0, 3.6),
]


def level_top(lv):
    return 0.0 if lv <= 0 else GROUND_H + (lv - 1) * FLOOR_H


# --------------------------------------------------------------------------- OSM

def load_osm(path):
    root = ET.parse(path).getroot()
    nodes = {n.get('id'): (float(n.get('lat')), float(n.get('lon'))) for n in root.iter('node')}
    ways = {}
    for w in root.iter('way'):
        ways[w.get('id')] = {
            'refs': [nd.get('ref') for nd in w.iter('nd')],
            'tags': {t.get('k'): t.get('v') for t in w.iter('tag')},
        }
    return nodes, ways


def make_projector(nodes, ref_ids):
    lat0 = sum(nodes[r][0] for r in ref_ids) / len(ref_ids)
    lon0 = sum(nodes[r][1] for r in ref_ids) / len(ref_ids)
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110574.0

    def proj(ref):
        lat, lon = nodes[ref]
        return Vector(((lon - lon0) * kx, (lat - lat0) * ky))
    return proj


# --------------------------------------------------------------------------- 2D helpers

def area2(pts):
    return sum(pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
               for i in range(len(pts))) / 2


def right_normal(d):
    return Vector((d.y, -d.x)).normalized()


def point_in_poly(p, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        a, b = poly[i], poly[j]
        if (a.y > p.y) != (b.y > p.y) and p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x:
            inside = not inside
        j = i
    return inside


def dist_to_poly(p, poly):
    best = 1e9
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
        best = min(best, (a + ab * t - p).length)
    return best


def catmull_rom(pts, samples=64):
    ext = [pts[0] * 2 - pts[1]] + list(pts) + [pts[-1] * 2 - pts[-2]]
    dense = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(20):
            t = k / 20
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(pts[-1].copy())
    cum = [0.0]
    for i in range(1, len(dense)):
        cum.append(cum[-1] + (dense[i] - dense[i - 1]).length)
    out, j = [], 0
    for k in range(samples + 1):
        s = cum[-1] * k / samples
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        t = (s - cum[j]) / max(cum[j + 1] - cum[j], 1e-9)
        out.append(dense[j].lerp(dense[j + 1], t))
    return out


# --------------------------------------------------------------------------- mesh builder

class MB:
    """Accumulates faces for one object; smooth faces share vertices so they shade smoothly."""

    def __init__(self, name):
        self.name = name
        self.verts, self.faces, self.fmat, self.fsmooth = [], [], [], []
        self.mats = []
        self.shared = {}

    def _mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def face(self, pts, mat, normal=None, smooth=False):
        pts = [tuple(p) for p in pts]
        if normal is not None:
            nx = ny = nz = 0.0
            for i in range(len(pts)):
                a, b = pts[i], pts[(i + 1) % len(pts)]
                nx += (a[1] - b[1]) * (a[2] + b[2])
                ny += (a[2] - b[2]) * (a[0] + b[0])
                nz += (a[0] - b[0]) * (a[1] + b[1])
            if nx * normal[0] + ny * normal[1] + nz * normal[2] < 0:
                pts.reverse()
        idx = []
        for p in pts:
            if smooth:
                key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
                if key not in self.shared:
                    self.shared[key] = len(self.verts)
                    self.verts.append(p)
                idx.append(self.shared[key])
            else:
                idx.append(len(self.verts))
                self.verts.append(p)
        self.faces.append(idx)
        self.fmat.append(self._mi(mat))
        self.fsmooth.append(smooth)

    def build(self, coll):
        if not self.faces:
            return None
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        for m in self.mats:
            me.materials.append(MAT[m])
        me.polygons.foreach_set('material_index', self.fmat)
        me.polygons.foreach_set('use_smooth', self.fsmooth)
        me.update()
        ob = bpy.data.objects.new(self.name, me)
        coll.objects.link(ob)
        return ob


def V3(p, z):
    return (p.x, p.y, z)


def N3(n, z=0.0):
    return (n.x, n.y, z)


def prism(mb, corners, z0, z1, mat, top=True, bottom=True):
    c = list(corners)
    if area2(c) < 0:
        c.reverse()
    for i in range(len(c)):
        a, b = c[i], c[(i + 1) % len(c)]
        if (b - a).length < 1e-6:
            continue
        mb.face([V3(a, z0), V3(b, z0), V3(b, z1), V3(a, z1)], mat, N3(right_normal(b - a)))
    if top:
        mb.face([V3(p, z1) for p in c], mat, (0, 0, 1))
    if bottom:
        mb.face([V3(p, z0) for p in c], mat, (0, 0, -1))


def box_along(mb, a, u, n, s0, s1, z0, z1, d0, d1, mat):
    if s1 - s0 < 1e-4 or z1 - z0 < 1e-4:
        return
    prism(mb, [a + u * s0 + n * d0, a + u * s1 + n * d0, a + u * s1 + n * d1, a + u * s0 + n * d1], z0, z1, mat)


def quad_along(mb, a, u, n, s0, s1, z0, z1, d, mat):
    p, q = a + u * s0 + n * d, a + u * s1 + n * d
    mb.face([V3(p, z0), V3(q, z0), V3(q, z1), V3(p, z1)], mat, N3(n))


def cylinder(mb, c, r, z0, z1, mat, seg=32, caps=True):
    ring = [c + Vector((math.cos(2 * math.pi * i / seg), math.sin(2 * math.pi * i / seg))) * r for i in range(seg)]
    for i in range(seg):
        a, b = ring[i], ring[(i + 1) % seg]
        mb.face([V3(a, z0), V3(b, z0), V3(b, z1), V3(a, z1)], mat, N3((a + b) / 2 - c), smooth=True)
    if caps:
        mb.face([V3(p, z1) for p in ring], mat, (0, 0, 1))
        mb.face([V3(p, z0) for p in ring], mat, (0, 0, -1))


def annulus(mb, c, r0, r1, z0, z1, mat, seg=64):
    dirs = [Vector((math.cos(2 * math.pi * i / seg), math.sin(2 * math.pi * i / seg))) for i in range(seg)]
    for i in range(seg):
        da, db = dirs[i], dirs[(i + 1) % seg]
        o0, o1, i0, i1 = c + da * r1, c + db * r1, c + da * r0, c + db * r0
        mb.face([V3(o0, z0), V3(o1, z0), V3(o1, z1), V3(o0, z1)], mat, N3(da + db), smooth=True)
        mb.face([V3(i0, z0), V3(i1, z0), V3(i1, z1), V3(i0, z1)], mat, N3(-(da + db)), smooth=True)
        mb.face([V3(i0, z1), V3(i1, z1), V3(o1, z1), V3(o0, z1)], mat, (0, 0, 1))
        mb.face([V3(i0, z0), V3(i1, z0), V3(o1, z0), V3(o0, z0)], mat, (0, 0, -1))


def ribbon(mb, P, N, i0, i1, d, z0, z1, mat, outward=True, smooth=True):
    sgn = 1 if outward else -1
    for i in range(i0, i1):
        a, b = P[i] + N[i] * d, P[i + 1] + N[i + 1] * d
        mb.face([V3(a, z0), V3(b, z0), V3(b, z1), V3(a, z1)], mat, N3((N[i] + N[i + 1]) * sgn), smooth=smooth)


def curved_solid(mb, P, N, i0, i1, z0, z1, d0, d1, mat):
    if i1 <= i0 or z1 - z0 < 1e-4:
        return
    ribbon(mb, P, N, i0, i1, d1, z0, z1, mat, True)
    ribbon(mb, P, N, i0, i1, d0, z0, z1, mat, False)
    for i in range(i0, i1):
        q = [P[i] + N[i] * d0, P[i + 1] + N[i + 1] * d0, P[i + 1] + N[i + 1] * d1, P[i] + N[i] * d1]
        mb.face([V3(p, z1) for p in q], mat, (0, 0, 1))
        mb.face([V3(p, z0) for p in q], mat, (0, 0, -1))
    for i, sgn in ((i0, -1), (i1, 1)):
        j = i + 1 if i == i0 else i - 1
        t = (P[i] - P[j]).normalized() if sgn > 0 else (P[i] - P[j]).normalized()
        p, q = P[i] + N[i] * d0, P[i] + N[i] * d1
        mb.face([V3(p, z0), V3(q, z0), V3(q, z1), V3(p, z1)], mat, N3(t))


# --------------------------------------------------------------------------- materials

MAT = {}


def principled(name, color, rough=0.5, metal=0.0, coat=0.0, emission=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    vals = {'Base Color': (*color, 1.0), 'Roughness': rough, 'Metallic': metal, 'Coat Weight': coat}
    for k, v in vals.items():
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    m.diffuse_color = (*color, 1.0)
    MAT[name] = m
    return m


def add_grime(mat_name, scale, dark):
    """Multiply the base colour by a soft object-space noise so big flat surfaces read as weathered."""
    m = MAT[mat_name]
    nt = m.node_tree
    if any(n.bl_idname == 'ShaderNodeTexNoise' for n in nt.nodes):
        return
    bsdf = nt.nodes['Principled BSDF']
    base = tuple(bsdf.inputs['Base Color'].default_value)
    coord = nt.nodes.new('ShaderNodeTexCoord')
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = 6.0
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = tuple(c * (1 - dark) for c in base[:3]) + (1,)
    ramp.color_ramp.elements[1].color = base
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[1].position = 0.65
    nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
    nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])


def make_materials():
    principled('B1_Wall', (0.80, 0.80, 0.77), 0.8)
    add_grime('B1_Wall', 0.6, 0.08)
    principled('B1_Frame', (0.62, 0.65, 0.66), 0.35, 0.6)
    principled('B1_FrameDark', (0.12, 0.13, 0.14), 0.4, 0.5)
    principled('B1_Glass', (0.035, 0.05, 0.065), 0.05, 0.0)
    principled('B1_GlassCurtain', (0.50, 0.46, 0.38), 0.6, 0.0, coat=1.0)
    principled('B1_GlassBlind', (0.40, 0.42, 0.43), 0.6, 0.0, coat=1.0)
    principled('B1_GlassDark', (0.008, 0.009, 0.01), 0.1)
    principled('B1_Roof', (0.38, 0.37, 0.35), 0.9)
    add_grime('B1_Roof', 0.3, 0.3)
    principled('B1_SignBlue', (0.03, 0.20, 0.62), 0.3)
    principled('B1_Metal', (0.55, 0.56, 0.58), 0.35, 1.0)
    principled('B1_Steel', (0.8, 0.8, 0.82), 0.15, 1.0)
    principled('Ctx_Asphalt', (0.07, 0.07, 0.075), 0.9)
    add_grime('Ctx_Asphalt', 0.4, 0.3)
    principled('Ctx_Paving', (0.36, 0.34, 0.31), 0.9)
    add_grime('Ctx_Paving', 0.15, 0.25)
    principled('Ctx_Footway', (0.45, 0.38, 0.33), 0.9)
    principled('Ctx_Rust', (0.33, 0.17, 0.08), 0.7, 0.3)
    principled('Ctx_Wall', (0.70, 0.66, 0.58), 0.85)
    add_grime('Ctx_Wall', 0.5, 0.12)
    principled('Ctx_Roof', (0.30, 0.29, 0.28), 0.9)
    principled('Ctx_Leaf', (0.07, 0.22, 0.035), 0.8)
    principled('Ctx_Trunk', (0.13, 0.09, 0.06), 0.9)
    principled('Ctx_Tyre', (0.02, 0.02, 0.02), 0.8)
    for name, col in [('Car_White', (0.8, 0.8, 0.8)), ('Car_Silver', (0.45, 0.46, 0.48)),
                      ('Car_Black', (0.02, 0.02, 0.025)), ('Car_Red', (0.55, 0.03, 0.03)),
                      ('Car_Grey', (0.18, 0.19, 0.2))]:
        principled(name, col, 0.25, 0.4, coat=1.0)


GLASS_POOL = ['B1_Glass'] * 12 + ['B1_GlassCurtain'] * 4 + ['B1_GlassBlind'] * 2 + ['B1_GlassDark'] * 2


# --------------------------------------------------------------------------- B1 facades

def strip_window(mb, rnd, a, u, n, s0, s1, z0, z1, panes, transom):
    """Recessed aluminium strip window: glass on the wall line, mullions/transom in front."""
    fw = 0.07
    pw = (s1 - s0) / panes
    zt = z1 - (z1 - z0) * transom
    for i in range(panes):
        p0, p1 = s0 + i * pw, s0 + (i + 1) * pw
        quad_along(mb, a, u, n, p0, p1, z0, zt, 0.0, rnd.choice(GLASS_POOL))
        quad_along(mb, a, u, n, p0, p1, zt, z1, 0.0, rnd.choice(GLASS_POOL))
    for i in range(panes + 1):
        sx = s0 + i * pw
        box_along(mb, a, u, n, max(s0, sx - fw / 2), min(s1, sx + fw / 2), z0, z1, 0.0, 0.08, 'B1_Frame')
    box_along(mb, a, u, n, s0, s1, zt - 0.03, zt + 0.03, 0.0, 0.08, 'B1_Frame')
    box_along(mb, a, u, n, s0, s1, z0, z0 + fw, 0.0, 0.08, 'B1_Frame')
    box_along(mb, a, u, n, s0, s1, z1 - fw, z1, 0.0, 0.08, 'B1_Frame')


def floors_in(levels, z0, z1):
    for lv in range(1, levels + 1):
        fb, ft = level_top(lv - 1), level_top(lv)
        if fb >= z0 - 0.01 and ft <= z1 + 0.01:
            yield lv, fb, ft


def facade_bays(mb, rnd, a, b, n, levels, z0, z1, ext):
    L = (b - a).length
    u = (b - a) / L
    nb = max(1, round(L / BAY_W))
    bw = L / nb
    for lv, fb, ft in floors_in(levels, z0, z1):
        oz0, oz1 = fb + 0.95, ft - 0.35
        ground = lv == 1
        for j in range(nb):
            strip_window(mb, rnd, a, u, n, j * bw + PIL_W / 2, (j + 1) * bw - PIL_W / 2, oz0, oz1,
                         5 if ground else 6, 0.3 if ground else 0.26)
    slabs = [level_top(lv) for lv in range(0, levels)]
    for s in slabs:
        if s >= z0 - 0.01 and s < z1 - 0.5:
            box_along(mb, a, u, n, -ext[0](BAND_D), L + ext[1](BAND_D),
                      max(z0, s - 0.35), min(z1, s + 0.95), 0.0, BAND_D, 'B1_Wall')
    box_along(mb, a, u, n, -ext[0](BAND_D), L + ext[1](BAND_D), z1 - 0.35, z1 + PARAPET, -0.25, BAND_D, 'B1_Wall')
    for j in range(nb + 1):
        s0 = -ext[0](PIL_D) if j == 0 else j * bw - PIL_W / 2
        s1 = L + ext[1](PIL_D) if j == nb else j * bw + PIL_W / 2
        box_along(mb, a, u, n, s0, s1, z0, z1 + PARAPET + 0.05, 0.0, PIL_D, 'B1_Wall')


def facade_end(mb, rnd, a, b, n, levels, z0, z1, ext, win_t=0.5, windows=True):
    L = (b - a).length
    u = (b - a) / L
    ww = 1.3
    wc = L * win_t
    if not windows or L < 3:
        box_along(mb, a, u, n, -ext[0](BAND_D), L + ext[1](BAND_D), z0, z1, 0.0, BAND_D, 'B1_Wall')
    else:
        box_along(mb, a, u, n, -ext[0](BAND_D), wc - ww / 2, z0, z1, 0.0, BAND_D, 'B1_Wall')
        box_along(mb, a, u, n, wc + ww / 2, L + ext[1](BAND_D), z0, z1, 0.0, BAND_D, 'B1_Wall')
        cur = z0
        for lv, fb, ft in floors_in(levels, z0, z1):
            oz0 = fb + (1.3 if lv == 1 else 1.0)
            oz1 = oz0 + (2.0 if lv == 1 else 1.6)
            box_along(mb, a, u, n, wc - ww / 2, wc + ww / 2, cur, oz0, 0.0, BAND_D, 'B1_Wall')
            quad_along(mb, a, u, n, wc - ww / 2, wc + ww / 2, oz0, oz1, 0.12, rnd.choice(GLASS_POOL))
            box_along(mb, a, u, n, wc - ww / 2, wc + ww / 2, oz0 + 0.62 * (oz1 - oz0) - 0.03,
                      oz0 + 0.62 * (oz1 - oz0) + 0.03, 0.12, 0.2, 'B1_Frame')
            box_along(mb, a, u, n, wc - 0.03, wc + 0.03, oz0, oz0 + 0.62 * (oz1 - oz0), 0.12, 0.2, 'B1_Frame')
            box_along(mb, a, u, n, wc - ww / 2 - 0.1, wc + ww / 2 + 0.1, oz0 - 0.08, oz0, BAND_D, BAND_D + 0.08, 'B1_Wall')
            cur = oz1
        box_along(mb, a, u, n, wc - ww / 2, wc + ww / 2, cur, z1, 0.0, BAND_D, 'B1_Wall')
    for lv in range(1, levels):
        s = level_top(lv)
        if z0 + 0.3 < s < z1 - 0.3:
            box_along(mb, a, u, n, -ext[0](BAND_D), L + ext[1](BAND_D), s - 0.06, s + 0.06, BAND_D, BAND_D + 0.04, 'B1_Wall')
    box_along(mb, a, u, n, -ext[0](BAND_D), L + ext[1](BAND_D), z1, z1 + PARAPET, -0.25, BAND_D, 'B1_Wall')


def corner_ext(prev_pt, pt, next_pt):
    d0, d1 = (pt - prev_pt).normalized(), (next_pt - pt).normalized()
    cross = d0.x * d1.y - d0.y * d1.x
    ang = abs(math.atan2(cross, d0.dot(d1)))
    if cross <= 1e-6:
        return lambda d: 0.0
    return lambda d: min(d * math.tan(ang / 2), 2 * d)


def build_parts(osm, proj, coll):
    nodes, ways = osm
    outline = set(ways[B1_WAY]['refs'])
    parts = []
    for wid, w in ways.items():
        if 'building:part' not in w['tags'] or not any(r in outline for r in w['refs']):
            continue
        refs = w['refs'][:-1] if w['refs'][0] == w['refs'][-1] else w['refs']
        pts = [proj(r) for r in refs]
        if area2(pts) < 0:
            refs, pts = refs[::-1], pts[::-1]
        lv = int(w['tags'].get('building:levels', '1'))
        parts.append({'id': wid, 'refs': refs, 'pts': pts, 'levels': lv, 'h': level_top(lv)})
    by_edge = {}
    for p in parts:
        for i in range(len(p['refs'])):
            by_edge.setdefault(frozenset((p['refs'][i], p['refs'][(i + 1) % len(p['refs'])])), []).append(p)

    rnd = random.Random(7)
    mb = MB('B1_Facades')
    roofs = MB('B1_Roofs')
    info = {}
    for p in parts:
        info[p['id']] = p
        roofs.face([V3(q, p['h']) for q in p['pts']], 'B1_Roof', (0, 0, 1))
        if p['id'] == ENTRANCE_PART:
            continue
        refs, pts, n_pts = p['refs'], p['pts'], len(p['pts'])
        for i in range(n_pts):
            ra, rb = refs[i], refs[(i + 1) % n_pts]
            key = frozenset((ra, rb))
            z0 = max([0.0] + [o['h'] for o in by_edge[key] if o is not p])
            if z0 >= p['h'] - 0.01:
                continue
            a, b = pts[i], pts[(i + 1) % n_pts]
            n = right_normal(b - a)
            ext = (corner_ext(pts[i - 1], a, b), corner_ext(a, b, pts[(i + 2) % n_pts]))
            if key in END_EDGES:
                facade_end(mb, rnd, a, b, n, p['levels'], z0, p['h'], ext,
                           win_t=0.22 if key == SIGN_EDGE else 0.5)
                if key == SIGN_EDGE:
                    p['sign'] = (a, b, n)
            elif (b - a).length < 3:
                facade_end(mb, rnd, a, b, n, p['levels'], z0, p['h'], ext, windows=False)
            else:
                facade_bays(mb, rnd, a, b, n, p['levels'], z0, p['h'], ext)
            p.setdefault('edges', {})[key] = (a, b, n)
    mb.build(coll)
    roofs.build(coll)
    return parts, info


# --------------------------------------------------------------------------- entrance + tower

def build_entrance(osm, proj, coll, info):
    nodes, ways = osm
    outline = set(ways[B1_WAY]['refs'])
    refs = ways[ENTRANCE_PART]['refs'][:-1]
    arc_refs = [r for r in refs if r in outline]
    apex = proj([r for r in refs if r not in outline][0])
    P = catmull_rom([proj(r) for r in arc_refs], 64)
    NS = len(P) - 1
    N = []
    for i in range(len(P)):
        t = (P[min(i + 1, NS)] - P[max(i - 1, 0)]).normalized()
        nrm = Vector((t.y, -t.x))
        if nrm.dot(P[i] - apex) < 0:
            nrm = -nrm
        N.append(nrm)
    HE = level_top(4)
    idx = lambda f: int(round(f * NS))
    rnd = random.Random(3)
    mb = MB('B1_Entrance')

    # roof + soffit over the recessed ground floor
    poly = P + [apex]
    mb.face([V3(q, HE) for q in poly], 'B1_Roof', (0, 0, 1))
    mb.face([V3(q, GROUND_H) for q in poly], 'B1_Wall', (0, 0, -1))

    # upper curved wall with two large gridded windows and a narrow slit window
    gz0, gz1 = level_top(1) + 0.9, level_top(3) - 0.35
    openings = [(idx(0.03), idx(0.07)), (idx(0.13), idx(0.43)), (idx(0.57), idx(0.87))]
    wall_top = HE - 1.4
    cur = 0
    for o0, o1 in openings:
        curved_solid(mb, P, N, cur, o0, GROUND_H, wall_top, -0.3, 0.0, 'B1_Wall')
        curved_solid(mb, P, N, o0, o1, GROUND_H, gz0, -0.3, 0.0, 'B1_Wall')
        curved_solid(mb, P, N, o0, o1, gz1, wall_top, -0.3, 0.0, 'B1_Wall')
        rows = 5
        for r in range(rows):
            za, zb = gz0 + (gz1 - gz0) * r / rows, gz0 + (gz1 - gz0) * (r + 1) / rows
            for i in range(o0, o1):
                ribbon(mb, P, N, i, i + 1, -0.2, za, zb, rnd.choice(GLASS_POOL), smooth=False)
            if r:
                curved_solid(mb, P, N, o0, o1, za - 0.04, za + 0.04, -0.2, -0.1, 'B1_Frame')
        for i in range(o0, o1 + 1, 2):
            t = (P[min(i + 1, NS)] - P[max(i - 1, 0)]).normalized()
            c = [P[i] + N[i] * -0.2 - t * 0.04, P[i] + N[i] * -0.2 + t * 0.04,
                 P[i] + N[i] * -0.1 + t * 0.04, P[i] + N[i] * -0.1 - t * 0.04]
            prism(mb, c, gz0, gz1, 'B1_Frame')
        cur = o1
    curved_solid(mb, P, N, cur, NS, GROUND_H, wall_top, -0.3, 0.0, 'B1_Wall')
    curved_solid(mb, P, N, 0, NS, wall_top, HE + 0.7, -0.3, 0.35, 'B1_Wall')          # cornice / parapet
    curved_solid(mb, P, N, 0, NS, GROUND_H - 0.05, GROUND_H + 0.35, -0.3, 0.15, 'B1_Wall')  # slab edge

    # recessed glazed ground floor with doors
    rec = -2.2
    for i in range(NS):
        ribbon(mb, P, N, i, i + 1, rec, 0.0, 3.1, 'B1_Glass', smooth=False)
        ribbon(mb, P, N, i, i + 1, rec, 3.1, GROUND_H, rnd.choice(GLASS_POOL), smooth=False)
    curved_solid(mb, P, N, 0, NS, 3.07, 3.17, rec, rec + 0.1, 'B1_FrameDark')
    for i in range(0, NS + 1, 3):
        t = (P[min(i + 1, NS)] - P[max(i - 1, 0)]).normalized()
        c = [P[i] + N[i] * rec - t * 0.05, P[i] + N[i] * rec + t * 0.05,
             P[i] + N[i] * (rec + 0.12) + t * 0.05, P[i] + N[i] * (rec + 0.12) - t * 0.05]
        prism(mb, c, 0.0, GROUND_H, 'B1_FrameDark')
    for i, j in ((0, 1), (NS, NS - 1)):
        t = (P[j] - P[i]).normalized()
        prism(mb, [P[i], P[i] + N[i] * (rec - 0.3), P[i] + N[i] * (rec - 0.3) + t * 0.5, P[i] + t * 0.5],
              0.0, GROUND_H, 'B1_Wall')
    for i in range(4, NS - 3, 5):
        cylinder(mb, P[i] + N[i] * -0.6, 0.28, 0.0, GROUND_H, 'B1_Wall', 20)

    # entrance canopy on two round columns
    ca, cb = idx(0.3), idx(0.7)
    curved_solid(mb, P, N, ca, cb, GROUND_H + 0.25, GROUND_H + 0.6, 0.0, 3.8, 'B1_Wall')
    for f in (0.36, 0.64):
        i = idx(f)
        cylinder(mb, P[i] + N[i] * 3.2, 0.42, 0.0, GROUND_H + 0.25, 'B1_Wall', 24)
    mb.build(coll)

    # round stair tower in the inner corner of the V, above the entrance block
    H10 = max(p['h'] for p in info.values())
    bis = ((P[0] + P[-1]) / 2 + P[NS // 2]) / 2 - apex
    bis.normalize()
    c = apex + bis * 2.0
    R = 4.2
    tw = MB('B1_StairTower')
    for lv in range(5, 11):
        fb, ft = level_top(lv - 1), level_top(lv)
        oz0, oz1 = fb + 0.95, ft - 0.35
        seg = 48
        for i in range(seg):
            a0 = 2 * math.pi * i / seg
            a1 = 2 * math.pi * (i + 1) / seg
            pa, pb = c + Vector((math.cos(a0), math.sin(a0))) * R, c + Vector((math.cos(a1), math.sin(a1))) * R
            tw.face([V3(pa, oz0), V3(pb, oz0), V3(pb, oz1), V3(pa, oz1)], rnd.choice(GLASS_POOL[:14]),
                    N3((pa + pb) / 2 - c))
            if i % 3 == 0:
                dvec = Vector((math.cos(a0), math.sin(a0)))
                tvec = Vector((-dvec.y, dvec.x))
                prism(tw, [c + dvec * (R - 0.02) - tvec * 0.035, c + dvec * (R - 0.02) + tvec * 0.035,
                           c + dvec * (R + 0.08) + tvec * 0.035, c + dvec * (R + 0.08) - tvec * 0.035],
                      oz0, oz1, 'B1_Frame', top=False, bottom=False)
        annulus(tw, c, R - 0.4, R + 0.35, max(HE, fb - 0.35), fb + 0.95, 'B1_Wall')
    annulus(tw, c, R - 0.3, R + 0.35, H10 - 0.35, H10 + PARAPET, 'B1_Wall')
    cylinder(tw, c, R - 0.3, H10 - 0.4, H10, 'B1_Roof', 48)
    tw.build(coll)


# --------------------------------------------------------------------------- rooftop + sign

def build_rooftop(coll, info):
    main = max(info.values(), key=lambda p: p['h'])
    H = main['h']
    mb = MB('B1_Rooftop')
    rnd = random.Random(11)
    tops = []
    for key, inward, w_along, w_in, h in PENTHOUSE_EDGES:
        if key not in main.get('edges', {}):
            continue
        a, b, n = main['edges'][key]
        u = (b - a).normalized()
        c = (a + b) / 2 - n * inward
        corners = [c - u * w_along / 2 - n * w_in / 2, c + u * w_along / 2 - n * w_in / 2,
                   c + u * w_along / 2 + n * w_in / 2, c - u * w_along / 2 + n * w_in / 2]
        prism(mb, corners, H, H + h, 'B1_Wall', bottom=False)
        prism(mb, [c - u * (w_along / 2 + 0.3) - n * (w_in / 2 + 0.3), c + u * (w_along / 2 + 0.3) - n * (w_in / 2 + 0.3),
                   c + u * (w_along / 2 + 0.3) + n * (w_in / 2 + 0.3), c - u * (w_along / 2 + 0.3) + n * (w_in / 2 + 0.3)],
              H + h, H + h + 0.35, 'B1_Wall')
        # door + louvre on the face looking along the wing
        quad_along(mb, c + n * (w_in / 2) - u * 1.0, u, n, 0, 1.0, H, H + 2.2, 0.02, 'B1_FrameDark')
        quad_along(mb, c + n * (w_in / 2) + u * 1.0, u, n, 0, 1.6, H + 1.4, H + 2.4, 0.02, 'B1_Glass')
        tops.append((c, u, n, H + h + 0.35, w_along, w_in))
        # AC condensers along the penthouse
        for k in range(3):
            p = c - n * (w_in / 2 + 1.2) + u * (-w_along / 2 + 1.2 + k * 1.5)
            prism(mb, [p - u * 0.45 - n * 0.3, p + u * 0.45 - n * 0.3, p + u * 0.45 + n * 0.3, p - u * 0.45 + n * 0.3],
                  H, H + 0.8, 'B1_Frame')

    if tops:
        # telecom mast with panel antennas on the higher penthouse
        c, u, n, zt, _, _ = tops[0]
        cylinder(mb, c, 0.12, zt, zt + 8.5, 'B1_Metal', 12)
        for k in range(3):
            ang = 2 * math.pi * k / 3
            d = Vector((math.cos(ang), math.sin(ang)))
            t = Vector((-d.y, d.x))
            p = c + d * 0.45
            prism(mb, [p - t * 0.15 - d * 0.05, p + t * 0.15 - d * 0.05, p + t * 0.15 + d * 0.05, p - t * 0.15 + d * 0.05],
                  zt + 6.3, zt + 8.0, 'B1_Frame')
            for leg_z in (zt, zt + 3.0):
                q = c + d * 1.0
                prism(mb, [q - t * 0.04, q + t * 0.04, c + t * 0.04, c - t * 0.04], leg_z, leg_z + 0.08, 'B1_Metal')
        # stainless water tanks on the main roof
        for k in range(2):
            p = c - n * 6.0 + u * (-1.6 + k * 3.2)
            cylinder(mb, p, 0.75, H + 0.4, H + 2.2, 'B1_Steel', 20)
            prism(mb, [p - u * 0.8 - n * 0.8, p + u * 0.8 - n * 0.8, p + u * 0.8 + n * 0.8, p - u * 0.8 + n * 0.8],
                  H, H + 0.4, 'B1_Metal')
    if len(tops) > 1:
        c, u, n, zt, wa, wi = tops[1]
        for k in range(4):
            p = c + u * (-wa / 2 + 1.5 + k * 2.2)
            prism(mb, [p - u * 0.5 - n * 0.35, p + u * 0.5 - n * 0.35, p + u * 0.5 + n * 0.35, p - u * 0.5 + n * 0.35],
                  zt, zt + 0.9, 'B1_Frame')
        cylinder(mb, c + n * (wi / 2 - 1), 0.06, zt, zt + 3.5, 'B1_Metal', 8)
    mb.build(coll)

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


# --------------------------------------------------------------------------- context

def build_context(osm, proj, coll, b1_outline):
    nodes, ways = osm
    rnd = random.Random(5)
    ground = MB('Ctx_Ground')
    S = 260
    ground.face([(-S, -S, 0), (S, -S, 0), (S, S, 0), (-S, S, 0)], 'Ctx_Paving', (0, 0, 1))
    ground.build(coll)

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


# --------------------------------------------------------------------------- scene

def setup_scene(coll):
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.5
    ramp.color_ramp.elements[0].color = (0.75, 0.85, 0.95, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.08, 0.28, 0.80, 1)
    map_range = nt.nodes.new('ShaderNodeMapRange')
    map_range.inputs['From Min'].default_value = -1.0
    map_range.inputs['From Max'].default_value = 1.0
    nt.links.new(coord.outputs['Generated'], sep.inputs['Vector'])
    nt.links.new(sep.outputs['Z'], map_range.inputs['Value'])
    nt.links.new(map_range.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])

    sun_data = bpy.data.lights.new('B1_Sun', 'SUN')
    sun_data.energy = 4.0
    sun_data.angle = math.radians(1.0)
    sun = bpy.data.objects.new('B1_Sun', sun_data)
    sun_dir = Vector((0.45, 0.55, 1.6)).normalized()   # high summer sun from the north-east
    sun.rotation_euler = sun_dir.to_track_quat('Z', 'Y').to_euler()
    coll.objects.link(sun)

    def cam(name, loc, target, lens):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.clip_end = 2000
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        coll.objects.link(ob)
        return ob

    ref_cam = cam('Cam_Ref', (-36.0, 62.0, 1.6), (-4.0, -4.0, 19.0), 20)
    cam('Cam_Aerial', (95.0, 85.0, 75.0), (-5.0, -5.0, 10.0), 35)
    scene.camera = ref_cam
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            pass
    scene.render.resolution_x, scene.render.resolution_y = 1500, 1000


def main():
    osm = load_osm(OSM_PATH)
    nodes, ways = osm
    proj = make_projector(nodes, ways[B1_WAY]['refs'][:-1])

    old = bpy.data.collections.get('B1_OSM')
    if old:
        for ob in list(old.all_objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for ch in list(old.children_recursive):
            bpy.data.collections.remove(ch)
        bpy.data.collections.remove(old)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for d in list(block):
            if d.users == 0 and d.name.startswith(('B1_', 'Ctx_', 'Cam_')):
                block.remove(d)
    root = bpy.data.collections.new('B1_OSM')
    bpy.context.scene.collection.children.link(root)
    c_b1 = bpy.data.collections.new('B1_Building')
    c_ctx = bpy.data.collections.new('B1_Context')
    c_rig = bpy.data.collections.new('B1_CamerasLights')
    for c in (c_b1, c_ctx, c_rig):
        root.children.link(c)

    for name in ('Cube',):  # default startup cube sits inside the footprint
        ob = bpy.data.objects.get(name)
        if ob:
            ob.hide_set(True)
            ob.hide_render = True

    make_materials()
    parts, info = build_parts(osm, proj, c_b1)
    build_entrance(osm, proj, c_b1, info)
    build_rooftop(c_b1, info)
    b1_outline = [proj(r) for r in ways[B1_WAY]['refs'][:-1]]
    build_context(osm, proj, c_ctx, b1_outline)
    setup_scene(c_rig)
    print('B1 built:', len(c_b1.objects), 'objects;', len(c_ctx.objects), 'context objects;',
          sum(len(o.data.polygons) for o in c_b1.objects if o.type == 'MESH'), 'B1 faces')


main()
