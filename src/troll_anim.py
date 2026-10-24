"""The troll's own clips (2026-10-23; Daniel: "Do the number 4"), keyed on TrollRig the way gob_anim keys the goblin's:
posed through the rig's IK from targets (where the feet stand, where the wrists go, which way the elbows and knees
point, where the club must touch), every frame keyed, exported as export/Troll/Anims/Troll@<clip>.fbx for TrollSetup.

    Roar      2.8 s, once. Feet planted. Gathers (crouch, chest down, head low, the club drawn in), rises, and roars:
              chest up, shoulders back, the head thrust forward and up, the jaw keyed open 30 deg, the free (left) arm
              out with the hand clawed, the club raised high on the right (the fist over head height, the club standing
              up and a little back); holds it with a tremor; settles back to the stance. Animation event "Roar" at the
              peak (EVENTS, 1.0 s). TrollBody has no jaw weights (no mouth interior, as the goblin): the jaw does not
              show until the troll gets a mouth.
    ClubDrag  2.0 s loop. A slow, stooped, menacing walk (1.5 m strides, root motion straight forward); the club trails
              on the ground behind the troll's right side, its lowest point 9 mm over the ground in every frame.

Hands are posed by comfort, not by aiming the club and letting the wrist take what is left (Daniel judges held props by
comfort: wrists bent 40-70 deg were rejected). _arm puts the wrist where it should be (the arm IK, the elbow swivelled),
then turns the hand from its forearm by a forearm twist, a wrist flexion and a deviation inside COMFORT; the club goes
where that hand points it. Where the club must reach the ground, the deviation is solved for it (_club_at). The club's
business end leaves the thumb side of the fist (Socket_RightHand +Y), so a club trailing behind needs the palm
turned forward (forearm supinated) and the upper arm turned out: it trails behind and out to the right.

The grips come from searches kept here for a new club, body or gait: optimise_drag (DRAG, over the whole cycle) and
optimise_roar_club (ROAR_CLUB). report() measures every frame (renders/anim/troll_clips_report.json), review() renders.

Headless: blender -b blender/troll.blend --python tools/troll_run.py -- anims anim_review
In Blender: import troll_anim as TA; TA.build_all(); TA.report(); TA.export_clips(); TA.use("Roar") to look (scene
Troll_Anim); TA.clear() before exporting the character again.
"""
import bpy, math, os, json
from mathutils import Vector, Matrix, Quaternion
from gob_common import ROOT
import gob_anim as GA
import gob_export
import troll_body as TB

RIG = TB.RIG
FPS = 30
UP = Vector((0, 0, 1))
FWD = Vector((0, -1, 0))
BACK = -FWD
RT = FWD.cross(UP)                 # the troll's right (-X)
LEFT = -RT
EXPORT = os.path.join(ROOT, "export", "Troll", "Anims")
RENDERS = os.path.join(ROOT, "renders")
CLUB = "Prop_TrollClub"
CONTACT = 0.009                    # the club's lowest point above the ground while dragging (m): Unity's retarget
                                   # moves it by up to 7 mm either way, so it never goes under there
CLIPS = ("Roar", "ClubDrag")

EVENTS = {"Roar": {"roar": 30, "end": 84}, "ClubDrag": {"end": 60}}
LOOP = {"Roar": False, "ClubDrag": True}
ROOT_MOTION = {"Roar": False, "ClubDrag": True}

# comfort: the worst a held pose may ask of a wrist and arm (degrees). Twist is the forearm's (+ supination for both
# hands) from the T-pose's palm-down; Unity's Humanoid forearm-twist muscle stops at 90.
COMFORT = dict(flex=25.0, ulnar=30.0, radial=15.0, twist=80.0, humerus=60.0)


class _OnTroll:
    """gob_anim's pose helpers act on GA.RIG: point them at the troll while authoring."""
    def __enter__(self):
        self.keep = GA.RIG
        GA.RIG = RIG

    def __exit__(self, *a):
        GA.RIG = self.keep


def _rig():
    return bpy.data.objects[RIG]


# ----------------------------------------------------------------------------------------- measures
def wrist(side):
    """The hand against its forearm, degrees: flexion (+ toward the palm), deviation (+ toward the pinky, ulnar),
    forearm twist (+ supination) from the rest pose."""
    lo, ha = GA._pose(side + "LowerArm"), GA._pose(side + "Hand")
    rlo, rha = GA._rest(side + "LowerArm"), GA._rest(side + "Hand")
    W = (rlo.inverted() @ rha).to_3x3().inverted() @ (lo.inverted() @ ha).to_3x3()
    y = W @ Vector((0, 1, 0))
    q = W.to_quaternion()
    tw = (math.degrees(2 * math.atan2(q.y, q.w)) + 180) % 360 - 180
    flex = math.degrees(math.atan2(-y.z, y.y))
    dev = math.degrees(math.atan2(y.x, y.y))
    if side == "Left":                        # the left hand's +X is the thumb side
        dev, tw = -dev, -tw
    return flex, dev, tw


def humerus(side):
    """The upper arm's turn about its own axis beyond the least turn from its rest direction (deg, + outward)."""
    up, rup = GA._pose(side + "UpperArm").to_3x3(), GA._rest(side + "UpperArm").to_3x3()
    swing = rup.col[1].rotation_difference(up.col[1]).to_matrix()
    q = ((swing @ rup).inverted() @ up).to_quaternion()
    tw = (math.degrees(2 * math.atan2(q.y, q.w)) + 180) % 360 - 180
    return -tw if side == "Left" else tw


def _club_verts():
    return [v.co.copy() for v in bpy.data.objects[CLUB].data.vertices]


def club_low(S, verts=None):
    """Lowest point of the club mesh with Socket_RightHand at armature-space matrix S (the club is modelled in socket
    space)."""
    return min((S @ v).z for v in (verts or _club_verts()))


def club_heading(S):
    """The club's heading from straight back toward the troll's right, and its pitch (deg, - = down)."""
    d = S.col[1].xyz.normalized()
    return math.degrees(math.atan2(-d.x, d.y)), math.degrees(math.asin(max(-1.0, min(1.0, d.z))))


def body_low():
    """Lowest point of the evaluated body (metres)."""
    body = bpy.data.objects[TB.NAMES["body"]]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    M = body.matrix_world
    z = min((M @ v.co).z for v in me.vertices)
    ev.to_mesh_clear()
    return z


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (p - (a + ab * t)).length


def _seg_seg(a0, a1, b0, b1, n=16):
    return min(_seg_dist(a0.lerp(a1, i / n), b0, b1) for i in range(n + 1))


LEG_R = dict(thigh=0.11, shin=0.08, fist=0.07, club=0.06)     # capsule radii (m) for the club / fist vs leg check


