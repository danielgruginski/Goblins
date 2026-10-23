"""Troll body: the goblin grown into a ~2.5 m gangly troll (a unit from Daniel's card game).

Daniel: "Trolls would look like goblins, slender with long arms and legs". So the troll starts from the approved goblin:
gob_body's own part builders (head, torso, legs, arms) make the parts in goblin space, and TrollWarp moves each part
into troll space before they are fused (gob_body.build_body(warp=...)). The same warp moves the goblin's bone table
(gob_rig.bone_table: Humanoid names, hierarchy, rolls, sockets) and its IK poles, so the troll's skeleton is the
goblin's with troll proportions and props on its sockets follow the goblin's conventions.

Every part vertex remembers where it came from (goblin-space position "gob_co", part "gob_part"); the fused troll
meshes get both back from the nearest part surface (transfer_gob_co), so the goblin's paint masks (nails, ears, nose,
mouth), UV seam cuts and shape keys run on the troll unchanged (troll_paint.py).

All sizes below are in goblin units times P['S'] (the troll's growth) unless marked as metres.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from gob_common import smoothstep
import gob_body, gob_rig

NAMES = dict(coll="TRL_Body", work="TRL_Work", parts="TRL_Parts", body="TrollBody", hi="TRL_BodyHi",
             eyes="TrollEyes", eyes_hi="TRL_EyesHi")
RIG = "TrollRig"
PART_IDS = {'head': 0, 'torso': 1, 'leg': 2, 'arm': 3}

# goblin landmarks (gob_rig.bone_table)
HIP_Z, NECK_Z = 0.445, 0.735
HEAD_J = np.array([0.0, -0.022, 0.815])
ARM_U = np.array([0.115, 0.315, 0.487, 0.550])            # shoulder joint, elbow, wrist, knuckles along |x|
ARM_Y = np.array([0.006, 0.009, 0.003, 0.000])
ARM_Z = np.array([0.713, 0.715, 0.715, 0.716])
LEG = np.array([[0.075, 0.0, 0.445], [0.088, -0.012, 0.245], [0.095, 0.0, 0.070]])   # hip, knee, ankle

P = dict(
    S=2.2,                                   # overall growth: goblin ~1.03 m -> troll ~2.5 m
    torso_w=0.86, torso_d=0.86, torso_l=1.08, belly=0.30, crotch=0.6,
    neck_l=1.0, neck_w=0.95,
    head=0.80, head_x=0.96, head_y=1.0, head_z=1.10, jaw=0.16, jaw_fwd=0.12, jaw_w=0.35, chin=0.008, brow=0.010,
    nose_len=0.85, nose_w=1.55, nose_bulb=0.45, nose_droop=26.0, ears=1.12, ear_tilt=16.0, eyes=0.88,
    thigh=1.30, shin=1.30, leg_w=0.80, calf_w=0.84, foot=1.08, leg_splay=0.6,
    upper_arm=1.12, forearm=1.12, arm_w=0.82, hand=1.10, fingers=1.12,
    hunch=0.04, head_fwd=0.07, hump=0.035, shrug=0.035, shoulder_fwd=0.02,     # metres
)


def _lerp(a, b, t):
    t = np.asarray(t, float)[..., None] if np.ndim(a) > np.ndim(t) else t
    return a * (1 - t) + b * t


class TrollWarp:
    """Goblin space -> troll space, per part. Vectorised over (n, 3) arrays; left and right by |x|."""

    def __init__(self, **over):
        if 'eye_L' not in gob_body.LM:                   # the goblin's landmarks come from its part builders
            fill_landmarks()
        self.p = dict(P, **over)
        p, S = self.p, self.p['S']
        self.W, self.D, self.L = S * p['torso_w'], S * p['torso_d'], S * p['torso_l']
        self.Ln, self.Wn = S * p['neck_l'], S * p['neck_w']
        self.Hs = S * p['head'] * np.array([p['head_x'], p['head_y'], p['head_z']])
        self.ankle_h = LEG[2, 2] * S * p['foot']
        self.hip_z = self.ankle_h + (LEG[1, 2] - LEG[2, 2]) * S * p['shin'] + (LEG[0, 2] - LEG[1, 2]) * S * p['thigh']
        self.neck_z = self.hip_z + (NECK_Z - HIP_Z) * self.L
        # joints in troll space
        self.J = self.trunk(HEAD_J[None])[0]
        sj = self.trunk(np.array([[ARM_U[0], ARM_Y[0], ARM_Z[0]]]))[0]
        self.Sj = sj
        lens = np.diff(ARM_U) * S * np.array([p['upper_arm'], p['forearm'], p['hand']])
        self.U = np.concatenate([[sj[0]], sj[0] + np.cumsum(lens)])
        H = self.trunk(LEG[:1])[0]
        K = H + (LEG[1] - LEG[0]) * S * p['thigh'] * np.array([p['leg_splay'], 1, 1])
        A = K + (LEG[2] - LEG[1]) * S * p['shin'] * np.array([p['leg_splay'], 1, 1])
        self.legJ = np.array([H, K, A])
        LM = gob_body.LM
        self.nose_root = np.array([0.0, LM['nose_root'][1] - 0.014, 0.900])
        self.nose_tip = np.asarray(LM['nose_tip'], float)
        self.nose_end = np.array([0.0, LM['nose_root'][1] - 0.086, 0.846])     # gob_body.build_head's last nose row
        self.ear_base = np.asarray(LM['ear_base_L'], float)
        self.eye = np.asarray(LM['eye_L'], float)
        self.eye_c = self.head(self.eye[None])[0]
        self.eye_r = gob_body.EYE_R * p['eyes'] * self.Hs.min()

    # ------------------------------------------------------------------ trunk (torso + neck), the frame for the rest
    def trunk(self, X):
        p = self.p
        x, y, z = X.T
        ax, sx = np.abs(x), np.where(x < 0, -1.0, 1.0)
        zt = np.where(z <= NECK_Z, self.hip_z + (z - HIP_Z) * self.L, self.neck_z + (z - NECK_Z) * self.Ln)
        # the goblin's crotch (below the hip joints) is drawn up between the troll's thighs, and narrowed
        low = smoothstep(HIP_Z, HIP_Z - 0.06, z)
        zt = np.where(z < HIP_Z, self.hip_z + (z - HIP_Z) * self.L * self.p['crotch'], zt)
        wn = smoothstep(0.72, 0.78, z)
        Wz = (self.W * (1 - wn) + self.Wn * wn) * (1 - (1 - self.p['crotch']) * low)
        Dz = self.D * (1 - wn) + self.Wn * wn
        belly = np.exp(-((z - 0.53) / 0.08) ** 2) * smoothstep(0.0, -0.06, y)
        yt = y * Dz * (1 - p['belly'] * belly)
        fwd = -p['hunch'] * smoothstep(0.58, NECK_Z, z) - p['head_fwd'] * np.clip((z - NECK_Z) / (HEAD_J[2] - NECK_Z), 0, None)
        hump = p['hump'] * np.exp(-((z - 0.68) / 0.05) ** 2) * smoothstep(0.02, 0.07, y)
        sh = smoothstep(0.04, 0.10, ax) * smoothstep(0.62, 0.69, z) * smoothstep(0.80, 0.76, z)
        return np.stack([sx * ax * Wz, yt + fwd + hump - p['shoulder_fwd'] * sh, zt + p['shrug'] * sh], 1)

    # ------------------------------------------------------------------ head: nose, ears, lids pre-warped, then scaled
    def head(self, X):
        p = self.p
        X = np.array(X, float)
        x, y, z = X.T
        ax, sx = np.abs(x), np.where(x < 0, -1.0, 1.0)
        # nose: a bulb rather than a longer spike (thicker more than longer), drooping, about its root
        a, b = self.nose_root, self.nose_tip
        t = np.clip(((X - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
        dn = np.linalg.norm(X - (a + t[:, None] * (b - a)), axis=1)
        wn = smoothstep(0.036, 0.026, dn) * smoothstep(a[1] + 0.006, a[1] - 0.004, y)
        ang = math.radians(p['nose_droop'])
        c, s = math.cos(ang), math.sin(ang)
        nd = (b - a) / np.linalg.norm(b - a)
        ln = (self.nose_end - a) @ nd                    # where the goblin nose's tip cap begins
        r = X - a
        pr = r @ nd
        rp = r - pr[:, None] * nd
        bulb = 1 + p['nose_bulb'] * smoothstep(0.35, 0.9, t)                   # a fat drooping tip
        tipw = p['nose_w'] * (1 + p['nose_bulb'])
        along = np.minimum(pr, ln) * p['nose_len'] + np.maximum(pr - ln, 0) * tipw   # the tip cap stays round
        r = along[:, None] * nd + rp * (p['nose_w'] * bulb)[:, None]
        rn = np.stack([r[:, 0], r[:, 1] * c + r[:, 2] * s, -r[:, 1] * s + r[:, 2] * c], 1)   # tip turns down
        X = _lerp(X, a + rn, wn)
        # ears: bigger, tipped down a little, about their base
        B = self.ear_base * np.stack([sx, np.ones_like(sx), np.ones_like(sx)], 1)
        we = smoothstep(0.086, 0.11, ax) * smoothstep(0.84, 0.86, z) * smoothstep(-0.05, -0.03, y)
        r = (X - B) * p['ears']
        ang = np.radians(p['ear_tilt']) * sx
        c, s = np.cos(ang), np.sin(ang)
        re = np.stack([r[:, 0] * c + r[:, 2] * s, r[:, 1], -r[:, 0] * s + r[:, 2] * c], 1)
        X = _lerp(X, B + re, we)
        # lids shrink with the eyes about the eye centre (deep-set little eyes)
        E = self.eye * np.stack([sx, np.ones_like(sx), np.ones_like(sx)], 1)
        de = np.linalg.norm(X - E, axis=1)
        rl = gob_body.EYE_R + 0.0035
        wl = smoothstep(rl + 0.006, rl + 0.001, de)
        X = _lerp(X, E + (X - E) * p['eyes'], wl)
        # a heavier brow over the little eyes, a blunter chin than the goblin's point
        hc, hr = gob_body.HC, gob_body.HR
        n = (X - hc) / hr
        n /= np.maximum(np.linalg.norm(n, axis=1), 1e-9)[:, None]
        brow = gob_body._g(n, (0.36, -0.82, 0.42), 0.17) + 0.6 * gob_body._g(n, (0, -0.9, 0.42), 0.12)
        brow *= 1 - wn
        chin = gob_body._g(n, (0, -0.55, -0.83), 0.16)
        X = X + n * (p['brow'] * brow - p['chin'] * chin)[:, None]
        return self.head_base(X)

    def head_base(self, X):
        p = self.p
        d = X - HEAD_J
        front = smoothstep(-0.05, -0.10, X[:, 1])
        low = np.clip(0.88 - X[:, 2], 0, None) * front
        d = d + np.stack([np.zeros(len(X)), -p['jaw_fwd'] * low, -p['jaw'] * low], 1)
        d[:, 0] *= 1 + p['jaw_w'] * smoothstep(0.885, 0.80, X[:, 2])      # a heavier jaw than the goblin's pointed one
        return self.J + d * self.Hs

    # ------------------------------------------------------------------ arms: stretched along |x|, thin, big hands
    def arm(self, X):
        p, S = self.p, self.p['S']
        x, y, z = X.T
        ax, sx = np.abs(x), np.where(x < 0, -1.0, 1.0)
        fing = S * p['hand'] * p['fingers']
        u = np.interp(ax, ARM_U, self.U)
        u = np.where(ax < ARM_U[0], self.U[0] + (ax - ARM_U[0]) * self.W, u)
        u = np.where(ax > ARM_U[-1], self.U[-1] + (ax - ARM_U[-1]) * fing, u)
        ya, za = np.interp(ax, ARM_U, ARM_Y), np.interp(ax, ARM_U, ARM_Z)
        k = np.interp(ax, ARM_U, self.U - self.U[0]) / np.maximum(np.interp(ax, ARM_U, ARM_U - ARM_U[0]), 1e-6)
        g_arm, g_hand = S * p['arm_w'], S * p['hand']
        t1 = smoothstep(0.10, 0.17, ax)                  # torso -> arm girth
        t2 = smoothstep(0.46, 0.50, ax)                  # arm -> hand
        gy = (self.D * (1 - t1) + g_arm * t1) * (1 - t2) + g_hand * t2
        gz = (self.L * (1 - t1) + g_arm * t1) * (1 - t2) + g_hand * t2
        out_y = self.Sj[1] + (y - ya) * gy + (ya - ARM_Y[0]) * k
        out_z = self.Sj[2] + (z - za) * gz + (za - ARM_Z[0]) * k
        res = np.stack([sx * u, out_y, out_z], 1)
        return _lerp(self.trunk(X), res, smoothstep(0.06, 0.13, ax))

    # ------------------------------------------------------------------ legs: long, thin, big feet
    def leg(self, X):
        p, S = self.p, self.p['S']
        x, y, z = X.T
        ax, sx = np.abs(x), np.where(x < 0, -1.0, 1.0)
        zs = LEG[::-1, 2]                                # ankle, knee, hip (ascending)
        J = self.legJ[::-1]
        G = LEG[::-1]
        zz = np.clip(z, zs[0], None)
        gx = np.interp(zz, zs, G[:, 0], right=None)
        gy = np.interp(zz, zs, G[:, 1])
        tx = np.interp(zz, zs, J[:, 0])
        ty = np.interp(zz, zs, J[:, 1])
        tz = np.interp(zz, zs, J[:, 2])
        above = zz > zs[-1]                              # thigh top inside the hips: carry the thigh on
        dz = zz - zs[-1]
        tz = np.where(above, J[-1, 2] + dz * S * p['thigh'], tz)
        gx = np.where(above, G[-1, 0] + dz * (G[-1, 0] - G[-2, 0]) / (zs[-1] - zs[-2]), gx)
        g = np.interp(zz, [0.07, 0.13, 0.245, 0.30, 0.50], S * np.array([p['foot'], p['calf_w'], p['calf_w'], p['leg_w'], p['leg_w']]))
        leg = np.stack([sx * (tx + (ax - gx) * g), ty + (y - gy) * g, tz], 1)
        foot = np.stack([sx * (J[0, 0] + (ax - G[0, 0]) * S * p['foot']), J[0, 1] + (y - G[0, 1]) * S * p['foot'],
                         z * S * p['foot']], 1)
        res = np.where((z < zs[0])[:, None], foot, leg)
        return _lerp(self.trunk(X), res, smoothstep(0.47, 0.40, z))

    def part(self, tag, X):
        X = np.atleast_2d(np.asarray(X, float))
        if tag == 'head':
            return self.head(X)
        if tag == 'arm':
            return self.arm(X)
        if tag == 'leg':
            return self.leg(X)
        out = self.trunk(X)                              # torso; the neck blends into the head near the jaw
        return _lerp(out, self.head_base(X), smoothstep(0.79, 0.83, X[:, 2]))

    # ------------------------------------------------------------------ gob_body.build_body hook
    def __call__(self, bm, ranges):
        """Move the goblin parts into troll space; keep each vertex's goblin position and part as layers."""
        bm.verts.ensure_lookup_table()
        lco = bm.verts.layers.float_vector.new("gob_co")
        lpart = bm.verts.layers.int.new("gob_part")
        for tag, v0, v1, _m in ranges:
            vs = bm.verts[v0:v1]
            X = np.array([v.co[:] for v in vs])
            Y = self.part(tag, X)
            for v, x, yv in zip(vs, X, Y):
                v[lco] = Vector(x)
                v[lpart] = PART_IDS[tag]
                v.co = Vector(yv)


