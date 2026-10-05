"""Custom goblin clips, keyframed on GoblinRig and exported as FBX takes for Unity Humanoid.

The Kevin Iglesias library has melee and locomotion but no bow, so the archer's clips are authored here:
    Bow_Ready   loop, 2 s: side-on stance, bow low and canted, arrow nocked, breathing
    Bow_Shoot   ready -> raise and draw to the jaw -> aim -> release -> follow through ->
                arrow from the quiver over the right shoulder -> nock -> ready
    Bow_Volley  the same, drawn 35 degrees up (arcing shot over the front rank)
and the shaman's (Kevin has no spellcasting either):
    Shaman_Idle   loop, 3 s: hunched, leaning on the planted staff with both hands, muttering
    Shaman_Hex    attack: staff drawn back, thrust at the target (the hex bolt leaves the staff head), recover
    Shaman_Chant  support: staff lifted overhead, other hand to the sky, slammed down (a pulse rings out)
The target is the goblin's forward (-Y in Blender, +Z in Unity); clips are in place and share one stance.

Poses are built from aim geometry, not hand-set angles: the arrow runs from the draw hand (Socket_RightHand, at
the jaw) through gob_gear.ARROW_REST on the bow along the aim direction, and the bow arm's reach sets the draw
length. Arms and feet are posed through the rig's IK controls; the FBX exporter bakes them onto the deform bones.
EVENTS (frames at 30 fps) mark release / arrow back in hand / nocked; GoblinArcher in Unity uses the same timing.
"""
import bpy, math, os
from mathutils import Vector, Matrix, Quaternion
import gob_gear
from gob_export import FBX, EXPORT

RIG = "GoblinRig"
FPS = 30
UP = Vector((0, 0, 1))
FWD = Vector((0, -1, 0))
RT = FWD.cross(UP)                      # the archer's right when facing the target (-X)

FINGERS = ("Thumb", "Index", "Middle", "Ring")
PARTS = ("Proximal", "Intermediate", "Distal")
HANDS = {   # curl in degrees about each finger bone's local X (negative closes): proximal, intermediate, distal
    'fist': {"Thumb": (-30, -40, -30), "Index": (-75, -80, -60), "Middle": (-80, -85, -60), "Ring": (-80, -85, -60)},
    'hook': {"Thumb": (-25, -40, -25), "Index": (-20, -85, -50), "Middle": (-20, -85, -50), "Ring": (-35, -85, -50)},
    'pinch': {"Thumb": (-25, -30, -20), "Index": (-40, -45, -30), "Middle": (-55, -70, -40), "Ring": (-65, -75, -45)},
    'spread': {"Thumb": (-4, 0, 0), "Index": (-4, -4, -2), "Middle": (-2, -4, -2), "Ring": (-6, -6, -4)},
    'claw': {"Thumb": (-25, -35, -25), "Index": (-30, -55, -45), "Middle": (-30, -55, -45), "Ring": (-35, -60, -45)},
    'open': {"Thumb": (-10, -10, -10), "Index": (-18, -25, -15), "Middle": (-22, -28, -15), "Ring": (-28, -30, -18)},
}
BODY = ("Hips", "Spine", "Chest", "UpperChest", "Neck", "Head", "LeftShoulder", "RightShoulder")
CONTROLS = ("IK_LeftHand", "IK_RightHand", "Pole_LeftElbow", "Pole_RightElbow",
            "IK_LeftFoot", "IK_RightFoot", "Pole_LeftKnee", "Pole_RightKnee")
STANCE = {"Left": (0.075, -0.10, -25.0), "Right": (-0.075, 0.09, -75.0)}   # foot x, y, yaw (fixed in every bow clip)
SHAMAN_STANCE = {"Left": (0.085, -0.03, 12.0), "Right": (-0.085, 0.03, -12.0)}   # square, toes out
ANCHOR = Vector((-0.100, -0.058, 0.808))     # rest-pose point below the right jaw corner where the string hand anchors
REACH = 0.356                                # shoulder -> wrist of the bow arm at full draw (0.372 = straight)
ARROW_REST = Vector(gob_gear.ARROW_REST)
BOW_BEND, BOW_HALF = gob_gear.BOW_BEND, gob_gear.BOW_HALF

EVENTS = {   # frames: arrow leaves / arrow back in the hand / arrow nocked again
    "Bow_Shoot": {"release": 33, "arrow": 62, "nock": 72, "end": 84},
    "Bow_Volley": {"release": 35, "arrow": 64, "nock": 74, "end": 86},
    "Bow_Ready": {"end": 60},
    "Shaman_Idle": {"end": 90},
    "Shaman_Hex": {"charge": 6, "cast": 22, "end": 60},        # cast = the bolt leaves the staff head
    "Shaman_Chant": {"charge": 16, "cast": 52, "end": 96},     # cast = the staff hits the ground, the ring goes out
}


