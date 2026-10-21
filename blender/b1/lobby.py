"""Main lobby (sảnh chính): the curved block in the inner corner of the V.

Pieces (each its own object):
  B1_Lobby_F1    ground floor, cream walls  - recessed curved glazing, square piers, entrance frame, soffit
  B1_Lobby_Ring  floor 2+, white            - curved ring wall with cornice/groove, gridded windows, roof
  B1_Lobby_Porch porte-cochere              - straight canopy with chamfered fascia, 2 steel columns, 2 steps

Layout reference: plan coordinates along the arc use P[i] (wall line) and N[i] (outward normal);
the straight porch/entrance pieces use the tangent frame (c0, u, n) at the middle of the arc,
s = distance along u, d = distance in front of the tangent plane.
"""
import math
import random

from mathutils import Vector

from .config import ENTRANCE_PART, B1_WAY, GROUND_H, level_top
from .geom import catmull_rom
from .materials import GLASS_POOL
from .meshkit import (MB, N3, V3, box_along, collection, curved_solid, cylinder, prism, quad_along,
                      ribbon)

NS = 96            # arc samples (~0.26 m each)
REC = -2.2         # ground floor glazing set back behind the ring wall line

# porch / entrance, in the mid-arc tangent frame
DOOR_BAYS = 5      # sketch: 5 bays x 3 rows, double doors in bays 2 and 4
DOOR_BAY_W = 1.3
DOOR_ROWS = (0.78, 2.75, 3.55, GROUND_H)
FLANK_W = 2.1      # cream wall either side of the entrance frame
CANOPY_HALF = 4.8
CANOPY_FRONT = 6.0
CANOPY_TOP, CANOPY_BOT = GROUND_H - 0.05, 3.8
CANOPY_SLOPE = 0.3  # fascia leans out towards the top
COL_S, COL_D, COL_R = 2.8, 4.4, 0.38
STEP_H = 0.15
N_STEPS = 5         # user: the porch stair has 5 risers
STEP_TREAD = 0.35
LANDING_Z = N_STEPS * STEP_H
ENTRY_F = 0.56    # entrance + canopy sit east of the arc middle (ref.jpg, 116c...jpg)
# ring windows (from, to, columns, rows) as fractions of the arc from its west end, P[0]
RING_WINDOWS = [(0.10, 0.33, 4, 6), (0.47, 0.80, 7, 5), (0.88, 0.915, 1, 5)]
# the ring's glazing reads light in the photos: curtains and blinds behind most panes
RING_GLASS = ['B1_GlassCurtain'] * 3 + ['B1_GlassBlind'] * 3 + ['B1_Glass'] * 4


def arc_frame(osm, proj):
    """Circle through the first, middle and last OSM arc points, sampled NS times."""
    nodes, ways = osm
    outline = set(ways[B1_WAY]['refs'])
    refs = ways[ENTRANCE_PART]['refs'][:-1]
    arc_pts = [proj(r) for r in refs if r in outline]
    apex = proj([r for r in refs if r not in outline][0])
    spline = catmull_rom(arc_pts, 64)
    a, b, c = arc_pts[0], spline[32], arc_pts[-1]
    d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    cen = Vector(((a.length_squared * (b.y - c.y) + b.length_squared * (c.y - a.y) + c.length_squared * (a.y - b.y)) / d,
                  (a.length_squared * (c.x - b.x) + b.length_squared * (a.x - c.x) + c.length_squared * (b.x - a.x)) / d))
    R = (a - cen).length
    th0, thm, th1 = (math.atan2(p.y - cen.y, p.x - cen.x) for p in (a, b, c))
    # walk from a to c through b
    span = (th1 - th0) % math.tau
    if (thm - th0) % math.tau > span:
        span -= math.tau
    P, N = [], []
    for i in range(NS + 1):
        th = th0 + span * i / NS
        r = Vector((math.cos(th), math.sin(th)))
        P.append(cen + r * R)
        N.append(r if r.dot(cen + r * R - apex) > 0 else -r)
    return {'P': P, 'N': N, 'apex': apex, 'center': cen, 'R': R, 'HE': level_top(4),
            'entry': tangent_frame(P, N)}


def tangent_frame(P, N, f=ENTRY_F):
    im = int(round(f * NS))
    n = N[im].copy()
    u = Vector((-n.y, n.x))
    if u.dot(P[-1] - P[0]) < 0:
        u = -u
    return P[im].copy(), u, n