def leg_clear(side="Right"):
    """How far the club's shaft and the right fist stay from a leg (capsules, metres; < 0 = through it)."""
    S = GA._pose("Socket_RightHand")
    g, tip = S.translation, S @ Vector((0, 1.0, 0))
    hip, knee, ank = (GA._pose(f"{side}{n}").translation for n in ("UpperLeg", "LowerLeg", "Foot"))
    r = LEG_R
    club = min(_seg_seg(g, tip, hip, knee) - r['thigh'], _seg_seg(g, tip, knee, ank) - r['shin']) - r['club']
    fist = min(_seg_dist(g, hip, knee) - r['thigh'], _seg_dist(g, knee, ank) - r['shin']) - r['fist']
    return min(club, fist)


def hands_clear():
    """How far the palms stay from the legs (as TrollSetup measures it in Unity: the palm between the wrist and the
    middle knuckle, thigh 0.11 / shin 0.08 / hand 0.06 m; metres, < 0 = into a leg)."""
    out = 9.0
    for side in ("Left", "Right"):
        palm = (GA._pose(f"{side}Hand").translation + GA._pose(f"{side}MiddleProximal").translation) / 2
        for leg in ("Left", "Right"):
            hip, knee, ank = (GA._pose(f"{leg}{n}").translation for n in ("UpperLeg", "LowerLeg", "Foot"))
            out = min(out, min(_seg_dist(palm, hip, knee) - 0.11, _seg_dist(palm, knee, ank) - 0.08) - 0.06)
    return out


def head_clear():
    """How far the club's shaft stays from the head (a 0.2 m ball round the Head bone's middle, metres)."""
    S = GA._pose("Socket_RightHand")
    H = GA._pose("Head")
    c = H @ Vector((0, 0.15, 0))
    return _seg_dist(c, S.translation, S @ Vector((0, 1.1, 0))) - 0.2 - LEG_R['club']


# ----------------------------------------------------------------------------------------- pose helpers
def _foot_G(side, pos, yaw=0.0, pitch=0.0, lift=0.0):
    """The rigid move of a rest foot to ground point pos (x, y) of its ankle's rest line, turned `yaw` deg (toes out for
    +), pitched `pitch` deg (+ toes up, about the heel; - heel up, about the ball), raised `lift`. Returns (G, G without
    the pitch, yaw matrix)."""
    a0 = GA._rest(f"IK_{side}Foot").translation.copy()
    piv = HEEL if pitch > 0 else BALL
    pv = Vector((a0.x, a0.y + piv, 0.0))
    P = Matrix.Translation(pv) @ Matrix.Rotation(math.radians(-pitch), 4, 'X') @ Matrix.Translation(-pv)
    s = 1 if side == "Left" else -1
    Y = Matrix.Rotation(math.radians(yaw * s), 4, 'Z')
    T = Matrix.Translation(Vector((pos[0] - a0.x, pos[1] - a0.y, lift)))
    g0 = Vector((a0.x, a0.y, 0))
    Ya = Matrix.Translation(g0) @ Y @ Matrix.Translation(-g0)
    return T @ Ya @ P, T @ Ya, Y


def _place_foot(side, pos, yaw=0.0, pitch=0.0, lift=0.0):
    """IK_<side>Foot (and its knee pole) for _foot_G's placement. The toes stay flat while the heel is up."""
    G, flat, Y = _foot_G(side, pos, yaw, pitch, lift)
    GA._set(f"IK_{side}Foot", G @ GA._rest(f"IK_{side}Foot"))
    a0 = GA._rest(f"IK_{side}Foot").translation
    GA._place(f"Pole_{side}Knee", G @ Vector((a0.x, a0.y, 0)) + Y.to_3x3() @ Vector((0, -0.75, 0.62)))
    if pitch < 0:                             # heel up on the ball: the toes keep flat on the ground
        GA._set(f"{side}Toes", flat @ GA._rest(f"{side}Toes"))
    return G


def _hips(pos_offset=Vector(), lean=0.0, yaw=0.0, list_=0.0):
    """Hips moved by pos_offset from rest, tipped forward `lean` deg, turned `yaw` deg (+ = right hip forward) and
    listed `list_` deg (+ = left hip down)."""
    M = GA._rest("Hips")
    R = (Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Rotation(math.radians(list_), 4, 'Y') @
         Matrix.Rotation(math.radians(lean), 4, 'X'))
    N = R @ M.to_3x3().to_4x4()
    N.translation = M.translation + pos_offset
    GA._set("Hips", N)


def _spine(bends, twist=0.0):
    """Forward bends (deg) of Spine, Chest, UpperChest (negative arches back); the chest turned `twist` deg about the
    vertical (+ = right shoulder forward)."""
    for n, b in zip(("Spine", "Chest", "UpperChest"), bends):
        GA._turn(n, 'X', b, local=True)
    if twist:
        for n, k in (("Chest", 0.4), ("UpperChest", 0.6)):
            GA._turn(n, UP, twist * k)


def _shoulder(side, down=0.0, back=0.0):
    """Shoulder girdle: dropped (deg, + down) and drawn back (deg)."""
    s = 1 if side == "Left" else -1
    if down:
        GA._turn(f"{side}Shoulder", FWD, -down * s)
    if back:
        GA._turn(f"{side}Shoulder", UP, back * s)


def _neck_head(look, thrust=0.0, roll=0.0, neck_share=0.45):
    """Neck bent forward `thrust` deg first (the head pushed out), then the face turned to `look`."""
    if thrust:
        GA._turn("Neck", 'X', thrust, local=True)
    GA._look(look.normalized(), roll=roll, neck_share=neck_share)


def _jaw(open_deg):
    """Jaw down by open_deg (the bone's -X turn opens it)."""
    pb = _rig().pose.bones["Jaw"]
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(-open_deg))


def _pole(side, sh, w, swivel):
    """Elbow pole swivelled `swivel` deg about the shoulder->wrist line from straight behind it (+ = out)."""
    ax = (w - sh).normalized()
    s = 1 if side == "Right" else -1
    p = Quaternion(ax, math.radians(swivel * s)) @ (BACK - BACK.project(ax)).normalized()
    GA._place(f"Pole_{side}Elbow", (sh + w) / 2 + p * 0.6)


# ----------------------------------------------------------------------------------------- arms by comfort
def _hand_from_forearm(side, twist, flex, dev):
    """The hand's armature-space matrix turned from its forearm (as posed now) by a forearm twist, a wrist flexion and
    a deviation (wrist()'s conventions: + supination, + toward the palm, + ulnar)."""
    lo = GA._pose(f"{side}LowerArm")
    rel = GA._rest(f"{side}LowerArm").inverted() @ GA._rest(f"{side}Hand")
    s = 1 if side == "Right" else -1
    W = (Matrix.Rotation(math.radians(-flex), 3, 'X') @ Matrix.Rotation(math.radians(-dev * s), 3, 'Z') @
         Matrix.Rotation(math.radians(twist * s), 3, 'Y'))
    base = lo @ rel
    M = (base.to_3x3() @ W).to_4x4()
    M.translation = base.translation
    return M