# ----------------------------------------------------------------------------------------- pose helpers
def _rig():
    return bpy.data.objects[RIG]


def _upd():
    bpy.context.view_layer.update()


def _rest(name):
    return _rig().data.bones[name].matrix_local.copy()


def _pose(name):
    return _rig().pose.bones[name].matrix.copy()


def _set(name, M):
    _rig().pose.bones[name].matrix = M
    _upd()


def _turn(name, axis, deg, local=False):
    M = _pose(name)
    if local:
        axis = M.col["XYZ".index(axis)].xyz
    R = Matrix.Rotation(math.radians(deg), 4, Vector(axis).normalized())
    h = M.translation.copy()
    _set(name, Matrix.Translation(h) @ R @ Matrix.Translation(-h) @ M)


def _rotate_about(v, axis, deg):
    return Matrix.Rotation(math.radians(deg), 3, Vector(axis).normalized()) @ Vector(v)


def _frame(pos, primary, secondary):
    """Bone-style frame (columns x, y, z) at pos. primary = (axis, vector) is exact, secondary is orthogonalised."""
    (pa, pv), (sa, sv) = primary, secondary
    ax = {pa: Vector(pv).normalized()}
    sv = Vector(sv)
    ax[sa] = (sv - sv.project(ax[pa])).normalized()
    third = ({'x', 'y', 'z'} - {pa, sa}).pop()
    if third == 'x':
        ax['x'] = ax['y'].cross(ax['z'])
    elif third == 'y':
        ax['y'] = ax['z'].cross(ax['x'])
    else:
        ax['z'] = ax['x'].cross(ax['y'])
    M = Matrix((ax['x'], ax['y'], ax['z'])).transposed().to_4x4()
    M.translation = Vector(pos)
    return M


def _hand(side, S):
    """Move the IK control so Socket_<side>Hand lands on armature-space matrix S; returns the wrist position."""
    H = S @ _rest(f"Socket_{side}Hand").inverted() @ _rest(f"{side}Hand")
    _set(f"IK_{side}Hand", H)
    return H.translation.copy()


def _wrist_of(side, S):
    return (S @ _rest(f"Socket_{side}Hand").inverted() @ _rest(f"{side}Hand")).translation


def _place(name, pos):
    M = _rest(name)
    M.translation = Vector(pos)
    _set(name, M)


def _stance(stance=None):
    for side, (x, y, yaw) in (stance or STANCE).items():
        M = _rest(f"IK_{side}Foot")
        R = Matrix.Rotation(math.radians(yaw), 4, 'Z')
        N = R @ M.to_3x3().to_4x4()
        N.translation = Vector((x, y, M.translation.z))
        _set(f"IK_{side}Foot", N)
        toe = R.to_3x3() @ Vector((0, -1, 0))
        _place(f"Pole_{side}Knee", Vector((x, y, 0.245)) + toe * 0.4)


def _fingers(side, shape):
    r = _rig()
    for f in FINGERS:
        for part, deg in zip(PARTS, HANDS[shape][f]):
            pb = r.pose.bones[f"{side}{f}{part}"]
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(deg))


def _body(yaw, lean=6.0, drop=0.03, twist=(-10, -8, -6), hunch=(7, 6, 6), pitch=0.0, breathe=0.0):
    """Hips turned `yaw` about Z (negative = right shoulder back), spine twisted further, goblin hunch, and the
    shoulder line tipped up by `pitch` (aiming high)."""
    M = _rest("Hips")
    R = Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Rotation(math.radians(lean), 4, 'X')
    N = R @ M.to_3x3().to_4x4()
    N.translation = M.translation + Vector((0, 0, -drop))
    _set("Hips", N)
    for name, tw, bd in zip(("Spine", "Chest", "UpperChest"), twist, hunch):
        _turn(name, 'Y', tw, local=True)
        _turn(name, 'X', bd - breathe, local=True)
    if pitch:
        _turn("Chest", RT, pitch * 0.25)
        _turn("UpperChest", RT, pitch * 0.2)


