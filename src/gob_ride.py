"""Goblin warg riders (2026-10-18): the goblin in the warg's saddle, one rider clip per warg clip plus its own blows.

Daniel: "We should have goblin warg riders ... complete with animations"; his picks: every rider clip made here (no
bought clips), art and a test scene first. The warg (Beasts repo, warg_*.py) is copied into this file's scene
**Goblin_Warg** by `setup()`: WargRig, WargBody, WargTack, WargMask and the Warg_* actions.

The rider is `GoblinRider`, a copy of GoblinRig (same armature data, its own pose and constraints) parented to the
warg's Socket_Saddle bone, so it rides along in the viewport while GoblinRig stays untouched for the character export.
At rest the rider's origin sits on the socket's head with the warg's axes (forward -Y, up +Z). Every pose is set in
the rider's armature space = saddle space; the clips are exported from GoblinRig itself (same bones, same IK), so a
clip moves the goblin relative to the saddle. In Unity the rider's root is a child of Socket_Saddle with that same
rest frame and plays WargRider_<warg clip> at the warg's own clip time (MountedRider).

Synced clips (every frame keyed, the warg's length and loop):
    the saddle's path in the warg clip drives a damped rider: the torso lags behind the saddle's accelerations and
    keeps half of its world uprightness, the hips float a little when the saddle drops away, the head stays level;
    the feet stand in the stirrups and the left fist holds the reins where the tack mesh has them in that frame;
    each warg clip adds its accents (ACCENTS: whoops in the howl, crouch in the lunge, pointing in the threat), and the
    warg's death throws the rider off its high side.
Own clips (upper body overlays in Unity, the warg standing; except Fall):
    WargRider_Slash   sword cut down the right flank (event 'Hit')
    WargRider_Thrust  overhand spear jab at the right front (event 'Hit')
    WargRider_Flinch  flinch (WargRider_Hit is the rider in the warg's own Hit)
    WargRider_Fall    killed in the saddle: slumps and slides off the left side to the ground (played detached)
"""
import bpy, math, os
import numpy as np
from mathutils import Vector, Matrix, Quaternion
import gob_anim as GA

SCENE = "Goblin_Warg"
RIDER = "GoblinRider"
MOUNT, BODY, TACK, MASK = "WargRig", "WargBody", "WargTack", "WargMask"
SEAT_BONE = "Socket_Saddle"
WARG_FILE = r"E:\Unity\Projects\GameArtGeneration\Beasts\blender\beasts_unsaved_2026-10-12_warg.blend"
PREFIX = "WargRider_"
FPS = 30
DT = 1.0 / FPS

UP, FWD = GA.UP, GA.FWD
RT = GA.RT                                   # the rider's right (-X)
LEFT, BACK = -RT, -FWD
SIDES = {"Left": 1.0, "Right": -1.0}         # +X is the rider's left

LOOK = {"GoblinBody", "Outfit_Loincloth", "Outfit_Wraps", "Prop_LeatherCap", "Prop_Spear", "Prop_ShieldPlank",
        "Prop_Pouch", "Prop_Knife"}
SWORD_LOOK = (LOOK - {"Prop_Spear"}) | {"Prop_Sword"}

# seat geometry (saddle space, metres)
HIP0 = Vector((0.0, 0.015, -0.006))          # hips joint above the dished seat
HIP_LEAN = 12.0                              # pelvis tipped forward (a goblin hunches)
SPINE_BEND = (6.0, 5.0, 4.0)
STIRRUP_DROP = 0.008                         # the ball of the foot on the tread, sole thickness
TOE_OUT = 14.0
HEEL_DOWN = 12.0


# ----------------------------------------------------------------------------------------- scene
def _scene():
    return bpy.data.scenes[SCENE]


def _rider():
    return bpy.data.objects[RIDER]


def _mount():
    return bpy.data.objects[MOUNT]


def setup():
    """Goblin_Warg: the warg (copied from the Beasts file if missing) and GoblinRider in its saddle, dressed with
    copies of the goblin's body, outfit and props (meshes shared)."""
    scn = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    if MOUNT not in bpy.data.objects:
        with bpy.data.libraries.load(WARG_FILE, link=False) as (src, dst):
            dst.objects = [MOUNT, BODY, TACK, MASK]
            dst.actions = [a for a in src.actions if a.startswith("Warg_")]
        for a in dst.actions:
            a.use_fake_user = True
    mc = bpy.data.collections.get("WRG_Mount") or bpy.data.collections.new("WRG_Mount")
    if mc.name not in scn.collection.children:
        scn.collection.children.link(mc)
    for n in (MOUNT, BODY, TACK, MASK):
        o = bpy.data.objects[n]
        if o.name not in mc.objects:
            mc.objects.link(o)
    rc = bpy.data.collections.get("GOB_Rider") or bpy.data.collections.new("GOB_Rider")
    if rc.name not in scn.collection.children:
        scn.collection.children.link(rc)
    for o in list(rc.objects):
        bpy.data.objects.remove(o)
    src = bpy.data.objects[GA.RIG]
    rider = src.copy()
    rider.name = RIDER
    rider.animation_data_clear()
    rc.objects.link(rider)
    mount = _mount()
    rider.parent = mount
    rider.parent_type = 'BONE'
    rider.parent_bone = SEAT_BONE
    b = mount.data.bones[SEAT_BONE]
    rider.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted() @ \
        Matrix.Translation(b.head_local)
    rider.matrix_basis = Matrix.Identity(4)
    names = set(LOOK) | set(SWORD_LOOK)
    for n in sorted(names):
        o = bpy.data.objects[n]
        c = o.copy()
        c.name = "R_" + n
        rc.objects.link(c)
        c.parent = rider
        for m in c.modifiers:
            if m.type == 'ARMATURE':
                m.object = rider
    dress('spear')
    for side in ("Left", "Right"):
        rider.pose.bones[f"{side}LowerArm"].constraints["IK"].influence = 1.0
        rider.pose.bones[f"{side}Hand"].constraints["IK rot"].influence = 1.0
    return rider


