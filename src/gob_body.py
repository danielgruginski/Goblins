"""Goblin base body: procedural parts fused into one mesh, built in T-pose.

build_body() -> GoblinBody (voxel-remeshed, symmetric, decimated) + GoblinEyes.
Landmarks used by the rig and the props are stored in LM.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from gob_common import loft, ellipsoid, cone, mesh_obj, get_coll, remove_obj, smoothstep

HC = np.array([0.0, -0.03, 0.905])      # head centre
HR = np.array([0.092, 0.100, 0.105])    # head radii
EYE_R = 0.0165
N_EYE = np.array([0.42, -0.88, 0.12]) / np.linalg.norm([0.42, -0.88, 0.12])
LM = {}


def _g(n, n0, s):
    n0 = np.asarray(n0, float)
    n0 = n0 / np.linalg.norm(n0)
    d2 = ((n - n0) ** 2).sum(1)
    out = np.exp(-d2 / (2 * s * s))
    if abs(n0[0]) > 1e-6:
        m = n0 * np.array([-1, 1, 1])
        out = out + np.exp(-((n - m) ** 2).sum(1) / (2 * s * s))
    return out


MOUTH_Z0, MOUTH_K, MOUTH_W = -0.45, 0.60, 0.60    # grin centre height, corner curl, half-width (unit-sphere nx)


def mouth_line(nx):
    return MOUTH_Z0 + MOUTH_K * np.asarray(nx) ** 2


def head_sculpt(n):
    n = np.atleast_2d(n)
    nx, ny, nz = n[:, 0], n[:, 1], n[:, 2]
    p = n * HR
    d = np.zeros(len(n))
    d += 0.015 * _g(n, (0.36, -0.82, 0.42), 0.19)    # brow ridge over each eye
    d += 0.007 * _g(n, (0, -0.9, 0.42), 0.13)        # glabella
    d -= 0.016 * _g(n, N_EYE, 0.13)                  # eye sockets
    d += 0.011 * _g(n, (0.62, -0.70, -0.12), 0.16)   # cheekbones
    d += 0.017 * _g(n, (0, -0.55, -0.83), 0.19)      # pointed chin
    d += 0.007 * _g(n, (0.6, -0.25, -0.75), 0.18)    # jaw corners
    d -= 0.007 * _g(n, (0.85, -0.35, 0.30), 0.15)    # temples
    d += 0.016 * _g(n, (0, 0.65, 0.75), 0.33)        # big cranium at the back
    d += 0.008 * _g(n, (0, -0.86, -0.30), 0.20)      # muzzle
    zc = mouth_line(nx)                              # wide grin, corners curl up past the nose
    front = smoothstep(-0.35, -0.65, ny)
    ax = np.abs(nx)
    d -= 0.011 * np.exp(-(nz - zc) ** 2 / (2 * 0.032 ** 2)) * smoothstep(MOUTH_W + 0.04, MOUTH_W - 0.08, ax) * front
    d += 0.004 * np.exp(-(nz - zc - 0.075) ** 2 / (2 * 0.03 ** 2)) * smoothstep(MOUTH_W, MOUTH_W - 0.15, ax) * front
    d += 0.006 * np.exp(-(nz - zc + 0.08) ** 2 / (2 * 0.032 ** 2)) * smoothstep(MOUTH_W - 0.05, MOUTH_W - 0.22, ax) * front
    d -= 0.004 * _g(n, (MOUTH_W, -0.78, mouth_line(MOUTH_W)), 0.06)     # dimples at the corners
    p = p + n * d[:, None]
    low = smoothstep(-0.1, -0.9, nz)
    p[:, 0] *= (1 - 0.24 * low) * (1 + 0.06 * smoothstep(-0.1, 0.9, nz))
    return p + HC


def build_head(bm):
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=64, v_segments=40, radius=1.0)
    n = np.array([v.co[:] for v in tmp.verts])
    n /= np.linalg.norm(n, axis=1)[:, None]
    p = head_sculpt(n)
    for v, q in zip(tmp.verts, p):
        v.co = Vector(q)
    me = bpy.data.meshes.new("_tmp_head")
    tmp.to_mesh(me)
    tmp.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)

    # eyes sit in the sockets; the lids are solid domes over their upper half (angry slant)
    ps = head_sculpt(N_EYE)[0]
    eye = ps - N_EYE * HR * 0.0 - N_EYE * (0.30 * EYE_R)
    LM['eye_L'] = eye.copy()
    for sgn in (1, -1):
        c = eye * np.array([sgn, 1, 1])
        lid = bmesh.new()
        bmesh.ops.create_uvsphere(lid, u_segments=20, v_segments=12, radius=EYE_R + 0.0035)
        k = 0.45
        nrm = Vector((-sgn * k, 0.12, 1.0)).normalized()
        off = 0.12 * EYE_R
        for v in lid.verts:
            h = v.co.dot(nrm) - off
            if h < 0:
                v.co -= nrm * h
            v.co += Vector(c)
        me = bpy.data.meshes.new("_tmp_lid")
        lid.to_mesh(me)
        lid.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    # long drooping nose with flared nostrils
    y0 = head_sculpt(np.array([[0, -0.995, -0.1]]))[0][1] + 0.014
    LM['nose_root'] = np.array([0, y0, 0.900])
    nose = [
        (0, y0 + 0.014, 0.906, 0.021, 0.020, 0.030),
        (0, y0 - 0.010, 0.894, 0.022, 0.019, 0.026),
        (0, y0 - 0.038, 0.879, 0.0175, 0.016, 0.019),
        (0, y0 - 0.064, 0.863, 0.0135, 0.0125, 0.0135),
        (0, y0 - 0.086, 0.846, 0.0095, 0.0095, 0.0095),
    ]
    loft(bm, nose, up=(0, 0, 1), seg=16, cap0=0.5, cap1=1.1)
    LM['nose_tip'] = np.array([0, y0 - 0.096, 0.842])
    for sgn in (1, -1):
        ellipsoid(bm, Vector((sgn * 0.018, y0 - 0.008, 0.876)), (0.011, 0.014, 0.0095))


    # big cupped ears, swept out and up
    ear = [
        (0.066, 0.012, 0.905, 0.013, 0.030, 0.034),
        (0.100, 0.022, 0.918, 0.011, 0.040, 0.041),
        (0.148, 0.040, 0.940, 0.0095, 0.043, 0.037),
        (0.196, 0.060, 0.960, 0.0085, 0.034, 0.026),
        (0.238, 0.077, 0.978, 0.008, 0.020, 0.013),
        (0.272, 0.090, 0.993, 0.0075, 0.008, 0.005),
    ]
    for sgn in (1, -1):
        # S points to the front for the left ear and to the back for the mirrored one
        cup = (lambda t, u, s=sgn: s * 0.013 * math.sin(math.pi * min(t, 0.97)) ** 0.7 * (u * u))
        loft(bm, ear, up=(0, 0, 1), seg=20, per_seg=5, cap0=0.4, cap1=1.4, cup=cup, mirror_x=(sgn < 0), shape=0.55)
    LM['ear_base_L'] = np.array([0.085, 0.015, 0.912])
    LM['ear_mid_L'] = np.array([0.172, 0.050, 0.950])
    LM['ear_tip_L'] = np.array([0.280, 0.094, 0.996])


def build_torso(bm):
    rows = [
        (0, 0.006, 0.385, 0.070, 0.055, 0.062),
        (0, 0.006, 0.415, 0.105, 0.072, 0.085),
        (0, 0.000, 0.455, 0.124, 0.088, 0.090),
        (0, -0.006, 0.505, 0.122, 0.112, 0.076),
        (0, -0.006, 0.555, 0.117, 0.108, 0.071),
        (0, 0.000, 0.605, 0.121, 0.085, 0.073),
        (0, 0.006, 0.655, 0.130, 0.075, 0.077),
        (0, 0.010, 0.695, 0.130, 0.062, 0.080),
        (0, 0.008, 0.733, 0.102, 0.052, 0.076),
        (0, 0.000, 0.765, 0.060, 0.045, 0.060),
        (0, -0.016, 0.797, 0.045, 0.040, 0.046),
        (0, -0.028, 0.840, 0.046, 0.040, 0.046),
    ]
    loft(bm, rows, up=(0, -1, 0), seg=24, cap0=0.8, cap1=0.8)
    for sgn in (1, -1):   # shoulder blades: flat plates, top and inner edges raised, lower tip fading into the back
        rot = (Matrix.Rotation(math.radians(-22 * sgn), 3, 'Z') @ Matrix.Rotation(math.radians(12 * sgn), 3, 'Y') @
               Matrix.Rotation(math.radians(-10), 3, 'X'))
        ellipsoid(bm, Vector((sgn * 0.056, 0.069, 0.668)), (0.040, 0.011, 0.052), rot)



def build_leg(bm, m):
    rows = [
        (0.070, 0.000, 0.460, 0.060, 0.065, 0.070),
        (0.075, 0.000, 0.400, 0.062, 0.062, 0.066),
        (0.080, -0.003, 0.330, 0.051, 0.052, 0.052),
        (0.085, -0.008, 0.275, 0.041, 0.042, 0.040),
        (0.088, -0.012, 0.245, 0.044, 0.048, 0.038),
        (0.090, -0.008, 0.215, 0.039, 0.039, 0.042),
        (0.092, -0.002, 0.175, 0.041, 0.035, 0.052),
        (0.094, 0.000, 0.120, 0.032, 0.031, 0.036),
        (0.095, 0.000, 0.085, 0.026, 0.026, 0.028),
        (0.095, 0.004, 0.058, 0.030, 0.030, 0.030),
    ]
    loft(bm, rows, up=(0, -1, 0), seg=18, cap0=0.6, cap1=0.6, mirror_x=m)
    s = -1 if m else 1
    ellipsoid(bm, Vector((s * 0.088, -0.040, 0.248)), (0.026, 0.016, 0.028))   # kneecap
    # big bare foot + three toes
    foot = [
        (0.095, 0.045, 0.036, 0.030, 0.024, 0.031),
        (0.096, 0.018, 0.042, 0.037, 0.034, 0.037),
        (0.098, -0.022, 0.036, 0.043, 0.027, 0.032),
        (0.100, -0.058, 0.029, 0.048, 0.021, 0.026),
        (0.100, -0.090, 0.024, 0.047, 0.016, 0.021),
        (0.100, -0.108, 0.022, 0.042, 0.013, 0.018),
    ]
    loft(bm, foot, up=(0, 0, 1), seg=18, cap0=0.9, cap1=0.5, mirror_x=m)
    for dx, r, ln in ((-0.028, 0.0185, 0.060), (0.001, 0.0155, 0.058), (0.029, 0.0135, 0.050)):
        x = 0.100 + dx
        toe = [
            (x, -0.090, 0.022, r, r * 0.8, r),
            (x + 0.004 * np.sign(dx), -0.090 - ln * 0.6, 0.017, r * 0.92, r * 0.72, r * 0.95),
            (x + 0.006 * np.sign(dx), -0.090 - ln, 0.014, r * 0.75, r * 0.62, r * 0.8),
        ]
        loft(bm, toe, up=(0, 0, 1), seg=12, cap0=0.4, cap1=0.9, mirror_x=m)
    LM['toe_tip_L'] = np.array([0.100, -0.160, 0.014])


def build_arm(bm, m):
    rows = [
        (0.070, 0.005, 0.700, 0.045, 0.045, 0.045),
        (0.120, 0.005, 0.712, 0.050, 0.051, 0.045),
        (0.170, 0.006, 0.715, 0.040, 0.041, 0.038),
        (0.230, 0.007, 0.715, 0.032, 0.032, 0.032),
        (0.285, 0.008, 0.715, 0.029, 0.029, 0.029),
        (0.315, 0.010, 0.715, 0.031, 0.031, 0.031),
        (0.350, 0.008, 0.715, 0.036, 0.034, 0.032),
        (0.400, 0.006, 0.715, 0.034, 0.030, 0.028),
        (0.450, 0.004, 0.715, 0.029, 0.022, 0.022),
        (0.487, 0.003, 0.715, 0.026, 0.018, 0.018),
    ]
    loft(bm, rows, up=(0, 0, 1), seg=16, cap0=0.6, cap1=0.6, mirror_x=m)
    s = -1 if m else 1
    ellipsoid(bm, Vector((s * 0.318, 0.028, 0.715)), (0.020, 0.015, 0.019))    # bony elbow
    palm = [
        (0.482, 0.002, 0.715, 0.028, 0.021, 0.020),
        (0.505, 0.000, 0.716, 0.037, 0.024, 0.021),
        (0.532, 0.000, 0.716, 0.040, 0.023, 0.019),
        (0.555, 0.001, 0.716, 0.038, 0.019, 0.017),
    ]
    loft(bm, palm, up=(0, 0, 1), seg=16, cap0=0.5, cap1=0.6, mirror_x=m)
    fingers = {
        'Index': [(0.548, -0.023, 0.717), (0.582, -0.029, 0.716), (0.607, -0.033, 0.714), (0.627, -0.036, 0.711)],
        'Middle': [(0.551, 0.000, 0.717), (0.588, 0.000, 0.716), (0.616, 0.000, 0.714), (0.638, 0.000, 0.711)],
        'Ring': [(0.546, 0.023, 0.717), (0.579, 0.030, 0.716), (0.603, 0.035, 0.714), (0.622, 0.038, 0.711)],
        'Thumb': [(0.492, -0.022, 0.707), (0.513, -0.047, 0.703), (0.532, -0.064, 0.700), (0.548, -0.075, 0.698)],
    }
    radii = {'Index': (0.0112, 0.0102, 0.0094, 0.0078), 'Middle': (0.0118, 0.0106, 0.0098, 0.0080),
             'Ring': (0.0108, 0.0098, 0.0090, 0.0074), 'Thumb': (0.0145, 0.0120, 0.0104, 0.0088)}
    for f, pts in fingers.items():
        rr = [r * 1.18 for r in radii[f]]
        rows = [(p[0], p[1], p[2], r, r * 0.92, r * 0.92) for p, r in zip(pts, rr)]
        loft(bm, rows, up=(0, 0, 1), seg=12, per_seg=3, cap0=0.5, cap1=1.3, mirror_x=m)
    LM['fingers_L'] = fingers


def _clean(bm):
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-5)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')


def _apply_mod(ob, mod):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def build_body(voxel=0.0033, target_tris=3300):
    scn = bpy.context.scene
    coll = get_coll("GOB_Body")
    work = get_coll("GOB_Work")
    bm = bmesh.new()
    build_head(bm)
    build_torso(bm)
    for m in (False, True):
        build_leg(bm, m)
        build_arm(bm, m)
    remove_obj("GOB_Parts")
    parts = mesh_obj("GOB_Parts", bm, work)
    parts.hide_render = True

    remove_obj("GoblinBody")
    body = bpy.data.objects.new("GoblinBody", parts.data.copy())
    coll.objects.link(body)
    mod = body.modifiers.new("remesh", 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    mod.use_smooth_shade = True
    _apply_mod(body, mod)

    bm = bmesh.new()
    bm.from_mesh(body.data)
    for v in bm.verts:            # flat soles
        if v.co.z < 0.0045:
            v.co.z = 0.0
    bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction='X', dist=voxel * 0.25)
    _clean(bm)
    for _ in range(2):
        bmesh.ops.smooth_laplacian_vert(bm, verts=bm.verts[:], lambda_factor=0.4, lambda_border=0.0,
                                        use_x=True, use_y=True, use_z=True, preserve_volume=True)
    seam = [v for v in bm.verts if abs(v.co.x) < 0.02]    # hide the symmetrize crease
    for _ in range(6):
        bmesh.ops.smooth_vert(bm, verts=seam, factor=0.5, use_axis_x=False, use_axis_y=True, use_axis_z=True)
    for v in bm.verts:
        if v.co.z < 0.0:
            v.co.z = 0.0
    bm.to_mesh(body.data)
    bm.free()

    remove_obj("GOB_BodyHi")         # dense copy kept for the texture bake
    hi = bpy.data.objects.new("GOB_BodyHi", body.data.copy())
    work.objects.link(hi)
    hi.hide_render = True
    hi.hide_set(True)

    tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
    dec = body.modifiers.new("decimate", 'DECIMATE')
    dec.decimate_type = 'COLLAPSE'
    dec.ratio = min(1.0, target_tris / tris)
    dec.use_symmetry = True
    dec.symmetry_axis = 'X'
    # spend relatively more of the budget on the face and ears (0 = keep, 1 = decimate freely)
    g = body.vertex_groups.new(name="_decimate")
    for v in body.data.vertices:
        g.add([v.index], 1.0 - 0.07 * float(smoothstep(0.78, 0.83, v.co.z)), 'REPLACE')
    dec.vertex_group = "_decimate"
    _apply_mod(body, dec)
    body.vertex_groups.remove(body.vertex_groups["_decimate"])
    bm = bmesh.new()
    bm.from_mesh(body.data)
    _clean(bm)
    bm.to_mesh(body.data)
    bm.free()
    for p in body.data.polygons:
        p.use_smooth = True

    # eyes: separate spheres (skinned to the eye bones later), pole = pupil looking forward
    # the game eyes are coarse; iris and pupil are baked from the dense GOB_EyesHi copy
    for name, seg, rings, dest in (("GoblinEyes", 12, 8, coll), ("GOB_EyesHi", 32, 24, work)):
        bm = bmesh.new()
        for sgn in (1, -1):
            c = LM['eye_L'] * np.array([sgn, 1, 1])
            ellipsoid(bm, Vector(c), (EYE_R, EYE_R, EYE_R), rot=Matrix.Rotation(math.pi / 2, 3, 'X'), seg=seg, rings=rings)
        remove_obj(name)
        ob = mesh_obj(name, bm, dest)
        for p in ob.data.polygons:
            p.use_smooth = True
    eyes = bpy.data.objects["GoblinEyes"]
    bpy.data.objects["GOB_EyesHi"].hide_render = True
    parts.hide_set(True)
    parts.hide_viewport = True
    return body, eyes