def _look(dirn, roll=0.0, neck_share=0.45):
    """Neck and head turn so the face points along dirn; roll tips the head toward the goblin's right."""
    want = _frame(Vector(), ('z', dirn), ('y', UP)).to_3x3()
    want = Matrix.Rotation(math.radians(roll), 3, Vector(dirn).normalized()) @ want
    cur = _pose("Head").to_3x3()
    q = (want @ cur.inverted()).to_quaternion()
    part = Quaternion().slerp(q, neck_share)
    Mn = _pose("Neck")
    h = Mn.translation.copy()
    _set("Neck", Matrix.Translation(h) @ part.to_matrix().to_4x4() @ Matrix.Translation(-h) @ Mn)
    Mh = _pose("Head")
    N = want.to_4x4()
    N.translation = Mh.translation
    _set("Head", N)


def _from_rest(bone, p):
    """A rest-pose world point carried along by `bone`."""
    return _pose(bone) @ _rest(bone).inverted() @ Vector(p)


def reset():
    r = _rig()
    for pb in r.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.matrix_basis = Matrix.Identity(4)
    for side in ("Left", "Right"):
        r.pose.bones[f"{side}LowerArm"].constraints["IK"].influence = 1.0
        r.pose.bones[f"{side}Hand"].constraints["IK rot"].influence = 1.0
    _upd()


# ----------------------------------------------------------------------------------------- key poses
def _aim_dir(pitch):
    return _rotate_about(FWD, RT, pitch)


def _bow_frame(pos, T, cant):
    """Socket_LeftHand frame holding the bow: back of the bow (-X) toward the target, limbs (+Y) up, canted."""
    U = _rotate_about((UP - UP.project(T)).normalized(), T, cant)
    return _frame(pos, ('x', -T), ('y', U)), U


READY = dict(grip=(0.11, -0.30, 0.45), cant=0.0, yaw=-28.0, pitch=-30.0)   # world grip point of the bow at low ready


def pose_ready(breathe=0.0, bob=0.0, **over):
    """Low ready: bow nearly upright in front of the left hip, both elbows soft, the draw hand resting on the nock
    by the belly, arrow pointing at the ground a couple of metres ahead."""
    p = dict(READY, **over)
    reset()
    _stance()
    _body(p['yaw'], lean=5, drop=0.03, twist=(-6, -4, -2), hunch=(6, 5, 5), breathe=breathe)
    _look(_rotate_about(FWD, RT, -14), roll=3)
    T = _aim_dir(p['pitch'])
    shoulder = _pose("LeftUpperArm").translation
    grip = Vector(p['grip']) + Vector((0, 0, bob))
    Sl, U = _bow_frame(grip, T, cant=p['cant'])
    _hand("Left", Sl)
    nock = Sl @ (ARROW_REST + Vector((BOW_BEND + 0.012, 0, 0)))
    Sr = _frame(nock, ('x', T), ('y', U))
    _hand("Right", Sr)
    _place("Pole_LeftElbow", (shoulder + grip) / 2 + Vector((0.2, 0.3, -0.05)))    # elbow soft, pointing back-out
    _place("Pole_RightElbow", Sr.translation + Vector((-0.30, 0.25, 0.05)))
    _fingers("Left", 'fist')
    _fingers("Right", 'hook')
    return {}


def pose_aim(pitch=0.0, draw=1.0, yaw=-52, twist=(-12, -10, -8), cant=8.0, roll=9.0, release=0.0, follow=0.0,
             grip='hook'):
    """Side-on, bow arm out along the aim line, string hand `draw` of the way from the bow to the jaw.
    release/follow move the string hand back and out after the loose (the bow arm drops a little)."""
    reset()
    _stance()
    _body(yaw, lean=3, drop=0.035, twist=twist, hunch=(5, 4, 3), pitch=pitch)
    T = _aim_dir(pitch)
    _look(T, roll=roll)
    A = _from_rest("Head", ANCHOR)
    shoulder = _pose("LeftUpperArm").translation
    Sl, U = _bow_frame(Vector(), T, cant)
    rot = Sl.to_3x3()

    def bow_at(D):
        R = A + T * D                                  # arrow rest on the bow
        M = Sl.copy()
        M.translation = R - rot @ ARROW_REST
        return M

    lo, hi = 0.15, 0.7                                 # draw length from the bow arm's reach
    for _ in range(40):
        mid = (lo + hi) / 2
        if (_wrist_of("Left", bow_at(mid)) - shoulder).length < REACH:
            lo = mid
        else:
            hi = mid
    D = lo
    Sl = bow_at(D)
    if release or follow:
        Sl.translation += T * 0.012 * release - UP * (0.012 * release + 0.03 * follow)
    _hand("Left", Sl)
    pull = BOW_BEND + 0.012 + (D - BOW_BEND - 0.012) * draw
    if release or follow:                              # the loose: the hand springs back past the ear and opens
        nock = A - T * (0.10 * release + 0.04 * follow) + T.cross(U) * (0.05 * release + 0.02 * follow) - U * 0.015 * follow
        Sr = _frame(nock, ('x', T.cross(U) * 0.8 - T * 0.4), ('y', U))          # fingers fall open outward, not across the face
    else:
        nock = Sl @ (ARROW_REST + Vector((pull, 0, 0)))
        Sr = _frame(nock, ('x', T), ('y', U))
    _hand("Right", Sr)
    _place("Pole_LeftElbow", (shoulder + Sl.translation) / 2 - UP * 0.3 - T.cross(U) * 0.15)
    _place("Pole_RightElbow", nock - T * 0.45 + T.cross(U) * 0.18 + UP * 0.05)
    _fingers("Left", 'fist')
    _fingers("Right", 'open' if (release or follow) else grip)
    return {"draw_length": round(D, 3)}