def tangent_at(P, i):
    return (P[min(i + 1, NS)] - P[max(i - 1, 0)]).normalized()


def square_post(mb, P, N, i, d, half, z0, z1, mat):
    t = tangent_at(P, i)
    c = P[i] + N[i] * d
    prism(mb, [c - t * half - N[i] * half, c + t * half - N[i] * half,
               c + t * half + N[i] * half, c - t * half + N[i] * half], z0, z1, mat)


# --------------------------------------------------------------------------- ground floor (cream)

UNIT_W = 4.4          # target width of one shopfront unit (m), stretched to fit its segment
UNIT_WALL = (0.237, 0.179)   # cream wall share of a unit on its left / right (sketch proportions)
BANK_Z = (0.15, 2.19, 2.65, GROUND_H)   # lower glass, cream band, upper glass
SHOP_WALL_D = (-1.3, -0.45)   # cream wall thickness range
SHOP_GLASS_D = -0.8


def seg_len(P, i0, i1):
    return sum((P[i + 1] - P[i]).length for i in range(i0, i1))


def lerp_arc(P, N, f0, f1, step=0.5):
    """Sub-sampled copy of the arc between fractional indices f0 and f1 (inclusive)."""
    n = max(1, math.ceil((f1 - f0) / step))
    Ps, Ns = [], []
    for k in range(n + 1):
        f = f0 + (f1 - f0) * k / n
        i = min(int(f), NS - 1)
        t = f - i
        Ps.append(P[i].lerp(P[i + 1], t))
        Ns.append(N[i].lerp(N[i + 1], t).normalized())
    return Ps, Ns


def shop_unit(gl, wl, P, N, f0, f1):
    w = f1 - f0
    a, b = f0 + w * UNIT_WALL[0], f1 - w * UNIT_WALL[1]
    d0, d1 = SHOP_WALL_D
    for x0, x1 in ((f0, a), (b, f1)):                     # cream wall margins
        Ps, Ns = lerp_arc(P, N, x0, x1)
        curved_solid(wl, Ps, Ns, 0, len(Ps) - 1, 0.0, GROUND_H, d0, d1, 'B1_WallCream')
    Ps, Ns = lerp_arc(P, N, a, b)
    last = len(Ps) - 1
    zl0, zl1, zu0, zu1 = BANK_Z
    curved_solid(wl, Ps, Ns, 0, last, zl1, zu0, d0, d1, 'B1_WallCream')       # cream band between banks
    curved_solid(wl, Ps, Ns, 0, last, 0.0, zl0, d0, d1, 'B1_WallCream')       # plinth under the lower bank
    ribbon(gl, Ps, Ns, 0, last, d0 + 0.2, 0.0, GROUND_H, 'B1_GlassDark', outward=True, smooth=False)  # backing
    for z0, z1 in ((zl0, zl1), (zu0, zu1)):
        ribbon(gl, Ps, Ns, 0, last, SHOP_GLASS_D, z0, z1, 'B1_GlassLobby', smooth=False)
        curved_solid(gl, Ps, Ns, 0, last, z0, z0 + 0.07, SHOP_GLASS_D, SHOP_GLASS_D + 0.14, 'B1_FrameDark')
        curved_solid(gl, Ps, Ns, 0, last, z1 - 0.07, z1, SHOP_GLASS_D, SHOP_GLASS_D + 0.14, 'B1_FrameDark')
    for k in range(6):                                       # 5 panes per bank = 6 mullions
        f = a + (b - a) * k / 5
        Pm, Nm = lerp_arc(P, N, f, f + 1e-3, step=1.0)
        t = (Pm[-1] - Pm[0]).normalized()
        c = Pm[0] + Nm[0] * SHOP_GLASS_D
        hw = 0.05 if 0 < k < 5 else 0.09
        n0 = Nm[0]
        for z0, z1 in ((zl0, zl1), (zu0, zu1)):
            prism(gl, [c - t * hw, c + t * hw, c + t * hw + n0 * 0.14, c - t * hw + n0 * 0.14], z0, z1, 'B1_FrameDark')



