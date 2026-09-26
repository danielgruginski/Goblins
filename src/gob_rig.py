"""Goblin armature: Unity-Humanoid bone names, prop sockets, IK helpers, skinning.

Sockets are the attachment points for modular props. Each is a bone whose HEAD is the attach point:
  Socket_LeftHand / Socket_RightHand   grip centre. +Y = along the handle toward the business end
                                       (points forward in the T-pose), +Z = up. Same frame on both hands.
                                       Knuckles face +X on the RIGHT hand (edges of blades go there) and -X
                                       on the LEFT hand: a left-hand prop with a facing side must be mirrored.
  Socket_LeftForearm / RightForearm    shield/buckler on the back of the forearm. +Y along the arm (outward),
                                       +Z = away from the forearm (the shield face).
  Socket_LeftShoulder / RightShoulder  pauldrons. +Y along the arm (outward), +Z up.
  Socket_LeftHip / RightHip            pouches, scabbards, bells. +Y up, +Z outward (away from the hip).
  Socket_Belt                          belt front (buckle, skull trophy). +Y up, +Z forward.
  Socket_Chest                         chest plate / amulet. +Y up, +Z forward.
  Socket_Back                          backpack, quiver, bomb sack, banner. +Y up, +Z backward (away from the back).
  Socket_Helm                          helmets, hats, crowns; sits at the head centre. +Y up, +Z forward.
Props are modelled in socket space: origin = attach point, axes as above.
"""
import bpy, math
import numpy as np
from mathutils import Vector, Matrix
from gob_common import get_coll
import gob_body

RIG = "GoblinRig"


def _mx(v):
    return (-v[0], v[1], v[2])


def bone_table():
    LM = gob_body.LM
    eye = tuple(LM['eye_L'])
    eb, em, et = (tuple(LM[k]) for k in ('ear_base_L', 'ear_mid_L', 'ear_tip_L'))
    center = [
        # name, head, tail, parent, roll vector (bone Z points along it), deform
        ("Root", (0, 0, 0), (0, 0, 0.10), None, (0, -1, 0), False),
        ("Hips", (0, 0, 0.445), (0, 0, 0.51), "Root", (0, -1, 0), True),
        ("Spine", (0, 0, 0.51), (0, 0, 0.575), "Hips", (0, -1, 0), True),
        ("Chest", (0, 0, 0.575), (0, 0.003, 0.645), "Spine", (0, -1, 0), True),
        ("UpperChest", (0, 0.003, 0.645), (0, 0.004, 0.735), "Chest", (0, -1, 0), True),
        ("Neck", (0, 0.004, 0.735), (0, -0.022, 0.815), "UpperChest", (0, -1, 0), True),
        ("Head", (0, -0.022, 0.815), (0, -0.022, 1.0), "Neck", (0, -1, 0), True),
        ("Jaw", (0, -0.060, 0.868), (0, -0.112, 0.846), "Head", (0, 0, 1), True),   # unweighted; keeps Humanoid Jaw off the sockets
        ("Socket_Helm", tuple(gob_body.HC), tuple(gob_body.HC + np.array([0, 0, 0.08])), "Head", (0, -1, 0), False),
        ("Socket_Back", (0, 0.100, 0.655), (0, 0.100, 0.735), "UpperChest", (0, 1, 0), False),
        ("Socket_Chest", (0, -0.085, 0.660), (0, -0.085, 0.740), "UpperChest", (0, -1, 0), False),
        ("Socket_Belt", (0, -0.120, 0.482), (0, -0.120, 0.562), "Hips", (0, -1, 0), False),
    ]
    left = [
        ("LeftEye", eye, (eye[0], eye[1] - 0.03, eye[2]), "Head", (0, 0, 1), True),
        ("LeftEar01", eb, em, "Head", (0, -1, 0), True),
        ("LeftEar02", em, et, "LeftEar01", (0, -1, 0), True),
        ("LeftShoulder", (0.025, 0.004, 0.705), (0.115, 0.006, 0.713), "UpperChest", (0, 0, 1), True),
        ("LeftUpperArm", (0.115, 0.006, 0.713), (0.315, 0.009, 0.715), "LeftShoulder", (0, 0, 1), True),
        ("LeftLowerArm", (0.315, 0.009, 0.715), (0.487, 0.003, 0.715), "LeftUpperArm", (0, 0, 1), True),
        ("LeftHand", (0.487, 0.003, 0.715), (0.550, 0.000, 0.716), "LeftLowerArm", (0, 0, 1), True),
        ("LeftUpperLeg", (0.075, 0.0, 0.445), (0.088, -0.012, 0.245), "Hips", (0, -1, 0), True),
        ("LeftLowerLeg", (0.088, -0.012, 0.245), (0.095, 0.0, 0.070), "LeftUpperLeg", (0, -1, 0), True),
        ("LeftFoot", (0.095, 0.0, 0.070), (0.099, -0.075, 0.022), "LeftLowerLeg", (0, 0, 1), True),
        ("LeftToes", (0.099, -0.075, 0.022), (0.100, -0.150, 0.018), "LeftFoot", (0, 0, 1), True),
        ("Socket_LeftHand", (0.538, 0.0, 0.688), (0.538, -0.08, 0.688), "LeftHand", (0, 0, 1), False),
        ("Socket_LeftForearm", (0.400, 0.006, 0.752), (0.480, 0.006, 0.752), "LeftLowerArm", (0, 0, 1), False),
        ("Socket_LeftShoulder", (0.150, 0.006, 0.765), (0.230, 0.006, 0.765), "LeftUpperArm", (0, 0, 1), False),
        ("Socket_LeftHip", (0.136, -0.050, 0.475), (0.136, -0.050, 0.555), "Hips", (0.94, -0.34, 0), False),
    ]
    names = {'Thumb': 'Thumb', 'Index': 'Index', 'Middle': 'Middle', 'Ring': 'Ring'}
    for f, pts in LM['fingers_L'].items():
        pts = [np.array(p, float) for p in pts]
        tip = pts[3] + (pts[3] - pts[2]) / np.linalg.norm(pts[3] - pts[2]) * 0.008
        seg = [pts[0], pts[1], pts[2], tip]
        par = "LeftHand"
        for i, part in enumerate(("Proximal", "Intermediate", "Distal")):
            n = f"Left{names[f]}{part}"
            left.append((n, tuple(seg[i]), tuple(seg[i + 1]), par, (0, 0, 1), True))
            par = n
    right = []
    for n, h, t, p, r, d in left:
        rn = n.replace("Left", "Right")
        rp = p.replace("Left", "Right") if p else p
        right.append((rn, _mx(h), _mx(t), rp, _mx(r), d))
    return center + left + right