def _quiver():
    """Mouth centre and axis (bottom -> mouth) of the quiver in the current pose."""
    mouth = _from_rest("UpperChest", gob_gear.QUIVER_MOUTH[0])
    bottom = _from_rest("UpperChest", gob_gear.QUIVER_MOUTH[1])
    return mouth, (mouth - bottom).normalized()


def pose_quiver(stage='reach', pitch=0.0):
    """Right hand at the quiver over the right shoulder ('reach'), or lifting a fresh arrow clear ('pull');
    the bow comes down to half height meanwhile."""
    reset()
    _stance()
    _body(-44, lean=5, drop=0.03, twist=(-8, -6, -4), hunch=(6, 5, 5))
    T = _aim_dir(-12 + pitch * 0.3)
    _look(_rotate_about(FWD, RT, -6) + Vector((-0.1, 0, 0)), roll=-4 if stage == 'reach' else 0)
    Sl, U = _bow_frame(Vector((0.06, -0.26, 0.60)), T, cant=25)
    _hand("Left", Sl)
    mouth, d = _quiver()
    back = -_pose("UpperChest").col[2].xyz
    sh = _pose("RightUpperArm").translation
    if stage == 'reach':
        grab = mouth + d * 0.085
        Sr = _frame(grab, ('x', -d), ('z', UP - back * 0.5))
        _place("Pole_RightElbow", sh + UP * 0.35 + RT * 0.12 - back * 0.15)
        _fingers("Right", 'pinch')
    elif stage == 'pull':
        grab = sh + UP * 0.30 + RT * 0.16 - back * 0.03
        fwd = _rotate_about(FWD, RT, 40) + RT * 0.25
        Sr = _frame(grab, ('x', fwd), ('z', RT))
        _place("Pole_RightElbow", sh + UP * 0.15 + RT * 0.35 - back * 0.1)
        _fingers("Right", 'pinch')
    else:                                            # 'swing': out past the right shoulder, arrow already heading for the bow
        grab = sh + RT * 0.17 - back * 0.14 + UP * 0.02
        Sr = _frame(grab, ('x', _aim_dir(-15) + RT * 0.15), ('z', RT))
        _place("Pole_RightElbow", sh + RT * 0.35 + back * 0.15 - UP * 0.1)
        _fingers("Right", 'pinch')
    _hand("Right", Sr)
    _place("Pole_LeftElbow", Sl.translation + Vector((0.35, 0.05, -0.05)))
    _fingers("Left", 'fist')
    return {"reach": round((Sr.translation - sh).length, 3)}


# ----------------------------------------------------------------------------------------- shaman poses
BACK = -FWD
LEFT = -RT
STAFF_BELOW = -gob_gear.STAFF_FOOT               # staff length from the grip down to its foot


def _staff(grip, axis, face):
    """Right hand on the staff at grip; the staff runs along axis toward its head, the skull faces `face`."""
    Sr = _frame(grip, ('y', axis), ('x', face))
    _hand("Right", Sr)
    return Sr


def _left_on_staff(Sr, up=0.085):
    """Left fist stacked on the staff above the right one, knuckles the same way."""
    axis, face = Sr.col[1].xyz, Sr.col[0].xyz
    Sl = _frame(Sr.translation + axis * up, ('y', axis), ('x', -face))
    _hand("Left", Sl)
    return Sl


def _shaman_body(**kw):
    reset()
    _stance(SHAMAN_STANCE)
    _body(**kw)