def build_f1(arc, coll):
    P, N, apex = arc['P'], arc['N'], arc['apex']
    c0, u, n = tangent_frame(P, N)
    rnd = random.Random(3)
    s_of = [(p - c0).dot(u) for p in P]
    zone = DOOR_BAYS * DOOR_BAY_W / 2 + FLANK_W        # half width of the straight entrance block
    i_lo = max(i for i in range(NS + 1) if s_of[i] <= -zone + 0.4)
    i_hi = min(i for i in range(NS + 1) if s_of[i] >= zone - 0.4)

    # shopfront units either side of the entrance block (user sketch): cream wall | upper glass bank over a
    # cream band over a lower glass bank | cream wall; 5 panes per bank
    gl = MB('Lobby_F1_Glass')
    wl = MB('Lobby_F1_Walls')
    for seg0, seg1 in ((0, i_lo), (i_hi, NS)):
        units = max(1, round(seg_len(P, seg0, seg1) / UNIT_W))
        for k in range(units):
            f0 = seg0 + (seg1 - seg0) * k / units
            f1 = seg0 + (seg1 - seg0) * (k + 1) / units
            shop_unit(gl, wl, P, N, f0, f1)
    gl.build(coll)
    wl.build(coll)

    # cream square piers under the ring, cream end walls, cream walls flanking the entrance
    pr = MB('Lobby_F1_EntranceWalls')
    for i, j in ((0, 1), (NS, NS - 1)):
        t = (P[j] - P[i]).normalized()
        prism(pr, [P[i], P[i] + N[i] * (REC - 0.3), P[i] + N[i] * (REC - 0.3) + t * 0.6, P[i] + t * 0.6],
              0.0, GROUND_H, 'B1_WallCream')
    half = DOOR_BAYS * DOOR_BAY_W / 2
    for sg in (-1, 1):
        s0, s1 = sorted((sg * half, sg * (zone + 0.15)))
        box_along(pr, c0, u, n, s0, s1, 0.0, GROUND_H, REC - 1.0, -0.45, 'B1_WallCream')
    pr.build(coll)

    # entrance frame: 5 bays x 3 rows, double doors in bays 2 and 4 (sketch sảnh.png, right)
    ef = MB('Lobby_F1_EntranceFrame')
    d_gl = REC + 0.04
    z_rows = DOOR_ROWS
    for b in range(DOOR_BAYS):
        s0, s1 = -half + b * DOOR_BAY_W, -half + (b + 1) * DOOR_BAY_W
        for r in range(len(z_rows) - 1):
            quad_along(ef, c0, u, n, s0, s1, z_rows[r], z_rows[r + 1], d_gl, 'B1_GlassLobby')
        if b in (1, 3):
            sm = (s0 + s1) / 2
            box_along(ef, c0, u, n, sm - 0.025, sm + 0.025, z_rows[0], z_rows[1], d_gl, d_gl + 0.1, 'B1_FrameDark')
            for sg in (-1, 1):  # long pull handles either side of the meeting stile
                hs = sm + sg * 0.12
                box_along(ef, c0, u, n, hs - 0.015, hs + 0.015, 0.95, 2.15, d_gl + 0.16, d_gl + 0.19, 'B1_Steel')
                for hz in (1.0, 2.1):
                    box_along(ef, c0, u, n, hs - 0.01, hs + 0.01, hz - 0.01, hz + 0.01, d_gl + 0.1, d_gl + 0.16, 'B1_Steel')
            for sx in (s0 + 0.04, s1 - 0.04):  # heavier door stiles
                box_along(ef, c0, u, n, sx - 0.04, sx + 0.04, z_rows[0], z_rows[1], d_gl, d_gl + 0.1, 'B1_FrameDark')
        box_along(ef, c0, u, n, s0 + 0.02, s1 - 0.02, 1.0, 1.06, d_gl + 0.005, d_gl + 0.01, 'B1_SignBlue')
    for b in range(DOOR_BAYS + 1):
        sx = -half + b * DOOR_BAY_W
        w = 0.07 if 0 < b < DOOR_BAYS else 0.1
        box_along(ef, c0, u, n, sx - w, sx + w, z_rows[0], GROUND_H, REC - 0.05, d_gl + 0.12, 'B1_FrameDark')
    for z in z_rows:
        box_along(ef, c0, u, n, -half, half, max(z_rows[0], z - 0.05), min(GROUND_H, z + 0.05),
                  REC - 0.05, d_gl + 0.12, 'B1_FrameDark')
    ef.build(coll)

    # ceiling under the ring
    so = MB('Lobby_F1_Soffit')
    so.face([V3(q, GROUND_H) for q in P + [apex]], 'B1_Wall', (0, 0, -1))
    so.build(coll)


