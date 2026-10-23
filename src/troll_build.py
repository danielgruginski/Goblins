"""Build, check and export the troll (blender/troll.blend, scene Troll). Run headless with tools/troll_run.py, or in
Blender's Python console:

    import sys; sys.path.insert(0, r"E:\\Unity\\Projects\\GameArtGeneration\\Goblins\\src")
    import troll_build as T
    T.build_all()        # body -> rig -> weights -> skin texture -> shape keys -> gear -> gear atlas
    T.review()           # renders/troll_*.png: views, close-ups, UV layout, size comparison, game camera, test poses
    T.export()           # export/Troll/Troll.fbx, export/Troll/Props/Prop_Troll*.fbx

Scenes: Troll (the troll, club, hair, loincloth), Troll_Compare (next to a goblin from goblins.blend and a 1.75 m
human-sized mannequin), Troll_Game (the game camera: 22 m, 50 deg pitch, fov 30).
"""
import bpy, os, math, json, shutil
import numpy as np
from mathutils import Vector, Matrix
from gob_common import ROOT, get_coll, remove_obj, loft, ellipsoid, mesh_obj
import gob_body, gob_rig, gob_shapes, gob_build, gob_export
import troll_body as TB, troll_paint as TP, troll_gear as TG

BLEND = os.path.join(ROOT, "blender", "troll.blend")
GOBLIN_BLEND = os.path.join(ROOT, "blender", "goblins.blend")
RENDERS = os.path.join(ROOT, "renders")
EXPORT = os.path.join(ROOT, "export", "Troll")
SCENE = "Troll"
LAST = {}


def _scene(name=SCENE):
    scn = bpy.data.scenes.get(name)
    if scn is None:
        scn = bpy.data.scenes.new(name)
    return scn


def work_layer(on, scn=None):
    vl = (scn or bpy.context.scene).view_layers[0]
    lc = vl.layer_collection.children.get(TB.NAMES["work"])
    if lc is not None:
        lc.exclude = not on


def setup_file():
    """First run in an empty file: the Troll scene, metric, standard view transform, lights, grey world."""
    scn = bpy.context.scene
    scn.name = SCENE
    for o in list(bpy.data.objects):
        if o.name in ("Cube", "Light", "Camera"):
            bpy.data.objects.remove(o, do_unlink=True)
    scn.unit_settings.system = 'METRIC'
    scn.view_settings.view_transform = 'Standard'
    _lights(scn)
    return scn


def _lights(scn):
    for name, energy, rot in (("TRL_Key", 3.5, (50, 0, 35)), ("TRL_Fill", 1.0, (60, 0, -140))):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SUN'))
            ob.data.energy = energy
            ob.rotation_euler = [math.radians(a) for a in rot]
        if ob.name not in scn.collection.objects:
            scn.collection.objects.link(ob)
    w = bpy.data.worlds.get("TRL_World") or bpy.data.worlds.new("TRL_World")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.32, 0.34, 0.38, 1)
    bg.inputs[1].default_value = 0.6
    scn.world = w


# ---------------------------------------------------------------------------------------------- build
def build_all(body_tris=5000, tex=1024, gear_tex=1024, **warp_over):
    scn = bpy.context.scene
    if scn.name != SCENE:
        setup_file()
    work_layer(True)
    warp = TB.TrollWarp(**warp_over)
    body, eyes = TB.build_body(warp, body_tris=body_tris)
    parts = bpy.data.objects[TB.NAMES["parts"]]
    hi = bpy.data.objects[TB.NAMES["hi"]]
    eyes_hi = bpy.data.objects[TB.NAMES["eyes_hi"]]
    rig = TB.build_armature(warp)
    gob_rig.skin(body, eyes, rig)
    gob_rig.smooth_weights(body, iterations=4, factor=0.5)
    gob_rig.clean_weights(body)
    gob_build.join_into(body, eyes)
    rep = {"weights": gob_rig.weight_report(body)}
    TB.transfer_gob_co(hi, parts)
    TB.transfer_gob_co(body, parts)
    rep.update(TP.paint_and_bake(body, hi, eyes_hi, warp, tex=tex))
    rep["shape_keys"] = TP.add_body_keys(body, warp)
    eyes_hi.hide_set(True)
    outfits, props = TG.build_gear(rig, warp)
    gob_shapes.add_outfit_keys(body, outfits)
    rep["gear_texture"] = TG.bake(outfits + props, rig, size=gear_tex)
    rep["tris"] = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in [body] + outfits + props}
    rep["tris_total"] = sum(rep["tris"].values())
    rep["measures"] = TB.measures(warp)
    rep["uv_missing"] = __import__("gob_gear").uv_report(outfits + props)
    for o in (parts, hi):
        o.hide_set(True)
    work_layer(False)
    body["troll_S"] = warp.p['S']
    LAST.update(rep)
    return rep