def reload_tack():
    """Take WargTack and WargMask again from the warg's file (after a tack rebuild there)."""
    keep = {n: bpy.data.objects[n].users_collection for n in (TACK, MASK) if n in bpy.data.objects}
    for n in (TACK, MASK):
        if n in bpy.data.objects:
            me = bpy.data.objects[n].data
            bpy.data.objects.remove(bpy.data.objects[n])
            if me.users == 0:
                bpy.data.meshes.remove(me)
    with bpy.data.libraries.load(WARG_FILE, link=False) as (src, dst):
        dst.objects = [TACK, MASK]
    mc = bpy.data.collections["WRG_Mount"]
    for o in dst.objects:
        mc.objects.link(o)
        o.parent = _mount()
        for m in o.modifiers:
            if m.type == 'ARMATURE':
                m.object = _mount()
    return dst.objects


def dress(kind='spear'):
    """Spear rider or sword-and-plank-shield rider (viewport and renders)."""
    look = LOOK if kind == 'spear' else SWORD_LOOK
    vl = _scene().view_layers[0]
    for o in bpy.data.collections["GOB_Rider"].objects:
        if o.name.startswith("R_"):
            on = o.name[2:] in look
            o.hide_render = not on
            o.hide_set(not on, view_layer=vl)


# ----------------------------------------------------------------------------------------- mount sampling
class Track:
    """Tack vertices followed through a warg clip: stirrup treads and the rein grip."""
    def __init__(self):
        tack = bpy.data.objects[TACK]
        me = tack.data
        a = me.attributes["info"]
        info = np.zeros(len(a.data) * 4)
        a.data.foreach_get("color", info)
        part = np.round(info.reshape(-1, 4)[:, 0] * 255).astype(int)
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        self.stirrup = {}
        for side, s in SIDES.items():
            m = np.where((part == 3) & (co[:, 2] < 0.95) & (np.sign(co[:, 0]) == s))[0]
            low = m[np.argsort(co[m, 2])[:6]]
            self.stirrup[side] = low
        rein = np.where(part == 5)[0]
        ys = co[rein, 1]
        self.rein = rein[(ys > -0.36) & (ys < -0.28)]

    def sample(self):
        """World points of the treads and the rein grip in the current frame."""
        dg = bpy.context.evaluated_depsgraph_get()
        tack = bpy.data.objects[TACK]
        ev = tack.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        co = co.reshape(-1, 3)
        Mw = tack.matrix_world
        out = {side: Mw @ Vector(co[idx].mean(0)) for side, idx in self.stirrup.items()}
        out["rein"] = Mw @ Vector(co[self.rein].mean(0))
        return out


def mount_clip(clip):
    act = bpy.data.actions["Warg_" + clip]
    m = _mount()
    if m.animation_data is None:
        m.animation_data_create()
    m.animation_data.action = act
    return int(act.frame_range[0]), int(act.frame_range[1])


def sample_clip(clip, track=None):
    """Per frame: the saddle's world matrix and the tack points (world)."""
    track = track or Track()
    f0, f1 = mount_clip(clip)
    scn = bpy.context.scene
    out = []
    for f in range(f0, f1 + 1):
        scn.frame_set(f)
        bpy.context.view_layer.update()
        out.append(dict(S=_rider().matrix_world.copy(), **track.sample()))
    return out


LOOPS = {"Idle", "IdlePant", "Walk", "Trot", "Run", "Threat"}


def simulate(samples, loop):
    """The rider's lag behind the saddle: torso pitch / roll (deg, + = forward / to the right) and hips float (m),
    a damped spring driven by the saddle's acceleration in its own frame. Loops run three times, the last kept."""
    n = len(samples)
    P = np.array([s["S"].translation[:] for s in samples])
    R = [s["S"].to_3x3() for s in samples]
    idx = (lambda i: i % (n - 1)) if loop else (lambda i: min(max(i, 0), n - 1))
    acc = []
    tilt = []
    for i in range(n):
        a = (P[idx(i + 1)] - 2 * P[idx(i)] + P[idx(i - 1)]) / (DT * DT)
        loc = R[i].transposed() @ Vector(a)                     # saddle frame: -Y forward, +X left, +Z up
        up = R[i].transposed() @ UP                             # world up seen from the saddle
        acc.append((loc, up))
        tilt.append((math.degrees(math.atan2(up.y, up.z)), math.degrees(math.atan2(up.x, up.z))))   # saddle nose-down, right-down
    w0, zeta = 2 * math.pi * 2.2, 0.55                         # torso spring: 2.2 Hz, under-damped
    wh, zh = 2 * math.pi * 3.0, 0.7
    th = ph = h = 0.0
    dth = dph = dh = 0.0
    out = [None] * n
    reps = 3 if loop else 1
    for rep in range(reps):
        for i in range(n if not loop else n - 1):
            a, up = acc[i]
            fwd_a = -a.y                                         # forward acceleration
            right_a = -a.x
            # balance: half of the saddle's tilt is taken back so the torso stays nearer world upright
            t_pitch, t_roll = tilt[i]
            tgt_th = -0.5 * t_pitch - 0.9 * fwd_a
            tgt_ph = -0.5 * t_roll - 0.9 * right_a
            ddth = w0 * w0 * (tgt_th - th) - 2 * zeta * w0 * dth
            ddph = w0 * w0 * (tgt_ph - ph) - 2 * zeta * w0 * dph
            ddh = wh * wh * (0 - h) - 2 * zh * wh * dh - 0.012 * a.z
            dth += ddth * DT; th += dth * DT
            dph += ddph * DT; ph += dph * DT
            dh += ddh * DT; h += dh * DT
            h = min(max(h, -0.004), 0.03)
            out[i] = (max(min(th, 25), -20), max(min(ph, 15), -15), h, Vector(up))
    if loop:
        out[n - 1] = out[0]
    return out