def fill_landmarks():
    bm = bmesh.new()
    gob_body.build_head(bm)
    gob_body.build_leg(bm, False)
    gob_body.build_arm(bm, False)
    bm.free()


# ---------------------------------------------------------------------------------------------- skeleton
def _bone_part(name):
    n = name.replace("Left", "").replace("Right", "")
    if n in ("Head", "Jaw", "Socket_Helm", "Eye") or n.startswith("Ear"):
        return 'head'
    if n in ("UpperLeg", "LowerLeg", "Foot", "Toes"):
        return 'leg'
    if n in ("Shoulder", "UpperArm", "LowerArm", "Hand", "Socket_Hand", "Socket_Forearm", "Socket_Shoulder") or \
            any(f in n for f in ("Thumb", "Index", "Middle", "Ring")):
        return 'arm'
    return 'torso'


def bone_table(warp):
    """gob_rig.bone_table() moved into troll space (same names, parents, rolls and deform flags)."""
    rows = []
    for n, h, t, par, roll, d in gob_rig.bone_table():
        if n == "Root":
            rows.append((n, (0, 0, 0), (0, 0, 0.10 * warp.p['S']), par, roll, d))
            continue
        if n.endswith("Eye"):
            sx = 1 if n.startswith("Left") else -1
            c = warp.eye_c * np.array([sx, 1, 1])
            rows.append((n, tuple(c), tuple(c + np.array([0, -0.03 * warp.Hs[1], 0])), par, roll, d))
            continue
        part = _bone_part(n)
        if n == "Head":
            hh = warp.J
            tt = warp.head_base(np.array([t]))[0]
        else:
            if part == 'torso' and n == "Neck":
                hh = warp.trunk(np.array([h]))[0]
                tt = warp.J
            else:
                hh, tt = warp.part(part, np.array([h, t]))
        rows.append((n, tuple(hh), tuple(tt), par, roll, d))
    # chains must stay connected: a child's head is its parent's tail where the goblin's were
    by = {r[0]: i for i, r in enumerate(rows)}
    gob = {r[0]: r for r in gob_rig.bone_table()}
    for i, (n, h, t, par, roll, d) in enumerate(rows):
        if par and not n.startswith("Socket") and np.allclose(gob[par][2], gob[n][1], atol=1e-6):
            rows[i] = (n, rows[by[par]][2], t, par, roll, d)
    return rows