def objs():
    rig = bpy.data.objects[TB.RIG]
    body = bpy.data.objects[TB.NAMES["body"]]
    outfits = sorted(bpy.data.collections[TG.OUTFIT_COLL].objects, key=lambda o: o.name)
    props = sorted(bpy.data.collections[TG.PROP_COLL].objects, key=lambda o: o.name)
    return rig, body, outfits, props


# ---------------------------------------------------------------------------------------------- export
def export():
    """export/Troll/Troll.fbx (rig + body + loincloth), export/Troll/Props/Prop_*.fbx in socket space; the same FBX
    settings as the goblins (gob_export.FBX)."""
    os.makedirs(os.path.join(EXPORT, "Props"), exist_ok=True)
    rig, body, outfits, props = objs()
    rest_pose(rig)
    written = []
    gob_export._select([rig, body] + outfits)
    path = os.path.join(EXPORT, "Troll.fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH'}, **gob_export.FBX)
    written.append(path)
    coll = bpy.context.scene.collection
    for p in props:
        name = p.name
        p.name = name + "__src"
        tmp = bpy.data.objects.new(name, p.data)
        tmp["socket"] = p["socket"]
        coll.objects.link(tmp)
        try:
            gob_export._select([tmp])
            path = os.path.join(EXPORT, "Props", name + ".fbx")
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, **gob_export.FBX)
            written.append(path)
        finally:
            bpy.data.objects.remove(tmp, do_unlink=True)
            p.name = name
    for o in bpy.context.selected_objects:
        o.select_set(False)
    return written


def rest_pose(rig):
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
        for c in pb.constraints:
            c.mute = False
    bpy.context.view_layer.update()


# ---------------------------------------------------------------------------------------------- review renders
def _engine(scn, want='BLENDER_EEVEE_NEXT'):
    for e in (want, 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'):
        try:
            scn.render.engine = e
            return e
        except TypeError:
            continue


def _cam(scn, name, loc, target, ortho=None, lens=85, angle=None):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    if cam.name not in scn.collection.objects:
        scn.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    d = cam.data
    d.clip_start, d.clip_end = 0.01, 200
    if ortho:
        d.type, d.ortho_scale = 'ORTHO', ortho
    else:
        d.type = 'PERSP'
        if angle:
            d.sensor_fit = 'VERTICAL'
            d.angle = math.radians(angle)
        else:
            d.lens = lens
    return cam


def shot(scn, cam, name, res=(1000, 1000), engine='BLENDER_EEVEE_NEXT'):
    scn.camera = bpy.data.objects[cam]
    _engine(scn, engine)
    if scn.render.engine == 'BLENDER_WORKBENCH':
        sh = scn.display.shading
        sh.light, sh.color_type, sh.show_cavity = 'STUDIO', 'TEXTURE', True
    else:
        try:
            scn.eevee.taa_render_samples = 32
        except AttributeError:
            pass
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.render.film_transparent = False
    path = os.path.join(RENDERS, name + ".png")
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=scn.name)
    return path


