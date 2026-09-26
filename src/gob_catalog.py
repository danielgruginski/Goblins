"""Goblin_Props scene: every prop laid out on a grid with a label and a camera, for looking at the library."""
import bpy, math
from mathutils import Vector
from gob_common import ROOT
import gob_gear, gob_scene

SCENE = "Goblin_Props"


def build_catalog(cols=7, dx=0.55, dz=0.9):
    scn = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    scn.view_settings.view_transform = 'Standard'
    for o in list(scn.collection.all_objects):
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data is not None and data.users == 0 and isinstance(data, (bpy.types.Mesh, bpy.types.Curve)):
            (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.curves).remove(data)
    names = [n for n, _, _ in gob_gear.PROPS]
    for i, n in enumerate(names):
        src = bpy.data.objects[n]
        ob = bpy.data.objects.new("CAT_" + n, src.data)          # shares the prop's mesh
        scn.collection.objects.link(ob)
        # show each prop upright: socket +Y up, +Z toward the camera
        ob.rotation_euler = (math.radians(90), 0, 0)
        c, r = i % cols, i // cols
        bb = [Vector(v) for v in src.bound_box]
        ctr = sum(bb, Vector()) / 8
        ob.location = Vector((c * dx, 0, -r * dz)) - Vector((ctr.x, -ctr.z, ctr.y))
        big = max((max(v[k] for v in bb) - min(v[k] for v in bb)) for k in range(3))
        if big > 0.5:
            ob.scale = (0.5 / big,) * 3
            ob.location = Vector((c * dx, 0, -r * dz)) - Vector((ctr.x, -ctr.z, ctr.y)) * (0.5 / big)
        cu = bpy.data.curves.new("LBL_" + n, 'FONT')
        cu.body = n.replace("Prop_", "")
        cu.size = 0.06
        cu.align_x = 'CENTER'
        lbl = bpy.data.objects.new("LBL_" + n, cu)
        lbl.location = (c * dx, 0, -r * dz - 0.38)
        lbl.rotation_euler = (math.radians(90), 0, 0)
        scn.collection.objects.link(lbl)
    rows = (len(names) + cols - 1) // cols
    cam = bpy.data.objects.new("CAM_Catalog", bpy.data.cameras.new("CAM_Catalog"))
    scn.collection.objects.link(cam)
    cx, cz = (cols - 1) * dx / 2, -(rows - 1) * dz / 2
    cam.location = (cx, -6.0, cz)
    cam.rotation_euler = (math.radians(90), 0, 0)
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(cols * dx, rows * dz * 16 / 9) * 1.05
    scn.camera = cam
    sun = bpy.data.objects.new("SUN_Catalog", bpy.data.lights.new("SUN_Catalog", 'SUN'))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(60), 0, math.radians(25))
    scn.collection.objects.link(sun)
    scn.world = bpy.data.scenes["Goblin"].world
    scn.render.resolution_x, scn.render.resolution_y = 1600, 900
    return scn