def ik_rows(warp):
    out = []
    for ctl, src, pole, pos, chain, infl in gob_rig.IK:
        part = 'leg' if 'Foot' in src else 'arm'
        out.append((ctl, src, pole, tuple(warp.part(part, np.array([pos]))[0]), chain, infl))
    return out


def build_armature(warp):
    return gob_rig.build_armature(coll_name="TRL_Rig", name=RIG, table=bone_table(warp), ik_rows=ik_rows(warp))


# ---------------------------------------------------------------------------------------------- body
def keep_weights(warp):
    """Decimation weights in troll space (0 = keep, 1 = decimate freely): the face, hands and the long limbs'
    joints keep more loops, so elbows and knees still bend round."""
    S = warp.p['S']
    joints = [np.array([warp.U[1], warp.Sj[1], warp.Sj[2]]), np.array([warp.U[2], warp.Sj[1], warp.Sj[2]]),
              warp.Sj, warp.legJ[1], warp.legJ[2], warp.legJ[0]]
    jz = warp.J[2]

    def keep(co):
        p = np.array([abs(co.x), co.y, co.z])
        j = max(math.exp(-((p - c) ** 2).sum() / (2 * (0.06 * S) ** 2)) for c in joints)
        face = float(smoothstep(jz - 0.06, jz + 0.02, co.z))
        hand = float(smoothstep(warp.U[2] - 0.02, warp.U[2] + 0.04, abs(co.x))) * (co.z > warp.Sj[2] - 0.3)
        return 1.0 - 0.10 * face - 0.12 * j - 0.05 * hand
    return keep