def _socket_of(side, H):
    return H @ GA._rest(f"{side}Hand").inverted() @ GA._rest(f"Socket_{side}Hand")


def _arm(side, wrist_pos, swivel, twist=0.0, flex=0.0, dev=0.0, solve=None):
    """The wrist at wrist_pos (arm IK, the elbow swivelled), the hand turned from the forearm by twist / flex / dev.
    solve(socket_of_dev) -> dev picks the deviation (the club's ground contact). Returns the deviation used."""
    sh = GA._pose(f"{side}UpperArm").translation.copy()
    M = GA._rest(f"IK_{side}Hand")
    M.translation = Vector(wrist_pos)
    GA._set(f"IK_{side}Hand", M)
    _pole(side, sh, Vector(wrist_pos), swivel)
    if solve is not None:
        dev = solve(lambda d: _socket_of(side, _hand_from_forearm(side, twist, flex, d)))
    GA._set(f"IK_{side}Hand", _hand_from_forearm(side, twist, flex, dev))
    return dev


def _club_at(height, verts=None, lo=-15.0, hi=32.0):
    """A solve for _arm: the deviation (inside lo..hi) that puts the club's lowest point at `height`, never under it."""
    def solve(sock_of):
        f = lambda d: club_low(sock_of(d), verts) - height
        a, b = lo, hi
        fa, fb = f(a), f(b)
        if fa * fb > 0:                       # out of reach: the end that comes closest (report() shows the miss)
            return a if abs(fa) < abs(fb) else b
        for _ in range(24):
            m = (a + b) / 2
            fm = f(m)
            if (fa <= 0) == (fm <= 0):
                a, fa = m, fm
            else:
                b, fb = m, fm
        return a if fa >= 0 else b
    return solve


def _off(sh, side, out, fwd, up):
    """A point offset from a shoulder: out (away from the body), forward, up (metres)."""
    return sh + (RT if side == "Right" else LEFT) * out + FWD * fwd + UP * up


def _geometry():
    """Foot landmarks from the rest body: heel and ball (y offsets from the ankle, metres)."""
    global HEEL, BALL
    r = _rig()
    a = r.data.bones["RightFoot"].head_local
    b = r.data.bones["RightToes"].head_local
    body = bpy.data.objects[TB.NAMES["body"]]
    gi = {g.index for g in body.vertex_groups if g.name in ("RightFoot", "RightToes")}
    ys = [v.co.y for v in body.data.vertices if v.groups and max(v.groups, key=lambda g: g.weight).group in gi and v.co.z < 0.05]
    HEEL = (max(ys) if ys else a.y + 0.07) - a.y - 0.01
    BALL = b.y - a.y
    return HEEL, BALL


HEEL, BALL = 0.07, -0.178


# ----------------------------------------------------------------------------------------- keying
def _keyed():
    fingers = [f"{s}{f}{p}" for s in ("Left", "Right") for f in GA.FINGERS for p in GA.PARTS]
    return list(GA.BODY) + list(GA.CONTROLS) + fingers + ["LeftToes", "RightToes", "Jaw"]


def _key(frame, prev):
    r = _rig()
    for name in _keyed():
        pb = r.pose.bones[name]
        pb.rotation_mode = 'QUATERNION'
        q = pb.rotation_quaternion.copy()
        if name in prev and q.dot(prev[name]) < 0:
            pb.rotation_quaternion = -q
        prev[name] = pb.rotation_quaternion.copy()
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)
        if name == "Hips" or name.startswith(("IK_", "Pole_")):
            pb.keyframe_insert("location", frame=frame, group=name)


def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ----------------------------------------------------------------------------------------- Roar
ROAR_FEET = {"Left": ((0.23, -0.07), 10.0), "Right": ((-0.25, 0.11), 16.0)}    # (x, y), toes out: planted throughout
# Per stage: hips drop / lean, spine bends, look (deg up), neck thrust, head roll, jaw, shoulders (down, back), and the
# arms as (out, forward, up from the shoulder, elbow swivel, forearm twist, wrist flex, deviation); a stage may ask
# for "club": the right wrist's deviation that puts the club's lowest point at that height. Fingers: (shape, shape, mix).
PEAK_L = (0.50, 0.40, -0.12, 60, 15, 10, 0)      # the free arm out at the peak, the claw palm down-forward
ROAR = {
    'stance': dict(drop=0.07, lean=8, bends=(8, 7, 8), look=-4, thrust=0, roll=0, jaw=0, sh=(0, 0),
                   R=(0.07, 0.15, -0.83, 25, 5, 5, 18),
                   L=(0.08, 0.04, -0.86, 15, -10, 8, 3), Lf=('open', 'open', 0)),
    'gather': dict(drop=0.19, lean=22, bends=(12, 12, 10), look=-28, thrust=6, roll=0, jaw=4, sh=(6, -4),
                   R=(0.17, -0.10, -0.78, 35, 10, 5, 15),
                   L=(0.14, 0.34, -0.70, 20, 15, 15, 5), Lf=('claw', 'claw', 0)),
    'rise': dict(drop=0.14, lean=8, bends=(3, 1, -1), look=8, thrust=16, roll=0, jaw=14, sh=(-4, 6),
                 R=None, L=None, Lf=('claw', 'spread', 0.5)),
    'peak': dict(drop=0.12, lean=3, bends=(-3, -6, -8), look=26, thrust=36, roll=-4, jaw=30, sh=(-9, 10),
                 R=None, L=PEAK_L, Lf=('spread', 'claw', 0.35)),
    'hold': dict(drop=0.13, lean=4, bends=(-2, -5, -7), look=24, thrust=34, roll=3, jaw=26, sh=(-7, 8),
                 R=None, L=PEAK_L[:2] + (PEAK_L[2] - 0.02,) + PEAK_L[3:], Lf=('spread', 'claw', 0.5)),
    'settle': dict(drop=0.11, lean=12, bends=(9, 8, 8), look=-10, thrust=4, roll=0, jaw=6, sh=(3, -1),
                   R=(0.07, 0.15, -0.82, 25, 5, 5, 18),
                   L=(0.08, 0.06, -0.84, 15, -5, 10, 3), Lf=('open', 'claw', 0.3)),
}
# the raised club (optimise_roar_club, 2026-10-23): the right arm reaching up and forward-out, the fist over head
# height, the club standing up and a little back, palm forward (the club leaves the thumb side, so a club pointing up
# wants the forearm near level and turned out)
ROAR_CLUB = dict(out=0.60, fwd=0.50, up=0.33, swivel=59.0, twist=78.0, flex=11.0, dev=9.0)
ROAR_KEYS = [(0, 'stance'), (12, 'gather'), (22, 'rise'), (30, 'peak'), (54, 'hold'), (68, 'settle'), (84, 'stance')]


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _roar_stage(stage, solved=None):
    """The stage's parameters with the raised club filled in ('rise' = part way from the solved 'gather' to 'peak')."""
    P = dict(ROAR[stage])
    c = ROAR_CLUB
    peak_R = (c['out'], c['fwd'], c['up'], c['swivel'], c['twist'], c['flex'], c['dev'])
    if stage in ('peak', 'hold'):
        k = 1.0 if stage == 'peak' else 0.96
        P['R'] = (peak_R[0], peak_R[1], peak_R[2] * k) + peak_R[3:]
    elif stage == 'rise':
        g = solved['gather']
        R = _mix(g['R'], peak_R, 0.55)
        P['R'] = R[:2] + (R[2] + 0.10,) + R[3:]          # the club comes up in front, not through the chest
        P['L'] = _mix(g['L'], ROAR['peak']['L'], 0.5)
    return P