def cameras(scn):
    rig = bpy.data.objects[TB.RIG]
    B = rig.data.bones
    head = Vector(B["Head"].head_local)
    hand = Vector(B["RightHand"].head_local)
    foot = Vector(B["RightFoot"].head_local)
    face = head + Vector((0, -0.12, 0.17))
    h = 1.3
    _cam(scn, "TRL_CAM_Front", (0, -9, h), (0, 0, h), ortho=3.3)
    _cam(scn, "TRL_CAM_Side", (9, 0, h), (0, 0, h), ortho=3.3)
    _cam(scn, "TRL_CAM_Back", (0, 9, h), (0, 0, h), ortho=3.3)
    _cam(scn, "TRL_CAM_34", (4.6, -6.2, 2.4), (0, 0, 1.25), lens=80)
    _cam(scn, "TRL_CAM_Back34", (-4.4, 6.0, 2.6), (0, 0, 1.35), lens=80)
    _cam(scn, "TRL_CAM_Face", face + Vector((0, -1.6, 0.05)), face, lens=85)
    _cam(scn, "TRL_CAM_Face34", face + Vector((1.05, -1.25, 0.15)), face + Vector((0, 0.03, 0)), lens=85)
    _cam(scn, "TRL_CAM_FaceSide", face + Vector((1.7, 0.0, 0.0)), face + Vector((0, 0.05, 0)), lens=85)
    _cam(scn, "TRL_CAM_HandTop", hand + Vector((-0.12, -0.25, 0.95)), hand + Vector((-0.12, 0, -0.05)), lens=60)
    _cam(scn, "TRL_CAM_HandUnder", hand + Vector((-0.12, -0.35, -0.9)), hand + Vector((-0.12, 0, 0)), lens=60)
    _cam(scn, "TRL_CAM_Feet", (0.9, -1.6, 0.6), (0, -0.1, 0.12), lens=50)
    _cam(scn, "TRL_CAM_Club", hand + Vector((0.4, -1.7, 0.7)), hand + Vector((0, -0.6, 0)), lens=45)
    if scn.camera is None:
        scn.camera = bpy.data.objects["TRL_CAM_34"]


def review(tag="troll"):
    os.makedirs(RENDERS, exist_ok=True)
    scn = _scene()
    cameras(scn)
    _lights(scn)
    out = []
    for cam, nm, res in (("TRL_CAM_Front", "front", (1000, 1000)), ("TRL_CAM_Side", "side", (1000, 1000)),
                         ("TRL_CAM_Back", "back", (1000, 1000)), ("TRL_CAM_34", "34", (1200, 1200)),
                         ("TRL_CAM_Back34", "back34", (1200, 1200)), ("TRL_CAM_Face", "face", (1000, 1000)),
                         ("TRL_CAM_Face34", "face34", (1000, 1000)), ("TRL_CAM_FaceSide", "faceside", (1000, 1000)),
                         ("TRL_CAM_HandTop", "hand_top", (1000, 1000)), ("TRL_CAM_HandUnder", "hand_under", (1000, 1000)),
                         ("TRL_CAM_Feet", "feet", (1000, 1000)), ("TRL_CAM_Club", "club", (1000, 1000))):
        out.append(shot(scn, cam, f"{tag}_{nm}", res))
    out.append(uv_layout(tag))
    out += shape_keys(tag)
    out += compare(tag)
    out += game_view(tag)
    out += pose_tests(tag)
    return out


def uv_layout(tag="troll"):
    """UV layouts over their textures (body and gear), as Daniel asked after the goblins' smart-UV mess."""
    rig, body, outfits, props = objs()
    paths = []
    for obs, img_name, nm in (([body], "T_Troll_Skin", "uv_body"), (outfits + props, "T_Troll_Gear", "uv_gear")):
        img = bpy.data.images[img_name]
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4).copy()
        for ob in obs:
            me = ob.data
            uv = me.uv_layers.active.data
            for poly in me.polygons:
                L = [uv[i].uv[:] for i in poly.loop_indices]
                for a, b in zip(L, L[1:] + L[:1]):
                    n = int(max(abs(a[0] - b[0]) * w, abs(a[1] - b[1]) * h)) + 1
                    for t in np.linspace(0, 1, n + 1):
                        x = int((a[0] + (b[0] - a[0]) * t) * (w - 1))
                        y = int((a[1] + (b[1] - a[1]) * t) * (h - 1))
                        if 0 <= x < w and 0 <= y < h:
                            px[y, x, :3] = (1.0, 0.85, 0.1)
        out = bpy.data.images.get("_uvshot") or bpy.data.images.new("_uvshot", w, h, alpha=True)
        out.scale(w, h)
        out.pixels.foreach_set(px.ravel())
        out.filepath_raw = os.path.join(RENDERS, f"{tag}_{nm}.png")
        out.file_format = 'PNG'
        out.save()
        paths.append(out.filepath_raw)
    return paths