def build_body(warp, body_tris=5000, voxel=0.0066):
    S = warp.p['S']
    body, eyes = gob_body.build_body(voxel=voxel, target_tris=body_tris, warp=warp, names=NAMES, seam_w=0.02 * S,
                                     sole=0.0045 * S, keep=keep_weights(warp), eye_c=warp.eye_c, eye_r=warp.eye_r)
    return body, eyes


def transfer_gob_co(target, parts, name="gob_co"):
    """Goblin-space position (and part) for every vertex of `target` from the nearest point of the warped parts."""
    pm = parts.data
    V = len(pm.vertices)
    pco = np.empty(V * 3)
    pm.vertices.foreach_get('co', pco)
    pco = pco.reshape(-1, 3)
    gco = np.empty(V * 3)
    pm.attributes["gob_co"].data.foreach_get('vector', gco)
    gco = gco.reshape(-1, 3)
    gpart = np.empty(V, dtype=np.int32)
    pm.attributes["gob_part"].data.foreach_get('value', gpart)
    polys = [tuple(p.vertices) for p in pm.polygons]
    bvh = BVHTree.FromPolygons([Vector(c) for c in pco], polys)
    tm = target.data
    T = len(tm.vertices)
    tco = np.empty(T * 3)
    tm.vertices.foreach_get('co', tco)
    tco = tco.reshape(-1, 3)
    out = np.empty((T, 3))
    part = np.empty(T, dtype=np.int32)
    for i, c in enumerate(tco):
        loc, nrm, fi, dist = bvh.find_nearest(Vector(c))
        vs = polys[fi]
        d = np.linalg.norm(pco[list(vs)] - np.array(loc), axis=1)
        w = 1.0 / np.maximum(d, 1e-6)
        w /= w.sum()
        g = (gco[list(vs)] * w[:, None]).sum(0)
        out[i] = g
        part[i] = gpart[vs[int(np.argmax(w))]]
    for nm, data, typ in ((name, out, 'FLOAT_VECTOR'), ("gob_part", part, 'INT')):
        if nm in tm.attributes:
            tm.attributes.remove(tm.attributes[nm])
        a = tm.attributes.new(nm, typ, 'POINT')
        a.data.foreach_set('vector' if typ == 'FLOAT_VECTOR' else 'value', data.ravel())
    return out, part


