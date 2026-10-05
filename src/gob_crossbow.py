"""Crossbow clips on the goblin rig, for the game's humans (Humanoid retargets them, as with the bow clips):

    Crossbow_Ready  loop, 2 s: half side-on, the crossbow low across the body, nose down, both hands on it
    Crossbow_Shoot  3.1 s: raise to the cheek -> aim -> loose (a small kick) -> lower, nose down, and draw the string back
                    to the nut -> a bolt from the right hip -> lay it in the groove -> back to ready

The crossbow is the weapon kit's (GameArtGeneration/Weapons, wpn_roster): a LEFT-hand prop, the left fist on the
fore-stock, the stock running through it toward the prod. Here a copy scaled to goblin size (SCALE) rides on
Socket_LeftHand in the scene "Goblin_Crossbow"; the hands are placed through the rig's IK from the crossbow's own
points (fore-grip, trigger grip, string, nut, groove), as gob_anim does for the bow.

    import gob_crossbow; gob_crossbow.setup_scene(); gob_crossbow.build_clips()
    gob_anim.export_clips(("Crossbow_Ready", "Crossbow_Shoot")); gob_anim.clear()
"""
import bpy, math, sys
from mathutils import Vector, Matrix
import gob_anim as A
from gob_anim import (_rig, _pose, _set, _place, _hand, _fingers, _body, _look, _from_rest, _frame, _rotate_about, reset,
                      _author, UP, FWD, RT)

WEAPONS_SRC = r"E:\Unity\Projects\GameArtGeneration\Weapons\src"
SCENE = "Goblin_Crossbow"
PREVIEW = "GOB_PreviewCrossbow"
SCALE = 0.6                                   # goblin (1.01 m) to human (~1.75 m)
STANCE = {"Left": (0.07, -0.085, -18.0), "Right": (-0.08, 0.075, -62.0)}
EVENTS = {"Crossbow_Shoot": {"loose": 24, "loaded": 78, "end": 94}, "Crossbow_Ready": {"end": 60}}
A.EVENTS.update(EVENTS)

# the light crossbow's points in its own frame (+Y toward the prod, +Z its top, origin the fore-grip; wpn_roster)
GRIP_R = Vector((0.0, -0.27, -0.012))         # the right fist round the stock's wrist
BUTT = Vector((0.0, -0.40, -0.01))
STRING_FRONT = Vector((0.0, 0.19, 0.03))      # the string's middle when slack-ish, by the prod
NUT = Vector((0.0, -0.11, 0.03))
GROOVE = Vector((0.0, 0.02, 0.036))           # where a fresh bolt is laid
CHEEK = Vector((0.0, -0.33, 0.03))            # the point of the stock against the cheek


def _G():
    """the crossbow's frame -> Socket_LeftHand frame (wpn_roster.CROSSBOW_GRIP: half a turn about Y)"""
    return Matrix.Rotation(math.pi, 4, 'Y')


def _sl(W):
    """Socket_LeftHand world matrix for a crossbow whose own frame (unscaled axes) sits at W"""
    return W @ _G().inverted()


def _cb(W, p):
    """a crossbow point (its own frame, human size) in the world"""
    return W @ (Vector(p) * SCALE)


def _cb_frame(origin, aim, roll=0.0):
    """the crossbow's frame: origin = the fore-grip, +Y along `aim`, +Z its top (world up, rolled `roll` deg)"""
    aim = Vector(aim).normalized()
    up = _rotate_about((UP - UP.project(aim)).normalized(), aim, roll)
    return _frame(origin, ('y', aim), ('z', up))


def _right_on(W, p, cant=-25.0, shape='fist'):
    """the right fist round the stock at crossbow point p: index toward the prod, knuckles to the crossbow's left
    and a little down (the forearm comes in from the right)"""
    aim = W.col[1].xyz.normalized()
    left = -W.col[0].xyz.normalized()
    k = _rotate_about(left, aim, -cant)
    S = _frame(_cb(W, p), ('y', aim), ('x', k))
    _hand("Right", S)
    _fingers("Right", shape)
    return S


def _arms(W, right_pole=None):
    shl = _pose("LeftUpperArm").translation
    shr = _pose("RightUpperArm").translation
    _place("Pole_LeftElbow", (shl + W.translation) / 2 - UP * 0.25 + RT * -0.12)
    _place("Pole_RightElbow", right_pole if right_pole is not None else shr + RT * 0.25 - UP * 0.12 + FWD * -0.05)