def pose_staff_idle(breathe=0.0, look=0.0, lift=0.0):
    """Old and hunched, leaning on the staff planted beside the right foot with both hands on it, muttering."""
    _shaman_body(yaw=-6, lean=10, drop=0.045, twist=(-2, -2, 0), hunch=(9, 8, 9), breathe=breathe)
    _look(_rotate_about(FWD, RT, -8) + RT * look, roll=2 + 4 * look)
    axis = Vector((-0.06, -0.08, 1.0)).normalized()             # top leaning out and forward a little
    foot = Vector((-0.2, -0.13, lift))
    Sr = _staff(foot + axis * STAFF_BELOW, axis, FWD)
    Sl = _left_on_staff(Sr)
    _place("Pole_RightElbow", Sr.translation + RT * 0.25 + BACK * 0.12 - UP * 0.25)
    _place("Pole_LeftElbow", Sl.translation + LEFT * 0.12 + BACK * 0.2 - UP * 0.3)
    _fingers("Right", 'fist')
    _fingers("Left", 'fist')
    return {}


def pose_hex(stage='cast'):
    """Hex bolt: 'windup' staff drawn back past the ear, the other hand cupping the spell at the chest;
    'cast' lunging thrust with the staff head at the target and the palm pushed after it; 'follow' the recoil."""
    if stage == 'windup':
        _shaman_body(yaw=-26, lean=4, drop=0.04, twist=(-6, -5, -4), hunch=(6, 5, 5))
        _look(FWD + RT * 0.15, roll=-3)
        sh = _pose("RightUpperArm").translation
        Sr = _staff(sh + UP * 0.08 + BACK * 0.04 + RT * 0.1, (UP + BACK * 0.75 + RT * 0.2).normalized(), FWD)
        Sl = _frame(Vector((0.05, -0.2, 0.66)), ('x', BACK), ('z', -UP))      # palm up at the chest, fingers forward
        _hand("Left", Sl)
        _place("Pole_RightElbow", sh + RT * 0.3 - UP * 0.2 + BACK * 0.1)
        _place("Pole_LeftElbow", Sl.translation + LEFT * 0.25 - UP * 0.2 + BACK * 0.15)
        _fingers("Left", 'claw')
    else:
        follow = stage == 'follow'
        _shaman_body(yaw=8, lean=9 if follow else 14, drop=0.06, twist=(4, 3, 2), hunch=(6, 5, 5))
        _look(_rotate_about(FWD, RT, 4), roll=0)
        sh = _pose("RightUpperArm").translation
        axis = (FWD + UP * 0.8 + RT * 0.1).normalized()                 # staff head raised at the target
        grip = sh + FWD * (0.22 if follow else 0.27) + UP * 0.07 + RT * 0.04
        Sr = _staff(grip, axis, UP)
        shl = _pose("LeftUpperArm").translation
        Sl = _frame(shl + FWD * (0.26 if follow else 0.33) + RT * 0.07 - UP * 0.02, ('x', -UP), ('z', BACK))   # palm out
        _hand("Left", Sl)
        _place("Pole_RightElbow", sh + RT * 0.25 - UP * 0.3)
        _place("Pole_LeftElbow", shl + LEFT * 0.2 - UP * 0.3)
        _fingers("Left", 'spread')
    _fingers("Right", 'fist')
    return {}


def pose_chant(stage='raise', shake=0.0):
    """Chant: 'gather' both hands lift the staff; 'raise' staff high overhead, the other hand open to the sky, head
    back; 'slam' crouched over the staff driven into the ground in front."""
    if stage == 'gather':
        return pose_staff_idle(breathe=-2.0, look=0.0, lift=0.09)
    if stage == 'raise':
        _shaman_body(yaw=0, lean=-6 + shake, drop=0.025, twist=(0, 0, 0), hunch=(-3, -4, -4))   # knees never locked
        _look(_rotate_about(FWD, RT, 32), roll=shake)
        sh = _pose("RightUpperArm").translation
        Sr = _staff(sh + UP * 0.34 + RT * 0.06 + FWD * 0.06, (UP + FWD * 0.12).normalized(), FWD)
        shl = _pose("LeftUpperArm").translation
        Sl = _frame(shl + UP * 0.3 + LEFT * 0.17 + FWD * 0.08 + UP * 0.01 * shake,
                    ('x', -(UP + LEFT * 0.5)), ('z', BACK - UP * 0.3))                # open hand to the sky
        _hand("Left", Sl)
        _place("Pole_RightElbow", sh + RT * 0.4 + UP * 0.05)
        _place("Pole_LeftElbow", shl + LEFT * 0.4 + UP * 0.05)
        _fingers("Right", 'fist')
        _fingers("Left", 'spread')
        return {}
    settle = 0.012 if stage == 'hold' else 0.0
    _shaman_body(yaw=-4, lean=18, drop=0.08 + settle, twist=(-2, -2, 0), hunch=(10, 9, 9))
    _look(_rotate_about(FWD, RT, -18), roll=0)
    foot = Vector((-0.07, -0.33, 0.0))
    grip = Vector((-0.07, -0.25, 0.56 - settle))
    axis = (grip - foot).normalized()
    Sr = _staff(foot + axis * STAFF_BELOW, axis, FWD)
    Sl = _left_on_staff(Sr, up=0.09)
    _place("Pole_RightElbow", Sr.translation + RT * 0.3 + BACK * 0.1 - UP * 0.1)
    _place("Pole_LeftElbow", Sl.translation + LEFT * 0.3 + BACK * 0.1 - UP * 0.1)
    _fingers("Right", 'fist')
    _fingers("Left", 'fist')
    return {}