def gob_co(ob):
    """(goblin-space positions, parts) stored on a troll mesh by transfer_gob_co."""
    me = ob.data
    n = len(me.vertices)
    g = np.empty(n * 3)
    me.attributes["gob_co"].data.foreach_get('vector', g)
    pt = np.empty(n, dtype=np.int32)
    me.attributes["gob_part"].data.foreach_get('value', pt)
    return g.reshape(-1, 3), pt


def eye_gob_co(eyes_ob, warp):
    """Goblin-space positions for the eye spheres: same direction from the eye centre, the goblin's eye radius."""
    me = eyes_ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    sx = np.where(co[:, 0] < 0, -1.0, 1.0)[:, None]
    c = warp.eye_c * np.hstack([sx, np.ones_like(sx), np.ones_like(sx)])
    d = co - c
    d /= np.maximum(np.linalg.norm(d, axis=1), 1e-9)[:, None]
    e = warp.eye * np.hstack([sx, np.ones_like(sx), np.ones_like(sx)])
    return e + d * gob_body.EYE_R


def measures(warp):
    """Heights and lengths in metres, for the report."""
    rig = bpy.data.objects.get(RIG)
    out = {"hip": round(warp.hip_z, 3), "neck_base": round(warp.neck_z, 3), "head_joint": round(warp.J[2], 3),
           "shoulder_joint": [round(v, 3) for v in warp.Sj], "elbow_x": round(warp.U[1], 3), "wrist_x": round(warp.U[2], 3),
           "knee": [round(v, 3) for v in warp.legJ[1]], "ankle": [round(v, 3) for v in warp.legJ[2]]}
    body = bpy.data.objects.get(NAMES["body"])
    if body is not None:
        zs = [v.co.z for v in body.data.vertices]
        xs = [v.co.x for v in body.data.vertices]
        ys = [v.co.y for v in body.data.vertices]
        out["height"] = round(max(zs), 3)
        out["span"] = round(max(xs) - min(xs), 3)
        out["depth"] = round(max(ys) - min(ys), 3)
    arm_len = (warp.U[-1] - warp.Sj[0]) + 0.095 * warp.p['S'] * warp.p['hand'] * warp.p['fingers']
    out["shoulder_to_fingertip"] = round(arm_len, 3)
    out["fingertip_hanging_z"] = round(warp.Sj[2] - arm_len, 3)
    return out