# ----------------------------------------------------------------------------------------- posing
def _A(S, p):
    """World point -> saddle (rider armature) space for saddle matrix S."""
    return S.inverted() @ Vector(p)


def _seat_body(lean=0.0, roll=0.0, float_=0.0, crouch=0.0, twist=0.0, hips_yaw=0.0, slump=0.0):
    """Hips on the seat (pitched forward by HIP_LEAN plus a share of the lean), spine bent to carry the rest of the
    torso lean and roll, chest twisted by `twist` (deg, + = right shoulder forward)."""
    M = GA._rest("Hips")
    hp = HIP_LEAN + 0.35 * lean + 0.5 * crouch
    R = Matrix.Rotation(math.radians(hips_yaw), 4, 'Z') @ Matrix.Rotation(math.radians(-roll * 0.3), 4, 'Y') @ \
        Matrix.Rotation(math.radians(hp), 4, 'X')
    N = R @ M.to_3x3().to_4x4()
    N.translation = HIP0 + Vector((0, 0, float_)) + FWD * 0.03 * crouch / 20.0 - UP * 0.01 * crouch / 20.0
    GA._set("Hips", N)
    rest = lean * 0.65 + crouch
    for name, base, share in zip(("Spine", "Chest", "UpperChest"), SPINE_BEND, (0.35, 0.35, 0.3)):
        GA._turn(name, 'X', base + rest * share + slump * share, local=True)
        GA._turn(name, 'Z', roll * 0.7 * share, local=True)
        GA._turn(name, 'Y', twist * share, local=True)


def _feet(S, pts, out_of=0.0):
    """Feet in the stirrups (the ball on the tread), toes out, heels down, knees round the warg's barrel."""
    for side, s in SIDES.items():
        tread = _A(S, pts[side]) + UP * STIRRUP_DROP
        ctrl = GA._rest(f"IK_{side}Foot")
        toe = GA._rest(f"{side}Toes").translation
        ball = Vector((toe.x - ctrl.translation.x, toe.y - ctrl.translation.y, -ctrl.translation.z))
        Rf = Matrix.Rotation(math.radians(s * TOE_OUT), 4, 'Z') @ \
            Matrix.Rotation(math.radians(-HEEL_DOWN), 4, Vector((1, 0, 0)))
        N = Rf @ ctrl.to_3x3().to_4x4()
        N.translation = tread - Rf.to_3x3() @ ball + LEFT * s * out_of * 0.06
        GA._set(f"IK_{side}Foot", N)
        knee = GA._pose(f"{side}UpperLeg").translation
        GA._place(f"Pole_{side}Knee", knee + LEFT * s * 0.55 + FWD * 0.45 - UP * 0.1)


def _rein_hand(S, pts, lift=0.0, slack=0.0):
    """Left fist on both reins in front of the pommel, knuckles forward, thumb up and in."""
    g = _A(S, pts["rein"]) + UP * (0.045 + lift) + BACK * (0.03 + slack) + LEFT * 0.01
    Sl = GA._frame(g, ('y', UP + RT * 0.6), ('x', BACK))
    GA._hand("Left", Sl)
    sh = GA._pose("LeftUpperArm").translation
    GA._place("Pole_LeftElbow", (sh + g) / 2 + LEFT * 0.12 + BACK * 0.3 - UP * 0.25)
    GA._fingers("Left", 'fist')


def _weapon_rest(bob=0.0):
    """Right fist by the right hip, the weapon up and forward (spear point / sword blade), edge forward."""
    hp = GA._pose("Hips").translation
    g = hp + RT * 0.11 + FWD * 0.20 + UP * (0.13 + bob)
    yv = (UP + FWD * 0.55 + RT * 0.12).normalized()
    Sr = GA._frame(g, ('y', yv), ('x', FWD + RT * 0.4))
    GA._hand("Right", Sr)
    sh = GA._pose("RightUpperArm").translation
    GA._place("Pole_RightElbow", sh + RT * 0.12 + BACK * 0.3 - UP * 0.3)
    GA._fingers("Right", 'fist')
    return Sr


def _weapon_raised(shake=0.0):
    """Weapon brandished overhead (the whoop)."""
    sh = GA._pose("RightUpperArm").translation
    g = sh + UP * 0.30 + RT * 0.08 + FWD * 0.05 + FWD * 0.03 * shake
    yv = (UP + BACK * 0.35 + RT * 0.15 + FWD * 0.3 * shake).normalized()
    Sr = GA._frame(g, ('y', yv), ('x', FWD))
    GA._hand("Right", Sr)
    GA._place("Pole_RightElbow", sh + RT * 0.4 + UP * 0.05)
    GA._fingers("Right", 'fist')