def _shaman_keys():
    hx, ch = EVENTS["Shaman_Hex"], EVENTS["Shaman_Chant"]
    return {
        "Shaman_Idle": [(0, pose_staff_idle, {}), (45, pose_staff_idle, dict(breathe=2.0, look=0.14)),
                        (90, pose_staff_idle, {})],
        "Shaman_Hex": [(0, pose_staff_idle, {}), (hx["cast"] - 10, pose_hex, dict(stage='windup')),
                       (hx["cast"], pose_hex, dict(stage='cast')), (hx["cast"] + 8, pose_hex, dict(stage='follow')),
                       (hx["end"] - 14, pose_staff_idle, dict(breathe=1.0)), (hx["end"], pose_staff_idle, {})],
        "Shaman_Chant": [(0, pose_staff_idle, {}), (14, pose_chant, dict(stage='gather')),
                         (30, pose_chant, dict(stage='raise')), (42, pose_chant, dict(stage='raise', shake=3.0)),
                         (ch["cast"], pose_chant, dict(stage='slam')), (ch["cast"] + 12, pose_chant, dict(stage='hold')),
                         (ch["end"] - 16, pose_staff_idle, dict(breathe=1.0)), (ch["end"], pose_staff_idle, {})],
    }


def build_shaman_clips():
    return {name: _author(name, keys)[1] for name, keys in _shaman_keys().items()}


SHAMAN_LOOK = {"GoblinBody", "Prop_ShamanStaff", "Prop_ShamanHeaddress", "Prop_Necklace", "Prop_Pouch",
               "Prop_SkullTrophy", "Outfit_Loincloth", "Outfit_Wraps", "Outfit_ShamanCloak"}
ORB = "GOB_PreviewOrb"


def preview_orb():
    """A glowing ball on the staff head in the shaman scene only (GoblinShaman makes the real glow in Unity)."""
    scn = bpy.data.scenes["Goblin_Shaman"]
    ob = bpy.data.objects.get(ORB)
    if ob is None:
        me = bpy.data.meshes.new(ORB)
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.022)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(ORB, me)
        scn.collection.objects.link(ob)
        mat = bpy.data.materials.get("GOB_PreviewOrbMat") or bpy.data.materials.new("GOB_PreviewOrbMat")
        mat.use_nodes = True
        nt = mat.node_tree
        out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs[0].default_value = (0.45, 1.0, 0.3, 1.0)
        em.inputs[1].default_value = 8.0
        nt.links.new(em.outputs[0], out.inputs[0])
        mat.diffuse_color = (0.45, 1.0, 0.3, 1.0)
        me.materials.append(mat)
    rig = _rig()
    ob.parent = rig
    ob.parent_type = 'BONE'
    ob.parent_bone = "Socket_RightHand"
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.matrix_basis = Matrix.Translation(Vector(gob_gear.STAFF_ORB) + Vector((0, -rig.data.bones["Socket_RightHand"].length, 0)))
    return ob


# ----------------------------------------------------------------------------------------- keying
def _keyed_bones():
    fingers = [f"{s}{f}{p}" for s in ("Left", "Right") for f in FINGERS for p in PARTS]
    return list(BODY) + list(CONTROLS) + fingers


def _new_action(name):
    r = _rig()
    old = bpy.data.actions.get(name)
    if old is not None:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if r.animation_data is None:
        r.animation_data_create()
    r.animation_data.action = act
    return act


def _key(frame, prev):
    r = _rig()
    for name in _keyed_bones():
        pb = r.pose.bones[name]
        q = pb.rotation_quaternion.copy()
        if name in prev and q.dot(prev[name]) < 0:
            pb.rotation_quaternion = -q
        prev[name] = pb.rotation_quaternion.copy()
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)
        if name == "Hips" or name.startswith(("IK_", "Pole_")):
            pb.keyframe_insert("location", frame=frame, group=name)