def _curls(shape_a, shape_b, m):
    return {(f, i): da + (db - da) * m for f in GA.FINGERS
            for i, (da, db) in enumerate(zip(GA.HANDS[shape_a][f], GA.HANDS[shape_b][f]))}


def _set_curls(side, curls):
    r = _rig()
    for (f, i), deg in curls.items():
        pb = r.pose.bones[f"{side}{f}{GA.PARTS[i]}"]
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(deg))


def _roar_params(t_frame, solved):
    """Every number of the Roar at a frame: the bracketing stages' numbers eased (stage poses are comfortable, so are
    the frames between them)."""
    for (f0, s0), (f1, s1) in zip(ROAR_KEYS, ROAR_KEYS[1:]):
        if f0 <= t_frame <= f1:
            break
    t = _ease((t_frame - f0) / (f1 - f0))
    a, b = solved[s0], solved[s1]
    out = {}
    for k in a:
        va, vb = a[k], b[k]
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[k] = va + (vb - va) * t
        elif isinstance(va, tuple) and k != 'Lf':
            out[k] = tuple(x + (y - x) * t for x, y in zip(va, vb))
        else:
            out[k] = (va, vb, t)
    return out


def _roar_body(P, shake=0.0):
    GA.reset()
    for side, (pos, yaw) in ROAR_FEET.items():
        _place_foot(side, pos, yaw)
    _hips(Vector((0, -0.03 * max(0.0, min(1.0, P['look'] / 30.0)), -P['drop'])), lean=P['lean'], yaw=-4)
    _spine(P['bends'], twist=-4 * max(0.0, min(1.0, P['look'] / 30.0)))
    for side in ("Left", "Right"):
        _shoulder(side, down=P['sh'][0], back=P['sh'][1])
    if shake:
        GA._turn("UpperChest", FWD, 1.2 * shake)
    look = GA._rotate_about(FWD, RT, P['look'] + 2.0 * shake)
    _neck_head(look, thrust=P['thrust'], roll=P['roll'] + 2 * shake, neck_share=0.25 if P['thrust'] > 8 else 0.45)
    _jaw(P['jaw'] + 3.0 * shake)


def pose_roar(P, shake=0.0, verts=None):
    """One Roar frame from its numbers (_roar_params). Returns the right wrist's deviation."""
    _roar_body(P, shake)
    shL = GA._pose("LeftUpperArm").translation.copy()
    shR = GA._pose("RightUpperArm").translation.copy()
    o, f, u, sw, tw, fl, dv = P['L']
    _arm("Left", _off(shL, "Left", o, f, u + 0.012 * shake), sw, tw, fl, dv)
    Lf = P['Lf']
    if isinstance(Lf[0], tuple):              # between two stages: the two stages' hands blended
        c0, c1, t = _curls(*Lf[0]), _curls(*Lf[1]), Lf[2]
        _set_curls("Left", {k: c0[k] + (c1[k] - c0[k]) * t for k in c0})
    else:
        _set_curls("Left", _curls(*Lf))
    o, f, u, sw, tw, fl, dv = P['R']
    dev = _arm("Right", _off(shR, "Right", o, f, u + 0.012 * shake), sw, tw, fl, dv)
    GA._fingers("Right", 'fist')
    return dev


def _solve_roar(verts):
    """Stage numbers with the club heights turned into wrist deviations (each stage posed once)."""
    solved = {}
    for stage in sorted(ROAR, key=lambda s: s == 'rise'):         # 'rise' after the stages it is mixed from
        P = _roar_stage(stage, solved)
        if P.get('club') is not None:
            _roar_body(P)
            sh = GA._pose("RightUpperArm").translation.copy()
            o, f, u, sw, tw, fl, _ = P['R']
            dv = _arm("Right", _off(sh, "Right", o, f, u), sw, tw, fl, solve=_club_at(P['club'], verts))
            P['R'] = (o, f, u, sw, tw, fl, dv)
        P.pop('club', None)
        solved[stage] = P
    return solved


def build_roar():
    """Every frame posed from the eased stage numbers and keyed; a tremor on the held roar."""
    verts = _club_verts()
    solved = _solve_roar(verts)
    act = GA._new_action("Roar")
    prev = {}
    ev = EVENTS["Roar"]
    for f in range(0, ROAR_KEYS[-1][0] + 1):
        sh = 0.0
        if ev["roar"] <= f <= 58:                        # the tremor while the roar is held, fading
            fade = _ease((f - ev["roar"]) / 4.0) * _ease((58 - f) / 6.0)
            sh = fade * math.sin(2 * math.pi * 7.5 * f / FPS)
        pose_roar(_roar_params(f, solved), shake=sh, verts=verts)
        _key(f, prev)
    GA._key_constraints(0)
    act.frame_range = (0, ROAR_KEYS[-1][0])
    act.use_frame_range = True
    return act


# ----------------------------------------------------------------------------------------- ClubDrag
# ClubDrag gait (metres, frames at 30 fps). The troll stoops low and bows toward the club (side, club_shoulder): from a
# fist any higher, the 1.15 m club reaches the ground only with the wrist bent past 30 deg.
GAIT = dict(cycle=60, stride=1.5, duty=0.62, front=0.42, foot_x=0.20, toe_out=6.0, lift=0.10, strike=12.0, push=28.0,
            drop=0.30, bob=0.022, sway=0.035, yaw=6.0, list_=3.0, lean=16.0, hunch=(12.0, 10.0, 8.0), arm_swing=0.20,
            side=7.0, club_shoulder=14.0)   # side: the chest bowed toward the club (deg); the right shoulder dropped