IK = [
    # control bones copy the rest of the bone they drive; none of them deform or export
    ("IK_LeftFoot", "LeftFoot", "Pole_LeftKnee", (0.088, -0.40, 0.245), "LeftLowerLeg", 1.0),
    ("IK_RightFoot", "RightFoot", "Pole_RightKnee", (-0.088, -0.40, 0.245), "RightLowerLeg", 1.0),
    ("IK_LeftHand", "LeftHand", "Pole_LeftElbow", (0.315, 0.40, 0.715), "LeftLowerArm", 0.0),
    ("IK_RightHand", "RightHand", "Pole_RightElbow", (-0.315, 0.40, 0.715), "RightLowerArm", 0.0),
]


def build_armature(coll_name="GOB_Rig"):
    coll = get_coll(coll_name)
    old = bpy.data.objects.get(RIG)
    if old is not None:
        arm_data = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        bpy.data.armatures.remove(arm_data)
    ad = bpy.data.armatures.new(RIG)
    ad.display_type = 'OCTAHEDRAL'
    ob = bpy.data.objects.new(RIG, ad)
    coll.objects.link(ob)
    ob.show_in_front = True
    vl = bpy.context.view_layer
    vl.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = ad.edit_bones
    table = bone_table()
    for n, h, t, p, r, d in table:
        b = eb.new(n)
        b.head, b.tail = Vector(h), Vector(t)
        b.align_roll(Vector(r))
        b.use_deform = d
    for n, h, t, p, r, d in table:
        if p:
            eb[n].parent = eb[p]
            eb[n].use_connect = (Vector(eb[p].tail) - Vector(eb[n].head)).length < 1e-5 and not n.startswith("Socket")
    for ctl, src, pole, pole_pos, chain_bone, infl in IK:
        s = eb[src]
        c = eb.new(ctl)
        c.head, c.tail, c.roll = s.head.copy(), s.tail.copy(), s.roll
        c.parent = eb["Root"]
        c.use_deform = False
        pb = eb.new(pole)
        pb.head = Vector(pole_pos)
        pb.tail = Vector(pole_pos) + Vector((0, 0, 0.04))
        pb.parent = eb["Root"]
        pb.use_deform = False
    bpy.ops.object.mode_set(mode='OBJECT')

    # bone collections for the animator
    cols = {nm: ad.collections.new(nm) for nm in ("Body", "Fingers", "Face", "Sockets", "IK")}
    for b in ad.bones:
        n = b.name
        if n.startswith("Socket_"):
            cols["Sockets"].assign(b)
        elif n.startswith(("IK_", "Pole_")):
            cols["IK"].assign(b)
        elif any(k in n for k in ("Thumb", "Index", "Middle", "Ring")):
            cols["Fingers"].assign(b)
        elif any(k in n for k in ("Eye", "Ear", "Jaw")):
            cols["Face"].assign(b)
        else:
            cols["Body"].assign(b)
    for b in ad.bones:
        if b.name.startswith("Socket_"):
            b.color.palette = 'THEME09'
        elif b.name.startswith(("IK_", "Pole_")):
            b.color.palette = 'THEME01'

    # IK constraints with pole angles solved so the rest pose is unchanged
    for ctl, src, pole, pole_pos, chain_bone, infl in IK:
        pb = ob.pose.bones[chain_bone]
        ik = pb.constraints.new('IK')
        ik.name = "IK"
        ik.target, ik.subtarget = ob, ctl
        ik.pole_target, ik.pole_subtarget = ob, pole
        ik.chain_count = 2
        ik.influence = infl
        ik.pole_angle = _solve_pole_angle(ob, chain_bone, ik)
        cr = ob.pose.bones[src].constraints.new('COPY_ROTATION')
        cr.name = "IK rot"
        cr.target, cr.subtarget = ob, ctl
        cr.influence = infl
    return ob


