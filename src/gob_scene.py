"""Scene, cameras, lights and verification renders for the goblin file."""
import bpy, math, os
from mathutils import Vector
from gob_common import ROOT

RENDERS = os.path.join(ROOT, "renders")


def setup_scene(name="Goblin"):
    scn = bpy.context.scene
    scn.name = name
    for n in ("Cube", "Light", "Camera"):
        ob = bpy.data.objects.get(n)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
    scn.unit_settings.system = 'METRIC'
    scn.view_settings.view_transform = 'Standard'
    scn.render.resolution_x = 1000
    scn.render.resolution_y = 1000
    add_cameras(scn)
    add_lights(scn)
    return scn


def _cam(scn, name, loc, target, ortho=None, lens=85):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scn.collection.objects.link(cam)
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = 'PERSP'
        cam.data.lens = lens
    cam.data.clip_start = 0.01
    return cam


def add_cameras(scn):
    _cam(scn, "CAM_Front", (0, -4, 0.55), (0, 0, 0.55), ortho=1.3)
    _cam(scn, "CAM_Side", (4, 0, 0.55), (0, 0, 0.55), ortho=1.3)
    _cam(scn, "CAM_34", (1.9, -2.6, 1.35), (0, 0, 0.55), lens=70)
    _cam(scn, "CAM_Face", (0.35, -0.9, 0.98), (0, -0.08, 0.90), lens=85)
    _cam(scn, "CAM_Hand", (0.56, -0.35, 0.95), (0.56, 0.0, 0.715), lens=85)
    _cam(scn, "CAM_Colony", (0, -26, 31), (0, 0, 0.4), lens=300)   # ~40 m at 50 deg pitch
    if scn.camera is None:
        scn.camera = bpy.data.objects["CAM_34"]


def add_lights(scn):
    if bpy.data.objects.get("KEY") is None:
        key = bpy.data.objects.new("KEY", bpy.data.lights.new("KEY", 'SUN'))
        key.data.energy = 3.5
        key.rotation_euler = (math.radians(50), 0, math.radians(35))
        scn.collection.objects.link(key)
        fill = bpy.data.objects.new("FILL", bpy.data.lights.new("FILL", 'SUN'))
        fill.data.energy = 1.0
        fill.rotation_euler = (math.radians(60), 0, math.radians(-140))
        scn.collection.objects.link(fill)
    w = scn.world or bpy.data.worlds.new("World")
    scn.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.32, 0.34, 0.38, 1)
    bg.inputs[1].default_value = 0.6


def shot(cam="CAM_34", name=None, engine='BLENDER_WORKBENCH', res=1000, scene=None):
    scn = scene or bpy.context.scene
    prev_cam, prev_engine = scn.camera, scn.render.engine
    scn.camera = bpy.data.objects[cam]
    try:
        scn.render.engine = engine
    except TypeError:
        scn.render.engine = 'BLENDER_WORKBENCH'
    if scn.render.engine == 'BLENDER_WORKBENCH':
        sh = scn.display.shading
        sh.light = 'STUDIO'
        sh.color_type = 'TEXTURE'
        sh.show_cavity = True
        sh.cavity_type = 'WORLD'
        sh.show_shadows = False
        sh.show_object_outline = False
    scn.render.resolution_x = res
    scn.render.resolution_y = res
    scn.render.film_transparent = False
    path = os.path.join(RENDERS, (name or cam) + ".png")
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=scn.name)
    scn.camera, scn.render.engine = prev_cam, prev_engine
    return path


def show_scene(scn):
    """Put the scene on Daniel's screen."""
    bpy.context.window_manager.windows[0].scene = scn