# the dragging arm (optimise_drag, 2026-10-23): the wrist from the right shoulder (out, back, down), the elbow's swivel,
# the forearm's twist (palm forward) and the wrist's flexion; the deviation is solved per frame for the club's contact
DRAG = dict(out=0.112, back=-0.212, down=0.867, swivel=51.6, twist=79.9, flex=17.3)
# the free (left) arm: hanging out past the stooped knee (the palm clear of the thigh), swinging against the left leg
FREE_ARM = dict(out=0.28, fwd=0.15, down=0.78, swivel=20.0, twist=-15.0, flex=10.0, dev=3.0)
DEV_RANGE = [-15.0, 32.0]          # where the contact solve looks for the deviation (the optimiser widens it)


def _foot_track(u, phase0):
    """One foot at cycle fraction u (0..1); phase0 = the cycle fraction of its heel strike. Returns (plant y, pitch,
    swing fraction, next plant y): pitch is None while the foot swings."""
    g = GAIT
    L, duty = g['stride'], g['duty']
    v = (u - phase0) % 1.0                   # time since this foot's heel strike
    n = math.floor(u - phase0)               # which strike (cycles since)
    strike_hip = -L * (phase0 + n)            # hips' y at that strike
    y_plant = strike_hip - g['front']
    if v <= duty:                             # stance
        s = v / duty
        if s < 0.12:
            pitch = g['strike'] * (1 - _ease(s / 0.12))
        elif s > 0.62:
            pitch = -g['push'] * _ease((s - 0.62) / 0.38)
        else:
            pitch = 0.0
        return y_plant, pitch, 0.0, None
    s = (v - duty) / (1 - duty)              # swing: from this plant to the next one
    return y_plant, None, s, y_plant - L


def _foot_swing(side, x, y_plant, s, y_next, yaw):
    """A swinging foot at fraction s between the toe-off and the next strike."""
    g = GAIT
    F0 = GA._rest(f"IK_{side}Foot")
    G0, flat0, _ = _foot_G(side, (x, y_plant), yaw, -g['push'])
    G1, _, _ = _foot_G(side, (x, y_next), yaw, g['strike'])
    a0, a1 = (G0 @ F0).translation, (G1 @ F0).translation
    e = _ease(s)
    pitch = -g['push'] + (g['push'] + g['strike']) * _ease(min(1.0, s * 1.25))
    a = a0.lerp(a1, e) + UP * (g['lift'] * math.sin(math.pi * min(1.0, s * 1.08)) ** 1.2)
    sgn = 1 if side == "Left" else -1
    R = Matrix.Rotation(math.radians(yaw * sgn), 4, 'Z') @ Matrix.Rotation(math.radians(-pitch), 4, 'X')
    M = R @ F0.to_3x3().to_4x4()
    M.translation = a
    GA._set(f"IK_{side}Foot", M)
    GA._place(f"Pole_{side}Knee", a + Matrix.Rotation(math.radians(yaw * sgn), 3, 'Z') @ Vector((0, -0.75, 0.46)))
    k = 1.0 - _ease(s / 0.35)                 # the toes, flat at toe-off, ease back into line with the foot
    if k > 0:
        toes = GA._pose(f"{side}Toes")
        flat = Matrix.Translation(toes.translation) @ (flat0 @ GA._rest(f"{side}Toes")).to_3x3().to_4x4()
        q = toes.to_quaternion().slerp(flat.to_quaternion(), k)
        T = q.to_matrix().to_4x4()
        T.translation = toes.translation
        GA._set(f"{side}Toes", T)


def _drag_body(f):
    """Legs, hips, spine, head and the free arm of ClubDrag at frame f; returns the hips' yaw."""
    g = GAIT
    u = f / g['cycle']
    GA.reset()
    for side, ph, sx in (("Right", 0.0, -1), ("Left", 0.5, 1)):      # right heel strikes at u = 0, left at 0.5
        y_plant, pitch, s, y_next = _foot_track(u, ph)
        if pitch is not None:
            _place_foot(side, (sx * g['foot_x'], y_plant), g['toe_out'], pitch)
        else:
            _foot_swing(side, sx * g['foot_x'], y_plant, s, y_next, g['toe_out'])
    # hips: forward at a steady speed, low, bobbing (high at mid-stance), swaying over the stance foot
    w = 2 * math.pi
    y = -g['stride'] * u
    x = -g['sway'] * math.cos(w * (u - 0.30))
    z = -g['drop'] + g['bob'] * math.cos(2 * w * (u - 0.30))
    yaw = g['yaw'] * math.cos(w * u)
    lst = g['list_'] * math.cos(w * (u - 0.31))
    _hips(Vector((x, y, z)), lean=g['lean'], yaw=yaw, list_=lst)
    _spine(g['hunch'], twist=-1.4 * yaw)
    if g['side']:                                                # bowed toward the club: the right shoulder lower
        for n, k in (("Chest", 0.45), ("UpperChest", 0.55)):
            GA._turn(n, FWD, g['side'] * k)
    _shoulder("Right", down=g['club_shoulder'], back=4.0)        # the club's weight
    _shoulder("Left", down=2.0, back=-2.0 * math.cos(w * u))
    look = GA._rotate_about(FWD, RT, -6.0 + 1.5 * math.cos(2 * w * (u - 0.30)))
    _neck_head(look, thrust=8.0, roll=-1.5 * math.cos(w * (u - 0.30)), neck_share=0.35)
    _jaw(3.0)
    # the free arm swings against the left leg (forward when the right foot is), hand half-clawed
    shL = GA._pose("LeftUpperArm").translation.copy()
    sw = g['arm_swing'] * math.cos(w * u)
    a = FREE_ARM
    _arm("Left", _off(shL, "Left", a['out'], a['fwd'] + sw, -a['down'] + 0.05 * abs(sw) / g['arm_swing']), a['swivel'],
         a['twist'], a['flex'], a['dev'])
    GA._fingers("Left", 'claw')
    return yaw


def pose_drag(f, verts=None):
    """ClubDrag at frame f (0..cycle). Returns the right wrist's deviation."""
    g = GAIT
    _drag_body(f)
    # the club arm: the wrist follows the shoulder with a little lag, the deviation lays the club on the ground
    shR = GA._pose("RightUpperArm").translation.copy()
    lag = 0.03 * math.cos(2 * math.pi * f / g['cycle'])
    d = DRAG
    dev = _arm("Right", _off(shR, "Right", d['out'], -(d['back'] + lag), -d['down']), d['swivel'], d['twist'], d['flex'],
               solve=_club_at(CONTACT, verts, *DEV_RANGE))
    GA._fingers("Right", 'fist')
    return dev


