"""Shared helpers for the goblin build: lofted tubes, mesh objects, scenes.

Coordinates: metres, Z up, the goblin faces -Y (Blender front view), its left side is +X.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix

ROOT = r"E:\Unity\Projects\GameArtGeneration\Goblins"
CAPK = 4          # rings per rounded loft cap (the game-budget gear sets 2)


def _cr(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def spline(ctrl, per_seg=4):
    """Uniform Catmull-Rom through the control rows (any number of columns)."""
    c = np.asarray(ctrl, float)
    ext = np.vstack([2 * c[0] - c[1], c, 2 * c[-1] - c[-2]])
    out = []
    for i in range(len(c) - 1):
        for k in range(per_seg):
            out.append(_cr(ext[i], ext[i + 1], ext[i + 2], ext[i + 3], k / per_seg))
    out.append(c[-1])
    return np.array(out)


def loft(bm, rows, up=(0, 0, 1), seg=16, per_seg=4, cap0=0.8, cap1=0.8, cup=None, mirror_x=False, shape=1.0):
    """Closed tube through control rows (x, y, z, a, b, c).

    a = radius along the side axis S, b = radius toward +N, c = radius toward -N,
    where N is `up` made perpendicular to the path and S = T x N.
    cap0/cap1 scale the length of the rounded end caps (0 = flat pole).
    cup(t, u) -> offset along S, used to cup the ears (t = 0..1 along path, u = -1..1 across N).
    """
    rows = spline(rows, per_seg)
    P = rows[:, :3].copy()
    if mirror_x:
        P[:, 0] *= -1
    n = len(P)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    U = np.array(up, float)
    rings = []
    for i in range(n):
        t = T[i]
        N = U - np.dot(U, t) * t
        N /= np.linalg.norm(N)
        S = np.cross(t, N)
        a, b, c = rows[i, 3], rows[i, 4], rows[i, 5]
        ring = []
        for j in range(seg):
            th = 2 * math.pi * j / seg
            s, u = math.cos(th), math.sin(th)
            if shape != 1.0:
                s = math.copysign(abs(s) ** shape, s)
                u = math.copysign(abs(u) ** shape, u)
            p = P[i] + S * a * s + N * (b if u >= 0 else c) * u
            if cup is not None:
                p = p + S * cup(i / (n - 1), u)
            ring.append(p)
        rings.append((np.array(ring), P[i], t, min(a, b, c)))

    def cap_rings(ring, center, t, r, sign, f):
        out = []
        K = CAPK
        for k in range(1, K):
            ph = (k / K) * math.pi / 2
            out.append(center + (ring - center) * math.cos(ph) + sign * t * r * f * math.sin(ph))
        return out, center + sign * t * r * f

    all_rings = [r[0] for r in rings]
    pole0 = pole1 = None
    if cap0 > 0:
        extra, pole0 = cap_rings(rings[0][0], rings[0][1], rings[0][2], rings[0][3], -1, cap0)
        all_rings = extra[::-1] + all_rings
    else:
        pole0 = rings[0][1]
    if cap1 > 0:
        extra, pole1 = cap_rings(rings[-1][0], rings[-1][1], rings[-1][2], rings[-1][3], 1, cap1)
        all_rings = all_rings + extra
    else:
        pole1 = rings[-1][1]
    vr = [[bm.verts.new(Vector(p)) for p in ring] for ring in all_rings]
    for r0, r1 in zip(vr[:-1], vr[1:]):
        for j in range(seg):
            bm.faces.new((r0[j], r0[(j + 1) % seg], r1[(j + 1) % seg], r1[j]))
    v0 = bm.verts.new(Vector(pole0))
    v1 = bm.verts.new(Vector(pole1))
    for j in range(seg):
        bm.faces.new((v0, vr[0][(j + 1) % seg], vr[0][j]))
        bm.faces.new((v1, vr[-1][j], vr[-1][(j + 1) % seg]))


def ellipsoid(bm, center, radii, rot=None, seg=16, rings=10):
    m = Matrix.Diagonal((radii[0], radii[1], radii[2], 1.0))
    if rot is not None:
        m = rot.to_4x4() @ m
    m = Matrix.Translation(center) @ m
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0, matrix=m)


def cone(bm, base, tip, r0, r1=0.0, seg=10):
    base, tip = Vector(base), Vector(tip)
    d = tip - base
    rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    m = Matrix.Translation(base + d / 2) @ rot
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r0, radius2=r1, depth=d.length, matrix=m)


def mesh_obj(name, bm, coll=None, recalc=True):
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.get(name)
    if me is None:
        me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, me)
    else:
        ob.data = me
    if coll is not None and ob.name not in coll.objects:
        coll.objects.link(ob)
    return ob


def get_coll(name, parent=None, scene=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    par = parent if parent is not None else (scene or bpy.context.scene).collection
    if c.name not in [x.name for x in par.children]:
        par.children.link(c)
    return c


def remove_obj(name):
    ob = bpy.data.objects.get(name)
    if ob is not None:
        me = ob.data if ob.type == 'MESH' else None
        bpy.data.objects.remove(ob, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def gauss(d2, s):
    return np.exp(-d2 / (2 * s * s))