# --------------------------------------------------------------------------- ring, floor 2+ (white)

def build_ring(arc, coll):
    P, N, apex, HE = arc['P'], arc['N'], arc['apex'], arc['HE']
    idx = lambda f: int(round(f * NS))
    rnd = random.Random(4)
    gz0, gz1 = level_top(1) + 1.4, level_top(3) + 0.4
    zg = HE - 1.6                      # recessed groove below the cornice
    body0 = GROUND_H + 0.35
    openings = [(idx(f0), idx(f1), cols, rows) for f0, f1, cols, rows in RING_WINDOWS]

    wl = MB('Lobby_Ring_Wall')
    curved_solid(wl, P, N, 0, NS, GROUND_H - 0.05, body0, -0.3, 0.25, 'B1_Wall')       # floor-2 slab ledge
    cur = 0
    for o0, o1, _, _ in openings:
        curved_solid(wl, P, N, cur, o0, body0, zg, -0.3, 0.0, 'B1_Wall')
        curved_solid(wl, P, N, o0, o1, body0, gz0, -0.3, 0.0, 'B1_Wall')
        curved_solid(wl, P, N, o0, o1, gz1, zg, -0.3, 0.0, 'B1_Wall')
        curved_solid(wl, P, N, o0, o1, gz0 - 0.1, gz0, -0.2, 0.1, 'B1_Wall')            # sill
        for i in (o0, o1):                                                              # reveals
            j = i + 1 if i == o0 else i - 1
            t = (P[j] - P[i]).normalized()
            q = [P[i] + N[i] * -0.2, P[i] + N[i] * -0.2 + t * 0.02, P[i] + t * 0.02, P[i]]
            wl.face([V3(q[0], gz0), V3(q[3], gz0), V3(q[3], gz1), V3(q[0], gz1)], 'B1_Wall', N3(t))
        cur = o1
    curved_solid(wl, P, N, cur, NS, body0, zg, -0.3, 0.0, 'B1_Wall')
    curved_solid(wl, P, N, 0, NS, zg, zg + 0.12, -0.3, -0.07, 'B1_Wall')                # groove
    curved_solid(wl, P, N, 0, NS, zg + 0.12, HE - 0.3, -0.3, 0.0, 'B1_Wall')
    curved_solid(wl, P, N, 0, NS, HE - 0.3, HE + 0.05, -0.3, 0.3, 'B1_Wall')             # cornice
    curved_solid(wl, P, N, 0, NS, HE + 0.05, HE + 0.8, -0.3, 0.05, 'B1_Wall')            # parapet
    curved_solid(wl, P, N, 0, NS, HE + 0.8, HE + 0.9, -0.35, 0.12, 'B1_Wall')            # coping
    wl.build(coll)

    win = MB('Lobby_Ring_Windows')
    for o0, o1, cols, rows in openings:
        for r in range(rows):
            za, zb = gz0 + (gz1 - gz0) * r / rows, gz0 + (gz1 - gz0) * (r + 1) / rows
            for i in range(o0, o1):
                ribbon(win, P, N, i, i + 1, -0.2, za, zb, rnd.choice(RING_GLASS), smooth=False)
            if r:
                curved_solid(win, P, N, o0, o1, za - 0.035, za + 0.035, -0.2, -0.11, 'B1_Frame')
        for i in sorted({o0 + round(k * (o1 - o0) / cols) for k in range(cols + 1)}):
            t = tangent_at(P, i)
            c = [P[i] + N[i] * -0.2 - t * 0.035, P[i] + N[i] * -0.2 + t * 0.035,
                 P[i] + N[i] * -0.11 + t * 0.035, P[i] + N[i] * -0.11 - t * 0.035]
            prism(win, c, gz0, gz1, 'B1_Frame')
        curved_solid(win, P, N, o0, o1, gz0, gz0 + 0.07, -0.2, -0.11, 'B1_Frame')
        curved_solid(win, P, N, o0, o1, gz1 - 0.07, gz1, -0.2, -0.11, 'B1_Frame')
    win.build(coll)

    rf = MB('Lobby_Roof')
    rf.face([V3(q, HE) for q in P + [apex]], 'B1_Roof', (0, 0, 1))
    rf.build(coll)