def _key_constraints(frame):
    r = _rig()
    for side in ("Left", "Right"):
        r.pose.bones[f"{side}LowerArm"].constraints["IK"].keyframe_insert("influence", frame=frame)
        r.pose.bones[f"{side}Hand"].constraints["IK rot"].keyframe_insert("influence", frame=frame)


def _author(name, keys):
    """keys: [(frame, pose_fn, kwargs)] -> action on the rig. Returns per-key info."""
    act = _new_action(name)
    prev, info = {}, {}
    for frame, fn, kw in keys:
        info[frame] = fn(**kw)
        _key(frame, prev)
    _key_constraints(keys[0][0])
    act.frame_range = (keys[0][0], keys[-1][0])
    act.use_frame_range = True
    return act, info


def _shoot_keys(pitch, ev):
    rel, arrow, nock, end = ev["release"], ev["arrow"], ev["nock"], ev["end"]
    return [
        (0, pose_ready, {}),
        (10, pose_aim, dict(pitch=pitch * 0.7 - 6, draw=0.35, yaw=-46, twist=(-9, -7, -5), cant=18, roll=5)),
        (20, pose_aim, dict(pitch=pitch, draw=0.96)),
        (rel - 1, pose_aim, dict(pitch=pitch, draw=1.0, roll=10)),
        (rel, pose_aim, dict(pitch=pitch, release=1.0)),
        (rel + 7, pose_aim, dict(pitch=pitch, release=1.0, follow=1.0)),
        (arrow - 8, pose_quiver, dict(stage='reach', pitch=pitch)),
        (arrow, pose_quiver, dict(stage='pull', pitch=pitch)),
        (arrow + 5, pose_quiver, dict(stage='swing', pitch=pitch)),
        (nock, pose_ready, dict(bob=0.04)),
        (end, pose_ready, {}),
    ]


def build_clips():
    out = {}
    act, info = _author("Bow_Ready", [(0, pose_ready, {}), (30, pose_ready, dict(breathe=2.0, bob=0.012)),
                                      (60, pose_ready, {})])
    out["Bow_Ready"] = info
    for name, pitch in (("Bow_Shoot", 0.0), ("Bow_Volley", 35.0)):
        act, info = _author(name, _shoot_keys(pitch, EVENTS[name]))
        out[name] = info
    return out


def use(name, frame=None, scene=None):
    """Put a clip on the rig (and a scene's timeline) for viewing."""
    r = _rig()
    act = bpy.data.actions[name]
    if r.animation_data is None:
        r.animation_data_create()
    r.animation_data.action = act
    scn = bpy.data.scenes.get(scene or ("Goblin_Shaman" if name.startswith("Shaman") else "Goblin_Archer")) or bpy.context.scene
    scn.frame_start, scn.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    scn.frame_set(int(act.frame_range[0]) if frame is None else frame)


def clear():
    """Back to the T-pose with FK arms (the state the character export expects)."""
    r = _rig()
    if r.animation_data is not None:
        r.animation_data.action = None
    for pb in r.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    for side in ("Left", "Right"):
        r.pose.bones[f"{side}LowerArm"].constraints["IK"].influence = 0.0
        r.pose.bones[f"{side}Hand"].constraints["IK rot"].influence = 0.0
    _upd()


# ----------------------------------------------------------------------------------------- preview string
STRING = "GOB_PreviewString"


def string_points():
    """Bow tips and nock point in world space for the current frame (nocked = string on the right hand)."""
    r = _rig()
    Ml = r.matrix_world @ _pose("Socket_LeftHand")
    Mr = r.matrix_world @ _pose("Socket_RightHand")
    top, bot = Ml @ Vector((BOW_BEND, BOW_HALF, 0)), Ml @ Vector((BOW_BEND, -BOW_HALF, 0))
    act = r.animation_data.action if r.animation_data else None
    ev = EVENTS.get(act.name, {}) if act else {}
    f = bpy.context.scene.frame_current
    nocked = not ("release" in ev and ev["release"] <= f < ev["nock"])
    mid = Mr.translation if nocked else (top + bot) / 2
    return top, mid, bot, nocked, ("release" in ev and ev["arrow"] <= f < ev["nock"])


def update_string(scene=None, depsgraph=None):
    ob = bpy.data.objects.get(STRING)
    if ob is None:
        return
    top, mid, bot, nocked, in_hand = string_points()
    for p, v in zip(ob.data.splines[0].points, (top, mid, bot)):
        p.co = (v.x, v.y, v.z, 1)
    arrow = bpy.data.objects.get("Prop_Arrow")
    if arrow is not None:
        vl = bpy.data.scenes["Goblin_Archer"].view_layers[0]
        show = nocked or in_hand
        arrow.hide_set(not show, view_layer=vl)