def build_drag():
    verts = _club_verts()
    act = GA._new_action("ClubDrag")
    prev = {}
    for f in range(GAIT['cycle'] + 1):
        pose_drag(f, verts)
        _key(f, prev)
    GA._key_constraints(0)
    act.frame_range = (0, GAIT['cycle'])
    act.use_frame_range = True
    return act


DRAG_RANGES = dict(out=(0.05, 0.40), back=(-0.40, 0.20), down=(0.55, 0.90), swivel=(-60, 120), twist=(-80, 80),
                   flex=(-20, 20))


def _nelder_mead(f, x0, step, iters=300, tol=1e-4):
    """A small Nelder-Mead minimiser (Blender's Python has no scipy)."""
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (step[j] if j == i else 0.0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol:
            break
        c = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        xr = [c[j] + (c[j] - pts[-1][j]) for j in range(n)]
        fr = f(xr)
        if fr < vals[0]:
            xe = [c[j] + 2 * (c[j] - pts[-1][j]) for j in range(n)]
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(n)]
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    i = min(range(n + 1), key=lambda i: vals[i])
    return pts[i], vals[i]


HEADING = [25.0, 60.0]             # the club's heading the drag optimiser accepts (deg from straight back)


def drag_cost(frames=(9, 24, 39, 54), verts=None, detail=False):
    """How far the current DRAG is from a comfortable drag over `frames`: the club off the ground, the solved
    deviation, the upper arm's twist, the club or fist near a leg and a heading outside HEADING, either hand near a leg weigh as faults; the
    strain inside COMFORT as a small cost."""
    cost, worst = 0.0, dict(miss=0.0, dev_lo=99.0, dev_hi=-99.0, humerus=0.0, clear=9.0, head_lo=999.0, head_hi=-999.0,
                            ik=0.0)
    lim = COMFORT
    for f in frames:
        dev = pose_drag(f, verts)
        S = GA._pose("Socket_RightHand")
        miss = abs(club_low(S, verts) - CONTACT)
        hu = abs(humerus("Right"))
        cl = min(leg_clear("Right"), leg_clear("Left"))
        hc = hands_clear()
        hd, _ = club_heading(S)
        ik = (GA._pose("RightHand").translation - GA._pose("IK_RightHand").translation).length
        cost += (1e4 * max(0.0, miss - 0.002) ** 2 + max(0.0, dev - lim['ulnar']) ** 2 + max(0.0, -lim['radial'] - dev) ** 2
                 + max(0.0, hu - lim['humerus']) ** 2 + 1e5 * max(0.0, 0.03 - cl) ** 2 + max(0.0, HEADING[0] - hd) ** 2
                 + max(0.0, hd - HEADING[1]) ** 2 + 1e5 * max(0.0, 0.02 - hc) ** 2 + 1e5 * max(0.0, ik - 0.005) ** 2
                 + 0.5 * ((dev / 30) ** 2 + (hu / 60) ** 2))
        worst.update(miss=max(worst['miss'], miss), dev_lo=min(worst['dev_lo'], dev), dev_hi=max(worst['dev_hi'], dev),
                     humerus=max(worst['humerus'], hu), clear=min(worst['clear'], cl), head_lo=min(worst['head_lo'], hd),
                     head_hi=max(worst['head_hi'], hd), ik=max(worst['ik'], ik))
    d = DRAG
    cost += len(frames) * (0.5 * ((d['twist'] / 80) ** 2 + (d['flex'] / 25) ** 2) + 1e3 * max(0.0, abs(d['twist']) - 80) ** 2
                           + 1e3 * max(0.0, abs(d['flex']) - 20) ** 2)
    return (cost, worst) if detail else cost


def optimise_drag(starts=16, seed=7, iters=250, frames=(9, 24, 39, 54), near=None):
    """Nelder-Mead from random DRAG_RANGES starts (or jittered round `near`, a fraction of each range) on drag_cost;
    returns the best few (cost, DRAG, worst frames)."""
    import random
    random.seed(seed)
    keys = list(DRAG_RANGES)
    keep = dict(DRAG)
    verts = _club_verts()
    out = []
    DEV_RANGE[:] = [-35.0, 55.0]
    try:
        with _OnTroll():
            def f(x):
                DRAG.update(zip(keys, x))
                if math.sqrt(DRAG['out'] ** 2 + DRAG['back'] ** 2 + DRAG['down'] ** 2) > 0.90:
                    return 1e6
                return drag_cost(frames, verts)
            for s in range(starts):
                span = {k: DRAG_RANGES[k][1] - DRAG_RANGES[k][0] for k in keys}
                if near:
                    x0 = [keep[k] + random.uniform(-near, near) * span[k] for k in keys]
                else:
                    x0 = [random.uniform(*DRAG_RANGES[k]) for k in keys]
                step = [span[k] * (near or 0.15) for k in keys]
                x, v = _nelder_mead(f, x0, step, iters=iters)
                DRAG.update(zip(keys, x))
                c, w = drag_cost(frames, verts, detail=True)
                out.append((round(c, 3), {k: round(DRAG[k], 3) for k in keys}, {k: round(v, 3) for k, v in w.items()}))
    finally:
        DEV_RANGE[:] = [-15.0, 32.0]
        DRAG.clear()
        DRAG.update(keep)
    out.sort(key=lambda r: r[0])
    return out


ROAR_CLUB_RANGES = dict(out=(0.20, 0.60), fwd=(-0.10, 0.50), up=(0.0, 0.60), swivel=(-60, 180), twist=(-80, 80),
                        flex=(-25, 25), dev=(-15, 30))