def _weapon_point(reach=1.0):
    """Weapon levelled at the front (taunting)."""
    sh = GA._pose("RightUpperArm").translation
    g = sh + FWD * 0.24 * reach + RT * 0.07 + UP * 0.02
    yv = (FWD + UP * 0.12 + LEFT * 0.08).normalized()
    Sr = GA._frame(g, ('y', yv), ('x', UP + RT))
    GA._hand("Right", Sr)
    GA._place("Pole_RightElbow", sh + RT * 0.3 - UP * 0.3)
    GA._fingers("Right", 'fist')


def _head(S, up, pitch=0.0, yaw=0.0, roll=0.0):
    """Face level in the world (a rider's head stays steady), plus pitch (+ up) and yaw (+ to the right)."""
    lvl = FWD - FWD.project(up)
    lvl = lvl.normalized() if lvl.length > 1e-4 else FWD
    side = lvl.cross(up).normalized()
    d = GA._rotate_about(lvl, side, pitch)
    d = GA._rotate_about(d, up, -yaw)
    GA._look(d, roll=roll)


def _jaw(open_deg):
    pb = _rig_pb("Jaw")
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(open_deg))


def _rig_pb(name):
    return GA._rig().pose.bones[name]


# ----------------------------------------------------------------------------------------- accents per warg clip
def _env(t, a, b, ramp=0.15):
    """0 outside [a, b] seconds, 1 inside, smooth ramps."""
    if t <= a - ramp or t >= b + ramp:
        return 0.0
    if t < a:
        return GA_ease((t - (a - ramp)) / ramp)
    if t > b:
        return GA_ease(((b + ramp) - t) / ramp)
    return 1.0


def GA_ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def accents(clip, t, T):
    """Extra lean, crouch, head and arm calls for one warg clip at time t of T seconds."""
    a = dict(lean=0.0, crouch=0.0, pitch=0.0, yaw=0.0, roll=0.0, jaw=0.0, arm='rest', shake=0.0, twist=0.0,
             blend=0.0, lift=0.0)
    w = 2 * math.pi * t / T
    if clip in ("Idle", "IdlePant"):
        a.update(yaw=14 * math.sin(w) + (6 * math.sin(3 * w) if clip == "Idle" else 0), pitch=-4 + 3 * math.sin(2 * w),
                 lean=2 * math.sin(w + 1))
    elif clip == "Walk":
        a.update(yaw=5 * math.sin(w), pitch=-5)
    elif clip == "Trot":
        a.update(pitch=-6, lean=4)
    elif clip == "Run":
        a.update(pitch=-2, lean=14, crouch=8, lift=0.02)
    elif clip == "Threat":
        a.update(lean=8, pitch=-6, arm='point', blend=_env(t, 0.3, T - 0.3, 0.3), jaw=10 * abs(math.sin(5 * w)),
                 shake=math.sin(4 * w))
    elif clip == "Howl":
        e = _env(t, 0.9, 2.9, 0.35)
        a.update(lean=-6 * e, pitch=22 * e, arm='raised', blend=e, jaw=24 * e, shake=math.sin(2 * math.pi * 3 * t) * e,
                 roll=4 * math.sin(2 * math.pi * 1.5 * t) * e)
    elif clip == "Bite":
        e = _env(t, 0.35, 0.65, 0.2)
        a.update(lean=10 * e, crouch=4 * e, pitch=-8 * e, arm='point', blend=0.6 * e, jaw=12 * e)
    elif clip == "Lunge":
        crouch = _env(t, 0.25, 0.45, 0.2)
        leap = _env(t, 0.6, 0.95, 0.15)
        a.update(lean=14 * crouch + 18 * leap, crouch=10 * crouch + 14 * leap, pitch=-6, arm='point', blend=leap,
                 jaw=14 * leap, lift=0.01 * leap)
    elif clip == "Hit":
        e = _env(t, 0.05, 0.2, 0.1)
        a.update(lean=-10 * e, pitch=-10 * e, yaw=-12 * e, jaw=10 * e)
    return a


# ----------------------------------------------------------------------------------------- the synced clips
def pose_frame(sample, state, ac):
    S = sample["S"]
    th, ph, h, up = state
    GA.reset()
    _seat_body(lean=th + ac['lean'], roll=ph + ac['roll'], float_=h + ac['lift'], crouch=ac['crouch'],
               twist=ac['twist'])
    _feet(S, sample)
    _rein_hand(S, sample)
    Sr = _weapon_rest()
    if ac['arm'] != 'rest' and ac['blend'] > 1e-3:
        rest = {n: GA._pose(n) for n in ("IK_RightHand", "Pole_RightElbow")}
        if ac['arm'] == 'raised':
            _weapon_raised(ac['shake'])
        else:
            _weapon_point(1.0 + 0.15 * ac['shake'])
        for n, M0 in rest.items():
            M1 = GA._pose(n)
            GA._set(n, _lerp_m(M0, M1, ac['blend']))
    _head(S, up, pitch=ac['pitch'], yaw=ac['yaw'], roll=ac['roll'])
    _jaw(ac['jaw'])


def _lerp_m(A, B, t):
    q = A.to_quaternion().slerp(B.to_quaternion(), t)
    M = q.to_matrix().to_4x4()
    M.translation = A.translation.lerp(B.translation, t)
    return M


KEYED_EXTRA = ("Jaw",)


def _key_all(frame, prev):
    GA._key(frame, prev)
    r = GA._rig()
    for n in KEYED_EXTRA:
        pb = r.pose.bones[n]
        q = pb.rotation_quaternion.copy()
        if n in prev and q.dot(prev[n]) < 0:
            pb.rotation_quaternion = -q
        prev[n] = pb.rotation_quaternion.copy()
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=n)