def shape_keys(tag="troll"):
    """Each body shape key at full weight (Unity blend shapes; GoblinAppearance rolls them)."""
    scn = _scene()
    rig, body, outfits, props = objs()
    out = []
    for name in ("Skinny", "Brawny", "Fat", "EarsDroop", "EarTornL"):
        for o in [body] + outfits:
            if o.data.shape_keys:
                for k in o.data.shape_keys.key_blocks:
                    k.value = 0.0
        for o in [body] + outfits:
            if o.data.shape_keys and name in o.data.shape_keys.key_blocks:
                o.data.shape_keys.key_blocks[name].value = 1.0
        out.append(shot(scn, "TRL_CAM_34", f"{tag}_key_{name}", (800, 800)))
    for o in [body] + outfits:
        if o.data.shape_keys:
            for k in o.data.shape_keys.key_blocks:
                k.value = 0.0
    return out


# ---------------------------------------------------------------------------------------------- comparisons
def _link_troll(scn):
    for cn in (TB.NAMES["coll"], "TRL_Rig", TG.OUTFIT_COLL, TG.PROP_COLL):
        c = bpy.data.collections.get(cn)
        if c is not None and c.name not in [x.name for x in scn.collection.children]:
            scn.collection.children.link(c)


def goblin_copy(scn, x=-1.2):
    """A plain goblin appended from goblins.blend (body, loincloth, harness, spear, helmet) in its rest pose."""
    names = ["GoblinRig", "GoblinBody", "Outfit_Loincloth", "Outfit_Harness", "Prop_Spear", "Prop_Helmet"]
    have = [n for n in names if bpy.data.objects.get("CMP_" + n)]
    if len(have) < len(names) and os.path.exists(GOBLIN_BLEND):
        with bpy.data.libraries.load(GOBLIN_BLEND, link=False) as (src, dst):
            dst.objects = [n for n in names if n in src.objects]
        for ob in dst.objects:
            if ob is None:
                continue
            ob.name = "CMP_" + ob.name
    coll = get_coll("TRL_Compare_Goblin", scene=scn)
    rig = bpy.data.objects.get("CMP_GoblinRig")
    for n in names:
        ob = bpy.data.objects.get("CMP_" + n)
        if ob is None:
            continue
        if ob.name not in coll.objects:
            coll.objects.link(ob)
        ob.hide_render = False
        ob.hide_viewport = False
    if rig is not None:
        if rig.animation_data:
            rig.animation_data_clear()
        rest_pose(rig)
        rig.location = (x, 0, 0)
        rig.hide_render = True
    return coll


def mannequin(scn, x=1.3, height=1.75):
    """A plain grey 1.75 m human-sized figure, for scale."""
    name = "CMP_Human175"
    if bpy.data.objects.get(name) is None:
        import bmesh
        bm = bmesh.new()
        k = height / 1.75
        ellipsoid(bm, Vector((0, 0, 1.62 * k)), (0.085 * k, 0.10 * k, 0.12 * k))
        loft(bm, [(0, 0, 1.47 * k, 0.05 * k, 0.05 * k, 0.05 * k), (0, 0, 1.56 * k, 0.05 * k, 0.05 * k, 0.05 * k)], up=(0, -1, 0), seg=12)
        loft(bm, [(0, 0, 0.92 * k, 0.16 * k, 0.10 * k, 0.10 * k), (0, 0, 1.15 * k, 0.15 * k, 0.11 * k, 0.10 * k),
                  (0, 0, 1.38 * k, 0.20 * k, 0.11 * k, 0.11 * k), (0, 0, 1.48 * k, 0.12 * k, 0.07 * k, 0.07 * k)],
             up=(0, -1, 0), seg=16)
        for s in (1, -1):
            loft(bm, [(s * 0.09 * k, 0, 0.95 * k, 0.075 * k, 0.075 * k, 0.075 * k), (s * 0.10 * k, 0, 0.50 * k, 0.05 * k, 0.05 * k, 0.05 * k),
                      (s * 0.10 * k, 0, 0.08 * k, 0.04 * k, 0.04 * k, 0.04 * k)], up=(0, -1, 0), seg=12)
            loft(bm, [(s * 0.10 * k, -0.06 * k, 0.03 * k, 0.045 * k, 0.03 * k, 0.03 * k), (s * 0.10 * k, -0.20 * k, 0.03 * k, 0.045 * k, 0.025 * k, 0.025 * k)],
                 up=(0, 0, 1), seg=10)
            loft(bm, [(s * 0.20 * k, 0, 1.40 * k, 0.045 * k, 0.045 * k, 0.045 * k), (s * 0.24 * k, 0, 1.12 * k, 0.04 * k, 0.04 * k, 0.04 * k),
                      (s * 0.27 * k, 0, 0.86 * k, 0.03 * k, 0.03 * k, 0.03 * k), (s * 0.28 * k, 0, 0.72 * k, 0.035 * k, 0.02 * k, 0.02 * k)],
                 up=(0, -1, 0), seg=10)
        ob = mesh_obj(name, bm, None)
        m = bpy.data.materials.get("CMP_Grey") or bpy.data.materials.new("CMP_Grey")
        m.use_nodes = True
        bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = (0.55, 0.55, 0.58, 1)
        ob.data.materials.append(m)
        for p in ob.data.polygons:
            p.use_smooth = True
    ob = bpy.data.objects[name]
    coll = get_coll("TRL_Compare_Human", scene=scn)
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    ob.location = (x, 0, 0)
    return ob


