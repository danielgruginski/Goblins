"""Troll gear, built with the goblin's gear tools (gob_gear) on the troll's body and rig, baked into its own atlas
(T_Troll_Gear, 1024, material M_Troll_Gear) so the goblins' T_Goblin_Gear stays as it is.

    Prop_TrollClub   Socket_RightHand   a gnarled tree-branch club, bark, knots, two lopped-off stubs, a hide grip
    Prop_TrollHair   Socket_Helm        a lank tuft from the crown down the back of the head
    Outfit_TrollLoincloth (skinned)     a rope belt with a ragged hide flap in front and a longer one behind

Props follow the goblin convention: modelled in socket space (origin = attach point); in Socket_RightHand +Y runs
along the handle toward the business end and the knuckles face +X.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
import gob_common
from gob_common import loft, ellipsoid, cone, get_coll, remove_obj, smoothstep, grid_faces
import gob_gear as GG
from gob_gear import Builder, S, SR, PS
import troll_body as TB

OUTFIT_COLL, PROP_COLL = "TRL_Outfit", "TRL_Props"


def materials():
    mats = GG.build_materials()
    mats['bark'] = GG._src_material("GS_Bark", '#2b2219', '#5b4631', scale=(70, 4, 70), stain=('#4b5a2a', 5, 0.62), edge=0.5)
    mats['hide'] = GG._src_material("GS_Hide", '#6e5439', '#a3875f', scale=(25, 25, 25), stain=('#4a3624', 7, 0.57), edge=0.4)
    mats['troll_hair'] = GG._src_material("GS_TrollHair", '#11160f', '#34402c', scale=(8, 8, 80), edge=0.3)
    return mats


# ---------------------------------------------------------------------------------------------- club
def prop_club():
    """A gnarled branch, 1.3 m: grip at the origin, thickening to a knobbly end with burls and two stubs."""
    b = Builder()
    rng = np.random.default_rng(31)
    prof = [(-0.22, 0.034), (-0.08, 0.036), (0.10, 0.039), (0.35, 0.048), (0.60, 0.064), (0.80, 0.084),
            (0.95, 0.098), (1.05, 0.094), (1.12, 0.066)]

    def bend(y):
        return 0.045 * math.sin(y * 2.6) - 0.03 * y * y, 0.025 * math.sin(y * 3.7 + 1.0)
    rows = []
    for y, r in prof:
        bx, bz = bend(y)
        rows.append((bx, y, bz, r * rng.uniform(0.92, 1.06), r * rng.uniform(0.94, 1.06), r))
    b.part('bark', loft, rows, up=(0, 0, 1), seg=S(16), per_seg=PS(4), cap0=0.5, cap1=0.6)
    # burls on the business end, standing well out of it
    for i in range(7):
        y = rng.uniform(0.62, 1.06)
        r = float(np.interp(y, [p[0] for p in prof], [p[1] for p in prof]))
        a = 2 * math.pi * i / 7 + rng.uniform(-0.4, 0.4)
        bx, bz = bend(y)
        s = rng.uniform(0.040, 0.058)
        c = Vector((bx + math.cos(a) * (r + s * 0.25), y, bz + math.sin(a) * (r + s * 0.25)))
        b.part('bark', ellipsoid, c, (s, s * 1.25, s), None, S(10), SR(6))
    # two lopped-off side branches: thick short stubs with pale cut ends
    for y, a, ln in ((0.50, 0.6, 0.055), (0.80, 3.6, 0.07)):
        r = float(np.interp(y, [p[0] for p in prof], [p[1] for p in prof]))
        bx, bz = bend(y)
        base = Vector((bx, y, bz))
        d = Vector((math.cos(a), 0.45, math.sin(a))).normalized()
        b.part('bark', cone, base, base + d * (r + ln), r * 0.62, r * 0.48, seg=S(10))
        b.part('wood', cone, base + d * (r + ln), base + d * (r + ln + 0.008), r * 0.48, r * 0.40, seg=S(10))
    # rawhide wrapped round the grip, tied with rope
    wrap = [(0.0, y, 0.0, 0.041, 0.041, 0.041) for y in (-0.17, -0.05, 0.08)]
    b.part('hide', loft, wrap, up=(0, 0, 1), seg=S(12), per_seg=PS(2), cap0=0.2, cap1=0.2)
    for y in (-0.15, 0.06):
        b.part('rope', loft, [(0, y - 0.008, 0, 0.044, 0.044, 0.044), (0, y + 0.008, 0, 0.044, 0.044, 0.044)],
               up=(0, 0, 1), seg=S(12), per_seg=1, cap0=0.2, cap1=0.2)
    return b, 'socket'


# ---------------------------------------------------------------------------------------------- hair
def prop_hair(surf, rig):
    """Lank strands from the crown, lying on the skull and falling down the back of the head (world space)."""
    b = Builder()
    rng = np.random.default_rng(17)
    head = rig.data.bones["Socket_Helm"].head_local
    hc = np.array(head[:])
    top_r = (surf.ray(hc, (0, 0, 1)) or 0.2)
    for i in range(7):
        lat = (i / 6 - 0.5) * 0.9 + rng.uniform(-0.06, 0.06)  # across the crown
        start = rng.uniform(-0.30, -0.12)                     # from just in front of the crown top
        ln = rng.uniform(1.15, 1.35)                          # round the back of the skull to the nape
        pts = []
        for t in np.linspace(0, 1, 6):
            th = (start + t * ln) * math.pi * 0.5            # 0 = straight up, 1 = straight back
            d = np.array([math.sin(lat) * 0.8, math.sin(th), math.cos(th)])
            d /= np.linalg.norm(d)
            loc, nrm, _ = surf.nearest(hc + d * top_r * 1.6)
            pts.append(np.array(loc) + np.array(nrm) * (0.012 + 0.016 * t))
        # past the skull the strands hang lank down the nape
        pts.append(pts[-1] + np.array([0, 0.05, -0.12 - 0.08 * rng.random()]))
        w0 = rng.uniform(0.030, 0.040)
        rows = [(p[0], p[1], p[2], w0 * (1 - 0.6 * k / (len(pts) - 1)), 0.008, 0.008) for k, p in enumerate(pts)]
        b.part('troll_hair', loft, rows, up=(0, 0, 1), seg=S(8), per_seg=1, cap0=0.3, cap1=0.6)
    return b, 'world'


# ---------------------------------------------------------------------------------------------- loincloth
def build_loincloth(surf, mats, coll, rig, warp, J=20):
    """Rope belt round the waist; ragged hide flaps front and back, hanging clear of the body."""
    remove_obj("Outfit_TrollLoincloth")
    rng = np.random.default_rng(5)
    S_ = warp.p['S']
    zb = warp.hip_z + 0.06                                   # belt height: just above the hip joints
    th = np.linspace(0, 2 * math.pi, J, endpoint=False)
    D = np.stack([np.sin(th), -np.cos(th), np.zeros(J)], 1)
    yc = warp.trunk(np.array([[0.0, 0.0, 0.48]]))[0][1]

    def ring_r(z):
        return np.array([surf.ray((0, yc, z), d) or 0.2 for d in D])
    b = Builder()
    rb = ring_r(zb)
    P = D * (rb + 0.012)[:, None] + np.array([0, yc, zb])
    b.part('rope', GG.band, P, D, np.tile([0, 0, 1.0], (J, 1)), 0.045, 0.022)
    knot = Vector((0.06, yc - rb[0] - 0.03, zb - 0.005))
    b.part('rope', ellipsoid, knot, (0.030, 0.022, 0.026), None, S(10), SR(6))
    belt = GG._finish("Outfit_TrollLoincloth_Belt", b, coll, mats)

    def flap(front, width0, width1, length):
        sgn = -1 if front else 1
        cols, rows = 6, 5
        grid = []
        bb = Builder()
        for i in range(rows + 1):
            t = i / rows
            z = zb - 0.015 - t * length
            w = width0 + (width1 - width0) * t
            ring = []
            for j in range(cols + 1):
                u = j / cols - 0.5
                x = u * w
                d = Vector((x, sgn, 0)).normalized()
                r = surf.ray((0, yc, z), d)
                if r is None:                                # below the crotch: hang on from the last row
                    r = grid[-1][j][1] if grid else 0.15
                yy = yc + sgn * (max(r * abs(d.y), 0.05) + 0.03 + 0.04 * t * t)
                zz = z - (rng.uniform(0, 0.05) if i == rows else 0.0) - (0.025 if (i == rows and j % 2) else 0.0)
                ring.append((Vector((x, yy, zz)), r))
            grid.append(ring)
        V = [[bb.bm.verts.new(p) for p, _ in row] for row in grid]
        if 'hide' not in bb.mats:
            bb.mats.append('hide')
        for f in grid_faces(bb.bm, V)[0]:
            f.material_index = 0
        return GG._finish("Outfit_TrollLoincloth_" + ("Front" if front else "Back"), bb, coll, mats, solidify=0.010)
    fr = flap(True, 0.30, 0.24, 0.40)
    bk = flap(False, 0.36, 0.30, 0.48)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in (belt, fr, bk):
        o.select_set(True)
    bpy.context.view_layer.objects.active = belt
    bpy.ops.object.join()
    belt.name = belt.data.name = "Outfit_TrollLoincloth"

    hip = warp.hip_z

    def hips(co):
        centre = smoothstep(0.15, 0.05, abs(co.x))
        low = smoothstep(hip + 0.02, hip - 0.20, co.z)
        return max(0.4 * low, 0.8 * centre * low)
    GG.skin_to_rig(belt, surf, hips_blend=hips, rig=rig)
    return belt


# ---------------------------------------------------------------------------------------------- all gear
def build_gear(rig, warp):
    gob_common.CAPK = 2
    mats = materials()
    oc, pc = get_coll(OUTFIT_COLL), get_coll(PROP_COLL)
    surf = GG.BodySurface(TB.NAMES["body"])
    try:
        outfits = [build_loincloth(surf, mats, oc, rig, warp)]
        club = GG.build_prop("Prop_TrollClub", prop_club, "Socket_RightHand", mats, pc, rig=rig)
        hair = GG.build_prop("Prop_TrollHair", lambda: prop_hair(surf, rig), "Socket_Helm", mats, pc, rig=rig)
    finally:
        surf.free()
        gob_common.CAPK = 4
    return outfits, [club, hair]


def bake(objs, rig, size=1024):
    return GG.bake_gear(objs, size=size, name="T_Troll_Gear", rig=rig, game_mat="M_Troll_Gear")