class _OnRider:
    """gob_anim's helpers pose GoblinRig; point them at the rider while authoring."""
    def __enter__(self):
        self.keep = GA.RIG
        GA.RIG = RIDER

    def __exit__(self, *a):
        GA.RIG = self.keep


def build_synced(clip, track=None):
    """WargRider_<clip>: keyed on every frame of the warg's clip."""
    samples = sample_clip(clip, track)
    loop = clip in LOOPS
    states = simulate(samples, loop)
    f0 = int(bpy.data.actions["Warg_" + clip].frame_range[0])
    T = (len(samples) - 1) / FPS
    name = PREFIX + clip
    scn = bpy.context.scene
    with _OnRider():
        act = GA._new_action(name)
        prev = {}
        for i, (smp, st) in enumerate(zip(samples, states)):
            scn.frame_set(f0 + i)
            ac = accents(clip, i / FPS, T)
            if clip == "Death":
                pose_thrown(smp, st, i / FPS)
            else:
                pose_frame(smp, st, ac)
            _key_all(f0 + i, prev)
        GA._key_constraints(f0)
        act.frame_range = (f0, f0 + len(samples) - 1)
        act.use_frame_range = True
    return act


# ----------------------------------------------------------------------------------------- thrown off (warg Death)
THROW = dict(t0=0.75, t1=1.35, land=Vector((-1.35, -0.55, 0.0)))   # leaves the saddle / lands clear of the legs (world)


def pose_thrown(sample, state, t):
    """The warg staggers and falls onto its left side: the rider clings, then pushes off its high (right) side and
    lands on the ground on its back beside the warg."""
    S = sample["S"]
    t0, t1 = THROW['t0'], THROW['t1']
    if t <= t0:
        th, ph, h, up = state
        GA.reset()
        k = GA_ease(t / t0)
        _seat_body(lean=th + 12 * k, roll=ph - 10 * k, float_=h, crouch=6 * k)
        _feet(S, sample)
        _rein_hand(S, sample)
        _weapon_rest()
        _head(S, up, pitch=-6, yaw=-20 * k)
        _jaw(14 * k)
        return
    # world path of the hips: from where the seat had them at t0 to the landing spot, a short arc
    seat0 = _THROW_CACHE["seat0"]
    hip0 = seat0 @ HIP0
    land = THROW['land'] + Vector((0, 0, 0.10))
    u = min((t - t0) / (t1 - t0), 1.0)
    e = GA_ease(u)
    pos = hip0.lerp(land, e) + UP * (0.18 * math.sin(math.pi * u) if u < 1 else 0.0)
    # body: upright -> tipping over to the right -> lying on the back, feet toward the warg
    Rw = _lying(RT + BACK * 0.3, e)                     # head away from the warg, on its back
    GA.reset()
    Hw = Rw.to_4x4() @ GA._rest("Hips").to_3x3().to_4x4()
    Hw.translation = pos
    GA._set("Hips", S.inverted() @ Hw)
    settle = 1.0 if t > t1 else 0.0
    for name, bend in zip(("Spine", "Chest", "UpperChest"), (10 - 14 * e, 8 - 12 * e, 6 - 10 * e)):
        GA._turn(name, 'X', bend, local=True)
    # limbs flung: feet up and out, then lying sprawled
    for side, s in SIDES.items():
        hipj = GA._pose(f"{side}UpperLeg").translation
        down_w = -UP if u >= 1 else (-UP).lerp(Rw @ (-UP), 0.6)
        tuck = math.sin(math.pi * u)                    # knees drawn up in the air, legs out once down
        foot_w = (S @ hipj) + Rw @ Vector((s * 0.16, -0.02 - 0.18 * tuck, -0.36 + 0.15 * tuck))
        foot_w.z = max(foot_w.z, 0.06)
        ctrl = GA._rest(f"IK_{side}Foot")
        N = S.inverted().to_3x3().to_4x4() @ Rw.to_4x4() @ ctrl.to_3x3().to_4x4()
        N.translation = _A(S, foot_w)
        GA._set(f"IK_{side}Foot", N)
        GA._place(f"Pole_{side}Knee", _A(S, (S @ hipj) + Rw @ Vector((s * 0.3, -0.15 - 0.3 * tuck, -0.2))))
    for side, s in SIDES.items():
        sh = GA._pose(f"{side}UpperArm").translation
        hand_w = (S @ sh) + Rw @ Vector((s * (0.25 + 0.08 * math.sin(math.pi * u)), -0.05, 0.12 * (1 - e) - 0.05))
        hand_w.z = max(hand_w.z, 0.05)
        Sx = GA._frame(_A(S, hand_w), ('y', S.inverted().to_3x3() @ (Rw @ (LEFT * s + FWD * 0.4))),
                       ('x', S.inverted().to_3x3() @ (Rw @ BACK)))           # the weapon flat, out along the arm
        GA._hand(side, Sx)
        GA._place(f"Pole_{side}Elbow", _A(S, (S @ sh) + Rw @ Vector((s * 0.3, 0.2, -0.2))))
        GA._fingers(side, 'open' if side == "Left" else 'fist')
    up_a = S.inverted().to_3x3() @ UP
    d = S.inverted().to_3x3() @ (Rw @ FWD)
    GA._look((d + up_a * (0.6 * e)).normalized(), roll=0)
    _jaw(20 * (1 - settle) + 6 * settle)


_THROW_CACHE = {}


def _lying(head, e):
    """Upright (identity) slerped toward lying on the back: body axis along `head`, face to the sky."""
    head = Vector(head).normalized()
    y = -UP
    R1 = Matrix((y.cross(head), y, head)).transposed()
    return Quaternion().slerp(R1.to_quaternion(), e).to_matrix()