def _solve_pole_angle(ob, bone, ik):
    rest = ob.pose.bones[bone].matrix.copy()
    best, best_err = 0.0, 1e9
    infl = ik.influence
    ik.influence = 1.0
    for deg in range(-180, 180, 1):
        ik.pole_angle = math.radians(deg)
        bpy.context.view_layer.update()
        m = ob.pose.bones[bone].matrix
        err = sum((m.col[i] - ob.data.bones[bone].matrix_local.col[i]).length for i in range(4))
        if err < best_err:
            best, best_err = math.radians(deg), err
    ik.influence = infl
    return best


def skin(body, eyes, rig):
    """Heat-map weights for the body from the deform bones (not eyes, sockets, IK); eyes rigid to eye bones."""
    ad = rig.data
    keep = {}
    for b in ad.bones:
        keep[b.name] = b.use_deform
        if b.name.startswith(("Socket_", "IK_", "Pole_")) or "Eye" in b.name or b.name == "Jaw":
            b.use_deform = False
    for o in bpy.context.selected_objects:
        o.select_set(False)
    body.vertex_groups.clear()
    for m in [m for m in body.modifiers if m.type == 'ARMATURE']:
        body.modifiers.remove(m)
    body.parent = None
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    for n, d in keep.items():
        ad.bones[n].use_deform = d
    # sockets are exported as deform bones with no weights (so an FBX deform-only export keeps them)
    for b in ad.bones:
        if b.name.startswith("Socket_"):
            b.use_deform = True

    # eyes: rigid on their bones
    eyes.vertex_groups.clear()
    gl = eyes.vertex_groups.new(name="LeftEye")
    gr = eyes.vertex_groups.new(name="RightEye")
    for v in eyes.data.vertices:
        (gl if v.co.x > 0 else gr).add([v.index], 1.0, 'REPLACE')
    for m in [m for m in eyes.modifiers if m.type == 'ARMATURE']:
        eyes.modifiers.remove(m)
    mod = eyes.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    eyes.parent = rig
    eyes.matrix_parent_inverse = rig.matrix_world.inverted()
    return weight_report(body)