def optimise_roar_club(starts=30, seed=4, want=(0.25, 0.35, 0.9), iters=400):
    """The comfort search behind ROAR_CLUB: at the peak pose, Nelder-Mead from random starts over the right wrist's place
    (out, forward, up from the shoulder, kept inside ROAR_CLUB_RANGES), the elbow's swivel, the forearm's twist and the
    wrist's flexion and deviation, scored by how far the club points from `want` (out, back, up), how low the fist is and
    the strain; the arm's reach, the club clear of the head and COMFORT as faults. Returns the best few."""
    import random
    random.seed(seed)
    keys = list(ROAR_CLUB_RANGES)
    R = ROAR_CLUB_RANGES
    d_want = (RT * want[0] + BACK * want[1] + UP * want[2]).normalized()
    res = []
    with _OnTroll():
        P = _roar_stage('peak')
        P['R'] = (0.3, 0.0, 0.4, 60, 0, 0, 0)
        _roar_body(P)
        sh = GA._pose("RightUpperArm").translation.copy()

        def ev(x, detail=False):
            c = dict(zip(keys, x))
            w = _off(sh, "Right", c['out'], c['fwd'], c['up'])
            reach = (w - sh).length
            _arm("Right", w, c['swivel'], c['twist'], c['flex'], c['dev'])
            err = (GA._pose("RightHand").translation - w).length
            fl, dv, tw = wrist("Right")
            hu = humerus("Right")
            S = GA._pose("Socket_RightHand")
            ang = math.degrees(S.col[1].xyz.normalized().angle(d_want))
            hc = head_clear()
            lim = COMFORT
            cost = ((ang / 12) ** 2 + (tw / 80) ** 2 + (fl / 25) ** 2 + (dv / 30) ** 2 + (hu / 60) ** 2 +
                    ((0.45 - c['up']) / 0.3) ** 2 + 1e3 * max(0, abs(tw) - lim['twist']) ** 2 +
                    1e3 * max(0, abs(fl) - lim['flex']) ** 2 + 1e3 * max(0, dv - lim['ulnar']) ** 2 +
                    1e3 * max(0, -lim['radial'] - dv) ** 2 + 10 * max(0, abs(hu) - lim['humerus']) ** 2 +
                    1e5 * max(0, 0.08 - hc) ** 2 + 1e5 * max(0, err - 0.005) ** 2 + 1e5 * max(0, reach - 0.88) ** 2 +
                    1e3 * sum(max(0, R[k][0] - c[k]) ** 2 + max(0, c[k] - R[k][1]) ** 2 for k in ('out', 'fwd', 'up')))
            if detail:
                return cost, dict(aim=round(ang, 1), flex=round(fl, 1), dev=round(dv, 1), twist=round(tw, 1),
                                  humerus=round(hu, 1), head=round(hc, 3), fist_z=round(S.translation.z, 2))
            return cost
        for s in range(starts):
            x0 = [random.uniform(*R[k]) for k in keys]
            x, v = _nelder_mead(ev, x0, [(R[k][1] - R[k][0]) * 0.15 for k in keys], iters=iters)
            c, d = ev(x, True)
            res.append((round(c, 3), {k: round(val, 3) for k, val in zip(keys, x)}, d))
    res.sort(key=lambda r: r[0])
    return res[:8]


# ----------------------------------------------------------------------------------------- all, report, export
def build_all():
    _geometry()
    with _OnTroll():
        out = [build_roar().name, build_drag().name]
        use("Roar")
    return out


def use(name, frame=None):
    r = _rig()
    act = bpy.data.actions[name]
    if r.animation_data is None:
        r.animation_data_create()
    r.animation_data.action = act
    GA._slot(r, act)
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    scn.frame_set(int(act.frame_range[0]) if frame is None else frame)


def clear():
    """Back to the T-pose with FK arms (what the character export expects)."""
    with _OnTroll():
        GA.clear()