def build_death(track=None):
    samples = sample_clip("Death", track)
    i0 = int(round(THROW['t0'] * FPS))
    _THROW_CACHE["seat0"] = samples[i0]["S"].copy()
    return build_synced("Death", track)


# ----------------------------------------------------------------------------------------- own clips (warg standing)
OWN_EVENTS = {"Slash": {"hit": 14, "end": 40}, "Thrust": {"hit": 15, "end": 36}, "Flinch": {"end": 15},
              "Fall": {"ground": 34, "end": 60}}


def _still(track):
    """The warg standing (Idle frame 0): one saddle sample for the own clips."""
    mount_clip("Idle")
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    return dict(S=_rider().matrix_world.copy(), **track.sample())


def _base(smp, lean=0.0, twist=0.0, roll=0.0, crouch=0.0, pitch=-4.0, yaw=0.0, jaw=0.0):
    GA.reset()
    S = smp["S"]
    up = S.inverted().to_3x3() @ UP
    _seat_body(lean=lean, roll=roll, twist=twist, crouch=crouch)
    _feet(S, smp)
    _rein_hand(S, smp)
    _head(S, up, pitch=pitch, yaw=yaw)
    _jaw(jaw)


def pose_slash(smp, stage):
    """Sword cut at a man on foot at the warg's right: wind up high behind the right shoulder, cut down and forward
    along the flank, the edge (+X of the socket) leading."""
    if stage == 'ready':
        _base(smp)
        _weapon_rest()
        return
    if stage == 'windup':
        _base(smp, lean=-4, twist=-28, roll=6, pitch=-8, yaw=40, jaw=8)
        sh = GA._pose("RightUpperArm").translation
        g = sh + UP * 0.22 + BACK * 0.10 + RT * 0.10
        blade = (BACK * 0.7 + UP * 0.6 + RT * 0.2).normalized()
        cut = (FWD * 0.6 - UP * 0.8 + RT * 0.1).normalized()          # where the cut will go: edge faces it
        Sr = GA._frame(g, ('y', blade), ('x', cut))
        GA._place("Pole_RightElbow", sh + RT * 0.35 + UP * 0.15 + BACK * 0.1)
    elif stage in ('strike', 'through'):
        k = 1.0 if stage == 'through' else 0.0
        _base(smp, lean=10 + 8 * k, twist=22 + 10 * k, roll=14 + 6 * k, crouch=4, pitch=-22 - 6 * k, yaw=35 - 10 * k,
              jaw=22)
        sh = GA._pose("RightUpperArm").translation
        g = sh + RT * (0.28 + 0.03 * k) + FWD * (0.14 + 0.10 * k) - UP * (0.06 + 0.10 * k)
        blade = (RT * (0.85 + 0.1 * k) + FWD * (0.45 + 0.25 * k) - UP * (0.25 + 0.35 * k)).normalized()
        cut = (FWD * 0.5 - UP * 0.8 - RT * 0.1).normalized()
        Sr = GA._frame(g, ('y', blade), ('x', cut))
        GA._place("Pole_RightElbow", sh + RT * 0.25 + BACK * 0.15 - UP * 0.1)
    else:                                   # 'recover': blade swung back up
        _base(smp, lean=4, twist=6, roll=4, pitch=-10, yaw=18, jaw=6)
        sh = GA._pose("RightUpperArm").translation
        g = sh + RT * 0.2 + FWD * 0.1 - UP * 0.05
        Sr = GA._frame(g, ('y', (UP + FWD * 0.4 + RT * 0.3).normalized()), ('x', FWD))
        GA._place("Pole_RightElbow", sh + RT * 0.3 + BACK * 0.2 - UP * 0.25)
    GA._hand("Right", Sr)
    GA._fingers("Right", 'fist')


REST_GRIP = (UP + FWD * 0.55 + RT * 0.12).normalized()      # _weapon_rest: the weapon's line and the knuckles
REST_KNUCKLES = (FWD + RT * 0.4).normalized()


def _knuckles_for(grip):
    """The knuckles' way when the weapon is turned from its resting line to `grip` by the least rotation: the hand
    keeps its grip (an overhand stab from the upright rest asked for a half turn round the shaft, and the hand
    swirled the spear getting there, 2026-10-18)."""
    return REST_GRIP.rotation_difference(Vector(grip).normalized()) @ REST_KNUCKLES


def pose_thrust(smp, stage):
    """Underhand spear jab at a man off the warg's right shoulder: the fist drawn back by the hip with the point
    already on him, driven out along the line, pulled back, the spear up again. The grip never changes (palm up,
    thumb toward the point: the fist that held it upright)."""
    if stage == 'ready':
        _base(smp)
        _weapon_rest()
        return
    tgt = (FWD * 0.6 + RT * 0.65 - UP * 0.35).normalized()
    hp = GA._pose("Hips").translation
    if stage == 'cock':
        _base(smp, lean=-4, twist=-20, roll=4, pitch=-12, yaw=30, jaw=6)
        sh = GA._pose("RightUpperArm").translation
        g = hp + RT * 0.17 + BACK * 0.03 + UP * 0.17
        y = (tgt + UP * 0.25).normalized()
        GA._place("Pole_RightElbow", sh + RT * 0.25 + BACK * 0.35 - UP * 0.2)
    elif stage in ('jab', 'hold'):
        k = 1.0 if stage == 'hold' else 0.0
        _base(smp, lean=14 + 2 * k, twist=22, roll=12, crouch=4, pitch=-22, yaw=26, jaw=24)
        sh = GA._pose("RightUpperArm").translation
        g = sh + tgt * (0.31 - 0.02 * k) - UP * 0.03
        y = tgt
        GA._place("Pole_RightElbow", sh + RT * 0.3 - UP * 0.3 + BACK * 0.05)
    else:                                   # 'pull'
        _base(smp, lean=4, twist=-4, roll=4, pitch=-12, yaw=20, jaw=6)
        sh = GA._pose("RightUpperArm").translation
        g = hp + RT * 0.13 + FWD * 0.14 + UP * 0.15
        y = (tgt + UP * 0.9).normalized()
        GA._place("Pole_RightElbow", sh + RT * 0.25 + BACK * 0.3 - UP * 0.25)
    GA._hand("Right", GA._frame(g, ('y', y), ('x', _knuckles_for(y))))
    GA._fingers("Right", 'fist')


