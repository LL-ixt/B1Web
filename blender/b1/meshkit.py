"""Mesh builder and primitive generators shared by every building module."""
import math

import bpy
from mathutils import Vector

from .geom import area2, right_normal
from .materials import MAT


def collection(parent, name):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


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
    for i in (i0, i1):
        j = i + 1 if i == i0 else i - 1
        t = (P[i] - P[j]).normalized()
        p, q = P[i] + N[i] * d0, P[i] + N[i] * d1
        mb.face([V3(p, z0), V3(q, z0), V3(q, z1), V3(p, z1)], mat, N3(t))