def compare(tag="troll"):
    scn = _scene("Troll_Compare")
    scn.view_settings.view_transform = 'Standard'
    _lights(scn)
    _link_troll(scn)
    goblin_copy(scn, -1.25)
    mannequin(scn, 1.35)
    _cam(scn, "TRL_CMP_Front", (0, -12, 1.3), (0, 0, 1.3), ortho=4.4)
    _cam(scn, "TRL_CMP_34", (3.5, -7.5, 2.0), (0, 0, 1.2), lens=40)
    return [shot(scn, "TRL_CMP_Front", f"{tag}_compare_front", (1600, 1000)),
            shot(scn, "TRL_CMP_34", f"{tag}_compare_34", (1600, 1000))]


def game_view(tag="troll"):
    """The game camera: 22 m from the troll, 50 deg pitch, vertical fov 30, 1920x1080; with the goblin and the
    mannequin beside it on grass."""
    scn = _scene("Troll_Game")
    scn.view_settings.view_transform = 'Standard'
    _lights(scn)
    _link_troll(scn)
    goblin_copy(scn, -1.25)
    mannequin(scn, 1.35)
    g = bpy.data.objects.get("TRL_Ground")
    if g is None:
        me = bpy.data.meshes.new("TRL_Ground")
        me.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("TRL_Ground", me)
        m = bpy.data.materials.new("TRL_Grass")
        m.use_nodes = True
        bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = (0.13, 0.18, 0.06, 1)
        bsdf.inputs['Roughness'].default_value = 1.0
        me.materials.append(m)
    if g.name not in scn.collection.objects:
        scn.collection.objects.link(g)
    pitch, dist, tgt = math.radians(50), 22.0, Vector((0, 0, 1.0))
    loc = tgt + Vector((0, -math.cos(pitch), math.sin(pitch))) * dist
    _cam(scn, "TRL_GAME", loc, tgt, angle=30)
    p = shot(scn, "TRL_GAME", f"{tag}_game_22m", (1920, 1080))
    crop = _crop(p, f"{tag}_game_22m_x4", 4)
    return [p, crop]