def pose_flinch(smp, k):
    _base(smp, lean=-12 * k, twist=-10 * k, roll=-8 * k, pitch=-12 * k, yaw=-20 * k, jaw=14 * k)
    _weapon_rest(bob=0.05 * k)


def _own_keys(name):
    if name == "Slash":
        e = OWN_EVENTS["Slash"]
        return [(0, pose_slash, 'ready'), (9, pose_slash, 'windup'), (e['hit'], pose_slash, 'strike'),
                (e['hit'] + 5, pose_slash, 'through'), (e['hit'] + 13, pose_slash, 'recover'), (e['end'], pose_slash, 'ready')]
    if name == "Thrust":
        e = OWN_EVENTS["Thrust"]
        return [(0, pose_thrust, 'ready'), (9, pose_thrust, 'cock'), (e['hit'], pose_thrust, 'jab'),
                (e['hit'] + 4, pose_thrust, 'hold'), (e['hit'] + 11, pose_thrust, 'pull'), (e['end'], pose_thrust, 'ready')]
    if name == "Flinch":
        return [(0, pose_flinch, 0.0), (3, pose_flinch, 1.0), (7, pose_flinch, 0.7), (15, pose_flinch, 0.0)]
    raise KeyError(name)


def _snapshot():
    """The keyed bones as they stand: armature-space matrices of the body and the IK controls, finger and jaw turns."""
    r = GA._rig()
    mats = {n: GA._pose(n) for n in list(GA.BODY) + list(GA.CONTROLS)}
    quats = {n: r.pose.bones[n].rotation_quaternion.copy() for n in GA._keyed_bones() + list(KEYED_EXTRA)
             if n not in mats}
    return mats, quats


def _blend(a, b, t):
    """Between two snapshots: positions eased along, turns slerped (the shortest way, never round the long side)."""
    r = GA._rig()
    GA.reset()
    for n in list(GA.BODY) + list(GA.CONTROLS):            # parents first
        GA._set(n, _lerp_m(a[0][n], b[0][n], t))
    for n, q in a[1].items():
        pb = r.pose.bones[n]
        pb.rotation_mode = 'QUATERNION'
        q1 = b[1][n] if q.dot(b[1][n]) >= 0 else -b[1][n]
        pb.rotation_quaternion = q.slerp(q1, t)
    GA._upd()


def build_own(name, track=None):
    """An own clip: the key poses, then every frame between them blended (eased) and keyed, so the hand turns the
    shortest way and the IK solves each frame (keys alone left Blender's curves to turn the fist between them)."""
    track = track or Track()
    smp = _still(track)
    with _OnRider():
        keys = _own_keys(name)
        snaps = []
        for frame, fn, arg in keys:
            fn(smp, arg)
            snaps.append((frame, _snapshot()))
        act = GA._new_action(PREFIX + name)
        prev = {}
        for i in range(len(snaps) - 1):
            (f0, a), (f1, b) = snaps[i], snaps[i + 1]
            last = i == len(snaps) - 2
            for f in range(f0, f1 + (1 if last else 0)):
                _blend(a, b, GA_ease((f - f0) / (f1 - f0)))
                _key_all(f, prev)
        GA._key_constraints(keys[0][0])
        act.frame_range = (keys[0][0], keys[-1][0])
        act.use_frame_range = True
    return act