def preview_string():
    """A thin bow string in the archer scene only, re-shaped on every frame change (viewport scrubbing and renders)."""
    scn = bpy.data.scenes["Goblin_Archer"]
    ob = bpy.data.objects.get(STRING)
    if ob is None:
        cu = bpy.data.curves.new(STRING, 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = 0.0018
        cu.bevel_resolution = 1
        sp = cu.splines.new('POLY')
        sp.points.add(2)
        ob = bpy.data.objects.new(STRING, cu)
        scn.collection.objects.link(ob)
        mat = bpy.data.materials.get("GOB_PreviewStringMat") or bpy.data.materials.new("GOB_PreviewStringMat")
        mat.diffuse_color = (0.85, 0.8, 0.65, 1)
        cu.materials.append(mat)
    handlers = bpy.app.handlers.frame_change_post
    for h in [h for h in handlers if getattr(h, "__name__", "") == "update_string"]:
        handlers.remove(h)
    handlers.append(update_string)
    update_string()
    return ob


# ----------------------------------------------------------------------------------------- export
def export_clips(names=("Bow_Ready", "Bow_Shoot", "Bow_Volley", "Shaman_Idle", "Shaman_Hex", "Shaman_Chant")):
    """export/Anims/Goblin@<clip>.fbx: the deform skeleton with one baked take each."""
    os.makedirs(os.path.join(EXPORT, "Anims"), exist_ok=True)
    r = _rig()
    written = []
    scn = bpy.context.scene
    keep = (scn.frame_start, scn.frame_end, scn.render.fps)
    try:
        for name in names:
            use(name, scene=scn.name)                  # this scene's frame range is the take's
            scn.render.fps = FPS
            for o in bpy.context.selected_objects:
                o.select_set(False)
            r.hide_set(False)
            r.select_set(True)
            bpy.context.view_layer.objects.active = r
            path = os.path.join(EXPORT, "Anims", f"Goblin@{name}.fbx")
            opts = dict(FBX)
            opts.update(bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
                        bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                        bake_anim_simplify_factor=0.0)
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE'}, **opts)
            written.append(path)
    finally:
        scn.frame_start, scn.frame_end, scn.render.fps = keep
        r.select_set(False)
    return written


# ----------------------------------------------------------------------------------------- review renders
ARCHER_LOOK = {"GoblinBody", "Prop_Shortbow", "Prop_Arrow", "Prop_Quiver", "Prop_LeatherCap", "Prop_Pouch", "Prop_Knife",
               "Outfit_Loincloth", "Outfit_Wraps"}


def render_sheet(name, frames, cams=("CAM_ArcherFront", "CAM_ArcherSide"), res=360, scene="Goblin_Archer", look=None,
                 skin=None):
    """Workbench frames of the current clip in a grid (rows = cameras), saved to renders/<name>.png."""
    import numpy as np
    import gob_scene
    scn = bpy.data.scenes[scene]
    look = look or ARCHER_LOOK
    objs = list(bpy.data.collections["GOB_Props"].objects) + list(bpy.data.collections["GOB_Outfit"].objects)
    keep = {o.name: o.hide_render for o in objs}
    body = bpy.data.objects["GoblinBody"]
    keep_skin = body.material_slots[0].material
    tiles = []
    try:
        if skin:
            body.material_slots[0].material = bpy.data.materials[skin]
        for o in objs:
            o.hide_render = o.name not in look
        for cam in cams:
            row = []
            for f in frames:
                scn.frame_set(f)
                update_string()
                if "Prop_Arrow" in look:
                    arrow = bpy.data.objects["Prop_Arrow"]
                    arrow.hide_render = arrow.hide_get(view_layer=bpy.data.scenes["Goblin_Archer"].view_layers[0])
                p = gob_scene.shot(cam, f"anim/{name}_{cam}_{f:03d}", scene=scn, res=res)
                img = bpy.data.images.load(p, check_existing=False)
                a = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
                bpy.data.images.remove(img)
                row.append(a)
            tiles.append(np.concatenate(row, axis=1))
    finally:
        body.material_slots[0].material = keep_skin
        for o in objs:
            o.hide_render = keep[o.name]
    sheet = np.concatenate(tiles[::-1], axis=0)          # Blender images start at the bottom row
    h, w = sheet.shape[:2]
    out = bpy.data.images.new(name + "_sheet", w, h)
    out.pixels = sheet.ravel()
    path = os.path.join(gob_scene.RENDERS, name + ".png")
    out.filepath_raw = path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return path