def _crop(path, name, k):
    """The middle of a render, pixels blown up k times (nearest), to see what the game camera really shows."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    cw, ch = w // (2 * k), h // k
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    sub = px[y0:y0 + ch, x0:x0 + cw]
    big = np.repeat(np.repeat(sub, k, 0), k, 1)
    out = bpy.data.images.new("_crop", big.shape[1], big.shape[0], alpha=True)
    out.pixels.foreach_set(big.ravel())
    out.filepath_raw = os.path.join(RENDERS, name + ".png")
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(img)
    bpy.data.images.remove(out)
    return os.path.join(RENDERS, name + ".png")


# ---------------------------------------------------------------------------------------------- test poses
def _pose(rig, name):
    rest_pose(rig)
    R = gob_rig._rot
    for pb in rig.pose.bones:                     # arms posed by hand (arm IK is off anyway); legs keep their IK
        for c in pb.constraints:
            if pb.name.endswith(("LowerArm", "Hand")):
                c.mute = True
    for side, sg in (("Left", 1), ("Right", -1)):
        if name == "arms_down":
            R(rig, side + "Shoulder", (0, sg, 0), 12)
            R(rig, side + "UpperArm", (0, sg, 0), 72)
            R(rig, side + "LowerArm", (1, 0, 0), -12)
        elif name == "arms_up":
            R(rig, side + "Shoulder", (0, sg, 0), -15)
            R(rig, side + "UpperArm", (0, sg, 0), -70)
            R(rig, side + "LowerArm", (0, sg, 0), -20)
        elif name == "knee_bend":
            R(rig, side + "UpperArm", (0, sg, 0), 35)
            R(rig, side + "UpperArm", (0, 0, 1), -45 * sg)
            R(rig, side + "LowerArm", (0, 0, 1), -30 * sg)
    if name == "knee_bend":
        hips = rig.pose.bones["Hips"]
        hips.location = (0, -0.62, -0.12)             # down (the bone's +Y is up) and back (its +Z is forward)
        bpy.context.view_layer.update()
        R(rig, "Spine", (1, 0, 0), 22)
        R(rig, "Chest", (1, 0, 0), 10)
    for side in ("Left", "Right"):                # fists
        for f in ("Index", "Middle", "Ring", "Thumb"):
            for part in ("Proximal", "Intermediate", "Distal"):
                R(rig, f"{side}{f}{part}", 'X', -60 * (0.6 if f == "Thumb" else 1.0) * (1 if side == "Left" else 1), local=True)
    bpy.context.view_layer.update()


def pose_tests(tag="troll"):
    """Arms down by the sides, arms raised, a deep knee bend: front and side renders; returns the paths and writes the
    lowest fingertip in the arms-down pose into LAST['arms_down']."""
    scn = _scene()
    rig = bpy.data.objects[TB.RIG]
    body = bpy.data.objects[TB.NAMES["body"]]
    _cam(scn, "TRL_CAM_PoseFront", (0, -9, 1.25), (0, 0, 1.25), ortho=3.0)
    _cam(scn, "TRL_CAM_PoseSide", (9, 0, 1.25), (0, 0, 1.25), ortho=3.0)
    _cam(scn, "TRL_CAM_Pose34", (3.6, -4.8, 1.8), (0, 0, 1.0), lens=60)
    B = rig.data.bones
    sh = Vector(B["LeftUpperArm"].head_local)
    kn = Vector(B["LeftLowerLeg"].head_local)
    _cam(scn, "TRL_CAM_PoseShoulder", sh + Vector((0.9, -1.3, 0.25)), sh + Vector((0.05, 0, -0.15)), lens=60)
    _cam(scn, "TRL_CAM_PoseKnee", Vector((1.5, -1.6, 0.9)), Vector((0.15, -0.15, 0.45)), lens=60)
    close = {"arms_down": "TRL_CAM_PoseShoulder", "arms_up": "TRL_CAM_PoseShoulder", "knee_bend": "TRL_CAM_PoseKnee"}
    out = []
    try:
        for name in ("arms_down", "arms_up", "knee_bend"):
            _pose(rig, name)
            if name == "arms_down":
                hand = {g.index for g in body.vertex_groups
                        if g.name.endswith("Hand") or any(f in g.name for f in ("Thumb", "Index", "Middle", "Ring"))}
                sel = [v.index for v in body.data.vertices
                       if v.groups and max(v.groups, key=lambda g: g.weight).group in hand]
                dg = bpy.context.evaluated_depsgraph_get()
                me = body.evaluated_get(dg).to_mesh()
                LAST["arms_down"] = {"lowest_fingertip_z": round(min(me.vertices[i].co.z for i in sel), 3),
                                     "knee_z": round(rig.data.bones["LeftLowerLeg"].head_local.z, 3)}
                body.evaluated_get(dg).to_mesh_clear()
            for cam, v in (("TRL_CAM_PoseFront", "front"), ("TRL_CAM_PoseSide", "side"), ("TRL_CAM_Pose34", "34"),
                           (close[name], "close")):
                out.append(shot(scn, cam, f"{tag}_pose_{name}_{v}", (1000, 1000)))
    finally:
        rest_pose(rig)
    return out


def save():
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    return BLEND