def build_fall(track=None):
    """Killed in the saddle (warg standing): slumps forward, slides off its left side, lies on the ground. Keyed in
    saddle space like the rest; in Unity it plays after the rider is let go of the saddle."""
    track = track or Track()
    smp = _still(track)
    S = smp["S"]
    up = S.inverted().to_3x3() @ UP
    g, end = OWN_EVENTS["Fall"]["ground"], OWN_EVENTS["Fall"]["end"]
    hip0 = S @ HIP0
    land = Vector((1.05, 0.25, 0.10))
    with _OnRider():
        act = GA._new_action(PREFIX + "Fall")
        prev = {}
        for f in range(0, end + 1):
            t = f / FPS
            if f <= 12:                                   # hit: jerks back, then slumps over the neck
                k = GA_ease(f / 12)
                _base(smp, lean=-10 + 40 * k, roll=-6 * k, pitch=-20 * k, jaw=18)
                _weapon_rest(bob=-0.05 * k)
            else:
                u = min((f - 12) / (g - 12), 1.0)
                e = GA_ease(u)
                pos = hip0.lerp(land, e) + UP * (0.06 * math.sin(math.pi * u))
                Rw = _lying(LEFT + FWD * 0.2, e)          # over the left side, onto the back
                GA.reset()
                Hw = Rw.to_4x4() @ (Matrix.Rotation(math.radians(30 * (1 - e)), 4, 'X') @
                                    GA._rest("Hips").to_3x3().to_4x4())
                Hw.translation = pos
                GA._set("Hips", S.inverted() @ Hw)
                for name, bend in zip(("Spine", "Chest", "UpperChest"), (14 - 18 * e, 12 - 16 * e, 10 - 12 * e)):
                    GA._turn(name, 'X', bend, local=True)
                for side, s in SIDES.items():
                    hipj = GA._pose(f"{side}UpperLeg").translation
                    lift = 0.0 if side == "Left" else 0.25 * math.sin(math.pi * u)     # the right leg swings over
                    foot_w = (S @ hipj) + Rw @ Vector((s * 0.15, -0.02 - 0.1 * (1 - e), -0.36)) + UP * lift
                    foot_w.z = max(foot_w.z, 0.06)
                    ctrl = GA._rest(f"IK_{side}Foot")
                    N = S.inverted().to_3x3().to_4x4() @ Rw.to_4x4() @ ctrl.to_3x3().to_4x4()
                    N.translation = _A(S, foot_w)
                    GA._set(f"IK_{side}Foot", N)
                    GA._place(f"Pole_{side}Knee", _A(S, (S @ hipj) + Rw @ Vector((s * 0.3, -0.15, -0.2))))
                    sh = GA._pose(f"{side}UpperArm").translation
                    hand_w = (S @ sh) + Rw @ Vector((s * 0.28, -0.06, -0.08 * e))
                    hand_w.z = max(hand_w.z, 0.05)
                    Sx = GA._frame(_A(S, hand_w), ('y', S.inverted().to_3x3() @ (Rw @ (LEFT * s + FWD * 0.4))),
                                   ('x', S.inverted().to_3x3() @ (Rw @ BACK)))
                    GA._hand(side, Sx)
                    GA._place(f"Pole_{side}Elbow", _A(S, (S @ sh) + Rw @ Vector((s * 0.3, 0.2, -0.2))))
                    GA._fingers(side, 'open')
                d = S.inverted().to_3x3() @ (Rw @ FWD)
                GA._look((d + up * 0.5 * e).normalized(), roll=0)
                _jaw(16)
            _key_all(f, prev)
        GA._key_constraints(0)
        act.frame_range = (0, end)
        act.use_frame_range = True
    return act


# ----------------------------------------------------------------------------------------- all, view, export
SYNCED = ("Idle", "IdlePant", "Walk", "Trot", "Run", "Bite", "Lunge", "Threat", "Howl", "Hit", "Death")
OWN = ("Slash", "Thrust", "Flinch", "Fall")


def build_all():
    track = Track()
    out = []
    for c in SYNCED:
        out.append((build_death(track) if c == "Death" else build_synced(c, track)).name)
    for c in ("Slash", "Thrust", "Flinch"):
        out.append(build_own(c, track).name)
    out.append(build_fall(track).name)
    return out


def use(name, frame=None):
    """Rider clip on the rider and its warg clip on the warg (the own clips stand the warg in Idle)."""
    act = bpy.data.actions[name]
    r = _rider()
    if r.animation_data is None:
        r.animation_data_create()
    r.animation_data.action = act
    clip = name[len(PREFIX):]
    mount_clip(clip if ("Warg_" + clip) in bpy.data.actions else "Idle")
    scn = _scene()
    scn.frame_start, scn.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    scn.frame_set(int(act.frame_range[0]) if frame is None else frame)


def export_clips(names=None):
    """export/Anims/Goblin@WargRider_*.fbx from GoblinRig (same bones as the rider). Run with the Goblin scene on
    screen (GoblinRig must be in the view layer)."""
    names = names or [a.name for a in bpy.data.actions if a.name.startswith(PREFIX)]
    try:
        return GA.export_clips(names=names)
    finally:
        GA.clear()


# ----------------------------------------------------------------------------------------- review renders
VIEWS = {"side": Vector((-3.2, 0.0, 0.35)), "front34": Vector((-2.0, -2.4, 0.6)), "back34": Vector((1.9, 2.4, 0.9)),
         "top": Vector((-1.2, -0.6, 3.6))}


def _cam(view):
    name = "CAM_Ride_" + view
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        _scene().collection.objects.link(cam)
    cam.data.lens = 50
    return cam


def _aim(cam, target, offset):
    cam.location = target + offset
    d = (target - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def render_sheet(name, frames, views=("side", "front34"), res=420, follow=True, height=0.85):
    """Workbench frames of the current rider clip in a grid (rows = views), renders/ride/<name>.png. The cameras
    follow the saddle (root motion moves the warg)."""
    import gob_scene
    scn = _scene()
    tiles = []
    for v in views:
        cam = _cam(v)
        row = []
        for f in frames:
            scn.frame_set(f)
            bpy.context.view_layer.update()
            tgt = _rider().matrix_world.translation.copy() if follow else Vector((0, -0.2, 1.0))
            tgt.z = height
            _aim(cam, tgt + Vector((0, -0.25, 0)), VIEWS[v])
            p = gob_scene.shot(cam.name, f"ride/{name}_{v}_{f:03d}", scene=scn, res=res)
            img = bpy.data.images.load(p, check_existing=False)
            a = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
            bpy.data.images.remove(img)
            row.append(a)
        tiles.append(np.concatenate(row, axis=1))
    sheet = np.concatenate(tiles[::-1], axis=0)
    h, w = sheet.shape[:2]
    out = bpy.data.images.new(name + "_sheet", w, h)
    out.pixels = sheet.ravel()
    path = os.path.join(gob_scene.RENDERS, "ride", name + ".png")
    out.filepath_raw = path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return path