# ----------------------------------------------------------------------------------------- key poses
def pose_ready(breathe=0.0, bob=0.0):
    """Low ready: the crossbow across the body at the belly, nose down and forward, both fists on it."""
    reset()
    A._stance(STANCE)
    _body(-30, lean=5, drop=0.035, twist=(-6, -4, -2), hunch=(6, 5, 5), breathe=breathe)
    _look(_rotate_about(FWD, RT, -16), roll=2)
    W = _ready_frame()
    W.translation += Vector((0, 0, bob))
    _hand("Left", _sl(W))
    _fingers("Left", 'fist')
    _right_on(W, GRIP_R, cant=-35)
    _arms(W)
    return {}


def pose_aim(pitch=0.0, kick=0.0, raise_=1.0):
    """At the cheek: the stock's cheek point under the right jaw, the bolt line along the goblin's forward;
    kick tips it up and back at the loose; raise_ < 1 is on the way up from the ready."""
    reset()
    A._stance(STANCE)
    _body(-44, lean=3, drop=0.035, twist=(-12, -10, -8), hunch=(5, 4, 3), pitch=pitch)
    T = _rotate_about(FWD, RT, pitch + 5.0 * kick)
    _look(_rotate_about(FWD, RT, pitch), roll=14 * raise_)
    jaw = _from_rest("Head", A.ANCHOR)
    W = _cb_frame(Vector(), T, roll=-4)
    W.translation = jaw - (W.to_3x3() @ (CHEEK * SCALE)) + Vector((0, 0, -0.012)) - T * 0.012 * kick
    if raise_ < 1.0:                                   # blend from the ready's place
        reset_W = _ready_frame()
        W = _blend(reset_W, W, raise_)
    _hand("Left", _sl(W))
    _fingers("Left", 'fist')
    _right_on(W, GRIP_R, cant=-20)
    _arms(W, _pose("RightUpperArm").translation + RT * 0.28 - UP * 0.05 + FWD * 0.05)
    return {}


def _ready_frame():
    aim = _rotate_about(FWD, RT, -18) + RT * -0.22
    return _cb_frame(Vector((0.05, -0.25, 0.5)), aim, roll=-10)


def _blend(W0, W1, t):
    q = W0.to_quaternion().slerp(W1.to_quaternion(), t)
    M = q.to_matrix().to_4x4()
    M.translation = W0.translation.lerp(W1.translation, t)
    return M


def _span_frame():
    """lowered for spanning: nearly upright, nose down in front of the left thigh, its top (the string) toward the
    body, so the stock stands in front of the chest"""
    aim = -UP * 0.93 + FWD * 0.34 - RT * 0.1
    return _frame(Vector((0.06, -0.31, 0.31)), ('y', aim), ('z', -FWD * 0.9 + RT * 0.35))


def pose_span(t=0.0):
    """The string drawn from the prod (t = 0) back to the nut (t = 1) by the right hand; the left holds the
    fore-stock with the crossbow nose down."""
    reset()
    A._stance(STANCE)
    _body(-22, lean=16, drop=0.07, twist=(-5, -4, -3), hunch=(10, 9, 8))
    W = _span_frame()
    _look((_cb(W, STRING_FRONT.lerp(NUT, t)) - _pose("Head").translation), roll=0)
    _hand("Left", _sl(W))
    _fingers("Left", 'fist')
    aim = W.col[1].xyz.normalized()
    top = W.col[2].xyz.normalized()
    p = _cb(W, STRING_FRONT.lerp(NUT, t)) + top * 0.025
    S = _frame(p, ('y', W.col[0].xyz), ('x', aim * 0.7 - top * 0.3))     # above the string, fingers hooked round it
    _hand("Right", S)
    _fingers("Right", 'hook')
    shl = _pose("LeftUpperArm").translation
    _place("Pole_LeftElbow", (shl + W.translation) / 2 - RT * 0.2 - UP * 0.1)
    _place("Pole_RightElbow", _pose("RightUpperArm").translation + RT * 0.3 - UP * 0.1 - FWD * 0.15)
    return {}