def clean_weights(ob, limit=4):
    """Unity skins with up to 4 influences by default: keep the 4 strongest, drop dust, normalise."""
    names = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        ws = sorted(((g.weight, g.group) for g in v.groups), reverse=True)
        drop = [gi for i, (w, gi) in enumerate(ws) if i >= limit or w < 0.01]
        for gi in drop:
            ob.vertex_groups[names[gi]].remove([v.index])
        tot = sum(g.weight for g in v.groups)
        if tot > 0:
            for g in v.groups:
                g.weight /= tot


def weight_report(ob):
    zero = sum(1 for v in ob.data.vertices if sum(g.weight for g in v.groups) < 1e-4)
    over = sum(1 for v in ob.data.vertices if len(v.groups) > 4)
    return {"verts": len(ob.data.vertices), "unweighted": zero, "over4": over, "groups": len(ob.vertex_groups)}


def _rot(rig, bone, axis, deg, local=False):
    pb = rig.pose.bones[bone]
    m = pb.matrix.copy()
    if local:
        axis = m.col["XYZ".index(axis)].xyz.normalized()
    r = Matrix.Rotation(math.radians(deg), 4, Vector(axis))
    h = m.translation.copy()
    pb.matrix = Matrix.Translation(h) @ r @ Matrix.Translation(-h) @ m
    bpy.context.view_layer.update()


TEST_POSE = [
    # (bone, axis (world vector or local 'X'/'Y'/'Z'), degrees) for the left side; the right side is mirrored
    ("Spine", (1, 0, 0), 12), ("Chest", (1, 0, 0), 8), ("Head", (0, 0, 1), 25), ("Neck", (1, 0, 0), -10),
    ("LeftUpperArm", (0, 1, 0), 65), ("LeftUpperArm", (0, 0, 1), -20), ("LeftLowerArm", 'Z', -80),
    ("LeftUpperLeg", (1, 0, 0), -40), ("LeftLowerLeg", (1, 0, 0), 75),
    ("LeftEar01", (0, 1, 0), 25), ("LeftEar02", (0, 1, 0), 20),
]


def test_pose(rig, fist=75):
    for pb in rig.pose.bones:
        for c in pb.constraints:
            c.mute = True
    for side in ("Left", "Right"):
        for b, ax, deg in TEST_POSE:
            if not b.startswith("Left"):
                if side == "Right":
                    continue
                _rot(rig, b, ax, deg)
                continue
            n = b.replace("Left", side)
            if isinstance(ax, str):
                _rot(rig, n, ax, deg if side == "Left" else -deg, local=True)
            else:
                a = ax if side == "Left" else (ax[0], -ax[1], -ax[2])
                _rot(rig, n, a, deg)
        for f in ("Index", "Middle", "Ring", "Thumb"):
            for part in ("Proximal", "Intermediate", "Distal"):
                _rot(rig, f"{side}{f}{part}", 'X', -fist * (0.6 if f == "Thumb" else 1.0), local=True)


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
        for c in pb.constraints:
            c.mute = False
    bpy.context.view_layer.update()


def smooth_weights(ob, iterations=4, factor=0.5, skip=()):
    """Laplacian smoothing of all vertex groups over the mesh edges (softens heat-map creases at joints)."""
    import numpy as np
    me = ob.data
    V, G = len(me.vertices), len(ob.vertex_groups)
    W = np.zeros((V, G))
    for v in me.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    e = np.array([ed.vertices[:] for ed in me.edges])
    deg = np.bincount(e.ravel(), minlength=V).astype(float)
    locked = [ob.vertex_groups[n].index for n in skip if n in ob.vertex_groups]
    for _ in range(iterations):
        acc = np.zeros_like(W)
        np.add.at(acc, e[:, 0], W[e[:, 1]])
        np.add.at(acc, e[:, 1], W[e[:, 0]])
        Wn = (1 - factor) * W + factor * acc / np.maximum(deg, 1)[:, None]
        if locked:
            Wn[:, locked] = W[:, locked]
        W = Wn
    W /= np.maximum(W.sum(1), 1e-9)[:, None]
    for gi, g in enumerate(ob.vertex_groups):
        nz = np.nonzero(W[:, gi] > 1e-4)[0]
        g.remove(list(range(V)))
        for vi in nz:
            g.add([int(vi)], float(W[vi, gi]), 'REPLACE')
