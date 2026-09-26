"""Body-variation shape keys for the goblin (exported as Unity blend shapes).

Fat / Skinny / Brawny change the build (belly, limbs, neck; Brawny = shoulders, arms, chest, hands); the outfits get matching keys so harness, belt and
loincloth follow. EarsDroop bends both ears down; EarTornL / EarTornR rip the tip off one ear.
GoblinAppearance in Unity picks weights per goblin and bakes them into the merged mesh.
"""
import bpy, math
import numpy as np
from mathutils.kdtree import KDTree
from gob_common import smoothstep

BUILD_KEYS = ("Fat", "Skinny", "Brawny")


def _arrays(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    no = np.empty(n * 3)
    me.vertex_normals.foreach_get('vector', no)
    return co.reshape(-1, 3), no.reshape(-1, 3)


def _eye_mask(ob):
    m = np.zeros(len(ob.data.vertices), bool)
    idx = {ob.vertex_groups[n].index for n in ("LeftEye", "RightEye") if n in ob.vertex_groups}
    for v in ob.data.vertices:
        if any(g.group in idx and g.weight > 0.5 for g in v.groups):
            m[v.index] = True
    return m


def build_amounts(co):
    x, y, z = co.T
    ax = np.abs(x)
    arm = smoothstep(0.12, 0.15, ax) * (np.abs(z - 0.715) < 0.09)
    hand = smoothstep(0.45, 0.49, ax)
    torso = smoothstep(0.36, 0.42, z) * smoothstep(0.80, 0.75, z) * (1 - arm) * (ax < 0.17)
    belly = np.exp(-((z - 0.53) / 0.085) ** 2) * smoothstep(0.03, -0.07, y) * smoothstep(0.14, 0.05, ax) * (1 - arm)
    hips = np.exp(-((z - 0.44) / 0.05) ** 2) * (ax < 0.16) * (1 - arm)
    thigh = smoothstep(0.20, 0.30, z) * smoothstep(0.45, 0.40, z) * (ax > 0.02)
    calf = smoothstep(0.08, 0.12, z) * smoothstep(0.24, 0.20, z)
    upper_arm = arm * smoothstep(0.32, 0.29, ax)
    forearm = arm * smoothstep(0.29, 0.33, ax) * (1 - hand)
    neck = smoothstep(0.75, 0.78, z) * smoothstep(0.84, 0.81, z) * (ax < 0.07)
    jowl = smoothstep(0.80, 0.83, z) * smoothstep(0.89, 0.86, z) * smoothstep(-0.03, -0.08, y) * (ax < 0.09)
    fat = 0.014 * torso + 0.036 * belly + 0.010 * hips + 0.013 * thigh + 0.007 * calf + 0.011 * upper_arm \
        + 0.006 * forearm + 0.008 * neck + 0.006 * jowl
    skinny = -(0.011 * torso + 0.028 * belly + 0.006 * hips + 0.009 * thigh + 0.004 * calf + 0.006 * upper_arm
               + 0.004 * forearm + 0.005 * neck)
    shoulder = smoothstep(0.06, 0.10, ax) * smoothstep(0.22, 0.14, ax) * smoothstep(0.66, 0.70, z) * smoothstep(0.80, 0.76, z)
    chest_up = smoothstep(0.58, 0.64, z) * smoothstep(0.77, 0.72, z) * (ax < 0.15) * (1 - arm)
    brawny = 0.017 * upper_arm + 0.013 * forearm + 0.016 * shoulder + 0.013 * chest_up + 0.012 * neck + 0.006 * thigh \
        + 0.005 * calf + 0.0045 * hand * (np.abs(z - 0.715) < 0.1) + 0.004 * jowl
    return fat, skinny, brawny


def _ear_frame(sign):
    pivot = np.array([sign * 0.085, 0.015, 0.912])
    d = np.array([sign * 0.195, 0.078, 0.084])
    return pivot, d / np.linalg.norm(d)


def ear_droop(co, deg=50):
    out = co.copy()
    x, y, z = co.T
    ear = smoothstep(0.086, 0.10, np.abs(x)) * (z > 0.85) * (z < 1.06) * (y > -0.04)
    for sign in (1, -1):
        sel = (ear > 0) & (sign * x > 0)
        pivot, d = _ear_frame(sign)
        rel = co[sel] - pivot
        t = np.clip((rel @ d) / 0.21, 0, 1)
        a = np.radians(deg) * sign * t ** 1.2 * ear[sel]
        c, s = np.cos(a), np.sin(a)
        rx = rel[:, 0] * c + rel[:, 2] * s                  # rotation about +Y through the ear root
        rz = -rel[:, 0] * s + rel[:, 2] * c
        out[sel] = pivot + np.stack([rx, rel[:, 1], rz], 1)
    return out


def ear_torn(co, sign, cut=0.70):
    out = co.copy()
    x, y, z = co.T
    ear = (np.abs(x) > 0.09) & (z > 0.85) & (z < 1.06) & (y > -0.04) & (sign * x > 0)
    pivot, d = _ear_frame(sign)
    rel = co[ear] - pivot
    s = rel @ d
    L = 0.215
    over = np.clip(s - cut * L, 0, None)
    jag = 0.007 * np.sin(rel[:, 2] * 260.0) * (over > 0)            # ragged edge
    out[ear] = co[ear] - np.outer(over * 0.9 - jag, d)
    return out


def _set_keys(ob, keys):
    if ob.data.shape_keys is not None:
        ob.shape_key_clear()
    ob.shape_key_add(name="Basis", from_mix=False)
    for name, co in keys.items():
        k = ob.shape_key_add(name=name, from_mix=False)
        k.data.foreach_set('co', co.ravel())
        k.value = 0.0


def add_body_keys(body):
    co, no = _arrays(body)
    eyes = _eye_mask(body)
    fat, skinny, brawny = build_amounts(co)
    for a in (fat, skinny, brawny):
        a[eyes] = 0
    keys = {
        "Fat": co + no * fat[:, None],
        "Skinny": co + no * skinny[:, None],
        "Brawny": co + no * brawny[:, None],
        "EarsDroop": np.where(eyes[:, None], co, ear_droop(co)),
        "EarTornL": np.where(eyes[:, None], co, ear_torn(co, 1)),
        "EarTornR": np.where(eyes[:, None], co, ear_torn(co, -1)),
    }
    _set_keys(body, keys)
    return {k: float(np.abs(v - co).max()) for k, v in keys.items()}


def add_outfit_keys(body, outfits):
    """Outfits copy the build keys from the nearest body vertex, so they stay on the skin."""
    bco, _ = _arrays(body)
    eyes = _eye_mask(body)
    kd = KDTree(len(bco))
    for i, p in enumerate(bco):
        if not eyes[i]:
            kd.insert(p, i)
    kd.balance()
    kb = body.data.shape_keys.key_blocks
    deltas = {}
    for name in BUILD_KEYS:
        kc = np.empty(len(bco) * 3)
        kb[name].data.foreach_get('co', kc)
        deltas[name] = kc.reshape(-1, 3) - bco
    for ob in outfits:
        oco, _ = _arrays(ob)
        near = np.array([kd.find(p)[1] for p in oco])
        _set_keys(ob, {name: oco + deltas[name][near] for name in BUILD_KEYS})