# --------------------------------------------------------------------------- porte-cochere

def build_porch(arc, coll):
    P, N = arc['P'], arc['N']
    c0, u, n = tangent_frame(P, N)
    pt = lambda s, d: c0 + u * s + n * d

    cn = MB('Lobby_Canopy')
    # chamfered slab: top outline wider than the bottom outline (sketch sảnh.png, left)
    k = CANOPY_SLOPE
    top = [pt(-CANOPY_HALF, -0.3), pt(CANOPY_HALF, -0.3), pt(CANOPY_HALF, CANOPY_FRONT), pt(-CANOPY_HALF, CANOPY_FRONT)]
    bot = [pt(-CANOPY_HALF + k, -0.3), pt(CANOPY_HALF - k, -0.3), pt(CANOPY_HALF - k, CANOPY_FRONT - k),
           pt(-CANOPY_HALF + k, CANOPY_FRONT - k)]
    cn.face([V3(q, CANOPY_TOP) for q in top], 'B1_Canopy', (0, 0, 1))
    cn.face([V3(q, CANOPY_BOT) for q in bot], 'B1_Canopy', (0, 0, -1))
    for i in range(4):
        a0, a1, b0, b1 = top[i], top[(i + 1) % 4], bot[i], bot[(i + 1) % 4]
        mid = (a0 + a1 + b0 + b1) / 4 - (c0 + n * (CANOPY_FRONT / 2))
        cn.face([V3(b0, CANOPY_BOT), V3(b1, CANOPY_BOT), V3(a1, CANOPY_TOP), V3(a0, CANOPY_TOP)], 'B1_Canopy', N3(mid))
    # lighter dropped ceiling panel next to the building
    box_along(cn, c0, u, n, -3.0, 3.0, CANOPY_BOT - 0.14, CANOPY_BOT, 0.2, 3.0, 'B1_CanopySoffit')
    cn.build(coll)

    dl = MB('Lobby_Downlights')
    for s in (-3.8, -2.0, 0.0, 2.0, 3.8):
        for d in (3.9, 5.1):
            ring = [pt(s, d) + (u * math.cos(a) + n * math.sin(a)) * 0.09
                    for a in (2 * math.pi * j / 10 for j in range(10))]
            dl.face([V3(q, CANOPY_BOT - 0.005) for q in ring], 'B1_Downlight', (0, 0, -1))
    for s in (-2.0, 0.0, 2.0):
        ring = [pt(s, 1.6) + (u * math.cos(a) + n * math.sin(a)) * 0.09 for a in (2 * math.pi * j / 10 for j in range(10))]
        dl.face([V3(q, CANOPY_BOT - 0.145) for q in ring], 'B1_Downlight', (0, 0, -1))
    dl.build(coll)

    col = MB('Lobby_Columns')
    for sg in (-1, 1):
        cylinder(col, pt(sg * COL_S, COL_D), COL_R, LANDING_Z, CANOPY_BOT, 'B1_Steel', 32)
        cylinder(col, pt(sg * COL_S, COL_D), COL_R + 0.06, LANDING_Z, LANDING_Z + 0.08, 'B1_Steel', 32)
    col.build(coll)

    st = MB('Lobby_Steps')
    half = DOOR_BAYS * DOOR_BAY_W / 2
    for k in range(N_STEPS):  # tier k is k treads narrower and shorter than the one below it
        inset = k * STEP_TREAD
        box_along(st, c0, u, n, -CANOPY_HALF - 0.6 + inset, CANOPY_HALF + 0.6 - inset, 0.0, (k + 1) * STEP_H,
                  -0.45, CANOPY_FRONT + 0.3 - inset, 'B1_Stone')
    box_along(st, c0, u, n, -half, half, 0.0, LANDING_Z, REC, -0.45, 'B1_Stone')
    st.build(coll)


def build_lobby(osm, proj, parent):
    arc = arc_frame(osm, proj)
    root = collection(parent, 'B1_Lobby')
    build_f1(arc, collection(root, 'B1_Lobby_F1'))
    build_ring(arc, collection(root, 'B1_Lobby_Ring'))
    build_porch(arc, collection(root, 'B1_Lobby_Porch'))
    return arc