def pose_bolt(stage='reach'):
    """'reach': the right hand at the bolt pouch on the right hip; 'lay': a bolt laid in the groove."""
    reset()
    A._stance(STANCE)
    _body(-26, lean=10, drop=0.05, twist=(-6, -5, -3), hunch=(8, 7, 6))
    W = _span_frame() if stage == 'reach' else _blend(_span_frame(), _ready_frame(), 0.65)
    _look((W.translation - _pose("Head").translation).normalized() + FWD * 0.3, roll=0)
    _hand("Left", _sl(W))
    _fingers("Left", 'fist')
    if stage == 'reach':
        hip = _pose("RightUpperLeg").translation + RT * 0.07 + FWD * 0.02 + UP * 0.02
        S = _frame(hip, ('x', -UP), ('y', FWD))
        _hand("Right", S)
        _place("Pole_RightElbow", _pose("RightUpperArm").translation + RT * 0.25 - FWD * 0.15)
    else:
        aim = W.col[1].xyz.normalized()
        S = _frame(_cb(W, GROOVE) + W.col[2].xyz * 0.02, ('x', -W.col[2].xyz), ('y', aim))
        _hand("Right", S)
        _place("Pole_RightElbow", _pose("RightUpperArm").translation + RT * 0.32 - UP * 0.15 - FWD * 0.1)
    _fingers("Right", 'pinch')
    _place("Pole_LeftElbow", W.translation - UP * 0.25 + RT * -0.15)
    return {}


def _shoot_keys():
    return [
        (0, pose_ready, {}),
        (8, pose_aim, dict(raise_=0.5)),
        (16, pose_aim, {}),
        (23, pose_aim, {}),
        (25, pose_aim, dict(kick=1.0)),
        (30, pose_aim, dict(kick=0.3)),
        (38, pose_span, dict(t=0.0)),
        (48, pose_span, dict(t=0.55)),
        (58, pose_span, dict(t=1.0)),
        (68, pose_bolt, dict(stage='reach')),
        (78, pose_bolt, dict(stage='lay')),
        (86, pose_ready, dict(bob=0.03)),
        (94, pose_ready, {}),
    ]


def build_clips():
    out = {}
    act, info = _author("Crossbow_Ready", [(0, pose_ready, {}), (30, pose_ready, dict(breathe=2.0, bob=0.012)),
                                           (60, pose_ready, {})])
    out["Crossbow_Ready"] = info
    act, info = _author("Crossbow_Shoot", _shoot_keys())
    out["Crossbow_Shoot"] = info
    return out


# ----------------------------------------------------------------------------------------- the scene
LOOK = {"GoblinBody", "Outfit_Loincloth", "Outfit_Wraps", "Prop_LeatherCap", "Prop_Pouch"}


def preview_mesh():
    """the weapon kit's light crossbow, goblin size, as a mesh on Socket_LeftHand (the scene's own object)"""
    if WEAPONS_SRC not in sys.path:
        sys.path.insert(0, WEAPONS_SRC)
    import importlib, wpn_roster, wpn_parts, bmesh
    importlib.reload(wpn_parts)
    importlib.reload(wpn_roster)
    b = wpn_roster.light_crossbow(False)
    me = bpy.data.meshes.get(PREVIEW) or bpy.data.meshes.new(PREVIEW)
    bmesh.ops.scale(b.bm, vec=(SCALE,) * 3, verts=b.bm.verts[:])
    b.bm.to_mesh(me)
    b.bm.free()
    mat = bpy.data.materials.get("GOB_PreviewCrossbowMat") or bpy.data.materials.new("GOB_PreviewCrossbowMat")
    mat.diffuse_color = (0.42, 0.3, 0.2, 1)
    me.materials.clear()
    me.materials.append(mat)
    return me


def setup_scene():
    """Goblin_Crossbow: a linked copy of the Goblin scene showing the plain goblin and the preview crossbow."""
    src = bpy.data.scenes["Goblin"]
    scn = bpy.data.scenes.get(SCENE)
    if scn is None:                                    # links the same collections (like the archer's scene)
        win = bpy.context.window
        keep = win.scene
        win.scene = src
        with bpy.context.temp_override(window=win, scene=src):
            bpy.ops.scene.new(type='LINK_COPY')
        scn = win.scene
        scn.name = SCENE
        win.scene = keep
    me = preview_mesh()
    ob = bpy.data.objects.get(PREVIEW)
    if ob is None:
        ob = bpy.data.objects.new(PREVIEW, me)
        scn.collection.objects.link(ob)
    ob.data = me
    rig = _rig()
    ob.parent = rig
    ob.parent_type = 'BONE'
    ob.parent_bone = "Socket_LeftHand"
    ob.matrix_parent_inverse = Matrix.Identity(4)
    bone = rig.data.bones["Socket_LeftHand"]
    ob.matrix_basis = Matrix.Translation((0, -bone.length, 0))
    vl = scn.view_layers[0]
    for o in list(bpy.data.collections["GOB_Props"].objects) + list(bpy.data.collections["GOB_Outfit"].objects):
        try:
            o.hide_set(o.name not in LOOK, view_layer=vl)
        except RuntimeError:
            pass
    scn.render.fps = A.FPS
    return scn