def report(names=CLIPS):
    """Per clip and frame: the body's lowest point, the club's lowest point, heading and clearance from the legs (and
    the head), the wrists (flex, deviation, forearm twist) and the upper arms' twist, the legs' reach; plus per-clip
    ranges. Written to renders/anim/troll_clips_report.json."""
    verts = _club_verts()
    out = {}
    scn = bpy.context.scene
    with _OnTroll():
        for name in names:
            use(name)
            f0, f1 = int(scn.frame_start), int(scn.frame_end)
            rows = []
            for f in range(f0, f1 + 1):
                scn.frame_set(f)
                GA._upd()
                S = _rig().matrix_world @ GA._pose("Socket_RightHand")
                hd, pt = club_heading(S)
                row = dict(frame=f, body_low=round(body_low(), 3), club_low=round(club_low(S, verts), 3),
                           club_heading=round(hd, 1), club_pitch=round(pt, 1),
                           club_leg_clear=round(min(leg_clear("Right"), leg_clear("Left")), 3),
                           club_head_clear=round(head_clear(), 3), hands_leg_clear=round(hands_clear(), 3))
                for side in ("Right", "Left"):
                    fl, dv, tw = wrist(side)
                    row[side] = dict(flex=round(fl, 1), dev=round(dv, 1), twist=round(tw, 1), humerus=round(humerus(side), 1))
                row["hips"] = [round(c, 3) for c in GA._pose("Hips").translation]
                for side in ("Left", "Right"):                       # legs never fully straight
                    a = GA._pose(f"{side}UpperLeg").translation
                    b = GA._pose(f"{side}Foot").translation
                    L = _rig().data.bones[f"{side}UpperLeg"].length + _rig().data.bones[f"{side}LowerLeg"].length
                    row[side + "_leg_reach"] = round((b - a).length / L, 3)
                rows.append(row)

            def rng(k, s=None):
                vals = [r[s][k] if s else r[k] for r in rows]
                return [min(vals), max(vals)]
            summ = dict(frames=len(rows), body_low=rng('body_low'), club_low=rng('club_low'),
                        club_heading=rng('club_heading'), club_leg_clear=rng('club_leg_clear')[0],
                        club_head_clear=rng('club_head_clear')[0], hands_leg_clear=rng('hands_leg_clear')[0],
                        right_flex=rng("flex", "Right"), right_dev=rng("dev", "Right"), right_twist=rng("twist", "Right"),
                        right_humerus=rng("humerus", "Right"), left_flex=rng("flex", "Left"), left_dev=rng("dev", "Left"),
                        left_twist=rng("twist", "Left"), left_humerus=rng("humerus", "Left"),
                        leg_reach_max=max(max(r["Left_leg_reach"], r["Right_leg_reach"]) for r in rows),
                        hips_travel=[round(rows[-1]["hips"][i] - rows[0]["hips"][i], 3) for i in range(3)])
            out[name] = dict(summary=summ, frames=rows)
    os.makedirs(os.path.join(RENDERS, "anim"), exist_ok=True)
    with open(os.path.join(RENDERS, "anim", "troll_clips_report.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return {k: v["summary"] for k, v in out.items()}


# ----------------------------------------------------------------------------------------- review renders
ANIM_SCENE = "Troll_Anim"
VIEWS = {   # camera offset from the followed point (hips x/y at ground level), target height, ortho scale or lens
    "right": ((-7.0, -0.6, 1.25), 1.15, 3.4),
    "front": ((0.4, -7.0, 1.30), 1.20, 3.4),
    "34": ((3.4, -5.0, 2.3), 1.05, 55),
    "back34r": ((-3.6, 4.4, 2.4), 0.85, 55),
    "face": ((0.6, -2.4, 2.2), 1.95, 70),
    "low_right": ((-3.2, 1.6, 0.30), 0.22, 50),
    "hand_r": ((-1.9, -1.0, 1.0), 0.55, 45),         # the dragging fist and wrist, from the front right
    "hand_rb": ((-1.6, 1.4, 0.9), 0.55, 45),         # ... from behind right
}


def anim_scene():
    """Scene Troll_Anim: the troll (the Troll scene's own objects) on a checkered ground (0.5 m squares), for the
    clips' renders."""
    import troll_build as T
    scn = T._scene(ANIM_SCENE)
    scn.view_settings.view_transform = 'Standard'
    scn.render.fps = FPS
    T._lights(scn)
    T._link_troll(scn)
    g = bpy.data.objects.get("TRL_AnimGround")
    if g is None:
        me = bpy.data.meshes.new("TRL_AnimGround")
        me.from_pydata([(-12, -14, 0), (12, -14, 0), (12, 10, 0), (-12, 10, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("TRL_AnimGround", me)
        m = bpy.data.materials.new("TRL_AnimGround")
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        chk = nt.nodes.new("ShaderNodeTexChecker")
        chk.inputs["Scale"].default_value = 48.0                 # 0.5 m squares on the 24 m plane
        chk.inputs["Color1"].default_value = (0.20, 0.24, 0.13, 1)
        chk.inputs["Color2"].default_value = (0.25, 0.29, 0.17, 1)
        nt.links.new(chk.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 1.0
        me.materials.append(m)
    if g.name not in scn.collection.objects:
        scn.collection.objects.link(g)
    return scn


def _follow():
    h = _rig().matrix_world @ _rig().pose.bones["Hips"].matrix.translation
    return Vector((h.x, h.y, 0.0))


def render_strip(name, frames, views=("right", "34"), res=(460, 560), follow=True, tag=None):
    """renders/anim/<tag>.png: one row per view, one tile per frame (the camera keeps with the hips when follow)."""
    import numpy as np
    import troll_build as T
    scn = anim_scene()
    win = bpy.context.window
    if win is not None:
        win.scene = scn
    use(name)
    rows = []
    os.makedirs(os.path.join(RENDERS, "anim"), exist_ok=True)
    scn.frame_set(frames[0])                       # a first render of a new camera can come out framed stale: warm up
    off, th, k = VIEWS[views[0]]
    c = _follow() if follow else Vector()
    cam = T._cam(scn, "TRL_ANIM_CAM", c + Vector(off), c + Vector((0, 0, th)), ortho=k if k < 10 else None,
                 lens=k if k >= 10 else 85)
    T.shot(scn, cam.name, "anim/_tile", (64, 64))
    for v in views:
        off, th, k = VIEWS[v]
        row = []
        for f in frames:
            scn.frame_set(f)
            c = _follow() if follow else Vector()
            cam = T._cam(scn, "TRL_ANIM_CAM", c + Vector(off), c + Vector((0, 0, th)),
                         ortho=k if k < 10 else None, lens=k if k >= 10 else 85)
            p = T.shot(scn, cam.name, "anim/_tile", res)
            img = bpy.data.images.load(p, check_existing=False)
            a = np.array(img.pixels[:], dtype=np.float32).reshape(res[1], res[0], 4)
            bpy.data.images.remove(img)
            row.append(a)
        rows.append(np.concatenate(row, axis=1))
    sheet = np.concatenate(rows[::-1], axis=0)
    out = bpy.data.images.new("_strip", sheet.shape[1], sheet.shape[0])
    out.pixels = sheet.ravel()
    path = os.path.join(RENDERS, "anim", f"{tag or 'troll_' + name.lower()}.png")
    out.filepath_raw = path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return path


def game_shot(name, frame, tag):
    """The troll at a clip's frame from the game camera (troll_build.game_view: 22 m, 50 deg, fov 30, beside a goblin
    and a 1.75 m mannequin) and the 4x crop of it."""
    import troll_build as T
    use(name, frame)
    bpy.data.scenes["Troll_Game"].frame_set(frame)
    return T.game_view(tag)


def review():
    """renders/anim: strips of both clips (Roar: front, right, 3/4; ClubDrag: right, behind right, front), the roaring
    face, the dragging fist close up, and the game camera."""
    out = [render_strip("Roar", [0, 12, 22, 30, 40, 54, 68, 84], views=("front", "right", "34"), tag="troll_roar"),
           render_strip("ClubDrag", [0, 8, 15, 23, 30, 38, 45, 53], views=("right", "back34r", "front"), tag="troll_clubdrag"),
           render_strip("Roar", [0, 12, 30, 44], views=("face",), res=(600, 600), tag="troll_roar_face"),
           render_strip("ClubDrag", [0, 15, 30, 45], views=("hand_r", "hand_rb"), res=(560, 560), tag="troll_clubdrag_hand"),
           render_strip("ClubDrag", [0, 15, 30, 45], views=("low_right",), res=(700, 420), tag="troll_clubdrag_ground")]
    out += game_shot("Roar", 34, "anim/troll_roar")
    out += game_shot("ClubDrag", 15, "anim/troll_clubdrag")
    clear()
    return out


def clip_info():
    """What TrollSetup needs per clip (frames, loop, root motion, events in seconds)."""
    out = []
    for name in CLIPS:
        act = bpy.data.actions[name]
        n = int(act.frame_range[1] - act.frame_range[0])
        ev = [dict(name=("Roar" if k == "roar" else k), time=round(v / FPS, 4)) for k, v in EVENTS[name].items() if k != "end"]
        out.append(dict(name=name, frames=n, fps=FPS, loop=LOOP[name], rootMotion=ROOT_MOTION[name], events=ev))
    return dict(clips=out)


def export_clips(names=CLIPS):
    """export/Troll/Anims/Troll@<clip>.fbx (the deform skeleton, one baked take each) and troll_clips.json."""
    os.makedirs(EXPORT, exist_ok=True)
    r = _rig()
    scn = bpy.context.scene
    keep = (scn.frame_start, scn.frame_end, scn.render.fps)
    written = []
    try:
        for name in names:
            use(name)
            scn.render.fps = FPS
            for o in bpy.context.selected_objects:
                o.select_set(False)
            r.hide_set(False)
            r.select_set(True)
            bpy.context.view_layer.objects.active = r
            path = os.path.join(EXPORT, f"Troll@{name}.fbx")
            opts = dict(gob_export.FBX)
            opts.update(bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
                        bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                        bake_anim_simplify_factor=0.0)
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE'}, **opts)
            written.append(path)
        info = os.path.join(EXPORT, "troll_clips.json")
        with open(info, "w") as fh:
            json.dump(clip_info(), fh, indent=1)
        written.append(info)
    finally:
        scn.frame_start, scn.frame_end, scn.render.fps = keep
        r.select_set(False)
        clear()
    return written
